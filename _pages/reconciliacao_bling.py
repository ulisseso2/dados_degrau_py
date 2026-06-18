"""
Reconciliação Bling × Banco
Busca TODAS as notas emitidas na Bling por período e cruza com o banco.
Aproveita dois níveis de cache SQLite:
  1. Listagem por período (TTL 2h) — evita re-listar a API para o mesmo mês
  2. Detalhes por ID        (TTL 30d) — enriquece com chave de acesso, link DANFE, valor
"""

import io
import time
import calendar
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

from utils.bling_auth import get_bling_token
from utils.bling_cache import (
    buscar_cache, salvar_cache, ids_sem_campo,
    buscar_listagem, salvar_listagem, stats_listagem,
)
from utils.sql_loader import carregar_dados

_LIMITE        = 100
_PAUSA         = 0.5    # pausa entre páginas / situações
_PAUSA_429     = 12     # espera após 429 (rate-limit Bling ≈ 3 req/s, janela de 10s)
_TENTATIVAS    = 3      # re-tentativas por requisição antes de desistir
_LOTE          = 100
_SITUACOES     = list(range(1, 13))   # 1-12 cobre todos os estados conhecidos de NF-e/NFS-e


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extrair_situacao(v) -> str:
    if isinstance(v, dict):
        return v.get("descricao", "")
    return str(v) if v is not None else ""


def _periodo_key(data_inicio, data_fim) -> str:
    return f"{data_inicio}_{data_fim}"


# ---------------------------------------------------------------------------
# Listagem da API Bling (com cache SQLite de período)
# ---------------------------------------------------------------------------

def _listar_bling(token: str, endpoint: str,
                  data_inicio, data_fim, label: str) -> list[dict]:
    """
    Retorna TODAS as notas do endpoint para o período, iterando por cada
    código de situação para capturar também notas canceladas/denegadas que
    a API Bling omite quando nenhuma situação é informada.
    Usa cache SQLite (TTL 2h). Só chama a API se o cache estiver expirado.
    """
    # Chave com sufixo "_all" para distinguir de buscas parciais anteriores
    key  = f"{_periodo_key(data_inicio, data_fim)}_all"
    tipo = endpoint  # "nfe" ou "nfse"

    cached = buscar_listagem(key, tipo)
    if cached is not None:
        st.caption(f"✅ {label}: {len(cached)} notas (cache SQLite)")
        return cached

    # Cache expirado ou inexistente — itera sobre todos os códigos de situação
    todas: dict[int, dict] = {}   # id_bling → item  (dedup automático)
    status_ph = st.empty()

    for sit in _SITUACOES:
        pagina = 1
        while True:
            r = None
            for tentativa in range(_TENTATIVAS):
                try:
                    r = requests.get(
                        f"https://www.bling.com.br/Api/v3/{endpoint}",
                        headers={"Authorization": f"Bearer {token}"},
                        params={
                            "pagina":             pagina,
                            "limite":             _LIMITE,
                            "dataEmissaoInicial": str(data_inicio),
                            "dataEmissaoFinal":   str(data_fim),
                            "situacao":           sit,
                        },
                        timeout=15,
                    )
                    if r.status_code == 429:
                        # Rate-limit — aguarda e tenta novamente
                        status_ph.warning(
                            f"⏳ {label}: rate-limit (sit.{sit}) — aguardando {_PAUSA_429}s…"
                        )
                        time.sleep(_PAUSA_429)
                        continue
                    break   # sucesso ou erro definitivo
                except Exception as e:
                    if tentativa == _TENTATIVAS - 1:
                        st.error(f"Erro de conexão ({label}, sit.{sit}): {e}")
                    time.sleep(_PAUSA)

            if r is None:
                break
            # Código inválido para este endpoint — ignora silenciosamente
            if r.status_code in (400, 404, 422):
                break
            if r.status_code != 200:
                break  # outro erro — pula esta situação

            data = r.json().get("data", [])
            if not data:
                break

            for n in data:
                nid = n.get("id")
                if nid:
                    todas[int(nid)] = n

            status_ph.info(
                f"🔄 {label}: {len(todas)} notas acumuladas "
                f"(sit.{sit}, pág.{pagina})…"
            )

            if len(data) < _LIMITE:
                break
            pagina += 1
            time.sleep(_PAUSA)

        time.sleep(_PAUSA)   # pausa entre situações

    status_ph.empty()
    notas = list(todas.values())
    salvar_listagem(key, tipo, notas)
    st.caption(f"🆕 {label}: {len(notas)} notas (API Bling → salvo no SQLite)")
    return notas


