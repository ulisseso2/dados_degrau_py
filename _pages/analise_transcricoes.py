import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from collections import Counter
import re as _re
from datetime import datetime
from utils.sql_loader import carregar_dados

TIMEZONE = 'America/Sao_Paulo'

_PAT_CAT = _re.compile(r'^\[([^\]]+)\]\s*')

_CAT_LABELS = {
    'rapport':          '🤝 Rapport',
    'investigacao_spin':'🔍 Investigação SPIN',
    'valor_produto':    '💎 Valor do Produto',
    'gatilho_mental':   '⚡ Gatilho Mental',
    'objecao':          '🛡️ Objeção',
    'fechamento':       '🤝 Fechamento',
    'clareza':          '🗣️ Clareza',
    'outros':           '❓ Outros',
}

_CORES_CLASS = {
    'A': '#00CC96', 'B': '#636EFA',
    'C': '#FFA15A', 'D': '#EF553B', '—': '#AAAAAA',
}

# ──────────────────────────────────────────────
# CACHE
# ──────────────────────────────────────────────
@st.cache_data(ttl=21600, show_spinner=False)
def _carregar_dados() -> pd.DataFrame:
    df = carregar_dados("consultas/transcricoes/transcricoes.sql")
    if df.empty:
        return df
    df["data_ligacao"] = pd.to_datetime(
        df["data_ligacao"]
    ).dt.tz_localize(TIMEZONE, ambiguous='infer')
    df['avaliada'] = (
        df.get('insight_ia', pd.Series(dtype=str))
        .fillna('').astype(str).str.strip().ne('')
    )
    df['avaliavel'] = df.get('avaliavel', pd.Series(0, index=df.index)).astype(bool)
    df['evaluation_ia'] = pd.to_numeric(df.get('evaluation_ia'), errors='coerce')
    df['lead_score']    = pd.to_numeric(df.get('lead_score'),    errors='coerce')
    df['lead_classification'] = df.get(
        'lead_classification', pd.Series(dtype=str)
    ).fillna('—')
    df['duracao_seg'] = pd.to_numeric(df.get('duracao'), errors='coerce')
    df['duracao_min'] = df['duracao_seg'] / 60
    return df


# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────
def _cor_nota(nota) -> str:
    try:
        n = float(nota)
    except (TypeError, ValueError):
        return ""
    if n >= 75: return "🟢"
    if n >= 50: return "🟡"
    return "🔴"


def _strip_cat(txt: str) -> str:
    return _PAT_CAT.sub('', str(txt)).strip()


def _extract_cat(txt: str) -> str:
    m = _PAT_CAT.match(str(txt))
    return m.group(1) if m else 'outros'


def _top_items(series: pd.Series, n: int = 10) -> list:
    """Retorna top-n textos (sem prefixo [categoria]) com contagem."""
    itens = []
    for v in series.fillna(''):
        itens.extend([t.strip() for t in str(v).split(';') if t.strip()])
    contagem: dict = {}
    for item in itens:
        texto = _strip_cat(item)
        if texto:
            contagem[texto] = contagem.get(texto, 0) + 1
    return sorted(contagem.items(), key=lambda x: -x[1])[:n]


def _cat_counts(series: pd.Series) -> dict:
    """Conta itens por categoria SPIN."""
    contagem: dict = {}
    for v in series.fillna(''):
        for item in [t.strip() for t in str(v).split(';') if t.strip()]:
            cat = _extract_cat(item)
            contagem[cat] = contagem.get(cat, 0) + 1
    return contagem


def _safe_pct(num: int, den: int) -> float:
    return (num / den * 100) if den > 0 else 0.0


