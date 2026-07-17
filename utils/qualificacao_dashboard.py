# -*- coding: utf-8 -*-
"""
qualificacao_dashboard.py — Tab compartilhada "Bot × IA"
========================================================
Renderiza, nos dois dashboards (chats e ligações), a análise cruzada entre:
  • score DECLARADO pelo lead no bot (P1 urgência + P2 investimento), e
  • score INFERIDO pela IA lendo a conversa inteira (juiz cego),
mais o aproveitamento dos leads qualificados pelo vendedor (campo
`tratamento_lead_qualificado` da avaliação).

É esta tab que valida a régua P1/P2 e contextualiza a nota do vendedor pela
temperatura do lead recebido. Requer que o SQL da página exponha as colunas:
  oportunidade_id, p1_pontos, p2_pontos, score_bot_total, etapa_crm
(ver IMPLEMENTACAO_ULISSES.md §SQL). Sem elas, a tab exibe instrução.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.venda_consultiva_core import (
    SCORE_BOT_CORTE,
    SCORE_BOT_MAX,
    normalizar_score_bot,
)

_CORES_CLASS = {
    'A': '#00CC96', 'B': '#636EFA',
    'C': '#FFA15A', 'D': '#EF553B', '—': '#AAAAAA',
}

_TLQ_LABELS = {
    'adequado': '✅ Adequado',
    'parcial': '🟡 Parcial',
    'subaproveitado': '🔴 Subaproveitado',
    'nao_aplicavel': '— N/A',
}

_COLS_NECESSARIAS = ('score_bot_total',)


def tem_dados_qualificacao(df: pd.DataFrame) -> bool:
    """True se o df tem a coluna de score do bot com algum valor."""
    if df is None or df.empty:
        return False
    for c in _COLS_NECESSARIAS:
        if c not in df.columns:
            return False
    return pd.to_numeric(df['score_bot_total'], errors='coerce').notna().any()


def render_tab_bot_vs_ia(df_av: pd.DataFrame, id_col: str, canal_label: str):
    """
    Renderiza a tab completa. df_av: apenas avaliações concluídas (venda),
    com colunas lead_score, lead_classification, evaluation_ia, agente e,
    quando disponíveis, score_bot_total / p1_pontos / p2_pontos / tlq_status.
    """
    st.markdown("#### 🤝 Qualificação do Bot × Leitura da IA")
    st.caption(
        "Score declarado pelo lead nas perguntas P1/P2 (antes da conversa) "
        "cruzado com o score que a IA atribuiu lendo a conversa inteira "
        "(juiz cego — a IA não vê o P1/P2 ao pontuar o lead)."
    )

    if not tem_dados_qualificacao(df_av):
        st.info(
            "⚙️ Dados de qualificação (P1/P2) ainda não disponíveis nesta consulta. "
            "Habilite as colunas `oportunidade_id`, `p1_pontos`, `p2_pontos`, "
            "`score_bot_total` e `etapa_crm` no SQL da página "
            "(ver IMPLEMENTACAO_ULISSES.md, seção SQL)."
        )
        return

    df = df_av.copy()
    df['score_bot_total'] = pd.to_numeric(df['score_bot_total'], errors='coerce')
    df['lead_score'] = pd.to_numeric(df.get('lead_score'), errors='coerce')
    df = df[df['score_bot_total'].notna()].copy()
    df['bot_pct'] = df['score_bot_total'].apply(normalizar_score_bot)
    df['bot_qualificado'] = df['score_bot_total'] >= SCORE_BOT_CORTE

    st.caption(
        "⚠️ Régua da P2 (prontidão de investimento) vigente desde 10/07/2026. "
        "Períodos anteriores usam régua antiga — não misture eras na análise."
    )

    n_total = len(df)
    n_qual = int(df['bot_qualificado'].sum())
    df_cmp = df[df['lead_score'].notna() & (df['lead_score'] > 0)]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Com P1/P2 respondidas", n_total)
    k2.metric(f"Qualificados pelo bot (≥{SCORE_BOT_CORTE})", n_qual)
    if not df_cmp.empty:
        corr = df_cmp['bot_pct'].corr(df_cmp['lead_score'])
        k3.metric("Correlação bot × IA", f"{corr:.2f}" if pd.notna(corr) else "—",
                  help="Correlação de Pearson entre score declarado (normalizado 0-100) e score inferido pela IA.")
        gap_medio = (df_cmp['bot_pct'] - df_cmp['lead_score']).mean()
        k4.metric("Gap médio (bot − IA)", f"{gap_medio:+.1f} pts",
                  help="Positivo = leads se declaram mais quentes do que a conversa demonstra.")
    else:
        k3.metric("Correlação bot × IA", "—")
        k4.metric("Gap médio (bot − IA)", "—")

    # ── Scatter declarado × inferido ─────────────────────────────────────────
    if not df_cmp.empty:
        st.markdown("##### 📈 Declarado (bot) × Inferido (IA)")
        fig_sc = px.scatter(
            df_cmp, x='bot_pct', y='lead_score',
            color=df_cmp.get('lead_classification', pd.Series(['—'] * len(df_cmp))),
            color_discrete_map=_CORES_CLASS,
            hover_data=[c for c in ['agente', id_col, 'evaluation_ia'] if c in df_cmp.columns],
            labels={'bot_pct': 'Score do bot (normalizado 0-100)',
                    'lead_score': 'Score do lead pela IA', 'color': 'Classe IA'},
            opacity=0.7,
        )
        corte_pct = normalizar_score_bot(SCORE_BOT_CORTE)
        fig_sc.add_vline(x=corte_pct, line_dash='dash', line_color='#888',
                         annotation_text=f"corte bot ({SCORE_BOT_CORTE}/{SCORE_BOT_MAX})")
        fig_sc.add_shape(type='line', x0=0, y0=0, x1=100, y1=100,
                         line=dict(dash='dot', color='#BBBBBB'))
        fig_sc.update_layout(height=380, margin=dict(t=10, b=10))
        st.plotly_chart(fig_sc, use_container_width=True)

        # ── Matriz de concordância ───────────────────────────────────────────
        st.markdown("##### 🧭 Matriz de concordância")
        df_cmp = df_cmp.copy()
        df_cmp['ia_quente'] = df_cmp['lead_score'] >= 60  # classes A/B
        mat = pd.crosstab(
            df_cmp['bot_qualificado'].map({True: f'Bot ≥{SCORE_BOT_CORTE}', False: f'Bot <{SCORE_BOT_CORTE}'}),
            df_cmp['ia_quente'].map({True: 'IA quente (A/B)', False: 'IA frio (C/D)'}),
        )
        st.dataframe(mat, use_container_width=True)
        falsos_quentes = int(((df_cmp['bot_qualificado']) & (~df_cmp['ia_quente'])).sum())
        frios_ocultos = int(((~df_cmp['bot_qualificado']) & (df_cmp['ia_quente'])).sum())
        c_a, c_b = st.columns(2)
        c_a.metric("🔥→🧊 Bot quente / IA frio", falsos_quentes,
                   help="Declararam urgência+investimento mas a conversa não confirmou. Se alto, a régua está frouxa ou o lead chuta resposta.")
        c_b.metric("🧊→🔥 Bot frio / IA quente", frios_ocultos,
                   help="Não passaram do corte mas a conversa mostrou lead quente. Se alto, o corte 45 está deixando dinheiro na mesa.")

        # ── Maiores divergências ─────────────────────────────────────────────
        with st.expander("🔍 Maiores divergências (declarado − inferido)", expanded=False):
            df_div = df_cmp.copy()
            df_div['gap'] = (df_div['bot_pct'] - df_div['lead_score']).round(1)
            cols_show = [c for c in [id_col, 'agente', 'p1_pontos', 'p2_pontos',
                                     'score_bot_total', 'lead_score',
                                     'lead_classification', 'gap',
                                     'lead_disclaimer'] if c in df_div.columns]
            df_show = df_div.reindex(df_div['gap'].abs().sort_values(ascending=False).index)
            st.dataframe(df_show[cols_show].head(20), use_container_width=True, hide_index=True)

    # ── Aproveitamento por vendedor ──────────────────────────────────────────
    st.divider()
    st.markdown("##### 🎯 Aproveitamento de leads qualificados por vendedor")
    st.caption(
        "Leads que o bot marcou como qualificados (score ≥ corte): o vendedor "
        "tratou à altura? Fonte: campo `tratamento_lead_qualificado` da avaliação "
        "+ nota do vendedor no atendimento desses leads."
    )
    df_q = df[df['bot_qualificado']].copy()
    if df_q.empty:
        st.info("Nenhum lead qualificado pelo bot no período/filtms.")
        return

    if 'tlq_status' in df_q.columns and df_q['tlq_status'].fillna('').str.strip().ne('').any():
        df_q['tlq_status'] = df_q['tlq_status'].fillna('nao_aplicavel')
        resumo = (
            df_q.groupby('agente')
            .agg(
                leads_qualificados=(id_col, 'count'),
                nota_media_nesses=('evaluation_ia', 'mean'),
                subaproveitados=('tlq_status', lambda s: int((s == 'subaproveitado').sum())),
                parciais=('tlq_status', lambda s: int((s == 'parcial').sum())),
            )
            .reset_index()
        )
        resumo['% subaproveitado'] = (resumo['subaproveitados'] / resumo['leads_qualificados'] * 100).round(1)
        resumo['nota_media_nesses'] = resumo['nota_media_nesses'].round(1)
        resumo = resumo.sort_values('% subaproveitado', ascending=False)
        resumo.columns = ['Agente', 'Leads qualif.', 'Nota média', 'Subaproveitados', 'Parciais', '% Subaprov.']
        st.dataframe(resumo, use_container_width=True, hide_index=True,
                     height=min(420, 36 * len(resumo) + 42))

        dist = df_q['tlq_status'].map(_TLQ_LABELS).value_counts().reset_index()
        dist.columns = ['Tratamento', 'Qtd']
        fig_t = px.pie(dist, names='Tratamento', values='Qtd', hole=0.45)
        fig_t.update_traces(textinfo='percent+label')
        fig_t.update_layout(height=280, margin=dict(t=10, b=10))
        st.plotly_chart(fig_t, use_container_width=True)
    else:
        # Fallback quando avaliações antigas não têm o campo tlq_status
        resumo = (
            df_q.groupby('agente')
            .agg(leads_qualificados=(id_col, 'count'),
                 nota_media_nesses=('evaluation_ia', 'mean'))
            .reset_index()
        )
        resumo['nota_media_nesses'] = resumo['nota_media_nesses'].round(1)
        resumo.columns = ['Agente', 'Leads qualificados', 'Nota média nesses leads']
        st.dataframe(resumo.sort_values('Nota média nesses leads'),
                     use_container_width=True, hide_index=True)
        st.caption(
            "ℹ️ O detalhamento de tratamento (adequado/parcial/subaproveitado) "
            "aparece para avaliações feitas com a régua VCA-2026.07 em diante."
        )