# ---------------------------------------------------------------------------
# Enriquecimento com cache de detalhes
# ---------------------------------------------------------------------------

def _enriquecer_com_cache(notas: list[dict], tipo: str) -> list[dict]:
    """
    Para cada nota da listagem, sobrescreve/complementa com dados do cache
    de detalhes (mais completos: chave_acesso, link, valor preciso).
    """
    ids = [int(n.get("id", 0)) for n in notas if n.get("id")]
    cache = buscar_cache(ids, tipo)

    enriquecidas = []
    for n in notas:
        nid = int(n.get("id", 0))
        det = cache.get(nid, {})
        # Prefere cache de detalhes; fallback para o que veio da listagem
        enriquecidas.append({**n, "_det": det})
    return enriquecidas


# ---------------------------------------------------------------------------
# Normalização (listagem + detalhe mesclados)
# ---------------------------------------------------------------------------

def _normalizar_nfe(item: dict) -> dict:
    det     = item.get("_det", {})
    contato = item.get("contato", {})
    # chaveAcesso vem direto da listagem; valor só vem do detalhe
    return {
        "tipo":         "NFe",
        "id_bling":     int(item.get("id", 0)),
        "numero":       str(item.get("numero", "") or det.get("numero", "")),
        "data_emissao": item.get("dataEmissao", "") or det.get("data_emissao", ""),
        "valor":        float(det.get("valor") or 0),   # preenchido após reparo
        "situacao":     _extrair_situacao(item.get("situacao")) or det.get("situacao", ""),
        "chave_acesso": item.get("chaveAcesso", ""),    # listagem já traz
        "link":         _normalizar_link(det.get("link", "")),
        "cliente":      contato.get("nome", ""),
        "cpf":          contato.get("numeroDocumento", ""),
    }


def _normalizar_link(raw: str) -> str:
    """Garante que links relativos da Bling virem URLs absolutas."""
    if not raw:
        return ""
    if raw.startswith("http"):
        return raw
    return f"https://www.bling.com.br/{raw.lstrip('/')}"


def _normalizar_nfse(item: dict) -> dict:
    det     = item.get("_det", {})
    contato = item.get("contato", {})

    # numero: usa nota fiscal; se vazio cai para RPS (prefixado); fallback no cache
    _num = (item.get("numero") or
            det.get("numero") or
            "")
    if not _num and item.get("numeroRPS"):
        _num = f"RPS {item['numeroRPS']}"
    numero = str(_num)

    # dataEmissao: NFS-e retorna só a data "YYYY-MM-DD" (sem hora, ao contrário da NFe)
    data_emissao = (
        item.get("dataEmissao") or
        item.get("dataEmissaoRps") or
        item.get("dataCompetencia") or
        det.get("data_emissao") or
        ""
    )

    # situacao: listagem retorna inteiro (1, 2…); cache já tem string; preferir cache
    situacao = (det.get("situacao") or
                _extrair_situacao(item.get("situacao")) or
                "")

    return {
        "tipo":         "NFS-e",
        "id_bling":     int(item.get("id", 0)),
        "numero":       numero,
        "data_emissao": data_emissao,
        "valor":        float(item.get("valor") or det.get("valor") or 0),
        "situacao":     situacao,
        "chave_acesso": det.get("chave_acesso", ""),
        "link":         _normalizar_link(det.get("link", "")),
        "cliente":      contato.get("nome", ""),
        "cpf":          contato.get("numeroDocumento", ""),
    }