# ──────────────────────────────────────────────
# PÁGINA PRINCIPAL
# ──────────────────────────────────────────────
def run_page():
    st.title("📊 Análise de Desempenho — Ligações")
    st.caption(
        "Painel comercial · Análise de transcrições e avaliações da equipe de vendas"
    )

    # ── Carregamento ─────────────────────────────
    with st.spinner("Carregando dados..."):
        df_all = _carregar_dados()

    if df_all.empty:
        st.warning("⚠️ Nenhum dado encontrado. Verifique a conexão com o banco.")
        st.stop()

    # ── Filtros sidebar ───────────────────────────
    st.sidebar.header("🔍 Filtros")

    empresas = sorted(df_all["empresa"].dropna().unique().tolist())
    empresa = st.sidebar.radio("Empresa:", empresas, key="anl_empresa")

    hoje = pd.Timestamp.now(tz=TIMEZONE).date()
    periodo = st.sidebar.date_input(
        "Período:",
        [hoje - pd.Timedelta(days=30), hoje],
        key="anl_periodo",
    )
    try:
        d_ini = pd.Timestamp(periodo[0], tz=TIMEZONE)
        d_fim = pd.Timestamp(periodo[1], tz=TIMEZONE) + pd.Timedelta(days=1)
    except (IndexError, TypeError):
        st.sidebar.warning("Selecione um período completo.")
        st.stop()

    # Pré-filtro por empresa/período
    df_base = df_all[
        (df_all["empresa"] == empresa) &
        (df_all["data_ligacao"] >= d_ini) &
        (df_all["data_ligacao"] < d_fim)
    ].copy()

    # Filtros dinâmicos
    agentes_disp = sorted([
        a for a in df_base['agente'].dropna().unique() if str(a).strip()
    ])
    agente_sel = st.sidebar.multiselect(
        "Agente:", agentes_disp, default=agentes_disp, key="anl_agente"
    )

    tipos_disp = sorted([
        t for t in df_base.get(
            'tipo_ligacao', pd.Series(dtype=str)
        ).dropna().unique() if str(t).strip()
    ])
    tipo_sel = st.sidebar.multiselect(
        "Tipo de ligação:", tipos_disp, default=tipos_disp, key="anl_tipo"
    )

    if agente_sel:
        df_base = df_base[df_base['agente'].isin(agente_sel)]
    if tipo_sel:
        df_base = df_base[df_base['tipo_ligacao'].isin(tipo_sel)]

    if df_base.empty:
        st.warning("Nenhuma ligação encontrada para os filtros selecionados.")
        st.stop()

    df_av = df_base[df_base['avaliada']].copy()

    # ════════════════════════════════════════════
    # KPIs GLOBAIS
    # ════════════════════════════════════════════
    total      = len(df_base)
    avaliaveis = int(df_base['avaliavel'].sum())
    nao_aval   = total - avaliaveis
    avaliadas  = int(df_base['avaliada'].sum())
    pendentes  = max(0, avaliaveis - avaliadas)
    taxa_aval  = _safe_pct(avaliadas, avaliaveis)
    nota_media = df_av['evaluation_ia'].mean() if not df_av.empty else float('nan')
    lead_media = df_av['lead_score'].mean()    if not df_av.empty else float('nan')
    pct_ab     = (
        _safe_pct(df_av['lead_classification'].isin(['A', 'B']).sum(), len(df_av))
        if not df_av.empty else 0.0
    )

    st.markdown("### 📌 Resumo do Período")
    k1, k2, k3, k4, k5, k6, k7, k8 = st.columns(8)
    k1.metric("Total de ligações",    total)
    k2.metric("Avaliáveis",           avaliaveis)
    k3.metric("Não avaliáveis",       nao_aval)
    k4.metric("Avaliadas",            avaliadas)
    k5.metric("Pendentes",            pendentes)
    k6.metric("Taxa de avaliação",    f"{taxa_aval:.0f}%")
    k7.metric("Nota média vendedor",  f"{nota_media:.1f}" if pd.notna(nota_media) else "—")
    k8.metric("Leads A+B",            f"{pct_ab:.1f}%")

    st.divider()

    # ════════════════════════════════════════════
    # ABAS
    # ════════════════════════════════════════════
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📈 Visão Geral",
        "🏆 Ranking de Agentes",
        "🎯 Qualidade de Leads",
        "🔍 Análise SPIN",
        "👤 Relatório Individual",
    ])

    # ────────────────────────────────────────────
    # TAB 1 — VISÃO GERAL
    # ────────────────────────────────────────────
    with tab1:
        # ── Linha do tempo ──────────────────────
        st.markdown("#### 📅 Evolução Diária de Ligações")

        df_dia = (
            df_base.set_index('data_ligacao')
            .resample('D')
            .agg(total=('transcricao_id', 'count'), avaliadas_dia=('avaliada', 'sum'))
            .reset_index()
        )
        df_av_dia = (
            df_av.set_index('data_ligacao')['evaluation_ia']
            .resample('D').mean().reset_index()
            .rename(columns={'evaluation_ia': 'nota_media'})
        ) if not df_av.empty else pd.DataFrame(columns=['data_ligacao', 'nota_media'])
        df_dia = df_dia.merge(df_av_dia, on='data_ligacao', how='left')

        fig_tempo = go.Figure()
        fig_tempo.add_trace(go.Bar(
            x=df_dia['data_ligacao'], y=df_dia['total'],
            name='Total', marker_color='#636EFA', opacity=0.55,
        ))
        fig_tempo.add_trace(go.Bar(
            x=df_dia['data_ligacao'], y=df_dia['avaliadas_dia'],
            name='Avaliadas', marker_color='#00CC96', opacity=0.9,
        ))
        if df_dia['nota_media'].notna().any():
            fig_tempo.add_trace(go.Scatter(
                x=df_dia['data_ligacao'], y=df_dia['nota_media'],
                name='Nota Média', yaxis='y2', mode='lines+markers',
                line=dict(color='#EF553B', width=2),
                marker=dict(size=6),
            ))
        fig_tempo.update_layout(
            barmode='overlay',
            yaxis=dict(title='Qtd. Ligações'),
            yaxis2=dict(title='Nota Média', overlaying='y', side='right', range=[0, 100]),
            legend=dict(orientation='h', y=1.12),
            height=350, margin=dict(t=20, b=20),
        )
        st.plotly_chart(fig_tempo, use_container_width=True)

        # ── Linha 2: distribuição, classificação, duração ──
        col_v1, col_v2, col_v3 = st.columns(3)

        with col_v1:
            st.markdown("#### 📊 Distribuição de Notas")
            if not df_av.empty:
                fig_hist = px.histogram(
                    df_av, x='evaluation_ia', nbins=10, range_x=[0, 100],
                    labels={'evaluation_ia': 'Nota do Vendedor'},
                    color_discrete_sequence=['#636EFA'],
                )
                if pd.notna(nota_media):
                    fig_hist.add_vline(
                        x=nota_media, line_dash='dash', line_color='orange',
                        annotation_text=f"Média: {nota_media:.1f}",
                        annotation_position='top right',
                    )
                fig_hist.update_layout(height=270, margin=dict(t=10, b=10), showlegend=False)
                st.plotly_chart(fig_hist, use_container_width=True)
            else:
                st.info("Sem avaliações no período.")

        with col_v2:
            st.markdown("#### 🏷️ Classificação dos Leads")
            if not df_av.empty:
                df_cl = df_av['lead_classification'].value_counts().reset_index()
                df_cl.columns = ['Classificação', 'Qtd']
                fig_pie = px.pie(
                    df_cl, names='Classificação', values='Qtd',
                    color='Classificação', color_discrete_map=_CORES_CLASS, hole=0.45,
                )
                fig_pie.update_traces(textinfo='percent+label')
                fig_pie.update_layout(height=270, margin=dict(t=10, b=10))
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("Sem avaliações no período.")

        with col_v3:
            st.markdown("#### ⏱️ Duração Média por Tipo")
            df_dur = (
                df_base.dropna(subset=['tipo_ligacao', 'duracao_min'])
                .groupby('tipo_ligacao')['duracao_min']
                .agg(['mean', 'count']).reset_index()
                .rename(columns={
                    'tipo_ligacao': 'Tipo',
                    'mean': 'Duração Média (min)',
                    'count': 'Qtd',
                })
                .sort_values('Duração Média (min)', ascending=False)
            )
            if not df_dur.empty:
                fig_dur = px.bar(
                    df_dur, x='Tipo', y='Duração Média (min)',
                    text=df_dur['Qtd'].apply(lambda x: f"n={x}"),
                    color_discrete_sequence=['#AB63FA'],
                )
                fig_dur.update_traces(textposition='outside')
                fig_dur.update_layout(height=270, margin=dict(t=10, b=10), showlegend=False)
                st.plotly_chart(fig_dur, use_container_width=True)
            else:
                st.info("Sem dados de duração.")

        # ── Linha 3: etapa + produto ────────────
        col_v4, col_v5 = st.columns(2)

        with col_v4:
            st.markdown("#### 📍 Nota Média por Etapa do Funil")
            if not df_av.empty and 'etapa' in df_av.columns:
                df_etapa = (
                    df_av.groupby('etapa')['evaluation_ia']
                    .agg(['mean', 'count']).reset_index()
                    .rename(columns={
                        'etapa': 'Etapa', 'mean': 'Nota Média', 'count': 'Qtd'
                    })
                    .sort_values('Nota Média', ascending=False)
                )
                fig_etapa = px.bar(
                    df_etapa, x='Etapa', y='Nota Média', text='Qtd',
                    color='Nota Média',
                    color_continuous_scale='RdYlGn', range_color=[0, 100],
                )
                fig_etapa.update_traces(
                    texttemplate='n=%{text}', textposition='outside'
                )
                fig_etapa.update_layout(height=300, margin=dict(t=10, b=10))
                st.plotly_chart(fig_etapa, use_container_width=True)
            else:
                st.info("Sem dados de etapa.")

        with col_v5:
            st.markdown("#### 🎓 Produtos Mais Recomendados")
            if not df_av.empty and 'produto_recomendado' in df_av.columns:
                prods = df_av['produto_recomendado'].dropna()
                prods = prods[prods.str.strip() != '']
                if not prods.empty:
                    df_prod = prods.value_counts().head(10).reset_index()
                    df_prod.columns = ['Produto', 'Qtd']
                    fig_prod = px.bar(
                        df_prod, x='Qtd', y='Produto', orientation='h',
                        color_discrete_sequence=['#19D3F3'],
                    )
                    fig_prod.update_layout(
                        height=300, margin=dict(t=10, b=10),
                        yaxis=dict(categoryorder='total ascending'),
                    )
                    st.plotly_chart(fig_prod, use_container_width=True)
                else:
                    st.info("Sem dados de produtos recomendados.")
            else:
                st.info("Sem dados de produtos recomendados.")

    # ────────────────────────────────────────────
    # TAB 2 — RANKING DE AGENTES
    # ────────────────────────────────────────────
    with tab2:
        if df_av.empty:
            st.info("Sem avaliações para análise de agentes.")
        else:
            # Agrega por agente
            df_rank = (
                df_av.groupby('agente')
                .agg(
                    ligacoes=('transcricao_id', 'count'),
                    nota_media=('evaluation_ia', 'mean'),
                    nota_min=('evaluation_ia', 'min'),
                    nota_max=('evaluation_ia', 'max'),
                    lead_score_medio=('lead_score', 'mean'),
                )
                .reset_index()
            )
            for cls in ['A', 'B', 'C', 'D']:
                tmp = (
                    df_av[df_av['lead_classification'] == cls]
                    .groupby('agente').size()
                    .reset_index(name=f'leads_{cls}')
                )
                df_rank = df_rank.merge(tmp, on='agente', how='left')
                df_rank[f'leads_{cls}'] = df_rank[f'leads_{cls}'].fillna(0).astype(int)

            df_rank['leads_ab'] = df_rank['leads_A'] + df_rank['leads_B']
            df_rank['pct_ab']   = (df_rank['leads_ab'] / df_rank['ligacoes'] * 100).round(1)
            df_rank = df_rank.sort_values('nota_media', ascending=False).reset_index(drop=True)
            df_rank.index += 1

            media_time = df_av['evaluation_ia'].mean()
            melhor     = df_rank.iloc[0]

            # KPIs rápidos
            kr1, kr2, kr3, kr4 = st.columns(4)
            kr1.metric("🥇 Melhor vendedor",    melhor['agente'])
            kr2.metric("🎯 Nota do melhor",     f"{melhor['nota_media']:.1f}")
            kr3.metric("📊 Média do time",       f"{media_time:.1f}")
            kr4.metric("👥 Agentes avaliados",  len(df_rank))

            # Tabela de ranking
            st.markdown("#### 🏅 Ranking de Desempenho")
            df_exibir = df_rank[[
                'agente', 'ligacoes', 'nota_media', 'nota_min', 'nota_max',
                'lead_score_medio', 'pct_ab', 'leads_A', 'leads_B', 'leads_C', 'leads_D',
            ]].copy()
            df_exibir.columns = [
                'Agente', 'Ligações', 'Nota Média', 'Nota Mín', 'Nota Máx',
                'Score Lead Médio', '% Leads A+B', 'A', 'B', 'C', 'D',
            ]
            df_exibir['Nota Média']       = df_exibir['Nota Média'].round(1)
            df_exibir['Nota Mín']         = df_exibir['Nota Mín'].round(0).astype(int)
            df_exibir['Nota Máx']         = df_exibir['Nota Máx'].round(0).astype(int)
            df_exibir['Score Lead Médio'] = df_exibir['Score Lead Médio'].round(1)
            df_exibir['% Leads A+B']      = df_exibir['% Leads A+B'].astype(str) + '%'

            st.dataframe(
                df_exibir,
                use_container_width=True,
                height=min(420, 36 * len(df_exibir) + 42),
            )

            # Gráficos side-by-side
            col_r1, col_r2 = st.columns(2)

            with col_r1:
                st.markdown("#### 📊 Nota Média por Agente")
                df_bar = df_rank.sort_values('nota_media').copy()
                fig_bar = px.bar(
                    df_bar, x='nota_media', y='agente', orientation='h',
                    text='nota_media', color='nota_media',
                    color_continuous_scale='RdYlGn', range_color=[0, 100],
                    labels={'nota_media': 'Nota Média', 'agente': ''},
                )
                fig_bar.add_vline(
                    x=media_time, line_dash='dash', line_color='#636EFA',
                    annotation_text=f"Média: {media_time:.1f}",
                    annotation_position='top right',
                )
                fig_bar.update_traces(texttemplate='%{text:.1f}', textposition='outside')
                fig_bar.update_layout(
                    height=max(300, 44 * len(df_rank)),
                    margin=dict(t=10, b=10), showlegend=False,
                )
                st.plotly_chart(fig_bar, use_container_width=True)

            with col_r2:
                st.markdown("#### 🔵 Volume × Qualidade (tamanho = ligações)")
                fig_bbl = px.scatter(
                    df_rank, x='nota_media', y='lead_score_medio',
                    size='ligacoes', color='pct_ab',
                    color_continuous_scale='RdYlGn', range_color=[0, 100],
                    text='agente',
                    labels={
                        'nota_media':       'Nota Média Vendedor',
                        'lead_score_medio': 'Score Médio do Lead',
                        'pct_ab':           '% Leads A+B',
                        'ligacoes':         'Ligações',
                    },
                    hover_data=['ligacoes'],
                )
                fig_bbl.update_traces(textposition='top center', textfont_size=10)
                fig_bbl.update_layout(
                    height=max(300, 44 * len(df_rank)),
                    margin=dict(t=10, b=10),
                )
                st.plotly_chart(fig_bbl, use_container_width=True)

            # Distribuição de classificações empilhadas
            st.markdown("#### 🎯 Distribuição de Classificações por Agente")
            df_dist_m = df_rank[['agente', 'leads_A', 'leads_B', 'leads_C', 'leads_D']].melt(
                id_vars='agente', var_name='Classe', value_name='Qtd'
            )
            df_dist_m['Classe'] = df_dist_m['Classe'].str.replace('leads_', '', regex=False)
            fig_dist = px.bar(
                df_dist_m, x='agente', y='Qtd', color='Classe',
                barmode='stack', color_discrete_map=_CORES_CLASS,
                labels={'agente': 'Agente'},
            )
            fig_dist.update_layout(height=340, margin=dict(t=10, b=10))
            st.plotly_chart(fig_dist, use_container_width=True)

    # ────────────────────────────────────────────
    # TAB 3 — QUALIDADE DE LEADS
    # ────────────────────────────────────────────
    with tab3:
        if df_av.empty:
            st.info("Sem avaliações para análise de leads.")
        else:
            pct_a = (df_av['lead_classification'] == 'A').mean() * 100
            pct_b = (df_av['lead_classification'] == 'B').mean() * 100

            kl1, kl2, kl3, kl4 = st.columns(4)
            kl1.metric("Leads Classe A",   f"{pct_a:.1f}%")
            kl2.metric("Leads Classe B",   f"{pct_b:.1f}%")
            kl3.metric("Score Lead Médio", f"{lead_media:.1f}" if pd.notna(lead_media) else "—")
            kl4.metric("Leads A+B",        f"{pct_ab:.1f}%")

            col_l1, col_l2 = st.columns(2)

            with col_l1:
                st.markdown("#### 🏷️ Distribuição por Classificação")
                df_class = df_av['lead_classification'].value_counts().reset_index()
                df_class.columns = ['Classificação', 'Qtd']
                fig_cl = px.bar(
                    df_class.sort_values('Classificação'),
                    x='Classificação', y='Qtd',
                    color='Classificação', color_discrete_map=_CORES_CLASS, text='Qtd',
                )
                fig_cl.update_traces(textposition='outside')
                fig_cl.update_layout(height=290, margin=dict(t=10, b=10), showlegend=False)
                st.plotly_chart(fig_cl, use_container_width=True)

            with col_l2:
                st.markdown("#### 📦 Score do Lead por Classificação")
                fig_box = px.box(
                    df_av[df_av['lead_classification'] != '—'],
                    x='lead_classification', y='lead_score',
                    color='lead_classification', color_discrete_map=_CORES_CLASS,
                    labels={
                        'lead_classification': 'Classificação',
                        'lead_score': 'Score do Lead',
                    },
                )
                fig_box.update_layout(height=290, margin=dict(t=10, b=10), showlegend=False)
                st.plotly_chart(fig_box, use_container_width=True)

            col_l3, col_l4 = st.columns(2)

            with col_l3:
                st.markdown("#### 📈 Nota Vendedor × Score do Lead")
                fig_sc = px.scatter(
                    df_av.dropna(subset=['evaluation_ia', 'lead_score']),
                    x='evaluation_ia', y='lead_score',
                    color='lead_classification', color_discrete_map=_CORES_CLASS,
                    hover_data=['nome_lead', 'agente'],
                    labels={
                        'evaluation_ia':     'Nota do Vendedor',
                        'lead_score':        'Score do Lead',
                        'lead_classification':'Classificação',
                    },
                    opacity=0.7,
                )
                fig_sc.update_layout(height=310, margin=dict(t=10, b=10))
                st.plotly_chart(fig_sc, use_container_width=True)

            with col_l4:
                st.markdown("#### 🎓 Áreas / Concursos de Interesse")
                col_area = 'concurso_area'
                if col_area in df_av.columns:
                    areas = df_av[col_area].dropna()
                    areas = areas[areas.str.strip() != '']
                    if not areas.empty:
                        df_areas = areas.value_counts().head(12).reset_index()
                        df_areas.columns = ['Área', 'Qtd']
                        fig_areas = px.bar(
                            df_areas, x='Qtd', y='Área', orientation='h',
                            color_discrete_sequence=['#FF6692'],
                        )
                        fig_areas.update_layout(
                            height=310, margin=dict(t=10, b=10),
                            yaxis=dict(categoryorder='total ascending'),
                        )
                        st.plotly_chart(fig_areas, use_container_width=True)
                    else:
                        st.info("Sem dados de área/concurso.")
                else:
                    st.info("Sem dados de área/concurso.")

            # Evolução diária do score de lead
            st.markdown("#### 📅 Evolução Diária do Score de Lead")
            df_ld = (
                df_av.set_index('data_ligacao')['lead_score']
                .resample('D').mean().reset_index()
                .rename(columns={'lead_score': 'Score Médio'})
            )
            fig_ld = px.area(
                df_ld, x='data_ligacao', y='Score Médio',
                color_discrete_sequence=['#636EFA'],
                labels={'data_ligacao': 'Data'},
            )
            if pd.notna(lead_media):
                fig_ld.add_hline(
                    y=lead_media, line_dash='dash', line_color='orange',
                    annotation_text=f"Média: {lead_media:.1f}",
                )
            fig_ld.update_layout(height=260, margin=dict(t=10, b=10))
            st.plotly_chart(fig_ld, use_container_width=True)

    # ────────────────────────────────────────────
    # TAB 4 — ANÁLISE SPIN
    # ────────────────────────────────────────────
    with tab4:
        if df_av.empty:
            st.info("Sem avaliações para análise SPIN.")
        else:
            cat_fortes    = _cat_counts(df_av.get('strengths',   pd.Series(dtype=str)))
            cat_melhorias = _cat_counts(df_av.get('improvements', pd.Series(dtype=str)))

            col_s1, col_s2 = st.columns(2)

            with col_s1:
                st.markdown("#### ✅ Pontos Fortes por Categoria SPIN")
                if cat_fortes:
                    df_cf = pd.DataFrame(list(cat_fortes.items()), columns=['cat', 'qtd'])
                    df_cf['Categoria'] = df_cf['cat'].map(
                        lambda c: _CAT_LABELS.get(c, c)
                    )
                    fig_cf = px.bar(
                        df_cf.sort_values('qtd'), x='qtd', y='Categoria',
                        orientation='h', color='qtd',
                        color_continuous_scale='Greens',
                        labels={'qtd': 'Frequência', 'Categoria': ''},
                    )
                    fig_cf.update_layout(height=340, margin=dict(t=10, b=10), showlegend=False)
                    st.plotly_chart(fig_cf, use_container_width=True)
                else:
                    st.info("Sem dados de pontos fortes com categoria.")

            with col_s2:
                st.markdown("#### 🛠️ Pontos de Melhoria por Categoria SPIN")
                if cat_melhorias:
                    df_cm = pd.DataFrame(list(cat_melhorias.items()), columns=['cat', 'qtd'])
                    df_cm['Categoria'] = df_cm['cat'].map(
                        lambda c: _CAT_LABELS.get(c, c)
                    )
                    fig_cm = px.bar(
                        df_cm.sort_values('qtd'), x='qtd', y='Categoria',
                        orientation='h', color='qtd',
                        color_continuous_scale='Reds',
                        labels={'qtd': 'Frequência', 'Categoria': ''},
                    )
                    fig_cm.update_layout(height=340, margin=dict(t=10, b=10), showlegend=False)
                    st.plotly_chart(fig_cm, use_container_width=True)
                else:
                    st.info("Sem dados de pontos de melhoria com categoria.")

            # Radar SPIN por agente (top 5)
            st.markdown("#### 🕸️ Radar SPIN por Agente — Top 5 em Volume")
            top5_ag = df_av['agente'].value_counts().head(5).index.tolist()
            cats_spin = [
                'rapport', 'investigacao_spin', 'valor_produto',
                'gatilho_mental', 'objecao', 'fechamento', 'clareza',
            ]
            cats_lbl = [_CAT_LABELS.get(c, c) for c in cats_spin]
            fig_radar = go.Figure()
            for ag in top5_ag:
                df_ag_r = df_av[df_av['agente'] == ag]
                f_ag = _cat_counts(df_ag_r.get('strengths',   pd.Series(dtype=str)))
                m_ag = _cat_counts(df_ag_r.get('improvements', pd.Series(dtype=str)))
                scores = []
                for cat in cats_spin:
                    f      = f_ag.get(cat, 0)
                    m      = m_ag.get(cat, 0)
                    total_c = f + m
                    scores.append((f / total_c * 100) if total_c > 0 else 50)
                fig_radar.add_trace(go.Scatterpolar(
                    r=scores + [scores[0]],
                    theta=cats_lbl + [cats_lbl[0]],
                    name=ag, fill='toself', opacity=0.55,
                ))
            fig_radar.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                height=460, margin=dict(t=30, b=30),
                legend=dict(orientation='h', y=-0.15),
            )
            st.plotly_chart(fig_radar, use_container_width=True)

            # Top itens textuais
            st.markdown("#### 📋 Top Itens por Coluna")
            col_s3, col_s4, col_s5 = st.columns(3)

            with col_s3:
                st.markdown("**🏆 Top Pontos Fortes**")
                for txt, n in _top_items(df_av.get('strengths', pd.Series(dtype=str))):
                    st.write(f"• {txt} `({n})`")

            with col_s4:
                st.markdown("**🔧 Top Melhorias**")
                for txt, n in _top_items(df_av.get('improvements', pd.Series(dtype=str))):
                    st.write(f"• {txt} `({n})`")

            with col_s5:
                st.markdown("**💸 Top Erros Mais Caros**")
                erros_l = [
                    _strip_cat(str(v))
                    for v in df_av.get(
                        'most_expensive_mistake', pd.Series(dtype=str)
                    ).fillna('')
                    if str(v).strip()
                ]
                erros_l = [e for e in erros_l if e]
                for txt, n in Counter(erros_l).most_common(10):
                    st.write(f"• {txt} `({n})`")

    # ────────────────────────────────────────────
    # TAB 5 — RELATÓRIO INDIVIDUAL
    # ────────────────────────────────────────────
    with tab5:
        if df_av.empty:
            st.info("Sem avaliações para geração de relatório individual.")
        else:
            # Ordenado pelo volume de ligações (mais ativo no topo)
            agentes_ord = df_av['agente'].value_counts().index.tolist()
            agente_rel  = st.selectbox(
                "Selecione o vendedor:", agentes_ord, key="anl_agente_rel"
            )

            df_ag       = df_av[df_av['agente'] == agente_rel].copy()
            media_time  = df_av['evaluation_ia'].mean()
            nota_ag     = df_ag['evaluation_ia'].mean()
            lead_ag     = df_ag['lead_score'].mean()
            pct_ab_ag   = df_ag['lead_classification'].isin(['A', 'B']).mean() * 100
            pos_ranking = agentes_ord.index(agente_rel) + 1

            st.markdown(f"## 📋 Relatório: {agente_rel}")
            st.caption(
                f"Período: {d_ini.strftime('%d/%m/%Y')} – "
                f"{(d_fim - pd.Timedelta(days=1)).strftime('%d/%m/%Y')} · "
                f"{len(df_ag)} avaliação(ões)"
            )

            # KPIs com delta vs time
            kc1, kc2, kc3, kc4, kc5 = st.columns(5)
            kc1.metric("Ligações avaliadas", len(df_ag))
            kc2.metric(
                "Nota média",
                f"{nota_ag:.1f}" if pd.notna(nota_ag) else "—",
                delta=f"{nota_ag - media_time:+.1f} vs time"
                if pd.notna(nota_ag) and pd.notna(media_time) else None,
            )
            kc3.metric(
                "Score lead médio",
                f"{lead_ag:.1f}" if pd.notna(lead_ag) else "—",
                delta=f"{lead_ag - lead_media:+.1f} vs time"
                if pd.notna(lead_ag) and pd.notna(lead_media) else None,
            )
            kc4.metric(
                "Leads A+B", f"{pct_ab_ag:.1f}%",
                delta=f"{pct_ab_ag - pct_ab:+.1f}% vs time",
            )
            kc5.metric("Ranking", f"#{pos_ranking} / {len(agentes_ord)}")

            # Linha de evolução + histograma
            col_rel1, col_rel2 = st.columns(2)

            with col_rel1:
                st.markdown("#### 📈 Evolução da Nota ao Longo do Tempo")
                df_ag_dia = (
                    df_ag.set_index('data_ligacao')['evaluation_ia']
                    .resample('D').mean().reset_index()
                    .rename(columns={'evaluation_ia': 'Nota'})
                )
                fig_ev = px.line(
                    df_ag_dia, x='data_ligacao', y='Nota', markers=True,
                    color_discrete_sequence=['#00CC96'],
                    labels={'data_ligacao': 'Data'},
                )
                if pd.notna(nota_ag):
                    fig_ev.add_hline(
                        y=nota_ag, line_dash='dot', line_color='gray',
                        annotation_text=f"Média: {nota_ag:.1f}",
                    )
                if pd.notna(media_time):
                    fig_ev.add_hline(
                        y=media_time, line_dash='dash', line_color='#636EFA',
                        annotation_text=f"Time: {media_time:.1f}",
                    )
                fig_ev.update_layout(
                    height=270, margin=dict(t=10, b=10),
                    yaxis=dict(range=[0, 100]),
                )
                st.plotly_chart(fig_ev, use_container_width=True)

            with col_rel2:
                st.markdown("#### 📊 Distribuição de Notas")
                fig_hag = px.histogram(
                    df_ag, x='evaluation_ia', nbins=10, range_x=[0, 100],
                    labels={'evaluation_ia': 'Nota'},
                    color_discrete_sequence=['#00CC96'],
                )
                if pd.notna(nota_ag):
                    fig_hag.add_vline(
                        x=nota_ag, line_dash='dash', line_color='orange',
                        annotation_text=f"Média: {nota_ag:.1f}",
                    )
                if pd.notna(media_time):
                    fig_hag.add_vline(
                        x=media_time, line_dash='dash', line_color='#636EFA',
                        annotation_text=f"Time: {media_time:.1f}",
                    )
                fig_hag.update_layout(height=270, margin=dict(t=10, b=10), showlegend=False)
                st.plotly_chart(fig_hag, use_container_width=True)

            # Pontos fortes e melhorias
            col_rel3, col_rel4 = st.columns(2)

            with col_rel3:
                st.markdown("#### ✅ Principais Pontos Fortes")
                items_fortes = _top_items(
                    df_ag.get('strengths', pd.Series(dtype=str)), n=8
                )
                if items_fortes:
                    for txt, n in items_fortes:
                        st.write(f"• {txt} `({n})`")
                else:
                    st.info("Nenhum ponto forte registrado.")

            with col_rel4:
                st.markdown("#### 🛠️ Principais Pontos de Melhoria")
                items_melhoria = _top_items(
                    df_ag.get('improvements', pd.Series(dtype=str)), n=8
                )
                if items_melhoria:
                    for txt, n in items_melhoria:
                        st.write(f"• {txt} `({n})`")
                else:
                    st.info("Nenhum ponto de melhoria registrado.")

            # Erro mais caro recorrente
            erros_ag = [
                _strip_cat(str(v))
                for v in df_ag.get(
                    'most_expensive_mistake', pd.Series(dtype=str)
                ).fillna('')
                if str(v).strip()
            ]
            erros_ag = [e for e in erros_ag if e]
            if erros_ag:
                top_erro, freq_erro = Counter(erros_ag).most_common(1)[0]
                st.error(
                    f"💸 **Erro mais frequente:** {top_erro} "
                    f"— citado em **{freq_erro}** ligação(ões)"
                )

            # Classificação de leads deste agente
            col_rel5, col_rel6 = st.columns(2)
            with col_rel5:
                st.markdown("#### 🏷️ Classificação de Leads")
                df_cl_ag = df_ag['lead_classification'].value_counts().reset_index()
                df_cl_ag.columns = ['Classificação', 'Qtd']
                fig_cl_ag = px.pie(
                    df_cl_ag, names='Classificação', values='Qtd',
                    color='Classificação', color_discrete_map=_CORES_CLASS, hole=0.4,
                )
                fig_cl_ag.update_layout(height=240, margin=dict(t=10, b=10))
                st.plotly_chart(fig_cl_ag, use_container_width=True)

            with col_rel6:
                st.markdown("#### 🎓 Produtos Recomendados (Top 5)")
                if 'produto_recomendado' in df_ag.columns:
                    prod_ag = df_ag['produto_recomendado'].dropna()
                    prod_ag = prod_ag[prod_ag.str.strip() != '']
                    if not prod_ag.empty:
                        df_pa = prod_ag.value_counts().head(5).reset_index()
                        df_pa.columns = ['Produto', 'Qtd']
                        fig_pa = px.bar(
                            df_pa, x='Qtd', y='Produto', orientation='h',
                            color_discrete_sequence=['#19D3F3'],
                        )
                        fig_pa.update_layout(
                            height=240, margin=dict(t=10, b=10),
                            yaxis=dict(categoryorder='total ascending'),
                        )
                        st.plotly_chart(fig_pa, use_container_width=True)
                    else:
                        st.info("Sem dados de produto.")
                else:
                    st.info("Sem dados de produto.")

            # Tabela detalhada
            st.markdown("#### 📋 Ligações Avaliadas")
            df_ag_tab = df_ag[[
                'transcricao_id', 'data_ligacao', 'nome_lead',
                'evaluation_ia', 'lead_score', 'lead_classification',
                'tipo_ligacao', 'etapa',
            ]].copy()
            df_ag_tab['data_ligacao'] = df_ag['data_ligacao'].dt.strftime('%d/%m/%Y')
            df_ag_tab['Nota'] = df_ag['evaluation_ia'].apply(
                lambda x: f"{_cor_nota(x)} {int(x)}" if pd.notna(x) else "—"
            )
            df_ag_tab = df_ag_tab.rename(columns={
                'transcricao_id':       'ID',
                'data_ligacao':         'Data',
                'nome_lead':            'Lead',
                'lead_score':           'Score Lead',
                'lead_classification':  'Classificação',
                'tipo_ligacao':         'Tipo',
                'etapa':                'Etapa',
            }).drop(columns=['evaluation_ia'])
            st.dataframe(df_ag_tab.set_index('ID'), use_container_width=True, height=320)

            # Exportar
            st.divider()
            _, col_exp = st.columns([3, 1])
            with col_exp:
                csv_data = df_ag.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="⬇️ Exportar CSV deste vendedor",
                    data=csv_data,
                    file_name=(
                        f"relatorio_{agente_rel.replace(' ', '_')}"
                        f"_{datetime.now().strftime('%Y%m%d')}.csv"
                    ),
                    mime="text/csv",
                )
