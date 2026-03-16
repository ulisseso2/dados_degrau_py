import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from collections import Counter
import re as _re
import json
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
    'C': '#FFA15A', 'D': '#EF553B', 'NA': '#999999', '—': '#AAAAAA',
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
    df['evaluation_ia'] = df['evaluation_ia'].where(df['evaluation_ia'] > 0)  # 0 = não avaliado → NaN
    df['lead_score']    = pd.to_numeric(df.get('lead_score'),    errors='coerce')
    df['lead_classification'] = df.get(
        'lead_classification', pd.Series(dtype=str)
    ).fillna('—')
    df['duracao_seg'] = pd.to_numeric(df.get('duracao'), errors='coerce')
    df['duracao_min'] = df['duracao_seg'] / 60

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
    df['classificacao_ligacao'] = insight.apply(lambda x: x.get('classificacao_ligacao', '') if isinstance(x, dict) else '')
    df['motivo_nao_avaliacao'] = insight.apply(
        lambda x: x.get('motivo_classificacao', '') if isinstance(x, dict) and x.get('classificacao_ligacao') and x.get('classificacao_ligacao') != 'venda' else ''
    )
    df['observacao_whatsapp'] = insight.apply(
        lambda x: "; ".join(x.get('observacoes', [])) if isinstance(x, dict) and isinstance(x.get('observacoes'), list) else ''
    )
    lead_json = insight.apply(lambda x: x.get('lead_classificacao') if isinstance(x, dict) else None)
    df['lead_classification'] = lead_json.where(lead_json.notna(), df['lead_classification'])

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


