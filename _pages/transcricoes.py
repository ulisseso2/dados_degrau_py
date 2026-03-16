import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import streamlit as st
import plotly.express as px
from collections import Counter
from datetime import datetime
import json
from utils.sql_loader import carregar_dados
from utils.transcricao_analyzer import TranscricaoOpenAIAnalyzer
from utils.transcricao_mysql_writer import atualizar_avaliacao_transcricao

TIMEZONE = 'America/Sao_Paulo'

# ──────────────────────────────────────────────
# CACHE: lista principal (sem transcrição, sem JSON_EXTRACT)
# ──────────────────────────────────────────────
@st.cache_data(ttl=21600, show_spinner=False)
def carregar_transcricoes_base():
    df = carregar_dados("consultas/transcricoes/transcricoes.sql")
    if df.empty:
        return df
    df["data_ligacao"] = pd.to_datetime(df["data_ligacao"]).dt.tz_localize(TIMEZONE, ambiguous='infer')
    df['avaliada'] = (
        df.get('insight_ia', pd.Series(dtype=str))
        .fillna('').astype(str).str.strip().ne('')
    )
    df['avaliavel'] = df.get('avaliavel', pd.Series(0, index=df.index)).astype(bool)

    def _parse_insight(v):
        if v is None:
            return {}
        txt = str(v).strip()
        if not txt:
            return {}
        try:
            return json.loads(txt)
        except (TypeError, ValueError):
            return {}

    insight = df.get('insight_ia', pd.Series(dtype=str)).apply(_parse_insight)
    df['motivo_nao_avaliacao'] = insight.apply(
        lambda x: x.get('motivo_classificacao', '')
        if isinstance(x, dict) and x.get('classificacao_ligacao') and x.get('classificacao_ligacao') != 'venda'
        else ''
    )
    df['observacao_whatsapp'] = insight.apply(
        lambda x: "; ".join(x.get('observacoes', []))
        if isinstance(x, dict) and isinstance(x.get('observacoes'), list)
        else ''
    )

    return df


# ──────────────────────────────────────────────
# CACHE: detalhe individual (transcrição + agente/duração/tipo)
# ──────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def carregar_detalhe_transcricao(transcricao_id: int) -> dict:
    """Carrega transcrição, agente, duração e tipo de uma única linha via JSON_EXTRACT."""
    from conexao.mysql_connector import conectar_mysql
    from pathlib import Path
    engine = conectar_mysql()
    if not engine:
        return {}
    sql = Path("consultas/transcricoes/transcricao_detalhe.sql").read_text()
    sql = sql.replace("{ids}", str(int(transcricao_id)))
    try:
        df = pd.read_sql(sql, engine)
        if df.empty:
            return {}
        row = df.iloc[0]
        return {
            "transcricao": row.get("transcricao", ""),
            "agente": row.get("agente") or "Não identificado",
            "duracao": row.get("duracao"),
            "telefone": row.get("telefone"),
            "tipo": row.get("tipo") or "N/Informado",
            "insight_ia": row.get("insight_ia"),
        }
    except Exception as e:
        return {"erro": str(e)}


# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────
def _formatar_duracao(segundos) -> str:
    try:
        total = float(segundos)
    except (TypeError, ValueError):
        return "--:--"
    total = max(0.0, total)
    m, s = divmod(int(total), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _cor_nota(nota) -> str:
    try:
        n = float(nota)
    except (TypeError, ValueError):
        return ""
    if n >= 75:
        return "🟢"
    if n >= 50:
        return "🟡"
    return "🔴"


def _renderizar_transcricao(transcricao: str):
    import re
    texto = str(transcricao)
    padrao = re.compile(r"(?i)\b(ura|vendedor|cliente)\s*:")
    matches = list(padrao.finditer(texto))
    if not matches:
        st.markdown(texto)
        return
    for idx, match in enumerate(matches):
        marcador = match.group(1).lower()
        inicio = match.end()
        fim = matches[idx + 1].start() if idx + 1 < len(matches) else len(texto)
        conteudo = texto[inicio:fim].strip()
        if not conteudo:
            continue
        if marcador == "ura":
            st.markdown(f"**URA:** {conteudo}")
        elif marcador == "vendedor":
            st.markdown(f"**🎙️ Vendedor:** {conteudo}")
        else:
            st.markdown(f"**👤 Cliente:** {conteudo}")


def _limpar_selecao():
    st.session_state.transcricoes_selecionadas = []
    for key in list(st.session_state.keys()):
        if key.startswith("sel_"):
            del st.session_state[key]


# ──────────────────────────────────────────────
# EXECUÇÃO EM LOTE
# ──────────────────────────────────────────────
def _executar_avaliacoes(df_base: pd.DataFrame, ids_selecionados: list):
    if not ids_selecionados:
        return

    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Instância compartilhada — OpenAI client é thread-safe
    ia = TranscricaoOpenAIAnalyzer()
    total = len(ids_selecionados)
    bar = st.progress(0)
    status_txt = st.empty()

    # Estado compartilhado entre threads (protegido por lock)
    lock = threading.Lock()
    concluidos = [0]
    sucesso_count = [0]
    erros_count = [0]
    mensagens = []  # coletadas nas threads, exibidas no final (thread-safe)

    # Monta lista de tarefas com dados já extraídos do DataFrame
    tasks = []
    for tid in ids_selecionados:
        row_list = df_base[df_base['transcricao_id'] == tid]
        row_data = row_list.iloc[0] if not row_list.empty else {}
        nome = row_data.get('nome_lead', f'ID {tid}') if not row_list.empty else f'ID {tid}'
        tx = str(row_data.get('transcricao', '') or '') if not row_list.empty else ''
        tasks.append((tid, nome, tx, row_data if not row_list.empty else {}))

    def _avaliar_uma(task):
        tid, nome, tx, row_data = task

        if not tx or len(tx.strip()) < 500:
            return (tid, nome, 'insuficiente', None)

        try:
            analise = ia.analisar_transcricao(tx)
            if 'erro' in analise:
                return (tid, nome, 'erro_ia', analise['erro'])

            ok, err = atualizar_avaliacao_transcricao(
                transcricao_id=tid,
                insight_ia=analise.get('avaliacao_completa'),
                evaluation_ia=analise.get('nota_vendedor'),
                created_at=row_data.get('data_trancricao'),
                agent=row_data.get('agente'),
                duration=row_data.get('duracao'),
                phone=row_data.get('telefone_lead'),
                type_=row_data.get('tipo_ligacao'),
            )
            if ok:
                return (tid, nome, 'ok', None)
            return (tid, nome, 'erro_db', err or 'Erro desconhecido')

        except Exception as e:
            return (tid, nome, 'excecao', str(e))

    # 4 workers: bom equilíbrio entre paralelismo e limites de rate da API
    MAX_WORKERS = min(4, total)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_avaliar_uma, t): t for t in tasks}
        for future in as_completed(futures):
            tid, nome, status_r, detalhe = future.result()
            with lock:
                concluidos[0] += 1
                bar.progress(concluidos[0] / total)
                status_txt.text(f"Concluídas {concluidos[0]}/{total} ({MAX_WORKERS} em paralelo)...")
                if status_r == 'ok':
                    sucesso_count[0] += 1
                else:
                    erros_count[0] += 1
                    if status_r == 'insuficiente':
                        mensagens.append(('warning', f"Transcrição insuficiente: {nome}"))
                    elif status_r == 'erro_db':
                        mensagens.append(('error', f"Erro ao salvar {nome}: {detalhe}"))
                        st.session_state.ultimo_erro = detalhe
                    else:
                        mensagens.append(('error', f"Erro em {nome}: {detalhe}"))

    bar.empty()
    status_txt.empty()
    st.session_state.transcricoes_selecionadas = []

    # Exibe mensagens coletadas (chamadas Streamlit apenas no thread principal)
    for tipo, msg in mensagens:
        if tipo == 'warning':
            st.warning(msg)
        else:
            st.error(msg)

    if sucesso_count[0]:
        st.cache_data.clear()  # Limpa cache de ambas as páginas (transcrições + análise)
        st.success(f"✅ {sucesso_count[0]} avaliação(ões) concluída(s).")
        if erros_count[0]:
            st.warning(f"⚠️ {erros_count[0]} erro(s).")
        st.rerun()
    elif erros_count[0]:
        st.warning(f"⚠️ {erros_count[0]} erro(s). Nenhuma avaliação salva.")