def _buscar_valor_nfe(ids: list[int], token: str) -> dict[int, float]:
    """Busca valorNota do endpoint de detalhe para NFe sem valor em cache."""
    if not ids:
        return {}
    faltantes = ids_sem_campo(ids, "nfe", "valor")
    if not faltantes:
        cached = buscar_cache(ids, "nfe")
        return {nid: float(cached[nid].get("valor") or 0) for nid in ids if nid in cached}

    barra = st.progress(0, text=f"Buscando valor de {len(faltantes)} NFe…")
    novos: dict = {}
    for idx, nid in enumerate(faltantes):
        try:
            r = requests.get(
                f"https://www.bling.com.br/Api/v3/nfe/{nid}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            if r.status_code == 200:
                d = r.json().get("data", {})
                v = float(d.get("valorNota") or 0)
                novos[nid] = v
                # Atualiza cache de detalhes com o valor
                det_atual = buscar_cache([nid], "nfe").get(nid, {})
                det_atual["valor"] = v
                salvar_cache({nid: det_atual}, "nfe")
        except Exception:
            novos[nid] = 0.0
        barra.progress((idx + 1) / len(faltantes),
                       text=f"Valor NFe: {idx+1}/{len(faltantes)}")
        if (idx + 1) % _LOTE == 0 and (idx + 1) < len(faltantes):
            time.sleep(_PAUSA)
    barra.empty()

    # Retorna valor para todos os IDs (cached + recém-buscados)
    cached = buscar_cache(ids, "nfe")
    return {nid: float(novos.get(nid) or cached.get(nid, {}).get("valor") or 0)
            for nid in ids}


# ---------------------------------------------------------------------------
# Mapas do SQL
# ---------------------------------------------------------------------------

def _construir_mapas_sql(df_sql: pd.DataFrame) -> tuple[dict, dict]:
    """
    nfe_map:  { nfe_id  → {tipo_pgto, cliente, cpf, email} }
    nfse_map: { nfse_id → {tipo_pgto, cliente, cpf, email} }

    Vista   = nfe_id existe, nfse_id é nulo
    Parcela = ambos existem
    """
    nfe_map, nfse_map = {}, {}
    for _, row in df_sql.iterrows():
        nfe_id  = row.get("nfe_id")
        nfse_id = row.get("nfse_id")
        base = {
            "cliente":   row.get("full_name", ""),
            "cpf":       row.get("cpf", ""),
            "email":     row.get("email", ""),
            "tipo_pgto": "Vista" if pd.isna(nfse_id) else "Parcela",
        }
        if pd.notna(nfe_id):
            nfe_map[int(nfe_id)] = base
        if pd.notna(nfse_id):
            nfse_map[int(nfse_id)] = {**base, "tipo_pgto": "Parcela"}
    return nfe_map, nfse_map


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def run_page():
    st.title("Reconciliação Bling × Banco")
    st.caption(
        "Lista todas as notas emitidas na Bling no período e cruza com o banco. "
        "A listagem fica em cache por 2h no SQLite — clique em **Buscar** para forçar atualização."
    )

    def fmt_brl(v):
        try:
            return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            return "–"

    try:
        token = get_bling_token()
    except RuntimeError as e:
        st.error(str(e))
        st.stop()

    # --- Período ---
    st.subheader("Período de emissão")
    hoje = datetime.now()
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        data_inicio = st.date_input(
            "De", value=datetime(hoje.year, hoje.month, 1).date(), format="DD/MM/YYYY"
        )
    with col2:
        data_fim = st.date_input(
            "Até",
            value=datetime(hoje.year, hoje.month,
                           calendar.monthrange(hoje.year, hoje.month)[1]).date(),
            format="DD/MM/YYYY",
        )
    with col3:
        st.write("")
        st.write("")
        buscar = st.button("🔄 Buscar notas na Bling", use_container_width=True)

    # Chave de sessão para evitar re-processar sem clicar Buscar
    sess_key = f"recon_{data_inicio}_{data_fim}"
    if buscar:
        # Limpa estado anterior
        for k in [k for k in st.session_state if k.startswith("recon_")]:
            del st.session_state[k]

    if sess_key not in st.session_state:
        if not buscar:
            # Verifica se já tem listagem completa em cache para mostrar automaticamente
            key = f"{_periodo_key(data_inicio, data_fim)}_all"
            tem_cache = (buscar_listagem(key, "nfe") is not None or
                         buscar_listagem(key, "nfse") is not None)
            if not tem_cache:
                st.info("Selecione o período e clique em **Buscar notas na Bling**.")
                with st.expander("📦 Listagens em cache SQLite", expanded=False):
                    items = stats_listagem()
                    if items:
                        st.dataframe(pd.DataFrame(items), hide_index=True,
                                     use_container_width=True)
                    else:
                        st.write("Nenhuma listagem em cache ainda.")
                st.stop()

        # Carrega SQL e listas da Bling
        with st.spinner("Carregando SQL…"):
            df_sql = carregar_dados("consultas/notas/notas_bling.sql")

        col_l1, col_l2 = st.columns(2)
        with col_l1:
            raw_nfe  = _listar_bling(token, "nfe",  data_inicio, data_fim, "NFe")
        with col_l2:
            raw_nfse = _listar_bling(token, "nfse", data_inicio, data_fim, "NFS-e")

        st.session_state[sess_key] = {
            "df_sql": df_sql, "raw_nfe": raw_nfe, "raw_nfse": raw_nfse
        }

    cached  = st.session_state[sess_key]
    df_sql  = cached["df_sql"]
    raw_nfe = cached["raw_nfe"]
    raw_nfse= cached["raw_nfse"]

    if not raw_nfe and not raw_nfse:
        st.warning("Nenhuma nota encontrada na Bling para o período.")
        st.stop()

    # --- Complementa NFe com notas do cache de detalhe que a listagem perde ---
    # (notas emitidas tarde da noite em BRT caem no dia seguinte em UTC na listagem)
    ids_listagem_nfe = {int(n.get("id", 0)) for n in raw_nfe if n.get("id")}
    ids_sql_nfe = [int(i) for i in df_sql["nfe_id"].dropna().unique()]
    cache_det_sup = buscar_cache(ids_sql_nfe, "nfe")
    d_ini_str, d_fim_str = str(data_inicio), str(data_fim)
    extras_nfe = 0
    for nid, det in cache_det_sup.items():
        de = str(det.get("data_emissao", ""))[:10]
        if de and nid not in ids_listagem_nfe and d_ini_str <= de <= d_fim_str:
            raw_nfe.append({
                "id":          nid,
                "numero":      det.get("numero", ""),
                "dataEmissao": det.get("data_emissao", ""),
                "situacao":    det.get("situacao", ""),
                "chaveAcesso": det.get("chave_acesso", ""),
                "contato":     {},
                "_det":        det,
            })
            extras_nfe += 1
    if extras_nfe:
        st.caption(
            f"ℹ️ +{extras_nfe} NFe adicionadas do cache de detalhe "
            "(emitidas tarde da noite — listagem Bling as omite por fuso horário)."
        )

    # --- Enriquece com cache de detalhes ---
    raw_nfe  = _enriquecer_com_cache(raw_nfe,  "nfe")
    raw_nfse = _enriquecer_com_cache(raw_nfse, "nfse")

    ids_sem_detalhe_nfe  = [int(n["id"]) for n in raw_nfe
                             if not n.get("_det") and n.get("id")]
    ids_sem_detalhe_nfse = [int(n["id"]) for n in raw_nfse
                             if not n.get("_det") and n.get("id")]

    if ids_sem_detalhe_nfe or ids_sem_detalhe_nfse:
        st.caption(
            f"ℹ️ {len(ids_sem_detalhe_nfe)} NFe e "
            f"{len(ids_sem_detalhe_nfse)} NFS-e sem detalhe em cache "
            "(chave de acesso e link DANFE indisponíveis — serão preenchidos ao abrir "
            "a página **Notas Bling** para este período)."
        )

    # --- Mapas SQL e reconciliação ---
    nfe_map, nfse_map = _construir_mapas_sql(df_sql)

    linhas = []
    for item in raw_nfe:
        nota = _normalizar_nfe(item)
        sql  = nfe_map.get(nota["id_bling"])
        if sql:
            nota.update({"tipo_pgto": sql["tipo_pgto"],
                         "cliente":   sql["cliente"] or nota["cliente"],
                         "cpf":       sql["cpf"]     or nota["cpf"],
                         "email":     sql["email"],
                         "status":    "✅ No banco"})
        else:
            nota.update({"tipo_pgto": "—", "email": "", "status": "⚠️ Não encontrado no banco"})
        linhas.append(nota)

    for item in raw_nfse:
        nota = _normalizar_nfse(item)
        sql  = nfse_map.get(nota["id_bling"])
        if sql:
            nota.update({"tipo_pgto": "Parcela",
                         "cliente":   sql["cliente"] or nota["cliente"],
                         "cpf":       sql["cpf"]     or nota["cpf"],
                         "email":     sql["email"],
                         "status":    "✅ No banco"})
        else:
            nota.update({"tipo_pgto": "—", "email": "", "status": "⚠️ Não encontrado no banco"})
        linhas.append(nota)

    df = pd.DataFrame(linhas)

    # Busca valorNota para NFe (listagem não traz; NFS-e já vem com valor)
    ids_nfe_lista = df.loc[df["tipo"] == "NFe", "id_bling"].tolist()
    if ids_nfe_lista:
        valores_nfe = _buscar_valor_nfe(ids_nfe_lista, token)
        df.loc[df["tipo"] == "NFe", "valor"] = (
            df.loc[df["tipo"] == "NFe", "id_bling"].map(valores_nfe).fillna(0)
        )

    # NFe retorna "YYYY-MM-DD HH:MM:SS", NFS-e retorna "YYYY-MM-DD" — formatos mistos.
    # pd.to_datetime com format único infere pelo 1º valor e falha nos outros; apply resolve.
    df["data_emissao_dt"] = df["data_emissao"].apply(
        lambda x: pd.to_datetime(x, errors="coerce") if x else pd.NaT
    )
    df = df.sort_values("data_emissao_dt")
    df["emissao_fmt"] = df["data_emissao_dt"].apply(
        lambda x: x.strftime("%d/%m/%Y") if pd.notna(x) else ""
    )
    df["valor_fmt"]   = df["valor"].apply(fmt_brl)

    # --- Filtros de situação e tipo ---
    st.markdown("---")
    situacoes_disponiveis = sorted(df["situacao"].dropna().unique().tolist())
    tipos_disponiveis     = sorted(df["tipo"].unique().tolist())

    fc1, fc2, fc3 = st.columns([2, 1, 1])
    with fc1:
        sit_sel = st.multiselect(
            "Situação", situacoes_disponiveis,
            default=situacoes_disponiveis,
            help="Filtre por situação antes de exportar",
        )
    with fc2:
        tipo_sel = st.multiselect(
            "Tipo", tipos_disponiveis,
            default=tipos_disponiveis,
        )
    with fc3:
        status_sel = st.multiselect(
            "Status banco",
            ["✅ No banco", "⚠️ Não encontrado no banco"],
            default=["✅ No banco", "⚠️ Não encontrado no banco"],
        )

    _CHAVE_OPTS = ["✅ Com chave", "⚠️ Sem chave"]
    _LINK_OPTS  = ["✅ Com link",  "⚠️ Sem link"]
    fc4, fc5, _ = st.columns([1, 1, 2])
    with fc4:
        chave_sel = st.multiselect("Chave de acesso", _CHAVE_OPTS, default=_CHAVE_OPTS)
    with fc5:
        link_sel  = st.multiselect("Link Nota",       _LINK_OPTS,  default=_LINK_OPTS)

    tem_chave = df["chave_acesso"].fillna("").str.strip().ne("")
    tem_link  = df["link"].fillna("").str.strip().ne("")

    chave_mask = pd.Series(False, index=df.index)
    if "✅ Com chave" in (chave_sel or _CHAVE_OPTS):
        chave_mask |= tem_chave
    if "⚠️ Sem chave" in (chave_sel or _CHAVE_OPTS):
        chave_mask |= ~tem_chave

    link_mask = pd.Series(False, index=df.index)
    if "✅ Com link" in (link_sel or _LINK_OPTS):
        link_mask |= tem_link
    if "⚠️ Sem link" in (link_sel or _LINK_OPTS):
        link_mask |= ~tem_link

    df_vis = df[
        df["situacao"].isin(sit_sel if sit_sel else situacoes_disponiveis) &
        df["tipo"].isin(tipo_sel if tipo_sel else tipos_disponiveis) &
        df["status"].isin(status_sel if status_sel else ["✅ No banco", "⚠️ Não encontrado no banco"]) &
        chave_mask &
        link_mask
    ]

    no_banco        = (df_vis["status"] == "✅ No banco").sum()
    nao_encontrados = (df_vis["status"] == "⚠️ Não encontrado no banco").sum()

    # --- KPIs (refletem o filtro) ---
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total filtrado",  len(df_vis))
    k2.metric("NFe",             int((df_vis["tipo"] == "NFe").sum()))
    k3.metric("NFS-e",           int((df_vis["tipo"] == "NFS-e").sum()))
    k4.metric("No banco",        no_banco)
    k5.metric("Não encontrados", nao_encontrados,
              delta=f"-{nao_encontrados}" if nao_encontrados else None,
              delta_color="inverse")

    col_val1, col_val2, col_val3 = st.columns(3)
    col_val1.metric("Total Emitido",
                    fmt_brl(df_vis["valor"].sum()))
    col_val2.metric("Total NFe",
                    fmt_brl(df_vis[df_vis["tipo"] == "NFe"]["valor"].sum()))
    col_val3.metric("Total NFS-e",
                    fmt_brl(df_vis[df_vis["tipo"] == "NFS-e"]["valor"].sum()))
    st.markdown("---")

    # --- Tabela ---
    col_cfg = {
        "status":      st.column_config.TextColumn("Status",    width="medium"),
        "tipo":        st.column_config.TextColumn("Tipo",      width="small"),
        "id_bling":    st.column_config.NumberColumn("ID Bling", format="%d", width="medium"),
        "numero":      st.column_config.TextColumn("Nº Nota",   width="small"),
        "emissao_fmt": st.column_config.TextColumn("Emissão",   width="small"),
        "tipo_pgto":   st.column_config.TextColumn("Pgto",      width="small"),
        "cliente":     st.column_config.TextColumn("Cliente",   width="large"),
        "cpf":         st.column_config.TextColumn("CPF",       width="medium"),
        "valor_fmt":   st.column_config.TextColumn("Valor",     width="medium"),
        "situacao":    st.column_config.TextColumn("Situação",  width="medium"),
        "chave_acesso":st.column_config.TextColumn("Chave / Cód. Verificação", width="large"),
        "link":        st.column_config.LinkColumn("Nota",
                           display_text="Abrir", width="small"),
    }
    cols = ["status", "tipo", "id_bling", "numero", "emissao_fmt",
            "tipo_pgto", "cliente", "cpf", "valor_fmt", "situacao",
            "chave_acesso", "link"]

    aba_todas, aba_faltam, aba_cache = st.tabs([
        f"📋 Todas ({len(df_vis)})",
        f"⚠️ Não encontradas ({nao_encontrados})",
        "📦 Cache SQLite",
    ])

    with aba_todas:
        st.dataframe(df_vis[cols], column_config=col_cfg,
                     use_container_width=True, hide_index=True, height=500)

    with aba_faltam:
        df_falt = df_vis[df_vis["status"] == "⚠️ Não encontrado no banco"]
        if df_falt.empty:
            st.success("Todas as notas foram encontradas no banco.")
        else:
            st.warning(f"{len(df_falt)} nota(s) sem correspondência no banco — ajuste manual necessário.")
            st.dataframe(df_falt[cols], column_config=col_cfg,
                         use_container_width=True, hide_index=True)

    with aba_cache:
        items = stats_listagem()
        st.write("**Listagens em cache (TTL 2h):**")
        if items:
            st.dataframe(pd.DataFrame(items), hide_index=True, use_container_width=True)
        else:
            st.write("Nenhuma listagem em cache ainda.")
        nfe_stats  = {"tipo": "NFe (detalhes)",  **{"total_ids": len(raw_nfe),
                      "em_cache": sum(1 for n in raw_nfe if n.get("_det"))}}
        nfse_stats = {"tipo": "NFS-e (detalhes)", **{"total_ids": len(raw_nfse),
                      "em_cache": sum(1 for n in raw_nfse if n.get("_det"))}}
        st.write("**Cobertura de detalhes (cache por ID):**")
        st.dataframe(pd.DataFrame([nfe_stats, nfse_stats]),
                     hide_index=True, use_container_width=True)

        # --- Debug: estrutura real dos itens da listagem ---
        with st.expander("🔬 Debug — estrutura raw dos itens (listagem Bling)", expanded=False):
            raw_orig = st.session_state.get(sess_key, {})
            nfse_raw_orig = raw_orig.get("raw_nfse", [])
            nfe_raw_orig  = raw_orig.get("raw_nfe",  [])

            st.write("**Chaves do 1º item NFS-e (listagem, sem _det):**")
            if nfse_raw_orig:
                sample_nfse = {k: v for k, v in nfse_raw_orig[0].items() if k != "_det"}
                st.json(sample_nfse)
                st.write("**Cache SQLite (_det) do mesmo ID:**")
                _det_sample = raw_nfse[0].get("_det", {}) if raw_nfse else {}
                st.json({k: v for k, v in _det_sample.items() if k != "_debug"})
            else:
                st.info("Sem itens NFS-e na listagem.")

            st.write("**Chaves do 1º item NFe (listagem, para comparar):**")
            if nfe_raw_orig:
                st.json({k: v for k, v in nfe_raw_orig[0].items() if k != "_det"})
            else:
                st.info("Sem itens NFe na listagem.")

    # --- Exportar (usa df_vis — respeita os filtros de situação/tipo/status) ---
    st.markdown("---")
    df_exp = df_vis[[
        "status", "tipo", "id_bling", "numero", "emissao_fmt", "tipo_pgto",
        "cliente", "cpf", "email", "valor", "situacao", "chave_acesso", "link",
    ]].rename(columns={
        "status": "Status", "tipo": "Tipo", "id_bling": "ID Bling",
        "numero": "Nº Nota", "emissao_fmt": "Data Emissão", "tipo_pgto": "Tipo Pgto",
        "cliente": "Cliente", "cpf": "CPF", "email": "E-mail",
        "valor": "Valor", "situacao": "Situação",
        "chave_acesso": "Chave / Cód. Verificação", "link": "Link Nota",
    })

    _FMT_BRL = '#,##0.00'

    def _aplicar_fmt_valor(ws, df_ref):
        col_idx = list(df_ref.columns).index("Valor") + 1
        for row in ws.iter_rows(min_row=2, min_col=col_idx, max_col=col_idx):
            for cell in row:
                cell.number_format = _FMT_BRL

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df_exp.to_excel(w, index=False, sheet_name="Reconciliação")
        _aplicar_fmt_valor(w.sheets["Reconciliação"], df_exp)
        if nao_encontrados:
            df_nao = df_exp[df_exp["Status"] == "⚠️ Não encontrado no banco"]
            df_nao.to_excel(w, index=False, sheet_name="Não encontradas")
            _aplicar_fmt_valor(w.sheets["Não encontradas"], df_nao)
    buf.seek(0)

    nome = f"reconciliacao_{data_inicio.strftime('%Y%m%d')}_{data_fim.strftime('%Y%m%d')}.xlsx"
    st.download_button(
        "⬇️ Exportar Excel (Contabilidade)",
        data=buf, file_name=nome,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
