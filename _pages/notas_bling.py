import calendar
import io
import time
from datetime import datetime, timedelta

import pandas as pd
import requests
import streamlit as st

from utils.bling_auth import get_bling_token
from utils.bling_cache import buscar_cache, ids_sem_campo, salvar_cache, stats_cache
from utils.sql_loader import carregar_dados

_LOTE  = 100   # notas por lote
_PAUSA = 0.3   # segundos entre lotes (evita rate-limit da Bling)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def _extrair_situacao(v) -> str:
    if isinstance(v, dict):
        return v.get("descricao", "")
    return str(v) if v is not None else ""


def _chamar_nfe(nid: int, token: str) -> dict:
    try:
        r = requests.get(
            f"https://www.bling.com.br/Api/v3/nfe/{nid}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if r.status_code == 200:
            d = r.json().get("data", {})
            valor = d.get("valorNota") or 0
            return {
                "link":         d.get("linkDanfe", ""),
                "numero":       d.get("numero", ""),
                "situacao":     _extrair_situacao(d.get("situacao")),
                "data_emissao": d.get("dataEmissao", ""),
                "chave_acesso": d.get("chaveAcesso", ""),
                "valor":        float(valor),
                "_debug":       f"200 | valorNota={d.get('valorNota')}",
            }
        return _vazio(f"{r.status_code} — {r.text[:150]}")
    except Exception as e:
        return _vazio(f"Exceção: {e}")


def _chamar_nfse(nid: int, token: str) -> dict:
    try:
        r = requests.get(
            f"https://www.bling.com.br/Api/v3/nfse/{nid}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if r.status_code == 200:
            d = r.json().get("data", {})
            valor = d.get("valor") or 0
            raw_link = d.get("link", "") or d.get("linkDanfse", "") or d.get("linkPdf", "")
            link = raw_link if raw_link.startswith("http") else (
                f"https://www.bling.com.br/{raw_link.lstrip('/')}" if raw_link else ""
            )
            return {
                "link":         link,
                "numero":       str(d.get("numero", "")),
                "situacao":     _extrair_situacao(d.get("situacao")),
                "data_emissao": d.get("dataEmissao", ""),
                "chave_acesso": d.get("codigoVerificacao", ""),
                "valor":        float(valor),
                "_debug":       f"200 | valor={d.get('valor')}",
            }
        return _vazio(f"{r.status_code} — {r.text[:150]}")
    except Exception as e:
        return _vazio(f"Exceção: {e}")


def _vazio(debug="") -> dict:
    return {"link": "", "numero": "", "situacao": "", "data_emissao": "",
            "chave_acesso": "", "valor": 0.0, "_debug": debug}


def _df_sem_cache(df_sql: pd.DataFrame,
                  cache_nfe: dict, cache_nfse: dict) -> pd.DataFrame:
    """IDs do SQL que não têm dados válidos no cache SQLite (faltam ou data_emissao vazia)."""
    linhas = []
    seen_nfe:  set[int] = set()
    seen_nfse: set[int] = set()
    for _, row in df_sql.iterrows():
        r = row.to_dict()
        if pd.notna(r.get("nfe_id")):
            nid = int(r["nfe_id"])
            if nid not in seen_nfe:
                seen_nfe.add(nid)
                if not cache_nfe.get(nid, {}).get("data_emissao"):
                    linhas.append({
                        "buscar":      False,
                        "tipo":        "NFe",
                        "id_bling":    nid,
                        "cliente":     r.get("full_name", ""),
                        "cpf":         r.get("cpf", ""),
                        "data_pedido": str(r.get("date", "") or ""),
                    })
        if pd.notna(r.get("nfse_id")):
            nid = int(r["nfse_id"])
            if nid not in seen_nfse:
                seen_nfse.add(nid)
                if not cache_nfse.get(nid, {}).get("data_emissao"):
                    linhas.append({
                        "buscar":      False,
                        "tipo":        "NFS-e",
                        "id_bling":    nid,
                        "cliente":     r.get("full_name", ""),
                        "cpf":         r.get("cpf", ""),
                        "data_pedido": str(r.get("date", "") or ""),
                    })
    return pd.DataFrame(linhas) if linhas else pd.DataFrame()


# ---------------------------------------------------------------------------
# Fetch em lotes
# ---------------------------------------------------------------------------

def _fetch_lotes(pendentes: list[int], token: str, tipo: str,
                 fn_api, label: str) -> dict:
    """Busca IDs em lotes de _LOTE, salvando no SQLite após cada lote."""
    if not pendentes:
        return {}

    total = len(pendentes)
    barra  = st.progress(0, text=f"{label} — {total} notas")
    novos: dict = {}

    for i in range(0, total, _LOTE):
        lote = pendentes[i:i + _LOTE]
        lote_res = {nid: fn_api(nid, token) for nid in lote}
        salvar_cache(lote_res, tipo)
        novos.update(lote_res)

        n = min(i + _LOTE, total)
        barra.progress(n / total, text=f"{label}: {n}/{total}")
        if n < total:
            time.sleep(_PAUSA)

    barra.empty()
    return novos


# ---------------------------------------------------------------------------
# Montar df de notas (uma linha por nota)
# ---------------------------------------------------------------------------

def _montar_df(df_sql: pd.DataFrame, cache_nfe: dict,
               cache_nfse: dict, tipo_nota: str) -> pd.DataFrame:
    linhas = []
    seen_nfe:  set[int] = set()
    seen_nfse: set[int] = set()

    for _, row in df_sql.iterrows():
        r = row.to_dict()

        if pd.notna(r.get("nfe_id")) and tipo_nota in ("NFe e NFS-e", "NFe (Produto)"):
            nid = int(r["nfe_id"])
            if nid not in seen_nfe:
                seen_nfe.add(nid)
                linhas.append(_linha(r, "NFe", nid, cache_nfe.get(nid, {})))

        if pd.notna(r.get("nfse_id")) and tipo_nota in ("NFe e NFS-e", "NFS-e (Serviço)"):
            nid = int(r["nfse_id"])
            if nid not in seen_nfse:
                seen_nfse.add(nid)
                linhas.append(_linha(r, "NFS-e", nid, cache_nfse.get(nid, {})))

    return pd.DataFrame(linhas) if linhas else pd.DataFrame()


def _linha(r: dict, tipo: str, nid: int, info: dict) -> dict:
    return {
        "tipo":         tipo,
        "id_bling":     nid,
        "numero":       info.get("numero", ""),
        "data_emissao": pd.to_datetime(info.get("data_emissao", ""), errors="coerce"),
        "situacao":     info.get("situacao", ""),
        "valor":        float(info.get("valor") or 0),
        "chave_acesso": info.get("chave_acesso", ""),
        "link":         info.get("link", ""),
        "cliente":      r.get("full_name", ""),
        "cpf":          r.get("cpf", ""),
        "email":        r.get("email", ""),
        "pagamento":    r.get("name", ""),
        "parcelamento": r.get("parcelamento", ""),
    }


# ---------------------------------------------------------------------------
# Render tabela + KPIs (chamado várias vezes durante o reparo de valores)
# ---------------------------------------------------------------------------

def _render(df: pd.DataFrame, kpi_ph, table_ph, fmt_brl):
    df = df.copy()
    df["emissao_fmt"] = df["data_emissao"].dt.strftime("%d/%m/%Y")
    df["valor_fmt"]   = df["valor"].apply(fmt_brl)

    with kpi_ph.container():
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Emitido",   fmt_brl(df["valor"].sum()))
        k2.metric("Notas",           len(df))
        k3.metric("Clientes Únicos", df["cpf"].nunique())
        sem_valor = int((df["valor"] == 0).sum())
        k4.metric("Sem valor", sem_valor,
                  help="Notas sem valor retornado pela Bling (ainda carregando ou campo não encontrado)")

    with table_ph.container():
        st.dataframe(
            df[[
                "tipo", "id_bling", "numero", "emissao_fmt",
                "parcelamento", "cliente", "cpf",
                "valor_fmt", "situacao", "chave_acesso", "link",
            ]],
            column_config={
                "tipo":         st.column_config.TextColumn("Tipo",      width="small"),
                "id_bling":     st.column_config.NumberColumn("ID Bling", format="%d", width="medium"),
                "numero":       st.column_config.TextColumn("Nº Nota",   width="small"),
                "emissao_fmt":  st.column_config.TextColumn("Emissão",   width="small"),
                "parcelamento": st.column_config.TextColumn("Pgto",      width="small"),
                "cliente":      st.column_config.TextColumn("Cliente",   width="large"),
                "cpf":          st.column_config.TextColumn("CPF",       width="medium"),
                "valor_fmt":    st.column_config.TextColumn("Valor Nota", width="medium"),
                "situacao":     st.column_config.TextColumn("Situação",  width="medium"),
                "chave_acesso": st.column_config.TextColumn("Chave de Acesso", width="large"),
                "link":         st.column_config.LinkColumn("DANFE",
                                    display_text="Abrir", width="small"),
            },
            use_container_width=True,
            hide_index=True,
            height=480,
        )


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def run_page():
    st.title("Notas Fiscais — Bling")

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

    # --- SQL ---
    with st.spinner("Carregando notas do banco…"):
        df_sql = carregar_dados("consultas/notas/notas_bling.sql")

    if df_sql.empty:
        st.warning("Nenhum dado na consulta.")
        st.stop()

    # --- Busca por ID ---
    _busca_tem_res = bool(st.session_state.get("busca_id_res"))
    with st.expander("🔎 Busca por ID", expanded=_busca_tem_res):
        b1, b2, b3 = st.columns([1, 2, 1])
        with b1:
            tipo_busca = st.selectbox("Tipo", ["NFe", "NFS-e"], key="sb_busca_tipo")
        with b2:
            id_input = st.number_input(
                "ID Bling", min_value=1, step=1, value=None,
                placeholder="ex: 123456", key="ni_busca_id",
            )
        with b3:
            st.write(""); st.write("")
            clicou_buscar_id = st.button("🔍 Buscar", key="btn_buscar_id_unico",
                                          use_container_width=True)

        if clicou_buscar_id and id_input:
            st.session_state["busca_id_res"]   = int(id_input)
            st.session_state["busca_tipo_res"]  = tipo_busca

        nid_res  = st.session_state.get("busca_id_res")
        tipo_res = st.session_state.get("busca_tipo_res", "NFe")

        if nid_res:
            tc  = "nfe"    if tipo_res == "NFe" else "nfse"
            ic  = "nfe_id" if tipo_res == "NFe" else "nfse_id"

            det_res  = buscar_cache([nid_res], tc).get(nid_res, {})
            df_match = df_sql[
                df_sql[ic].notna() &
                df_sql[ic].apply(lambda x: int(x) if pd.notna(x) else -1) == nid_res
            ]

            col_sq, col_db = st.columns(2)
            with col_sq:
                st.markdown(f"**SQLite — {tipo_res} {nid_res}**")
                if det_res and det_res.get("data_emissao"):
                    st.json({k: v for k, v in det_res.items() if k != "_debug"})
                    if det_res.get("_debug"):
                        st.caption(det_res["_debug"])
                elif det_res:
                    st.warning("Entrada no cache sem dados válidos.")
                    st.json({k: v for k, v in det_res.items() if k != "_debug"})
                else:
                    st.warning("Não encontrado no SQLite.")

            with col_db:
                st.markdown(f"**Banco de dados — {tipo_res} {nid_res}**")
                if not df_match.empty:
                    st.dataframe(df_match.reset_index(drop=True),
                                 hide_index=True, use_container_width=True)
                else:
                    st.warning("Não encontrado no banco de dados.")

            fn_api = _chamar_nfe if tipo_res == "NFe" else _chamar_nfse
            if st.button("🔄 Buscar / Atualizar na Bling", key="btn_atualizar_id_unico"):
                with st.spinner(f"Buscando {tipo_res} {nid_res} na Bling…"):
                    novo = fn_api(nid_res, token)
                salvar_cache({nid_res: novo}, tc)
                if novo.get("data_emissao"):
                    st.success("✅ Cache atualizado.")
                else:
                    st.error(f"Erro: {novo.get('_debug', '—')}")
                st.rerun()

    # --- Filtros (definidos ANTES das chamadas API) ---
    st.subheader("Filtros")
    col_tipo, col_d1, col_d2 = st.columns([1, 1, 1])

    with col_tipo:
        tipo_nota = st.selectbox(
            "Tipo de nota",
            ["NFe e NFS-e", "NFe (Produto)", "NFS-e (Serviço)"],
        )

    # Default: último mês com data de ordem disponível no SQL
    datas_sql = df_sql["date"].apply(
        lambda x: pd.Timestamp(x) if x is not None and x == x else pd.NaT
    ).dropna()
    dt_max_sql = datas_sql.max() if not datas_sql.empty else pd.Timestamp(datetime.now())
    ref = dt_max_sql if pd.notna(dt_max_sql) else pd.Timestamp(datetime.now())
    primeiro_dia = datetime(ref.year, ref.month, 1).date()
    ultimo_dia   = datetime(ref.year, ref.month,
                            calendar.monthrange(ref.year, ref.month)[1]).date()

    with col_d1:
        data_inicio = st.date_input("Emissão de",  value=primeiro_dia, format="DD/MM/YYYY")
    with col_d2:
        data_fim    = st.date_input("Emissão até", value=ultimo_dia,   format="DD/MM/YYYY")

    # Chave de sessão para este conjunto de filtros
    sess_key = f"notas_{tipo_nota}_{data_inicio}_{data_fim}"

    col_btn, _ = st.columns([1, 3])
    with col_btn:
        buscar = st.button("🔄 Buscar notas", use_container_width=True)

    if buscar:
        for k in [k for k in st.session_state if k.startswith("notas_")]:
            del st.session_state[k]

    # IDs do SQL completo (para cache total)
    ids_nfe_all  = [int(i) for i in df_sql["nfe_id"].dropna().unique()]
    ids_nfse_all = [int(i) for i in df_sql["nfse_id"].dropna().unique()]

    # IDs aproximados do período (usa date do SQL ±30 dias como proxy)
    # datetime.date objects precisam de conversão explícita para Timestamp
    _buf = timedelta(days=30)
    _date_col = df_sql["date"].apply(
        lambda x: pd.Timestamp(x) if x is not None and x == x else pd.NaT
    )
    _ini_ts = pd.Timestamp(data_inicio) - _buf
    _fim_ts = pd.Timestamp(data_fim)   + _buf
    _mask_proxy = _date_col.notna() & (_date_col >= _ini_ts) & (_date_col <= _fim_ts)
    _df_period = df_sql[_mask_proxy]
    ids_nfe_period  = [int(i) for i in _df_period["nfe_id"].dropna().unique()]
    ids_nfse_period = [int(i) for i in _df_period["nfse_id"].dropna().unique()]

    # --- Lê cache existente para TODOS os IDs (rápido, sem API) ---
    cache_nfe  = buscar_cache(ids_nfe_all,  "nfe")
    cache_nfse = buscar_cache(ids_nfse_all, "nfse")

    # --- Pendentes: IDs do período sem cache OU com cache quebrado (data_emissao vazia) ---
    def _pendentes(cache: dict, ids_periodo: list) -> list:
        faltam    = [i for i in ids_periodo if i not in cache]
        quebrados = [i for i in ids_periodo
                     if i in cache and not cache[i].get("data_emissao")]
        return list(set(faltam + quebrados))

    pend_nfe  = _pendentes(cache_nfe,  ids_nfe_period)  if tipo_nota in ("NFe e NFS-e", "NFe (Produto)")    else []
    pend_nfse = _pendentes(cache_nfse, ids_nfse_period) if tipo_nota in ("NFe e NFS-e", "NFS-e (Serviço)") else []
    total_pend = len(pend_nfe) + len(pend_nfse)

    # --- Seção: IDs sem cache (sempre visível, independente do período) ---
    df_sc = _df_sem_cache(df_sql, cache_nfe, cache_nfse)
    n_sc  = len(df_sc)
    titulo_sc = (f"📋 {n_sc} ID(s) sem cache SQLite — clique para selecionar e buscar"
                 if n_sc else "📋 IDs sem cache SQLite")
    with st.expander(titulo_sc, expanded=(n_sc > 0 and total_pend > 0 and sess_key not in st.session_state)):
        if df_sc.empty:
            st.success("✅ Todos os IDs do banco têm dados em cache.")
        else:
            nfe_sc  = df_sc[df_sc["tipo"] == "NFe"]
            nfse_sc = df_sc[df_sc["tipo"] == "NFS-e"]

            def _lbl(row):
                return f"{row['id_bling']} — {row['cliente']}" if row["cliente"] else str(row["id_bling"])

            nfe_opts  = nfe_sc.apply(_lbl,  axis=1).tolist() if not nfe_sc.empty  else []
            nfse_opts = nfse_sc.apply(_lbl, axis=1).tolist() if not nfse_sc.empty else []
            nfe_id_map  = dict(zip(nfe_opts,  nfe_sc["id_bling"].tolist()))
            nfse_id_map = dict(zip(nfse_opts, nfse_sc["id_bling"].tolist()))

            mc1, mc2 = st.columns(2)
            with mc1:
                if nfe_opts:
                    sel_nfe_lbl = st.multiselect(
                        f"NFe sem cache ({len(nfe_opts)})",
                        options=nfe_opts, default=nfe_opts, key="ms_nfe_sc",
                    )
                else:
                    st.success("✅ Todas as NFe em cache")
                    sel_nfe_lbl = []
            with mc2:
                if nfse_opts:
                    sel_nfse_lbl = st.multiselect(
                        f"NFS-e sem cache ({len(nfse_opts)})",
                        options=nfse_opts, default=nfse_opts, key="ms_nfse_sc",
                    )
                else:
                    st.success("✅ Todas as NFS-e em cache")
                    sel_nfse_lbl = []

            sel_nfe  = [nfe_id_map[l]  for l in sel_nfe_lbl]
            sel_nfse = [nfse_id_map[l] for l in sel_nfse_lbl]
            n_sel    = len(sel_nfe) + len(sel_nfse)
            lbl_btn  = (f"🔄 Buscar {n_sel} selecionado(s) na Bling"
                        if n_sel else "🔄 Buscar selecionados")
            if st.button(lbl_btn, disabled=n_sel == 0, key="btn_buscar_sc"):
                if sel_nfe:
                    _fetch_lotes(sel_nfe,  token, "nfe",  _chamar_nfe,  "NFe")
                if sel_nfse:
                    _fetch_lotes(sel_nfse, token, "nfse", _chamar_nfse, "NFS-e")
                st.rerun()

    # Se há pendentes no período e o usuário não clicou Buscar, para aqui
    if total_pend > 0 and not buscar and sess_key not in st.session_state:
        st.info(
            f"📦 Cache local tem **{total_pend}** nota(s) sem dados para este período "
            f"({len(pend_nfe)} NFe + {len(pend_nfse)} NFS-e). "
            "Use a seção acima para buscar IDs específicos, ou clique em "
            "**Buscar notas** para carregar todos do período."
        )
        st.stop()

    # Busca da API (só executa se há pendentes)
    if pend_nfe:
        cache_nfe.update(
            _fetch_lotes(pend_nfe, token, "nfe", _chamar_nfe, "NFe")
        )
    if pend_nfse:
        cache_nfse.update(
            _fetch_lotes(pend_nfse, token, "nfse", _chamar_nfse, "NFS-e")
        )

    st.session_state[sess_key] = True

    # --- Monta df e filtra ---
    df_notas = _montar_df(df_sql, cache_nfe, cache_nfse, tipo_nota)

    if df_notas.empty:
        st.warning("Nenhuma nota encontrada.")
        st.stop()

    mask = (
        df_notas["data_emissao"].notna()
        & (df_notas["data_emissao"].dt.date >= data_inicio)
        & (df_notas["data_emissao"].dt.date <= data_fim)
    )
    df_filtrado = df_notas[mask].copy()

    if df_filtrado.empty:
        dmin = df_notas["data_emissao"].min()
        dmax = df_notas["data_emissao"].max()
        aviso = (f" Dados de **{dmin.strftime('%d/%m/%Y')}** a **{dmax.strftime('%d/%m/%Y')}**."
                 if pd.notna(dmin) and pd.notna(dmax) else "")
        st.warning(f"Nenhuma nota no período selecionado.{aviso}")
        st.stop()

    # --- Filtros adicionais (situação, parcelamento) ---
    st.markdown("---")
    situacoes_disp  = sorted(df_filtrado["situacao"].dropna().unique().tolist())
    pgto_disp       = sorted(df_filtrado["parcelamento"].dropna().unique().tolist())

    fa1, fa2 = st.columns(2)
    with fa1:
        sit_sel  = st.multiselect("Situação",     situacoes_disp, default=situacoes_disp)
    with fa2:
        pgto_sel = st.multiselect("Tipo de pgto", pgto_disp,      default=pgto_disp)

    mask_extra = (
        df_filtrado["situacao"].isin(sit_sel  if sit_sel  else situacoes_disp) &
        df_filtrado["parcelamento"].isin(pgto_sel if pgto_sel else pgto_disp)
    )
    df_filtrado = df_filtrado[mask_extra].copy()

    if df_filtrado.empty:
        st.warning("Nenhuma nota para os filtros selecionados.")
        st.stop()

    # --- Exibe tabela imediatamente com o que tem ---
    kpi_ph   = st.empty()
    table_ph = st.empty()
    _render(df_filtrado, kpi_ph, table_ph, fmt_brl)

    # --- Repara 'valor' em lotes apenas para os IDs do período ---
    ids_nfe_fil  = df_filtrado.loc[df_filtrado["tipo"] == "NFe",   "id_bling"].tolist()
    ids_nfse_fil = df_filtrado.loc[df_filtrado["tipo"] == "NFS-e", "id_bling"].tolist()

    falt_nfe  = ids_sem_campo(ids_nfe_fil,  "nfe",  "valor")
    falt_nfse = ids_sem_campo(ids_nfse_fil, "nfse", "valor")
    total_falt = len(falt_nfe) + len(falt_nfse)

    if total_falt:
        barra_rep = st.progress(0, text=f"Obtendo valor de {total_falt} notas…")
        concluidos = 0
        todos_falt = [("nfe", nid) for nid in falt_nfe] + \
                     [("nfse", nid) for nid in falt_nfse]

        for i in range(0, total_falt, _LOTE):
            lote = todos_falt[i:i + _LOTE]
            novos_nfe, novos_nfse = {}, {}

            for tipo, nid in lote:
                if tipo == "nfe":
                    novos_nfe[nid] = _chamar_nfe(nid, token)
                    cache_nfe[nid] = novos_nfe[nid]
                else:
                    novos_nfse[nid] = _chamar_nfse(nid, token)
                    cache_nfse[nid] = novos_nfse[nid]

            if novos_nfe:
                salvar_cache(novos_nfe, "nfe")
            if novos_nfse:
                salvar_cache(novos_nfse, "nfse")

            concluidos += len(lote)
            barra_rep.progress(concluidos / total_falt,
                               text=f"Valores: {concluidos}/{total_falt}")

            # Atualiza valor no df_filtrado e re-renderiza tabela
            df_filtrado["valor"] = df_filtrado.apply(
                lambda r: (cache_nfe if r["tipo"] == "NFe" else cache_nfse)
                           .get(r["id_bling"], {}).get("valor", r["valor"]),
                axis=1,
            )
            _render(df_filtrado, kpi_ph, table_ph, fmt_brl)

            if concluidos < total_falt:
                time.sleep(_PAUSA)

        barra_rep.empty()

    # --- Exportar Excel ---
    st.markdown("---")
    df_export = df_filtrado.copy()
    df_export["emissao_fmt"] = df_export["data_emissao"].dt.strftime("%d/%m/%Y")
    df_export["valor_fmt"]   = df_export["valor"].apply(fmt_brl)
    df_export = df_export[[
        "tipo", "id_bling", "numero", "emissao_fmt", "parcelamento",
        "cliente", "cpf", "email", "pagamento", "valor_fmt",
        "situacao", "chave_acesso", "link",
    ]].rename(columns={
        "tipo":         "Tipo",
        "id_bling":     "ID Bling",
        "numero":       "Nº Nota",
        "emissao_fmt":  "Data Emissão",
        "parcelamento": "Tipo Pgto",
        "cliente":      "Cliente",
        "cpf":          "CPF",
        "email":        "E-mail",
        "pagamento":    "Forma Pagamento",
        "valor_fmt":    "Valor Nota",
        "situacao":     "Situação",
        "chave_acesso": "Chave de Acesso",
        "link":         "Link DANFE",
    })

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df_export.to_excel(w, index=False, sheet_name="Notas")
    buf.seek(0)

    nome = f"notas_{data_inicio.strftime('%Y%m%d')}_{data_fim.strftime('%Y%m%d')}.xlsx"
    st.download_button(
        "⬇️ Exportar Excel", data=buf, file_name=nome,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    # --- Debug ---
    with st.expander("🔍 Debug", expanded=False):
        st.write(f"Cache: NFe={stats_cache('nfe')['total']} | NFS-e={stats_cache('nfse')['total']}")
        st.write(f"Período: {len(df_filtrado)} notas | sem valor: {int((df_filtrado['valor']==0).sum())}")
        st.write("**Amostra NFe:**")
        for k, v in list(cache_nfe.items())[:3]:
            st.write(f"- {k}: {v.get('_debug','–')} | valor={v.get('valor')}")