# ──────────────────────────────────────────────
# REAVALIAÇÃO EM LOTE (economia de tokens)
# ──────────────────────────────────────────────
def _executar_reavaliacao(df_avaliadas: pd.DataFrame):
    """
    Reavalia transcrições já avaliadas usando prompt otimizado.
    Economia de tokens:
    - Heurísticas expandidas eliminam chamadas NA sem usar API
    - Classificação usa modelo leve (~300 tokens)
    - Prompt de reavaliação ~50% menor que avaliação completa
    """
    if df_avaliadas.empty:
        return

    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    ia = TranscricaoOpenAIAnalyzer()
    total = len(df_avaliadas)
    bar = st.progress(0)
    status_txt = st.empty()

    lock = threading.Lock()
    concluidos = [0]
    sucesso_count = [0]
    na_count = [0]
    erros_count = [0]
    tokens_total = [0]
    mensagens = []

    tasks = []
    for _, row in df_avaliadas.iterrows():
        tid = row.get('transcricao_id')
        nome = row.get('nome_lead', f'ID {tid}')
        tx = str(row.get('transcricao', '') or '')
        insight_existente = str(row.get('insight_ia', '') or '')
        tasks.append((tid, nome, tx, insight_existente, row))

    def _reavaliar_uma(task):
        tid, nome, tx, insight_existente, row_data = task

        if not tx or len(tx.strip()) < 50:
            return (tid, nome, 'insuficiente', None, 0)

        try:
            analise = ia.reavaliar_transcricao(tx, insight_existente)

            if 'erro' in analise:
                return (tid, nome, 'erro_ia', analise['erro'], 0)

            tokens = analise.get('tokens_usados') or 0
            status_r = 'na' if analise.get('lead_classificacao') == 'NA' else 'reavaliada'

            ok, err = atualizar_avaliacao_transcricao(
                transcricao_id=tid,
                insight_ia=analise.get('avaliacao_completa'),
                evaluation_ia=analise.get('nota_vendedor'),
                created_at=row_data.get('data_trancricao'),
                agent=row_data.get('agente'),
                duration=row_data.get('duracao'),
                phone=row_data.get('telefone_lead'),
                type_=row_data.get('tipo_ligacao'),
            )
            if ok:
                return (tid, nome, status_r, analise.get('reavaliacao_motivo'), tokens)
            return (tid, nome, 'erro_db', err or 'Erro desconhecido', 0)

        except Exception as e:
            return (tid, nome, 'excecao', str(e), 0)

    MAX_WORKERS = min(4, total)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_reavaliar_uma, t): t for t in tasks}
        for future in as_completed(futures):
            tid, nome, status_r, detalhe, tokens = future.result()
            with lock:
                concluidos[0] += 1
                tokens_total[0] += tokens
                bar.progress(concluidos[0] / total)
                status_txt.text(
                    f"Reavaliadas {concluidos[0]}/{total} "
                    f"(NA: {na_count[0]} | tokens: ~{tokens_total[0]:,})"
                )
                if status_r in ('reavaliada', 'na'):
                    sucesso_count[0] += 1
                    if status_r == 'na':
                        na_count[0] += 1
                elif status_r == 'insuficiente':
                    erros_count[0] += 1
                    mensagens.append(('warning', f"Transcrição insuficiente: {nome}"))
                else:
                    erros_count[0] += 1
                    mensagens.append(('error', f"Erro em {nome}: {detalhe}"))

    bar.empty()
    status_txt.empty()

    for tipo, msg in mensagens:
        if tipo == 'warning':
            st.warning(msg)
        else:
            st.error(msg)

    if sucesso_count[0]:
        st.cache_data.clear()
        st.success(
            f"✅ Reavaliação concluída: **{sucesso_count[0]}** processada(s)\n\n"
            f"- 🔄 Reavaliadas via IA: **{sucesso_count[0] - na_count[0]}**\n"
            f"- 🚫 Reclassificadas como NA: **{na_count[0]}** (0 tokens)\n"
            f"- 🪙 Tokens estimados: **~{tokens_total[0]:,}**\n"
            f"- ❌ Erros: **{erros_count[0]}**"
        )
        st.rerun()
    elif erros_count[0]:
        st.warning(f"⚠️ {erros_count[0]} erro(s). Nenhuma reavaliação salva.")


