import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import streamlit as st
import plotly.express as px
from collections import Counter
from datetime import datetime
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

    ia = TranscricaoOpenAIAnalyzer()
    total = len(ids_selecionados)
    bar = st.progress(0)
    status = st.empty()
    sucesso = erros = 0

    for i, tid in enumerate(ids_selecionados):
        row_list = df_base[df_base['transcricao_id'] == tid]
        nome = row_list.iloc[0].get('nome_lead', f'ID {tid}') if not row_list.empty else f'ID {tid}'
        status.text(f"Avaliando {i+1}/{total}: {nome}...")

        detalhe = carregar_detalhe_transcricao(int(tid))
        tx = detalhe.get("transcricao", "")

        if not tx or len(tx.strip()) < 30:
            st.warning(f"Transcrição insuficiente: {nome}")
            erros += 1
            bar.progress((i + 1) / total)
            continue

        try:
            analise = ia.analisar_transcricao(tx)
            if 'erro' in analise:
                st.error(f"Erro na análise de {nome}: {analise['erro']}")
                erros += 1
            else:
                row_data = row_list.iloc[0] if not row_list.empty else {}
                ok, err = atualizar_avaliacao_transcricao(
                    transcricao_id=tid,
                    insight_ia=analise.get('avaliacao_completa'),
                    evaluation_ia=analise.get('nota_vendedor'),
                    created_at=row_data.get('data_trancricao') if not row_list.empty else None,
                    agent=detalhe.get('agente'),
                    duration=detalhe.get('duracao'),
                    phone=detalhe.get('telefone'),
                    type_=detalhe.get('tipo'),
                )
                if ok:
                    sucesso += 1
                else:
                    msg = err or "Erro desconhecido"
                    st.error(f"Erro ao salvar {nome}: {msg}")
                    st.session_state.ultimo_erro = msg
                    erros += 1
        except Exception as e:
            st.error(f"Erro inesperado em {nome}: {e}")
            erros += 1

        bar.progress((i + 1) / total)

    bar.empty()
    status.empty()
    st.session_state.transcricoes_selecionadas = []

    if sucesso:
        carregar_transcricoes_base.clear()
        carregar_detalhe_transcricao.clear()
        st.success(f"✅ {sucesso} avaliação(ões) concluída(s).")
    if erros:
        st.warning(f"⚠️ {erros} erro(s).")

    st.rerun()


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
    empresa = st.sidebar.radio(
        "Empresa:",
        empresas,
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
            df_tabela = fatia[['transcricao_id', 'data_ligacao', 'nome_lead', 'agente', 'etapa', 'avaliavel', 'avaliada']].copy()
            df_tabela['data_ligacao'] = fatia['data_ligacao'].dt.strftime('%d/%m/%Y %H:%M')
            df_tabela['Status'] = fatia['avaliada'].apply(lambda x: '✅' if x else '⏳')
            df_tabela['Avaliável'] = fatia['avaliavel'].apply(lambda x: '🟢' if x else '🔴')
            df_tabela = df_tabela.rename(columns={
                'transcricao_id': 'ID',
                'data_ligacao': 'Data',
                'nome_lead': 'Lead',
                'agente': 'Agente',
                'etapa': 'Etapa',
            }).drop(columns=['avaliavel', 'avaliada'])

            st.dataframe(
                df_tabela.set_index('ID'),
                use_container_width=True,
                height=min(400, 36 * len(df_tabela) + 38),
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
            lead_media = df_av['lead_score'].mean()
            m3.metric("Lead score médio", f"{lead_media:.1f}" if pd.notna(lead_media) else "—")

            # tabela resumo
            df_resumo = df_av[['transcricao_id', 'data_ligacao', 'nome_lead', 'telefone_lead',
                                'evaluation_ia', 'lead_score', 'lead_classification', 'etapa']].copy()
            df_resumo['data_ligacao'] = df_av['data_ligacao'].dt.strftime('%d/%m/%Y')
            df_resumo['Nota'] = df_av['evaluation_ia'].apply(
                lambda x: f"{_cor_nota(x)} {int(x)}" if pd.notna(x) else "—"
            )
            df_resumo = df_resumo.rename(columns={
                'transcricao_id': 'ID',
                'data_ligacao': 'Data',
                'nome_lead': 'Lead',
                'telefone_lead': 'Telefone',
                'lead_score': 'Score Lead',
                'lead_classification': 'Classificação',
                'etapa': 'Etapa',
            }).drop(columns=['evaluation_ia'])

            st.dataframe(df_resumo.set_index('ID'), use_container_width=True, height=300)

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