def _gerar_html_relatorio(
    agente: str,
    df_tab: pd.DataFrame,
    periodo_ini: str,
    periodo_fim: str,
    kpis: dict | None = None,
    df_raw: pd.DataFrame | None = None,
) -> str:
    """Gera HTML estilizado para download/impressão como PDF."""
    import collections

    # ── KPI cards ─────────────────────────────────────────
    kpi_html = ""
    if kpis:
        kpi_items = "".join(
            f'<div class="kpi"><span class="kpi-label">{k}</span><span class="kpi-val">{v}</span></div>'
            for k, v in kpis.items()
        )
        kpi_html = f'<div class="kpi-row">{kpi_items}</div>'

    # ── Gráficos e pontos (apenas se df_raw disponível) ────
    graficos_html = ""
    pontos_html   = ""

    if df_raw is not None and not df_raw.empty:

        def _barra(label, n, total, cor):
            pct = round(n / total * 100) if total > 0 else 0
            return (
                f'<div class="bar-row">'
                f'<span class="bar-label">{label}</span>'
                f'<div class="bar-wrap"><div class="bar-fill" style="width:{pct}%;background:{cor}"></div></div>'
                f'<span class="bar-count">{n}</span></div>'
            )

        # 1) Distribuição de Notas
        notas = df_raw['evaluation_ia'].dropna()
        if not notas.empty:
            faixas = [('0–20', 0, 20, '#dc3545'), ('21–40', 21, 40, '#fd7e14'),
                      ('41–60', 41, 60, '#ffc107'), ('61–80', 61, 80, '#28a745'), ('81–100', 81, 100, '#007bff')]
            bars = "".join(_barra(lbl, int(((notas >= lo) & (notas <= hi)).sum()), len(notas), cor)
                           for lbl, lo, hi, cor in faixas)
            graficos_html += f'<div class="chart-box"><h3>&#128202; Distribuição de Notas</h3><div class="bar-chart">{bars}</div></div>'

        # 2) Classificação de Leads
        if 'lead_classification' in df_raw.columns:
            lead_vc = df_raw['lead_classification'].dropna().value_counts()
            if not lead_vc.empty:
                CORES_LEAD = {'A': '#28a745', 'B': '#17a2b8', 'C': '#ffc107', 'D': '#dc3545'}
                total_leads = int(lead_vc.sum())
                bars_l = "".join(_barra(cls, int(lead_vc.get(cls, 0)), total_leads, CORES_LEAD.get(cls, '#999'))
                                 for cls in ['A', 'B', 'C', 'D'])
                graficos_html += f'<div class="chart-box"><h3>&#127919; Classificação de Leads</h3><div class="bar-chart">{bars_l}</div></div>'

        graficos_section = f'<div class="charts-row">{graficos_html}</div>' if graficos_html else ""

        # 3) Pontos Fortes
        if 'strengths' in df_raw.columns:
            all_s = [s.strip() for v in df_raw['strengths'].dropna()
                     for s in str(v).split(';') if s.strip()]
            if all_s:
                top_s = collections.Counter(all_s).most_common(5)
                items = "".join(f"<li>{t} <em>({c}x)</em></li>" for t, c in top_s)
                pontos_html += f'<div class="pontos-box pontos-forte"><h3>&#9989; Pontos Fortes (Top 5)</h3><ul>{items}</ul></div>'

        # 4) Melhorias
        if 'improvements' in df_raw.columns:
            all_i = [s.strip() for v in df_raw['improvements'].dropna()
                     for s in str(v).split(';') if s.strip()]
            if all_i:
                top_i = collections.Counter(all_i).most_common(5)
                items = "".join(f"<li>{t} <em>({c}x)</em></li>" for t, c in top_i)
                pontos_html += f'<div class="pontos-box pontos-melhoria"><h3>&#9888;&#65039; Melhorias (Top 5)</h3><ul>{items}</ul></div>'

        # 5) Erros mais caros
        if 'most_expensive_mistake' in df_raw.columns:
            erros = df_raw['most_expensive_mistake'].dropna()
            erros = erros[erros.str.strip() != '']
            if not erros.empty:
                top_e = erros.value_counts().head(5)
                items = "".join(f"<li>{t} <em>({c}x)</em></li>" for t, c in top_e.items())
                pontos_html += f'<div class="pontos-box pontos-erro"><h3>&#128184; Erros Mais Caros (Top 5)</h3><ul>{items}</ul></div>'

        pontos_section = f'<div class="pontos-row">{pontos_html}</div>' if pontos_html else ""
    else:
        graficos_section = ""
        pontos_section   = ""

    # ── Tabela ─────────────────────────────────────────────
    colunas = [c for c in df_tab.columns if c != 'Transcrição']
    thead = "".join(f"<th>{c}</th>" for c in colunas)
    tbody = ""
    for _, row in df_tab.iterrows():
        cells = "".join(f"<td>{row.get(c, '')}</td>" for c in colunas)
        tbody += f"<tr>{cells}</tr>\n"

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head><meta charset="utf-8"><title>Relatório – {agente}</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 24px; color: #222; }}
  h1 {{ font-size: 20px; margin-bottom: 4px; }}
  h2 {{ font-size: 15px; margin: 20px 0 6px; }}
  h3 {{ font-size: 13px; margin: 8px 0 6px; }}
  p.sub {{ color: #666; font-size: 13px; margin-top: 0; }}
  .kpi-row {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 14px 0; }}
  .kpi {{ background: #f0f4ff; border-radius: 6px; padding: 8px 14px; min-width: 110px; }}
  .kpi-label {{ display: block; font-size: 11px; color: #666; }}
  .kpi-val {{ display: block; font-size: 18px; font-weight: bold; color: #1e6fb5; }}
  .charts-row {{ display: flex; flex-wrap: wrap; gap: 16px; margin: 16px 0; }}
  .chart-box {{ flex: 1; min-width: 220px; background: #f9fbff; border: 1px solid #dde4f0; border-radius: 8px; padding: 12px; }}
  .bar-chart {{ margin-top: 6px; }}
  .bar-row {{ display: flex; align-items: center; margin-bottom: 5px; gap: 6px; }}
  .bar-label {{ width: 46px; font-size: 11px; text-align: right; flex-shrink: 0; }}
  .bar-wrap {{ flex: 1; background: #e8edf5; border-radius: 3px; height: 13px; overflow: hidden; }}
  .bar-fill {{ height: 100%; border-radius: 3px; }}
  .bar-count {{ width: 26px; font-size: 11px; color: #555; flex-shrink: 0; }}
  .pontos-row {{ display: flex; flex-wrap: wrap; gap: 14px; margin: 14px 0; }}
  .pontos-box {{ flex: 1; min-width: 200px; border-radius: 8px; padding: 10px 14px; }}
  .pontos-forte {{ background: #e8f5e9; border: 1px solid #a5d6a7; }}
  .pontos-melhoria {{ background: #fff8e1; border: 1px solid #ffe082; }}
  .pontos-erro {{ background: #fce4ec; border: 1px solid #f48fb1; }}
  .pontos-box ul {{ margin: 4px 0 0; padding-left: 16px; font-size: 12px; line-height: 1.75; }}
  .pontos-box em {{ color: #888; font-size: 11px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 12px; font-size: 12px; }}
  th {{ background: #1e6fb5; color: #fff; padding: 8px 10px; text-align: left; }}
  td {{ padding: 6px 10px; border-bottom: 1px solid #e0e0e0; }}
  tr:nth-child(even) {{ background: #f7f9fc; }}
  @media print {{ body {{ margin: 10px; }} .charts-row, .pontos-row {{ page-break-inside: avoid; }} }}
</style>
</head>
<body>
<h1>Relatório de Vendedor: {agente}</h1>
<p class="sub">Período: {periodo_ini} – {periodo_fim} &middot; {len(df_tab)} ligação(ões) avaliadas</p>
{kpi_html}
{graficos_section}
{pontos_section}
<h2>&#128203; Ligações Avaliadas</h2>
<table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>
</body></html>"""


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
        # Inclui registros sem tipo (não classificados pela IA) sempre
        df_base = df_base[
            df_base['tipo_ligacao'].isin(tipo_sel) | df_base['tipo_ligacao'].isna()
        ]

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
    _lead_validos = df_av.loc[df_av['lead_score'] > 0, 'lead_score'] if not df_av.empty else pd.Series(dtype=float)
    lead_media = _lead_validos.mean() if not _lead_validos.empty else float('nan')
    _df_classificados = df_av[df_av['lead_classification'].isin(['A', 'B', 'C', 'D'])] if not df_av.empty else df_av
    pct_ab     = (
        _safe_pct(_df_classificados['lead_classification'].isin(['A', 'B']).sum(), len(_df_classificados))
        if not _df_classificados.empty else 0.0
    )

    st.markdown("### 📌 Resumo do Período")
    k1, k2, k3 = st.columns(3)
    k1.metric("Total de ligações", total)
    k2.metric("Avaliáveis",        avaliaveis)
    k3.metric("Avaliadas",         avaliadas)

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

        _df_base_dia = df_base.copy()
        _df_base_dia['data_dia'] = _df_base_dia['data_ligacao'].dt.normalize()
        df_dia = (
            _df_base_dia.groupby('data_dia')
            .agg(total=('transcricao_id', 'size'), avaliadas_dia=('avaliada', 'sum'))
            .reset_index()
            .rename(columns={'data_dia': 'data_ligacao'})
        )
        if not df_av.empty:
            _df_av_d = df_av.copy()
            _df_av_d['data_dia'] = _df_av_d['data_ligacao'].dt.normalize()
            df_av_dia = (
                _df_av_d.groupby('data_dia')['evaluation_ia']
                .mean().reset_index()
                .rename(columns={'data_dia': 'data_ligacao', 'evaluation_ia': 'nota_media'})
            )
        else:
            df_av_dia = pd.DataFrame(columns=['data_ligacao', 'nota_media'])
        df_dia = df_dia.merge(df_av_dia, on='data_ligacao', how='left')

        df_dia['nao_avaliadas'] = df_dia['total'] - df_dia['avaliadas_dia']

        fig_tempo = go.Figure()
        fig_tempo.add_trace(go.Bar(
            x=df_dia['data_ligacao'], y=df_dia['avaliadas_dia'],
            name='Avaliadas', marker_color='#00CC96', opacity=0.9,
        ))
        fig_tempo.add_trace(go.Bar(
            x=df_dia['data_ligacao'], y=df_dia['nao_avaliadas'],
            name='Não avaliadas', marker_color='#636EFA', opacity=0.55,
        ))
        if df_dia['nota_media'].notna().any():
            fig_tempo.add_trace(go.Scatter(
                x=df_dia['data_ligacao'], y=df_dia['nota_media'],
                name='Nota Média', yaxis='y2', mode='lines+markers',
                line=dict(color='#EF553B', width=2),
                marker=dict(size=6),
            ))
        fig_tempo.update_layout(
            barmode='stack',
            yaxis=dict(title='Qtd. Ligações'),
            yaxis2=dict(title='Nota Média', overlaying='y', side='right', range=[0, 100]),
            legend=dict(orientation='h', y=1.12),
            height=350, margin=dict(t=20, b=20),
        )
        st.plotly_chart(fig_tempo, use_container_width=True)

        # ── Linha 2: classificação + duração ──
        col_v2, col_v3 = st.columns(2)

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
                .groupby('tipo_ligacao')
                .agg(duracao_media=('duracao_min', 'mean'), qtd=('transcricao_id', 'count'))
                .reset_index()
                .rename(columns={'tipo_ligacao': 'Tipo', 'duracao_media': 'Duração Média (min)'})
                .sort_values('Duração Média (min)', ascending=False)
            )
            if not df_dur.empty:
                if not df_av.empty:
                    nota_tipo = (
                        df_av.dropna(subset=['tipo_ligacao', 'evaluation_ia'])
                        .groupby('tipo_ligacao')['evaluation_ia']
                        .mean().reset_index()
                        .rename(columns={'tipo_ligacao': 'Tipo', 'evaluation_ia': 'nota_media'})
                    )
                    df_dur = df_dur.merge(nota_tipo, on='Tipo', how='left')
                    df_dur['label_bar'] = df_dur.apply(
                        lambda r: f"n={int(r['qtd'])} | ⭐{r['nota_media']:.0f}"
                        if pd.notna(r.get('nota_media')) else f"n={int(r['qtd'])}",
                        axis=1,
                    )
                else:
                    df_dur['label_bar'] = df_dur['qtd'].apply(lambda x: f"n={int(x)}")
                fig_dur = px.bar(
                    df_dur, x='Tipo', y='Duração Média (min)',
                    text='label_bar',
                    color_discrete_sequence=['#AB63FA'],
                )
                fig_dur.update_traces(textposition='outside')
                fig_dur.update_layout(height=270, margin=dict(t=10, b=10), showlegend=False)
                st.plotly_chart(fig_dur, use_container_width=True)
            else:
                st.info("Sem dados de duração.")

        # ── Linha 3: produtos ────────────────────
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
                )
                .reset_index()
            )
            # lead_score médio excluindo 0/NA
            _lead_por_agente = (
                df_av[df_av['lead_score'] > 0]
                .groupby('agente')['lead_score'].mean()
                .reset_index(name='lead_score_medio')
            )
            df_rank = df_rank.merge(_lead_por_agente, on='agente', how='left')
            df_rank['lead_score_medio'] = df_rank['lead_score_medio'].fillna(0)
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

            # Filtro de quantidade mínima de ligações
            max_lig = int(df_rank['ligacoes'].max())
            min_lig = st.slider(
                "Mínimo de ligações avaliadas:", 1, max(max_lig, 1), 1, key="min_lig_rank"
            )
            df_rank = df_rank[df_rank['ligacoes'] >= min_lig].reset_index(drop=True)
            df_rank.index += 1

            if df_rank.empty:
                st.info("Nenhum agente com o mínimo de ligações selecionado.")
                st.stop()

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
            df_exibir['Nota Média']       = df_exibir['Nota Média'].round(1).fillna(0)
            df_exibir['Nota Mín']         = df_exibir['Nota Mín'].round(0).fillna(0).astype(int)
            df_exibir['Nota Máx']         = df_exibir['Nota Máx'].round(0).fillna(0).astype(int)
            df_exibir['Score Lead Médio'] = df_exibir['Score Lead Médio'].round(1).fillna(0)
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

            # Radar SPIN por agente (todos)
            st.markdown("#### 🕸️ Radar SPIN por Agente")
            top5_ag = df_av['agente'].value_counts().index.tolist()
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
            _lead_ag_validos = df_ag.loc[df_ag['lead_score'] > 0, 'lead_score']
            lead_ag     = _lead_ag_validos.mean() if not _lead_ag_validos.empty else 0
            _df_ag_class = df_ag[df_ag['lead_classification'].isin(['A', 'B', 'C', 'D'])]
            pct_ab_ag   = _df_ag_class['lead_classification'].isin(['A', 'B']).mean() * 100 if not _df_ag_class.empty else 0
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

            # Evolução da nota (full width)
            st.markdown("#### 📈 Evolução da Nota ao Longo do Tempo")
            _df_ag_d = df_ag.copy()
            _df_ag_d['data_dia'] = _df_ag_d['data_ligacao'].dt.normalize()
            df_ag_dia = (
                _df_ag_d.groupby('data_dia')['evaluation_ia']
                .mean().reset_index()
                .rename(columns={'data_dia': 'data_ligacao', 'evaluation_ia': 'Nota'})
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
            _cols_tab = [
                'transcricao_id', 'data_ligacao', 'nome_lead',
                'evaluation_ia', 'lead_score', 'lead_classification',
                'etapa', 'transcricao',
            ]
            # campos adicionais
            extras = []
            if 'motivo_nao_avaliacao' in df_ag.columns:
                extras.append('motivo_nao_avaliacao')
            if 'observacao_whatsapp' in df_ag.columns:
                extras.append('observacao_whatsapp')
            if 'confianca_classificacao' in df_ag.columns:
                extras.append('confianca_classificacao')
            if extras:
                _cols_tab = _cols_tab[:6] + extras + _cols_tab[6:]
            # tipo_classificacao_ia vem do JSON; fallback para tipo_ligacao se ausente
            if 'tipo_classificacao_ia' in df_ag.columns:
                _cols_tab.insert(6, 'tipo_classificacao_ia')
            else:
                _cols_tab.insert(6, 'tipo_ligacao')
            df_ag_tab = df_ag[_cols_tab].copy()
            df_ag_tab['data_ligacao'] = df_ag['data_ligacao'].dt.strftime('%d/%m/%Y')
            df_ag_tab['Nota'] = df_ag['evaluation_ia'].apply(
                lambda x: f"{_cor_nota(x)} {int(x)}" if pd.notna(x) else "—"
            )
            df_ag_tab['transcricao'] = df_ag['transcricao'].fillna('').astype(str)
            _rename_map = {
                'transcricao_id':           'ID',
                'data_ligacao':             'Data',
                'nome_lead':                'Lead',
                'lead_score':               'Score Lead',
                'lead_classification':      'Classificação',
                'motivo_nao_avaliacao':     'Motivo da não avaliação',
                'observacao_whatsapp':      'Obs. WhatsApp',
                'tipo_classificacao_ia':    'Tipo IA',
                'tipo_ligacao':             'Tipo IA',
                'confianca_classificacao':  'Confiança IA',
                'etapa':                    'Etapa',
                'transcricao':              'Transcrição',
            }
            df_ag_tab = df_ag_tab.rename(columns=_rename_map).drop(columns=['evaluation_ia'])

            # ── Exportar (antes da tabela) ───────────────
            col_pdf, col_csv, _ = st.columns([1, 1, 3])
            with col_pdf:
                _kpis_rel = {
                    'Ligações Avaliadas': len(df_ag),
                    'Nota Média':  f"{nota_ag:.1f}" if pd.notna(nota_ag) else '—',
                    'Score Lead':  f"{lead_ag:.1f}" if pd.notna(lead_ag) else '—',
                    'Leads A+B':   f"{pct_ab_ag:.1f}%",
                    'Ranking':     f"#{pos_ranking}/{len(agentes_ord)}",
                    'Média Time':  f"{media_time:.1f}" if pd.notna(media_time) else '—',
                }
                html_rel = _gerar_html_relatorio(
                    agente_rel,
                    df_ag_tab,
                    d_ini.strftime('%d/%m/%Y'),
                    (d_fim - pd.Timedelta(days=1)).strftime('%d/%m/%Y'),
                    kpis=_kpis_rel,
                    df_raw=df_ag,
                )
                st.download_button(
                    label="📄 Baixar PDF (HTML)",
                    data=html_rel.encode('utf-8'),
                    file_name=(
                        f"relatorio_{agente_rel.replace(' ', '_')}"
                        f"_{datetime.now().strftime('%Y%m%d')}.html"
                    ),
                    mime="text/html",
                    help="Abra no navegador e use Ctrl+P → Salvar como PDF",
                )
            with col_csv:
                st.download_button(
                    label="⬇️ Exportar CSV",
                    data=df_ag.to_csv(index=False).encode('utf-8'),
                    file_name=(
                        f"relatorio_{agente_rel.replace(' ', '_')}"
                        f"_{datetime.now().strftime('%Y%m%d')}.csv"
                    ),
                    mime="text/csv",
                )

            st.dataframe(
                df_ag_tab.set_index('ID'),
                use_container_width=True,
                height=320,
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
            st.divider()