# ──────────────────────────────────────────────
# PÁGINA PRINCIPAL
# ──────────────────────────────────────────────
def run_page():
    st.title("📞 Transcrições de Ligações")

    if 'transcricoes_selecionadas' not in st.session_state:
        st.session_state.transcricoes_selecionadas = []
    if 'ultimo_erro' not in st.session_state:
        st.session_state.ultimo_erro = None

    # ── Carregamento ─────────────────────────────
    with st.spinner("Carregando dados..."):
        df = carregar_transcricoes_base()

    if df.empty:
        st.warning("⚠️ Nenhum dado encontrado. Verifique a conexão com o banco.")
        st.stop()

    # ── Filtros sidebar ───────────────────────────
    empresas = sorted(df["empresa"].dropna().unique().tolist())
    default_index = 0
    if "Degrau" in empresas:
        default_index = empresas.index("Degrau")
    
    empresa = st.sidebar.radio(
        "Empresa:",
        empresas,
        index=default_index,
        key="empresa_sel",
        on_change=_limpar_selecao,
    )

    hoje = pd.Timestamp.now(tz=TIMEZONE).date()
    periodo = st.sidebar.date_input(
        "Período:",
        [hoje - pd.Timedelta(days=7), hoje],
        key="periodo_sel",
        on_change=_limpar_selecao,
    )
    try:
        d_ini = pd.Timestamp(periodo[0], tz=TIMEZONE)
        d_fim = pd.Timestamp(periodo[1], tz=TIMEZONE) + pd.Timedelta(days=1)
    except (IndexError, TypeError):
        st.sidebar.warning("Selecione um período completo.")
        st.stop()

    # ── Filtros aplicados ─────────────────────────
    df_f = df[
        (df["empresa"] == empresa) &
        (df["data_ligacao"] >= d_ini) &
        (df["data_ligacao"] < d_fim)
    ].copy()

    # ── Métricas ──────────────────────────────────
    total = len(df_f)
    avaliaveis = int(df_f['avaliavel'].sum())
    avaliadas = int(df_f['avaliada'].sum())
    pendentes = avaliaveis - avaliadas

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total de ligações", total)
    c2.metric("Avaliáveis", avaliaveis)
    c3.metric("Avaliadas", avaliadas)
    c4.metric("Pendentes", max(0, pendentes))

    # ── Reavaliação do período ────────────────────
    if avaliadas > 0:
        with st.expander(f"🔄 Reavaliar período ({avaliadas} avaliada(s))", expanded=False):
            st.caption(
                "Reavalia as transcrições já avaliadas no período usando "
                "heurísticas expandidas e prompt otimizado para economia de tokens."
            )
            st.markdown(
                "**Como funciona:**\n"
                "- Ligações curtas/incompletas/internas → reclassificadas como **NA** (0 tokens)\n"
                "- Ligações não-venda via classificação IA → **NA** (~300 tokens)\n"
                "- Ligações de venda → reavaliação com prompt condensado (~50% menos tokens)"
            )
            confirmar = st.checkbox(
                f"Confirmo a reavaliação de {avaliadas} transcrição(ões)",
                key="confirmar_reav"
            )
            if confirmar:
                if st.button(
                    f"🔄 Reavaliar {avaliadas} avaliação(ões)",
                    type="primary",
                    key="btn_reavaliar_periodo"
                ):
                    df_avaliadas_periodo = df_f[df_f['avaliada']].copy()
                    _executar_reavaliacao(df_avaliadas_periodo)

    # ── Gráfico rápido: ligações por data ────────────────
    _df_por_data = df_f.copy()
    _df_por_data['data_dia'] = _df_por_data['data_ligacao'].dt.date
    _df_por_data = _df_por_data.groupby('data_dia').size().reset_index(name='Total')
    if not _df_por_data.empty:
        _fig_td = px.bar(
            _df_por_data, x='data_dia', y='Total',
            labels={'data_dia': 'Data', 'Total': 'Ligações'},
            color_discrete_sequence=['#636EFA'],
        )
        _fig_td.update_layout(height=200, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(_fig_td, use_container_width=True)

    if st.session_state.ultimo_erro:
        st.error(st.session_state.ultimo_erro)
        if st.button("Limpar erro"):
            st.session_state.ultimo_erro = None

    # ── Abas ──────────────────────────────────────
    tab1, tab2, tab3 = st.tabs(["🤖 Avaliar", "✅ Avaliações", "📤 Exportar"])

    # ════════════════════════════════════════════
    # TAB 1 — AVALIAR
    # ════════════════════════════════════════════
    with tab1:

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            filtro_avaliavel = st.radio(
                "Transcrições:",
                ["Avaliáveis", "Todas"],
                horizontal=True,
                key="filtro_avaliavel_tab1",
                on_change=_limpar_selecao,
            )
        with col_f2:
            filtro_status = st.radio(
                "Status:",
                ["Pendentes", "Avaliadas", "Todas"],
                horizontal=True,
                key="filtro_status_tab1",
                on_change=_limpar_selecao,
            )

        df_t1 = df_f.sort_values("data_ligacao", ascending=False).copy()
        if filtro_avaliavel == "Avaliáveis":
            df_t1 = df_t1[df_t1['avaliavel']]
        if filtro_status == "Pendentes":
            df_t1 = df_t1[~df_t1['avaliada']]
        elif filtro_status == "Avaliadas":
            df_t1 = df_t1[df_t1['avaliada']]

        st.caption(f"{len(df_t1)} registro(s)")

        if df_t1.empty:
            st.info("Nenhuma transcrição encontrada com este filtro.")
        else:
            # ── paginação ──
            col_p1, col_p2 = st.columns([3, 1])
            with col_p1:
                page_size = st.selectbox("Por página:", [20, 50, 100], key="ps_t1")
            total_pages = max(1, -(-len(df_t1) // page_size))
            with col_p2:
                pagina = st.number_input("Pág.", 1, total_pages, 1, key="pg_t1")

            inicio = (pagina - 1) * page_size
            fatia = df_t1.iloc[inicio: inicio + page_size]

            # ── ações rápidas ──
            col_sa, col_sb, col_av = st.columns([1, 1, 1])
            with col_sa:
                if st.button("☑️ Selecionar pendentes desta página"):
                    ids_pendentes = fatia[~fatia['avaliada']]['transcricao_id'].dropna().tolist()
                    for tid in ids_pendentes:
                        if tid not in st.session_state.transcricoes_selecionadas:
                            st.session_state.transcricoes_selecionadas.append(tid)
                    st.rerun()
            with col_sb:
                if st.button("🔁 Selecionar avaliadas desta página"):
                    ids_avaliadas = fatia[fatia['avaliada']]['transcricao_id'].dropna().tolist()
                    for tid in ids_avaliadas:
                        if tid not in st.session_state.transcricoes_selecionadas:
                            st.session_state.transcricoes_selecionadas.append(tid)
                    st.rerun()
                n_sel = len(st.session_state.transcricoes_selecionadas)
                if n_sel > 0:
                    if st.button(f"🤖 Avaliar {n_sel} selecionada(s)", type="primary", key="btn_avaliar_top"):
                        _executar_avaliacoes(df_t1, st.session_state.transcricoes_selecionadas)

            # ── tabela compacta ──
            df_tabela = fatia[[
                'transcricao_id', 'data_ligacao', 'nome_lead', 'agente', 'etapa',
                'avaliavel', 'avaliada', 'motivo_nao_avaliacao', 'observacao_whatsapp', 'transcricao'
            ]].copy()
            df_tabela['data_ligacao'] = fatia['data_ligacao'].dt.strftime('%d/%m/%Y %H:%M')
            df_tabela['Status'] = fatia['avaliada'].apply(lambda x: '✅' if x else '⏳')
            df_tabela['Avaliável'] = fatia['avaliavel'].apply(lambda x: '🟢' if x else '🔴')
            df_tabela['transcricao'] = fatia['transcricao'].fillna('').astype(str)
            df_tabela = df_tabela.rename(columns={
                'transcricao_id': 'ID',
                'data_ligacao': 'Data',
                'nome_lead': 'Lead',
                'agente': 'Agente',
                'etapa': 'Etapa',
                'motivo_nao_avaliacao': 'Motivo da não avaliação',
                'observacao_whatsapp': 'Obs. WhatsApp',
                'transcricao': 'Transcrição',
            }).drop(columns=['avaliavel', 'avaliada'])

            st.dataframe(
                df_tabela.set_index('ID'),
                use_container_width=True,
                height=min(400, 36 * len(df_tabela) + 38),
                column_config={
                    'Motivo da não avaliação': st.column_config.TextColumn(
                        'Motivo da não avaliação',
                        help='Motivo quando a ligação foi marcada como NA (não avaliável).',
                        width='medium',
                    ),
                    'Obs. WhatsApp': st.column_config.TextColumn(
                        'Obs. WhatsApp',
                        help='Registro automático quando a conversa migra para WhatsApp.',
                        width='medium',
                    ),
                    'Transcrição': st.column_config.TextColumn(
                        'Transcrição',
                        help='Clique na célula para ver a transcrição completa',
                        width='large',
                    ),
                },
            )

            # ── detalhe sob demanda ──
            st.divider()
            st.markdown("**Ver detalhes / selecionar para avaliação:**")

            ids_disponiveis = fatia['transcricao_id'].dropna().astype(int).tolist()
            id_escolhido = st.selectbox(
                "Selecione o ID da ligação:",
                options=["—"] + ids_disponiveis,
                key="id_detalhe",
            )

            if id_escolhido != "—":
                tid = int(id_escolhido)
                row_sel = fatia[fatia['transcricao_id'] == tid].iloc[0]

                col_d1, col_d2 = st.columns([3, 1])
                with col_d1:
                    st.markdown(
                        f"**Lead:** {row_sel.get('nome_lead', '—')}  \n"
                        f"**Telefone:** {row_sel.get('telefone_lead', '—')}  \n"
                        f"**Etapa:** {row_sel.get('etapa', '—')} | "
                        f"**Modalidade:** {row_sel.get('modalidade', '—')} | "
                        f"**Origem:** {row_sel.get('origem', '—')}"
                    )
                with col_d2:
                    status_str = "✅ Avaliada" if row_sel['avaliada'] else "⏳ Pendente"
                    st.markdown(f"**Status:** {status_str}")
                    label_checkbox = "🔁 Reavaliar" if row_sel['avaliada'] else "Incluir na avaliação"
                    sel_key = f"sel_{tid}"
                    marcado = st.checkbox(
                        label_checkbox,
                        value=tid in st.session_state.transcricoes_selecionadas,
                        key=sel_key,
                    )
                    if marcado and tid not in st.session_state.transcricoes_selecionadas:
                        st.session_state.transcricoes_selecionadas.append(tid)
                    elif not marcado and tid in st.session_state.transcricoes_selecionadas:
                        st.session_state.transcricoes_selecionadas.remove(tid)

                # Carrega transcrição só ao selecionar
                detalhe = carregar_detalhe_transcricao(tid)
                if detalhe.get("erro"):
                    st.error(f"Erro ao carregar: {detalhe['erro']}")
                elif detalhe.get("transcricao"):
                    info_cols = st.columns(3)
                    info_cols[0].caption(f"Agente: {detalhe.get('agente', '—')}")
                    info_cols[1].caption(f"Duração: {_formatar_duracao(detalhe.get('duracao'))}")
                    info_cols[2].caption(f"Tipo: {detalhe.get('tipo', '—')}")

                    with st.expander("📝 Transcrição", expanded=False):
                        with st.container(height=250):
                            _renderizar_transcricao(detalhe["transcricao"])
                else:
                    st.info("Transcrição não disponível para esta ligação.")

            # ── barra de ação final ──
            st.divider()
            n_sel = len(st.session_state.transcricoes_selecionadas)
            col_b1, col_b2, col_b3 = st.columns([2, 1, 1])
            col_b1.write(f"**{n_sel} selecionada(s)**")
            if n_sel > 0:
                with col_b2:
                    if st.button("🗑️ Limpar seleção"):
                        _limpar_selecao()
                        st.rerun()
                with col_b3:
                    if st.button(f"🤖 Avaliar {n_sel}", type="primary"):
                        _executar_avaliacoes(df_t1, st.session_state.transcricoes_selecionadas)

    # ════════════════════════════════════════════
    # TAB 2 — AVALIAÇÕES
    # ════════════════════════════════════════════
    with tab2:
        df_av = df_f[df_f['avaliada']].copy()

        if df_av.empty:
            st.info("Nenhuma avaliação realizada no período.")
        else:
            df_av['lead_score'] = pd.to_numeric(df_av.get('lead_score', 0), errors='coerce').fillna(0)
            df_av['evaluation_ia'] = pd.to_numeric(df_av.get('evaluation_ia', 0), errors='coerce').fillna(0)
            df_av['lead_classification'] = df_av.get('lead_classification', pd.Series(dtype=str)).fillna('—')

            # filtros rápidos
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                min_nota = st.slider("Nota mínima do vendedor:", 0, 100, 0, key="min_nota_t2")
            with col_f2:
                classes = sorted(df_av['lead_classification'].unique())
                class_sel = st.multiselect("Classificação do lead:", classes, default=classes, key="class_t2")

            col_f3, col_f4 = st.columns(2)
            with col_f3:
                agentes_disp = sorted([a for a in df_av.get('agente', pd.Series(dtype=str)).dropna().unique() if str(a).strip()])
                agente_sel = st.multiselect("Agente:", agentes_disp, default=agentes_disp, key="agente_t2") if agentes_disp else agentes_disp
            with col_f4:
                tipos_disp = sorted([t for t in df_av.get('tipo_ligacao', pd.Series(dtype=str)).dropna().unique() if str(t).strip()])
                tipo_sel = st.multiselect("Tipo de ligação:", tipos_disp, default=tipos_disp, key="tipo_t2") if tipos_disp else tipos_disp

            df_av = df_av[
                (df_av['evaluation_ia'] >= min_nota) &
                (df_av['lead_classification'].isin(class_sel))
            ]
            if agente_sel:
                df_av = df_av[df_av['agente'].isin(agente_sel)]
            if tipo_sel:
                df_av = df_av[df_av['tipo_ligacao'].isin(tipo_sel)]

            st.caption(f"{len(df_av)} avaliação(ões)")

            # métricas
            m1, m2, m3 = st.columns(3)
            m1.metric("Total", len(df_av))
            nota_media = df_av['evaluation_ia'].mean()
            m2.metric("Nota média vendedor", f"{nota_media:.1f}" if pd.notna(nota_media) else "—")
            _lead_validos = df_av.loc[df_av['lead_score'] > 0, 'lead_score']
            lead_media = _lead_validos.mean() if not _lead_validos.empty else float('nan')
            m3.metric("Lead score médio", f"{lead_media:.1f}" if pd.notna(lead_media) else "—")

            # tabela resumo
            df_resumo = df_av[['transcricao_id', 'data_ligacao', 'nome_lead', 'agente',
                                'evaluation_ia', 'lead_score', 'lead_classification', 'etapa', 'transcricao']].copy()
            df_resumo['data_ligacao'] = df_av['data_ligacao'].dt.strftime('%d/%m/%Y')
            df_resumo['Nota'] = df_av['evaluation_ia'].apply(
                lambda x: f"{_cor_nota(x)} {int(x)}" if pd.notna(x) else "—"
            )
            df_resumo['transcricao'] = df_av['transcricao'].fillna('').astype(str)
            df_resumo = df_resumo.rename(columns={
                'transcricao_id': 'ID',
                'data_ligacao': 'Data',
                'nome_lead': 'Lead',
                'agente': 'Agente',
                'lead_score': 'Score Lead',
                'lead_classification': 'Classificação',
                'etapa': 'Etapa',
                'transcricao': 'Transcrição',
            }).drop(columns=['evaluation_ia'])

            st.dataframe(
                df_resumo.set_index('ID'),
                use_container_width=True,
                height=300,
                column_config={
                    'Transcrição': st.column_config.TextColumn(
                        'Transcrição',
                        help='Clique na célula para ver a transcrição completa',
                        width='large',
                    ),
                },
            )

            # detalhe sob demanda
            st.divider()
            st.markdown("**Detalhes de avaliação:**")
            ids_av = df_av['transcricao_id'].dropna().astype(int).tolist()
            id_av = st.selectbox("Selecione o ID:", ["—"] + ids_av, key="id_av_det")

            if id_av != "—":
                tid = int(id_av)
                row_av = df_av[df_av['transcricao_id'] == tid].iloc[0]
                detalhe = carregar_detalhe_transcricao(tid)

                st.markdown(
                    f"**Lead:** {row_av.get('nome_lead', '—')} | "
                    f"**Nota:** {_cor_nota(row_av['evaluation_ia'])} {int(row_av['evaluation_ia'])} | "
                    f"**Score Lead:** {int(row_av['lead_score'])} | "
                    f"**Classificação:** {row_av['lead_classification']}"
                )
                st.caption(
                    f"Agente: {detalhe.get('agente', '—')} | "
                    f"Duração: {_formatar_duracao(detalhe.get('duracao'))} | "
                    f"Tipo: {detalhe.get('tipo', '—')}"
                )

                col_t1, col_t2 = st.columns(2)
                with col_t1:
                    with st.expander("📝 Transcrição", expanded=False):
                        tx = detalhe.get("transcricao", "")
                        if tx:
                            with st.container(height=250):
                                _renderizar_transcricao(tx)
                        else:
                            st.info("Transcrição não disponível.")

                with col_t2:
                    def _split(txt):
                        return [t.strip() for t in str(txt).split(";") if t.strip()] if txt else []

                    melhorias = _split(row_av.get('improvements'))
                    fortes = _split(row_av.get('strengths'))
                    erro_caro = row_av.get('most_expensive_mistake', '')

                    if fortes:
                        with st.expander("✅ Pontos fortes", expanded=False):
                            for p in fortes:
                                st.write(f"• {p}")
                    if melhorias:
                        with st.expander("🛠️ Pontos de melhoria", expanded=False):
                            for p in melhorias:
                                st.write(f"• {p}")
                    if erro_caro and str(erro_caro).strip():
                        st.info(f"💸 **Erro mais caro:** {erro_caro}")

                # Reavaliar
                if st.button("🔁 Reavaliar esta ligação", key=f"reav_{tid}"):
                    tx = detalhe.get("transcricao", "")
                    if not tx:
                        st.error("Transcrição não encontrada.")
                    else:
                        with st.spinner("Reavaliando..."):
                            ia = TranscricaoOpenAIAnalyzer()
                            analise = ia.analisar_transcricao(tx)
                        if 'erro' in analise:
                            st.error(analise['erro'])
                        else:
                            ok, err = atualizar_avaliacao_transcricao(
                                transcricao_id=tid,
                                insight_ia=analise.get('avaliacao_completa'),
                                evaluation_ia=analise.get('nota_vendedor'),
                                created_at=row_av.get('data_trancricao'),
                                agent=detalhe.get('agente'),
                                duration=detalhe.get('duracao'),
                                phone=detalhe.get('telefone'),
                                type_=detalhe.get('tipo'),
                            )
                            if ok:
                                carregar_transcricoes_base.clear()
                                carregar_detalhe_transcricao.clear()
                                st.success("Reavaliação concluída!")
                                st.rerun()
                            else:
                                msg = f"Erro ao salvar{f': {err}' if err else '.'}"
                                st.error(msg)
                                st.session_state.ultimo_erro = msg

            # gráficos (colapsados por padrão)
            with st.expander("📊 Gráficos", expanded=False):
                gc1, gc2 = st.columns(2)
                with gc1:
                    df_class = df_av['lead_classification'].value_counts().reset_index()
                    df_class.columns = ['Classificação', 'Qtd']
                    st.plotly_chart(
                        px.pie(df_class, names='Classificação', values='Qtd', title='Classificação do Lead'),
                        use_container_width=True
                    )
                with gc2:
                    df_ag = (df_av.groupby('etapa')['evaluation_ia']
                             .agg(['mean', 'count']).reset_index()
                             .rename(columns={'mean': 'Média', 'count': 'Qtd', 'etapa': 'Etapa'}))
                    st.plotly_chart(
                        px.bar(df_ag, x='Etapa', y='Média', text='Qtd', title='Nota média por Etapa'),
                        use_container_width=True
                    )

            # resumo top pontos (colapsado)
            with st.expander("🧾 Top pontos fortes / melhorias / erros", expanded=False):
                import re as _re
                _pat_cat = _re.compile(r'^\[[^\]]+\]\s*')

                def _top(col_name, n=10):
                    itens = []
                    for v in df_av.get(col_name, pd.Series(dtype=str)).fillna(''):
                        itens.extend([t.strip() for t in str(v).split(";") if t.strip()])
                    # agrupa pelo texto sem colchete, mas preserva o original para exibição
                    contagem: dict = {}
                    for item in itens:
                        texto = _pat_cat.sub('', item).strip()
                        if texto:
                            contagem[texto] = contagem.get(texto, 0) + 1
                    return sorted(contagem.items(), key=lambda x: -x[1])[:n]

                rc1, rc2, rc3 = st.columns(3)
                with rc1:
                    st.markdown("**Top Pontos Fortes**")
                    for txt, n in _top('strengths'):
                        st.write(f"• {txt} ({n})")
                with rc2:
                    st.markdown("**Top Melhorias**")
                    for txt, n in _top('improvements'):
                        st.write(f"• {txt} ({n})")
                with rc3:
                    st.markdown("**Top Erros Caros**")
                    erros_l = [_pat_cat.sub('', str(v)).strip() for v in df_av.get('most_expensive_mistake', pd.Series(dtype=str)).fillna('') if str(v).strip()]
                    erros_l = [e for e in erros_l if e]
                    for txt, n in Counter(erros_l).most_common(10):
                        st.write(f"• {txt} ({n})")

    # ════════════════════════════════════════════
    # TAB 3 — EXPORTAR
    # ════════════════════════════════════════════
    with tab3:
        st.subheader("Exportar")
        df_exp = df_f[df_f['avaliada']].copy()
        if df_exp.empty:
            st.info("Nenhuma avaliação no período para exportar.")
        else:
            csv = df_exp.to_csv(index=False)
            st.download_button(
                "⬇️ Baixar CSV das avaliações",
                data=csv,
                file_name=f"avaliacoes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
            st.caption(f"{len(df_exp)} registros")
