import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from collections import Counter
import json
from datetime import datetime
from utils.sql_loader import carregar_dados

TIMEZONE = 'America/Sao_Paulo'

_CORES_CLASS = {
    'A': '#00CC96', 'B': '#636EFA',
    'C': '#FFA15A', 'D': '#EF553B', '—': '#AAAAAA',
}

# Categorias de avaliação do vendedor (chave JSON → (label, max_pontos))
_CATS_VENDEDOR = {
    'rapport_conexao_0_10':                ('Rapport e Conexão',              10),
    'qualificacao_leitura_contexto_0_15':  ('Qualificação / Leitura',        15),
    'construcao_valor_diferenciacao_0_30': ('Construção de Valor',           30),
    'persuasao_etica_0_10':               ('Persuasão Ética',                10),
    'objecoes_0_10':                       ('Tratamento de Objeções',        10),
    'conducao_fechamento_0_20':            ('Condução ao Fechamento',        20),
    'clareza_compliance_0_5':              ('Clareza / Compliance',           5),
}

# Retrocompatibilidade: mapeamento das chaves antigas → novas
_CATS_LEGACY = {
    'abertura_rapport_0_10':           'rapport_conexao_0_10',
    'investigacao_spin_0_30':          'qualificacao_leitura_contexto_0_15',
    'valor_capacidade_0_20':           'construcao_valor_diferenciacao_0_30',
    'compromisso_prox_passos_0_15':    'conducao_fechamento_0_20',
    'clareza_compliance_whatsapp_0_5': 'clareza_compliance_0_5',
}

# ──────────────────────────────────────────────
# CACHE / CARREGAMENTO
# ──────────────────────────────────────────────
@st.cache_data(ttl=21600, show_spinner=False)
def _carregar_dados() -> pd.DataFrame:
    df = carregar_dados("consultas/analise_chats/analise_chats.sql")
    if df is None or df.empty:
        return pd.DataFrame()

    # ── Datetime ─────────────────────────────────────────────────────────────
    df["data_chat"] = pd.to_datetime(df["data_chat"], errors='coerce')
    try:
        df["data_chat"] = df["data_chat"].dt.tz_localize(TIMEZONE, ambiguous='infer')
    except Exception:
        pass  # já tem tz ou coluna nula

    # ── Booleanos ────────────────────────────────────────────────────────────
    df['avaliada']  = df.get('avaliada',  pd.Series(0, index=df.index)).astype(bool)
    df['avaliavel'] = df.get('avaliavel', pd.Series(1, index=df.index)).astype(bool)

    # ── Numéricos ────────────────────────────────────────────────────────────
    df['evaluation_ia'] = pd.to_numeric(df.get('evaluation_ia'), errors='coerce')
    df['lead_score']    = pd.to_numeric(df.get('lead_score'),    errors='coerce')

    # ── Tipo / triagem ───────────────────────────────────────────────────────
    df['tipo_ligacao'] = df.get('classificacao_triagem', pd.Series(dtype=str)).fillna('Sem triagem')

    # ── Motivo de não avaliação ──────────────────────────────────────────────
    df['motivo_nao_avaliacao'] = df.get('motivo_triagem', pd.Series(dtype=str)).fillna('')

    # ── Parse do JSON de avaliação ───────────────────────────────────────────
    def _parse_json(v):
        if not v or (isinstance(v, float) and pd.isna(v)):
            return {}
        txt = str(v).strip()
        if not txt:
            return {}
        try:
            return json.loads(txt)
        except (TypeError, ValueError):
            return {}

    df['parsed_json'] = df['ai_evaluation'].apply(_parse_json)

    # ── Lead classification ──────────────────────────────────────────────────
    def _extract_lead_class(j):
        if isinstance(j, dict):
            al = j.get('avaliacao_lead', {})
            if isinstance(al, dict):
                c = al.get('classificacao', '—')
                return c if c in ('A', 'B', 'C', 'D') else '—'
            return j.get('lead_classificacao', '—')
        return '—'

    df['lead_classification'] = df['parsed_json'].apply(_extract_lead_class).fillna('—')
    df.loc[df['lead_classification'].str.strip() == '', 'lead_classification'] = '—'

    # ── Pontos fortes, melhorias, erro mais caro ─────────────────────────────
    def _join_list(lst, field='ponto'):
        if not isinstance(lst, list):
            return ''
        parts = []
        for item in lst:
            if isinstance(item, dict):
                parts.append(item.get(field, item.get('melhoria', item.get('ponto', ''))))
            elif isinstance(item, str) and item.strip():
                parts.append(item.strip())
        return '; '.join(p for p in parts if p)

    df['strengths'] = df['parsed_json'].apply(
        lambda j: _join_list(j.get('avaliacao_vendedor', {}).get('pontos_fortes', []), 'ponto')
        if isinstance(j, dict) else ''
    )
    df['improvements'] = df['parsed_json'].apply(
        lambda j: _join_list(j.get('avaliacao_vendedor', {}).get('melhorias', []), 'melhoria')
        if isinstance(j, dict) else ''
    )
    df['most_expensive_mistake'] = df['parsed_json'].apply(
        lambda j: (
            j.get('avaliacao_vendedor', {}).get('erro_mais_caro', {}).get('descricao', '')
            if isinstance(j.get('avaliacao_vendedor', {}).get('erro_mais_caro'), dict)
            else str(j.get('avaliacao_vendedor', {}).get('erro_mais_caro', ''))
        ) if isinstance(j, dict) else ''
    )

    df['iqh'] = df['parsed_json'].apply(
        lambda j: pd.to_numeric(j.get('qualidade_entrada', {}).get('iqh_0_100'), errors='coerce') if isinstance(j, dict) else float('nan')
    )
    df['alertas'] = df['parsed_json'].apply(
        lambda j: _join_list(j.get('avaliacao_vendedor', {}).get('alertas', [])) if isinstance(j, dict) else ''
    )
    df['dores_principais'] = df['parsed_json'].apply(
        lambda j: _join_list(j.get('extracao', {}).get('dores_principais', [])) if isinstance(j, dict) else ''
    )
    df['restricoes'] = df['parsed_json'].apply(
        lambda j: _join_list(j.get('extracao', {}).get('restricoes', [])) if isinstance(j, dict) else ''
    )
    df['concurso_area'] = df['parsed_json'].apply(
        lambda j: str(j.get('extracao', {}).get('concurso_area', '')).strip() if isinstance(j, dict) else ''
    )
    df['perguntas_faltantes'] = df['parsed_json'].apply(
        lambda j: _join_list(
            j.get('avaliacao_lead', {}).get('perguntas_que_faltaram', []) or
            j.get('avaliacao_lead', {}).get('perguntas_faltantes', [])
        ) if isinstance(j, dict) else ''
    )

    # ── Disclaimers (resumos executivos das avaliações) ────────────────────
    def _get_disclaimer(j, field):
        if not isinstance(j, dict):
            return ''
        val = j.get(field, '')
        return str(val).strip() if val and str(val).lower() not in ('none', 'null', 'não mencionado') else ''

    # Tentar primeiro da coluna do banco (se existir), fallback pro JSON
    if 'vendedor_disclaimer' not in df.columns:
        df['vendedor_disclaimer'] = ''
    if 'lead_disclaimer' not in df.columns:
        df['lead_disclaimer'] = ''

    # Preencher vazios com dados do JSON
    mask_vd = df['vendedor_disclaimer'].fillna('').str.strip() == ''
    df.loc[mask_vd, 'vendedor_disclaimer'] = df.loc[mask_vd, 'parsed_json'].apply(
        lambda j: _get_disclaimer(j, 'vendedor_disclaimer')
    )
    mask_ld = df['lead_disclaimer'].fillna('').str.strip() == ''
    df.loc[mask_ld, 'lead_disclaimer'] = df.loc[mask_ld, 'parsed_json'].apply(
        lambda j: _get_disclaimer(j, 'lead_disclaimer')
    )

    # ── Notas por categoria (normalizadas 0-100%) ────────────────────────────
    def _extract_notas_pct(j):
        if not isinstance(j, dict):
            return {}
        notas = j.get('avaliacao_vendedor', {}).get('notas_por_categoria', {})
        if not isinstance(notas, dict):
            return {}
        result = {}
        # Tentar chaves novas primeiro
        for key, (_, max_val) in _CATS_VENDEDOR.items():
            val = notas.get(key)
            if val is not None:
                try:
                    result[key] = float(val) / max_val * 100
                except (TypeError, ValueError):
                    pass
        # Fallback: mapear chaves antigas pra novas (retrocompatibilidade)
        if not result:
            for old_key, new_key in _CATS_LEGACY.items():
                val = notas.get(old_key)
                if val is not None and new_key in _CATS_VENDEDOR:
                    _, max_val = _CATS_VENDEDOR[new_key]
                    try:
                        result[new_key] = float(val) / max_val * 100
                    except (TypeError, ValueError):
                        pass
            # Chaves que não mudaram (persuasao, objecoes)
            for key in ('persuasao_etica_0_10', 'objecoes_0_10'):
                if key not in result:
                    val = notas.get(key)
                    if val is not None and key in _CATS_VENDEDOR:
                        _, max_val = _CATS_VENDEDOR[key]
                        try:
                            result[key] = float(val) / max_val * 100
                        except (TypeError, ValueError):
                            pass
        return result

    df['notas_pct'] = df['parsed_json'].apply(_extract_notas_pct)

    return df


# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────
def _safe_pct(num: int, den: int) -> float:
    return (num / den * 100) if den > 0 else 0.0


def _cor_nota(nota) -> str:
    try:
        n = float(nota)
    except (TypeError, ValueError):
        return ""
    if n >= 75: return "🟢"
    if n >= 50: return "🟡"
    return "🔴"


def _top_items(series: pd.Series, n: int = 10) -> list:
    """Retorna top-n itens de colunas com texto semicolon-separated."""
    itens = []
    for v in series.fillna(''):
        itens.extend([t.strip() for t in str(v).split(';') if t.strip()])
    contagem: dict = {}
    for item in itens:
        if item:
            contagem[item] = contagem.get(item, 0) + 1
    return sorted(contagem.items(), key=lambda x: -x[1])[:n]


def _gerar_html_relatorio(
    agente: str,
    df_tab: pd.DataFrame,
    periodo_ini: str,
    periodo_fim: str,
    kpis: dict | None = None,
    df_raw: pd.DataFrame | None = None,
) -> str:
    """Gera HTML estilizado para download. Abrir no browser → Ctrl+P → Salvar como PDF."""
    import collections

    kpi_html = ""
    if kpis:
        kpi_items = "".join(
            f'<div class="kpi"><span class="kpi-label">{k}</span>'
            f'<span class="kpi-val">{v}</span></div>'
            for k, v in kpis.items()
        )
        kpi_html = f'<div class="kpi-row">{kpi_items}</div>'

    graficos_html = ""
    pontos_html   = ""

    if df_raw is not None and not df_raw.empty:
        def _barra(label, n, total, cor):
            pct = round(n / total * 100) if total > 0 else 0
            return (
                f'<div class="bar-row"><span class="bar-label">{label}</span>'
                f'<div class="bar-wrap"><div class="bar-fill" style="width:{pct}%;background:{cor}"></div></div>'
                f'<span class="bar-count">{n}</span></div>'
            )

        notas = df_raw['evaluation_ia'].dropna()
        if not notas.empty:
            faixas = [
                ('0–20', 0, 20, '#dc3545'), ('21–40', 21, 40, '#fd7e14'),
                ('41–60', 41, 60, '#ffc107'), ('61–80', 61, 80, '#28a745'),
                ('81–100', 81, 100, '#007bff'),
            ]
            bars = "".join(
                _barra(lbl, int(((notas >= lo) & (notas <= hi)).sum()), len(notas), cor)
                for lbl, lo, hi, cor in faixas
            )
            graficos_html += (
                f'<div class="chart-box"><h3>&#128202; Distribuição de Notas</h3>'
                f'<div class="bar-chart">{bars}</div></div>'
            )

        graficos_section = f'<div class="charts-row">{graficos_html}</div>' if graficos_html else ""

        if 'strengths' in df_raw.columns:
            all_s = [s.strip() for v in df_raw['strengths'].dropna()
                     for s in str(v).split(';') if s.strip()]
            if all_s:
                top_s = collections.Counter(all_s).most_common(5)
                items = "".join(f"<li>{t} <em>({c}x)</em></li>" for t, c in top_s)
                pontos_html += (
                    f'<div class="pontos-box pontos-forte">'
                    f'<h3>&#9989; Pontos Fortes (Top 5)</h3><ul>{items}</ul></div>'
                )

        if 'improvements' in df_raw.columns:
            all_i = [s.strip() for v in df_raw['improvements'].dropna()
                     for s in str(v).split(';') if s.strip()]
            if all_i:
                top_i = collections.Counter(all_i).most_common(5)
                items = "".join(f"<li>{t} <em>({c}x)</em></li>" for t, c in top_i)
                pontos_html += (
                    f'<div class="pontos-box pontos-melhoria">'
                    f'<h3>&#9888;&#65039; Melhorias (Top 5)</h3><ul>{items}</ul></div>'
                )

        if 'most_expensive_mistake' in df_raw.columns:
            erros = df_raw['most_expensive_mistake'].dropna()
            erros = erros[erros.str.strip() != '']
            if not erros.empty:
                top_e = erros.value_counts().head(5)
                items = "".join(f"<li>{t} <em>({c}x)</em></li>" for t, c in top_e.items())
                pontos_html += (
                    f'<div class="pontos-box pontos-erro">'
                    f'<h3>&#128184; Erros Mais Caros (Top 5)</h3><ul>{items}</ul></div>'
                )

        pontos_section = f'<div class="pontos-row">{pontos_html}</div>' if pontos_html else ""
    else:
        graficos_section = ""
        pontos_section   = ""

    colunas = [c for c in df_tab.columns if c != 'Transcrição']
    thead = "".join(f"<th>{c}</th>" for c in colunas)
    tbody = ""
    for _, row in df_tab.iterrows():
        cells = "".join(f"<td>{row.get(c, '')}</td>" for c in colunas)
        tbody += f"<tr>{cells}</tr>\n"

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head><meta charset="utf-8"><title>Relatório Chat – {agente}</title>
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
<h1>Relatório de Vendedor (Chat): {agente}</h1>
<p class="sub">Período: {periodo_ini} – {periodo_fim} &middot; {len(df_tab)} chat(s) avaliado(s)</p>
{kpi_html}
{graficos_section}
{pontos_section}
<h2>&#128203; Chats Avaliados</h2>
<table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>
</body></html>"""

# ──────────────────────────────────────────────
# PÁGINA PRINCIPAL
# ──────────────────────────────────────────────
def run_page():
    st.title("� Análise de Desempenho — Chats Octadesk")
    st.caption("Painel comercial · Conversas escritas avaliadas via IA (WhatsApp / Octadesk)")

    with st.spinner("Carregando dados..."):
        df_all = _carregar_dados()

    if df_all.empty:
        st.warning("⚠️ Nenhum dado encontrado. Verifique a conexão com o banco ou se a tabela existe.")
        st.stop()

    # ── Filtros sidebar ───────────────────────────────────────────────────────
    st.sidebar.header("🔍 Filtros")

    empresas = sorted([str(e) for e in df_all["empresa"].dropna().unique() if str(e).strip()])
    empresa  = st.sidebar.radio("Empresa:", empresas, key="anl_chat_empresa")

    hoje   = pd.Timestamp.now(tz=TIMEZONE).date()
    periodo = st.sidebar.date_input(
        "Período (Data Chat):",
        [hoje - pd.Timedelta(days=30), hoje],
        key="anl_chat_periodo",
    )
    try:
        d_ini = pd.Timestamp(periodo[0], tz=TIMEZONE)
        d_fim = pd.Timestamp(periodo[1], tz=TIMEZONE) + pd.Timedelta(days=1)
    except (IndexError, TypeError):
        st.sidebar.warning("Selecione um período completo.")
        st.stop()

    df_base = df_all[
        (df_all["empresa"] == empresa) &
        (df_all["data_chat"] >= d_ini) &
        (df_all["data_chat"] < d_fim)
    ].copy()

    agentes_disp = sorted([a for a in df_base['agente'].dropna().unique() if str(a).strip()])
    agente_sel   = st.sidebar.multiselect(
        "Agente:", agentes_disp, default=agentes_disp, key="anl_chat_agente"
    )
    if agente_sel:
        df_base = df_base[df_base['agente'].isin(agente_sel)]

    if 'octa_group' in df_base.columns:
        grupos_disp = sorted([str(g) for g in df_base['octa_group'].dropna().unique() if str(g).strip()])
        if grupos_disp:
            grupo_sel = st.sidebar.multiselect(
                "Grupo / Unidade:", grupos_disp, default=grupos_disp, key="anl_chat_grupo"
            )
            if grupo_sel:
                df_base = df_base[df_base['octa_group'].astype(str).isin(grupo_sel)]

    tipos_disp = sorted([t for t in df_base['tipo_ligacao'].dropna().unique() if str(t).strip()])
    tipo_sel   = st.sidebar.multiselect(
        "Tipo de Atendimento:", tipos_disp, default=tipos_disp, key="anl_chat_tipo"
    )
    if tipo_sel:
        df_base = df_base[df_base['tipo_ligacao'].isin(tipo_sel) | df_base['tipo_ligacao'].isna()]

    if df_base.empty:
        st.warning("Nenhum chat encontrado para os filtros selecionados.")
        st.stop()

    df_av = df_base[df_base['avaliada']].copy()

    # ════════════════════════════════════════════
    # KPIs GLOBAIS
    # ════════════════════════════════════════════
    total      = len(df_base)
    avaliaveis = int(df_base['avaliavel'].sum())
    avaliadas  = int(df_base['avaliada'].sum())
    taxa_aval  = _safe_pct(avaliadas, avaliaveis)
    nota_media = df_av['evaluation_ia'].mean() if not df_av.empty else float('nan')
    _lead_val  = df_av.loc[df_av['lead_score'] > 0, 'lead_score'] if not df_av.empty else pd.Series(dtype=float)
    lead_media = _lead_val.mean() if not _lead_val.empty else float('nan')
    _df_cls    = df_av[df_av['lead_classification'].isin(['A', 'B', 'C', 'D'])] if not df_av.empty else df_av
    pct_ab     = (
        _safe_pct(_df_cls['lead_classification'].isin(['A', 'B']).sum(), len(_df_cls))
        if not _df_cls.empty else 0.0
    )

    st.markdown("### 📌 Resumo do Período")
    k1, k2, k3 = st.columns(3)
    k1.metric("Total de Chats",        total)
    k2.metric("Avaliáveis",            avaliaveis)
    k3.metric("Avaliados via IA",      f"{avaliadas} ({taxa_aval:.1f}%)")
    k4, k5, k6 = st.columns(3)
    k4.metric("Nota Vendedor (Média)", f"{nota_media:.1f}" if pd.notna(nota_media) else "—")
    k5.metric("Score Lead (Média)",    f"{lead_media:.1f}" if pd.notna(lead_media) else "—")
    iqh_medio = df_av['iqh'].mean() if not df_av.empty else float('nan')
    k6.metric("IQH (Qualidade)", f"{iqh_medio:.1f}" if pd.notna(iqh_medio) else "—")

    st.divider()

    # ════════════════════════════════════════════
    # ABAS
    # ════════════════════════════════════════════
    tab1, tab_inteligencia, tab2, tab3, tab4, tab5 = st.tabs([
        "📈 Visão Geral",
        "🧠 Inteligência Comercial",
        "🏆 Ranking de Agentes",
        "🔬 Análise de Competências",
        "👤 Relatório Individual",
        "🔍 Detalhes Qualitativos",
    ])

    # ────────────────────────────────────────────
    # TAB 1 — VISÃO GERAL
    # ────────────────────────────────────────────
    with tab1:
        st.markdown("#### 📅 Evolução Diária de Avaliações")
        _db = df_base.copy()
        _db['data_dia'] = _db['data_chat'].dt.normalize()
        df_dia = (
            _db.groupby('data_dia')
            .agg(total=('chat_id', 'size'), avaliadas_dia=('avaliada', 'sum'))
            .reset_index().rename(columns={'data_dia': 'data_chat'})
        )
        if not df_av.empty:
            _da = df_av.copy()
            _da['data_dia'] = _da['data_chat'].dt.normalize()
            df_av_dia = (
                _da.groupby('data_dia')['evaluation_ia']
                .mean().reset_index()
                .rename(columns={'data_dia': 'data_chat', 'evaluation_ia': 'nota_media'})
            )
        else:
            df_av_dia = pd.DataFrame(columns=['data_chat', 'nota_media'])

        df_dia = df_dia.merge(df_av_dia, on='data_chat', how='left')
        df_dia['nao_avaliadas'] = df_dia['total'] - df_dia['avaliadas_dia']

        fig_tempo = go.Figure()
        fig_tempo.add_trace(go.Bar(
            x=df_dia['data_chat'], y=df_dia['avaliadas_dia'],
            name='Avaliadas', marker_color='#00CC96', opacity=0.9,
        ))
        fig_tempo.add_trace(go.Bar(
            x=df_dia['data_chat'], y=df_dia['nao_avaliadas'],
            name='Não avaliadas', marker_color='#636EFA', opacity=0.55,
        ))
        if df_dia['nota_media'].notna().any():
            fig_tempo.add_trace(go.Scatter(
                x=df_dia['data_chat'], y=df_dia['nota_media'],
                name='Nota Média do Vendedor', yaxis='y2', mode='lines+markers',
                line=dict(color='#EF553B', width=2), marker=dict(size=6),
            ))
        fig_tempo.update_layout(
            barmode='stack',
            yaxis=dict(title='Qtd. Chats'),
            yaxis2=dict(title='Nota Média', overlaying='y', side='right', range=[0, 100]),
            legend=dict(orientation='h', y=1.12),
            height=380, margin=dict(t=20, b=20),
        )
        st.plotly_chart(fig_tempo, use_container_width=True)

        col_v1, col_v2 = st.columns(2)
        with col_v1:
            st.markdown("#### 🏷️ Classificação dos Leads")
            if not df_av.empty:
                df_cl = df_av['lead_classification'].value_counts().reset_index()
                df_cl.columns = ['Classificação', 'Qtd']
                fig_pie = px.pie(
                    df_cl, names='Classificação', values='Qtd',
                    color='Classificação', color_discrete_map=_CORES_CLASS, hole=0.45,
                )
                fig_pie.update_traces(textinfo='percent+label')
                fig_pie.update_layout(height=300, margin=dict(t=10, b=10))
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("Sem avaliações no período.")

        with col_v2:
            st.markdown("#### 💬 Triagem por Tipo de Atendimento")
            if not df_base.empty:
                df_triagem = df_base['tipo_ligacao'].value_counts().reset_index()
                df_triagem.columns = ['Tipo', 'Qtd']
                fig_tria = px.pie(
                    df_triagem, names='Tipo', values='Qtd',
                    hole=0.45, color_discrete_sequence=px.colors.qualitative.Pastel,
                )
                fig_tria.update_traces(textinfo='percent+label')
                fig_tria.update_layout(height=300, margin=dict(t=10, b=10))
                st.plotly_chart(fig_tria, use_container_width=True)

        col_v3, col_v4 = st.columns(2)
        with col_v3:
            st.markdown("#### 📡 Chats por Origem (Octadesk)")
            if 'octa_origin' in df_base.columns:
                df_orig = (
                    df_base['octa_origin'].fillna('(sem origem)')
                    .value_counts().reset_index()
                )
                df_orig.columns = ['Origem', 'Qtd']
                fig_orig = px.bar(
                    df_orig.head(10), x='Qtd', y='Origem', orientation='h',
                    color_discrete_sequence=['#AB63FA'],
                )
                fig_orig.update_layout(
                    height=280, margin=dict(t=10, b=10),
                    yaxis=dict(categoryorder='total ascending'),
                )
                st.plotly_chart(fig_orig, use_container_width=True)
            else:
                st.info("Campo octa_origin não disponível.")

        with col_v4:
            st.markdown("#### 🎓 Produtos Mais Recomendados")
            if not df_av.empty and 'produto_recomendado' in df_av.columns:
                prods = df_av['produto_recomendado'].dropna()
                prods = prods[prods.str.strip() != '']
                if not prods.empty:
                    df_prod = prods.value_counts().head(8).reset_index()
                    df_prod.columns = ['Produto', 'Qtd']
                    fig_prod = px.bar(
                        df_prod, x='Qtd', y='Produto', orientation='h',
                        color_discrete_sequence=['#19D3F3'],
                    )
                    fig_prod.update_layout(
                        height=280, margin=dict(t=10, b=10),
                        yaxis=dict(categoryorder='total ascending'),
                    )
                    st.plotly_chart(fig_prod, use_container_width=True)
                else:
                    st.info("Sem produtos recomendados extraídos.")
            else:
                st.info("Sem dados de produto.")

        st.divider()

        # ════════════════════════════════════════════
        # ALERTAS DE RISCO / OPORTUNIDADES PERDIDAS
        # ════════════════════════════════════════════
        if not df_av.empty:
            alertas_df = df_av[(df_av['alertas'].str.strip() != '') & (~df_av['alertas'].str.lower().isin(['não mencionado', 'não houve', 'nenhum']))]
            op_perdidas_df = df_av[(df_av['lead_classification'].isin(['A', 'B'])) & (df_av['evaluation_ia'] < 50)]

            if not alertas_df.empty or not op_perdidas_df.empty:
                st.error("### 🚨 Painel de Atenção: Alertas e Oportunidades Perdidas")
                cols_alerta = st.columns(2)
                
                with cols_alerta[0]:
                    if not op_perdidas_df.empty:
                        st.markdown(f"**📉 Oportunidades em Risco ({len(op_perdidas_df)} chats):**")
                        st.caption("Leads Quentes (A ou B) mal atendidos (Nota < 50)")
                        for _, row in op_perdidas_df.sort_values(by='evaluation_ia').head(5).iterrows():
                            agente = row.get('agente', 'Desconhecido')
                            chat_id = row.get('chat_id', '')
                            lead_c = row.get('lead_classification', '-')
                            nota_v = row.get('evaluation_ia', 0)
                            vd_disc = str(row.get('vendedor_disclaimer', '')).strip()
                            st.write(f"- **{agente}** atendeu Lead {lead_c} (Nota: {nota_v:.0f}) - Chat `{chat_id}`")
                            if vd_disc and vd_disc.lower() not in ('nan', 'none', ''):
                                st.caption(f"  _{vd_disc}_")
                        if len(op_perdidas_df) > 5:
                            st.caption(f"+ {len(op_perdidas_df)-5} outros chats críticos...")
                    else:
                        st.success("✅ Nenhuma oportunidade crítica perdida (Leads A/B com Vendedor < 50).")

                with cols_alerta[1]:
                    if not alertas_df.empty:
                        st.markdown(f"**⚠️ Risco de Compliance ({len(alertas_df)} chats):**")
                        st.caption("Garantia irreal, quebra de regras, desrespeito, etc.")
                        for _, row in alertas_df.head(5).iterrows():
                            agente = row.get('agente', 'Desconhecido')
                            chat_id = row.get('chat_id', '')
                            alts = set([a.strip() for a in row['alertas'].split(';') if a.strip()])
                            for alt in list(alts)[:2]:
                                st.write(f"- **{agente}**: {alt} *(chat `{chat_id}`)*")
                        if len(alertas_df) > 5:
                            st.caption(f"+ {len(alertas_df)-5} outros chats com alertas...")
                    else:
                        st.success("✅ Nenhum alerta de compliance no período.")

    # ────────────────────────────────────────────
    # TAB INTELIGÊNCIA COMERCIAL
    # ────────────────────────────────────────────
    with tab_inteligencia:
        if df_av.empty:
            st.info("Sem dados para análise de Inteligência Comercial no período.")
        else:
            col_i1, col_i2 = st.columns(2)
            
            with col_i1:
                st.markdown("#### 🎯 Concursos Mais Procurados")
                concursos = df_av['concurso_area'].dropna()
                concursos = concursos[(concursos.str.strip() != '') & (~concursos.str.lower().isin(['não mencionado', 'nao mencionado', 'incerto', 'não identificada']))]
                if not concursos.empty:
                    df_conc = concursos.value_counts().head(8).reset_index()
                    df_conc.columns = ['Concurso', 'Qtd']
                    fig_conc = px.bar(
                        df_conc, x='Qtd', y='Concurso', orientation='h',
                        color_discrete_sequence=['#FF9900'],
                    )
                    fig_conc.update_layout(height=280, margin=dict(t=10, b=10), yaxis=dict(categoryorder='total ascending'))
                    st.plotly_chart(fig_conc, use_container_width=True)
                else:
                    st.info("Nenhum concurso/área explícito mapeado.")

            with col_i2:
                st.markdown("#### 🤔 Principais Dores dos Leads")
                dores = _top_items(df_av['dores_principais'], n=10)
                dores = [(d, n) for d, n in dores if str(d).lower() not in ['não mencionado', 'nao mencionado', 'não identificada', 'incerto']]
                if dores:
                    df_dores = pd.DataFrame(dores, columns=['Dor', 'Qtd'])
                    fig_dores = px.funnel(df_dores.head(8), x='Qtd', y='Dor', color_discrete_sequence=['#EF553B'])
                    fig_dores.update_layout(height=280, margin=dict(t=10, b=10))
                    st.plotly_chart(fig_dores, use_container_width=True)
                else:
                    st.info("Nenhuma dor mapeada.")

            st.divider()
            col_i3, col_i4 = st.columns(2)
            
            with col_i3:
                st.markdown("#### 🚧 Principais Restrições e Objeções")
                restricoes = _top_items(df_av['restricoes'], n=10)
                restricoes = [(r, n) for r, n in restricoes if str(r).lower() not in ['não mencionado', 'nao mencionado', 'não identificada', 'incerto', 'nenhuma']]
                if restricoes:
                    df_rest = pd.DataFrame(restricoes, columns=['Restrição', 'Qtd'])
                    fig_rest = px.bar(
                        df_rest.head(8), x='Qtd', y='Restrição', orientation='h',
                        color_discrete_sequence=['#B6E880'],
                    )
                    fig_rest.update_layout(height=280, margin=dict(t=10, b=10), yaxis=dict(categoryorder='total ascending'))
                    st.plotly_chart(fig_rest, use_container_width=True)
                else:
                    st.info("Nenhuma restrição mapeada.")
            
            with col_i4:
                st.markdown("#### ❓ Principais Perguntas que Faltaram")
                perguntas = _top_items(df_av['perguntas_faltantes'], n=10)
                perguntas = [(p, n) for p, n in perguntas if str(p).lower() not in ['não mencionado', 'nao mencionado', 'incerto', 'nenhuma']]
                if perguntas:
                    for p, n in perguntas[:6]:
                        st.write(f"- {p} `({n}x)`")
                else:
                    st.info("Não houve padrão forte de perguntas faltantes.")

    # ────────────────────────────────────────────
    # TAB 2 — RANKING DE AGENTES
    # ────────────────────────────────────────────
    with tab2:
        if df_av.empty:
            st.info("Sem avaliações para análise de agentes.")
        else:
            df_rank = (
                df_av.groupby('agente')
                .agg(
                    ligacoes=('chat_id', 'count'),
                    nota_media=('evaluation_ia', 'mean'),
                    nota_min=('evaluation_ia', 'min'),
                    nota_max=('evaluation_ia', 'max'),
                ).reset_index()
            )

            _ls = (
                df_av[df_av['lead_score'] > 0]
                .groupby('agente')['lead_score'].mean()
                .reset_index(name='lead_score_medio')
            )
            df_rank = df_rank.merge(_ls, on='agente', how='left')
            df_rank['lead_score_medio'] = df_rank['lead_score_medio'].fillna(0)

            for cls in ['A', 'B', 'C', 'D']:
                tmp = (
                    df_av[df_av['lead_classification'] == cls]
                    .groupby('agente').size().reset_index(name=f'leads_{cls}')
                )
                df_rank = df_rank.merge(tmp, on='agente', how='left')
                df_rank[f'leads_{cls}'] = df_rank[f'leads_{cls}'].fillna(0).astype(int)

            df_rank['leads_ab'] = df_rank['leads_A'] + df_rank['leads_B']
            df_rank['pct_ab']   = (df_rank['leads_ab'] / df_rank['ligacoes'] * 100).round(1)
            df_rank = df_rank.sort_values('nota_media', ascending=False).reset_index(drop=True)

            max_lig = int(df_rank['ligacoes'].max())
            _slider_max = max(max_lig, 2)
            min_lig = st.slider("Mínimo de chats avaliados:", 1, _slider_max, 1, key="min_chat_rank")
            df_rank = df_rank[df_rank['ligacoes'] >= min_lig].reset_index(drop=True)
            df_rank.index += 1

            if df_rank.empty:
                st.info("Nenhum agente enquadrado no mínimo selecionado.")
            else:
                media_time = df_av['evaluation_ia'].mean()
                melhor     = df_rank.iloc[0]

                kr1, kr2, kr3, kr4 = st.columns(4)
                kr1.metric("🥇 Melhor Vendedor",   melhor['agente'])
                kr2.metric("🎯 Nota do Melhor",    f"{melhor['nota_media']:.1f}")
                kr3.metric("📊 Média do Time",      f"{media_time:.1f}")
                kr4.metric("👥 Agentes Avaliados", len(df_rank))

                st.markdown("#### 🏅 Tabela de Desempenho (Chats)")
                df_exibir = df_rank[[
                    'agente', 'ligacoes', 'nota_media', 'nota_min', 'nota_max',
                    'lead_score_medio', 'pct_ab', 'leads_A', 'leads_B', 'leads_C', 'leads_D',
                ]].copy()
                df_exibir.columns = [
                    'Agente', 'Chats Eval.', 'Nota Vendedor', 'Mínimo', 'Máximo',
                    'Score Lead Médio', '% Leads A+B', 'A', 'B', 'C', 'D',
                ]
                df_exibir['Nota Vendedor']    = df_exibir['Nota Vendedor'].round(1)
                df_exibir['Score Lead Médio'] = df_exibir['Score Lead Médio'].round(1)
                st.dataframe(df_exibir, use_container_width=True, height=min(420, 36 * len(df_exibir) + 42))

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
                        annotation_text=f"Média: {media_time:.1f}", annotation_position='top right',
                    )
                    fig_bar.update_traces(texttemplate='%{text:.1f}', textposition='outside')
                    fig_bar.update_layout(
                        height=max(300, 44 * len(df_rank)), margin=dict(t=10, b=10), showlegend=False,
                    )
                    st.plotly_chart(fig_bar, use_container_width=True)

                with col_r2:
                    st.markdown("#### 🎯 Distribuição de Leads por Agente")
                    df_dist_m = df_rank[['agente', 'leads_A', 'leads_B', 'leads_C', 'leads_D']].melt(
                        id_vars='agente', var_name='Classe', value_name='Qtd'
                    )
                    df_dist_m['Classe'] = df_dist_m['Classe'].str.replace('leads_', '', regex=False)
                    fig_dist = px.bar(
                        df_dist_m, x='agente', y='Qtd', color='Classe',
                        barmode='stack', color_discrete_map=_CORES_CLASS,
                        labels={'agente': 'Agente'},
                    )
                    fig_dist.update_layout(height=max(300, 44 * len(df_rank)), margin=dict(t=10, b=10))
                    st.plotly_chart(fig_dist, use_container_width=True)

    # ────────────────────────────────────────────
    # TAB 3 — ANÁLISE DE COMPETÊNCIAS
    # ────────────────────────────────────────────
    with tab3:
        if df_av.empty:
            st.info("Sem avaliações para análise de competências.")
        else:
            # ── Notas médias por categoria (time) ────────────────────────────
            st.markdown("#### 📊 Notas Médias por Categoria — Time")
            cat_medias = {}
            for cat_key, (cat_label, _) in _CATS_VENDEDOR.items():
                vals = [
                    nd[cat_key]
                    for nd in df_av['notas_pct']
                    if isinstance(nd, dict) and cat_key in nd
                ]
                if vals:
                    cat_medias[cat_label] = round(sum(vals) / len(vals), 1)

            if cat_medias:
                df_cats = pd.DataFrame(list(cat_medias.items()), columns=['Categoria', 'Pct_Media'])
                df_cats = df_cats.sort_values('Pct_Media')
                fig_cats = px.bar(
                    df_cats, x='Pct_Media', y='Categoria', orientation='h',
                    text='Pct_Media', color='Pct_Media',
                    color_continuous_scale='RdYlGn', range_color=[0, 100],
                    labels={'Pct_Media': '% da nota máxima', 'Categoria': ''},
                )
                fig_cats.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
                fig_cats.update_layout(
                    height=340, margin=dict(t=10, b=10), showlegend=False,
                    xaxis=dict(range=[0, 115]),
                )
                st.plotly_chart(fig_cats, use_container_width=True)
            else:
                st.info("Nenhuma nota por categoria encontrada nos JSONs de avaliação.")

            # ── Radar de Competências por Agente (Top 7) ────────────────────────────────
            st.markdown("#### 🕸️ Radar de Competências por Agente (Top 7)")
            top_ags   = df_av['agente'].value_counts().index.tolist()[:7]
            cats_keys = list(_CATS_VENDEDOR.keys())
            cats_lbls = [_CATS_VENDEDOR[k][0] for k in cats_keys]
            fig_radar = go.Figure()
            for ag in top_ags:
                df_ag_r = df_av[df_av['agente'] == ag]
                scores = []
                for cat_key in cats_keys:
                    vals = [
                        nd[cat_key]
                        for nd in df_ag_r['notas_pct']
                        if isinstance(nd, dict) and cat_key in nd
                    ]
                    scores.append(round(sum(vals) / len(vals), 1) if vals else 50)
                fig_radar.add_trace(go.Scatterpolar(
                    r=scores + [scores[0]],
                    theta=cats_lbls + [cats_lbls[0]],
                    name=ag, fill='toself', opacity=0.55,
                ))
            fig_radar.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                height=460, margin=dict(t=30, b=30),
                legend=dict(orientation='h', y=-0.15),
            )
            st.plotly_chart(fig_radar, use_container_width=True)

            # ── Scatter Vendedor × Lead ──────────────────────────────────────
            st.markdown("#### 📈 Relação Habilidade do Vendedor × Perfil do Lead")
            fig_sc = px.scatter(
                df_av.dropna(subset=['evaluation_ia', 'lead_score']),
                x='evaluation_ia', y='lead_score',
                color='lead_classification', color_discrete_map=_CORES_CLASS,
                hover_data=['agente'],
                labels={
                    'evaluation_ia': 'Nota do Vendedor',
                    'lead_score': 'Score do Lead',
                    'lead_classification': 'Class',
                },
                opacity=0.7,
            )
            fig_sc.update_layout(height=340, margin=dict(t=10, b=10))
            st.plotly_chart(fig_sc, use_container_width=True)

            # ── Top itens ────────────────────────────────────────────────────
            col_s1, col_s2, col_s3 = st.columns(3)
            with col_s1:
                st.markdown("**✅ Top Pontos Fortes**")
                for txt, n in _top_items(df_av['strengths']):
                    st.write(f"• {txt} `({n})`")

            with col_s2:
                st.markdown("**🔧 Top Melhorias**")
                for txt, n in _top_items(df_av['improvements']):
                    st.write(f"• {txt} `({n})`")

            with col_s3:
                st.markdown("**💸 Top Erros Mais Caros**")
                erros_l = [
                    str(v).strip()
                    for v in df_av['most_expensive_mistake'].fillna('')
                    if str(v).strip()
                ]
                for txt, n in Counter(erros_l).most_common(10):
                    st.write(f"• {txt} `({n})`")

    # ────────────────────────────────────────────
    # TAB 4 — RELATÓRIO INDIVIDUAL
    # ────────────────────────────────────────────
    with tab4:
        if df_av.empty:
            st.info("Sem avaliações para gerar relatório individual.")
        else:
            agentes_ord = df_av['agente'].value_counts().index.tolist()
            agente_rel  = st.selectbox("Selecione o vendedor:", agentes_ord, key="anl_chat_agente_rel")

            df_ag      = df_av[df_av['agente'] == agente_rel].copy()
            media_time = df_av['evaluation_ia'].mean()
            nota_ag    = df_ag['evaluation_ia'].mean()
            pos_rank   = agentes_ord.index(agente_rel) + 1

            st.markdown(f"## 📋 Relatório: {agente_rel}")
            st.caption(
                f"Período: {d_ini.strftime('%d/%m/%Y')} – "
                f"{(d_fim - pd.Timedelta(days=1)).strftime('%d/%m/%Y')} · "
                f"{len(df_ag)} avaliação(ões)"
            )

            kc1, kc2, kc3 = st.columns(3)
            kc1.metric("Chats avaliados", len(df_ag))
            kc2.metric(
                "Nota média",
                f"{nota_ag:.1f}" if pd.notna(nota_ag) else "—",
                delta=f"{nota_ag - media_time:+.1f} vs time"
                if pd.notna(nota_ag) and pd.notna(media_time) else None,
            )
            kc3.metric("Ranking", f"#{pos_rank} / {len(agentes_ord)}")

            st.markdown("#### 📈 Evolução da Nota ao Longo do Tempo")
            _dag = df_ag.copy()
            _dag['data_dia'] = _dag['data_chat'].dt.normalize()
            df_ag_dia = (
                _dag.groupby('data_dia')['evaluation_ia'].mean().reset_index()
                .rename(columns={'data_dia': 'data_chat', 'evaluation_ia': 'Nota'})
            )
            fig_ev = px.line(
                df_ag_dia, x='data_chat', y='Nota', markers=True,
                color_discrete_sequence=['#00CC96'],
                labels={'data_chat': 'Data'},
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
            fig_ev.update_layout(height=270, margin=dict(t=10, b=10), yaxis=dict(range=[0, 100]))
            st.plotly_chart(fig_ev, use_container_width=True)

            col_rel1, col_rel2 = st.columns(2)
            with col_rel1:
                st.markdown("#### ✅ Principais Pontos Fortes")
                items_fortes = _top_items(df_ag['strengths'], n=8)
                if items_fortes:
                    for txt, n in items_fortes:
                        st.write(f"• {txt} `({n})`")
                else:
                    st.info("Nenhum ponto forte registrado.")

            with col_rel2:
                st.markdown("#### 🛠️ Principais Pontos de Melhoria")
                items_imp = _top_items(df_ag['improvements'], n=8)
                if items_imp:
                    for txt, n in items_imp:
                        st.write(f"• {txt} `({n})`")
                else:
                    st.info("Nenhum ponto de melhoria registrado.")

            erros_ag = [
                str(v).strip()
                for v in df_ag['most_expensive_mistake'].fillna('')
                if str(v).strip()
            ]
            if erros_ag:
                top_erro, freq_erro = Counter(erros_ag).most_common(1)[0]
                st.error(f"💸 **Erro mais frequente:** {top_erro} — citado em **{freq_erro}** chat(s)")

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

            st.markdown("#### 📋 Chats Avaliados")
            _cols_tab = [
                'chat_id', 'data_chat', 'lead_classification', 'lead_score',
                'tipo_ligacao', 'produto_recomendado', 'evaluation_ia',
                'vendedor_disclaimer', 'lead_disclaimer', 'transcript',
            ]
            cols_avail = [c for c in _cols_tab if c in df_ag.columns]
            df_ag_tab = df_ag[cols_avail].copy()

            if 'data_chat' in df_ag_tab.columns:
                df_ag_tab['data_chat'] = df_ag['data_chat'].dt.strftime('%d/%m/%Y %H:%M')
            if 'evaluation_ia' in df_ag_tab.columns:
                df_ag_tab['Nota'] = df_ag['evaluation_ia'].apply(
                    lambda x: f"{_cor_nota(x)} {int(x)}" if pd.notna(x) else "—"
                )
                df_ag_tab = df_ag_tab.drop(columns=['evaluation_ia'])

            _rename = {
                'chat_id': 'Chat ID', 'data_chat': 'Data',
                'lead_classification': 'Classe', 'lead_score': 'Score Lead',
                'tipo_ligacao': 'Tipo', 'produto_recomendado': 'Produto',
                'vendedor_disclaimer': 'Justificativa Vendedor',
                'lead_disclaimer': 'Justificativa Lead',
                'transcript': 'Transcrição',
            }
            df_ag_tab = df_ag_tab.rename(columns=_rename)

            col_pdf, col_csv, _ = st.columns([1, 1, 3])
            with col_pdf:
                _kpis_rel = {
                    'Chats Avaliados': len(df_ag),
                    'Nota Média':      f"{nota_ag:.1f}" if pd.notna(nota_ag) else '—',
                    'Ranking':         f"#{pos_rank}/{len(agentes_ord)}",
                    'Média Time':      f"{media_time:.1f}" if pd.notna(media_time) else '—',
                }
                html_rel = _gerar_html_relatorio(
                    agente_rel, df_ag_tab,
                    d_ini.strftime('%d/%m/%Y'),
                    (d_fim - pd.Timedelta(days=1)).strftime('%d/%m/%Y'),
                    kpis=_kpis_rel, df_raw=df_ag,
                )
                st.download_button(
                    label="📄 Baixar PDF (HTML)",
                    data=html_rel.encode('utf-8'),
                    file_name=(
                        f"relatorio_chat_{agente_rel.replace(' ', '_')}"
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
                        f"relatorio_chat_{agente_rel.replace(' ', '_')}"
                        f"_{datetime.now().strftime('%Y%m%d')}.csv"
                    ),
                    mime="text/csv",
                )

            colunas_tela = [c for c in df_ag_tab.columns]
            st.dataframe(
                df_ag_tab[colunas_tela],
                use_container_width=True,
                height=320,
                hide_index=True,
                column_config={
                    'Transcrição': st.column_config.TextColumn(
                        'Transcrição',
                        help='Clique na célula para ver a transcrição completa',
                        width='medium',
                    ),
                    'Justificativa Vendedor': st.column_config.TextColumn(
                        'Justificativa Vendedor',
                        help='Por que o vendedor recebeu essa nota',
                        width='large',
                    ),
                    'Justificativa Lead': st.column_config.TextColumn(
                        'Justificativa Lead',
                        help='Por que o lead recebeu essa classificação',
                        width='large',
                    ),
                },
            )

    # ────────────────────────────────────────────
    # TAB 5 — DETALHES QUALITATIVOS
    # ────────────────────────────────────────────
    with tab5:
        st.markdown("#### 🔍 Feedback Detalhado por Chat")
        if df_base.empty:
            st.info("Sem dados.")
        else:
            opcoes = []
            for _, row in df_base.iterrows():
                tipo_c = row.get('tipo_ligacao', '—')
                nota_s = f"{int(row['evaluation_ia'])}" if pd.notna(row.get('evaluation_ia')) else "—"
                lbl = (
                    f"{row['data_chat'].strftime('%d/%m %H:%M')}  |  "
                    f"{row['agente']}  |  Tipo: {tipo_c}  |  "
                    f"Nota: {nota_s}  |  {row['chat_id']}"
                )
                opcoes.append((row['chat_id'], lbl))

            sel_id = st.selectbox(
                "Selecione um chat:",
                [o[0] for o in opcoes],
                format_func=lambda x: next((o[1] for o in opcoes if o[0] == x), x),
            )

            if sel_id:
                row_data   = df_base[df_base['chat_id'] == sel_id].iloc[0]
                j          = row_data.get('parsed_json', {})
                transcript = row_data.get('transcript', '')

                st.write(f"### 📝 Chat ID: `{sel_id}`")
                
                nome_c = str(row_data.get('octa_contact_name', ''))
                tel_c = str(row_data.get('octa_contact_phone', ''))
                motivo = str(row_data.get('motivo_nao_avaliacao', ''))
                
                if nome_c != 'nan' and nome_c.strip():
                    st.caption(f"**Cliente:** {nome_c} | **Tel:** {tel_c if tel_c != 'nan' else 'Não informado'}")

                if row_data.get('avaliada') == False or not j:
                    if motivo and motivo != 'nan' and motivo.strip():
                        st.warning(f"**⚠️ Chat não avaliado comercialmente.** Motivo da Triagem: {motivo}")
                    else:
                        st.info("Chat sem avaliação da IA.")

                t_resumo, t_feed, t_trans = st.tabs(["📊 Resumo Executivo", "🤖 Feedback Completo", "💬 Transcrição"])

                # ── TAB RESUMO EXECUTIVO (disclaimers + KPIs rápidos) ─────────
                with t_resumo:
                    if isinstance(j, dict) and bool(j):
                        nota_vend = row_data.get('evaluation_ia')
                        lead_sc = row_data.get('lead_score')
                        lead_cl = row_data.get('lead_classification', '—')
                        vd_disclaimer = str(row_data.get('vendedor_disclaimer', '')).strip()
                        ld_disclaimer = str(row_data.get('lead_disclaimer', '')).strip()

                        # KPIs rápidos
                        kr1, kr2, kr3, kr4 = st.columns(4)
                        kr1.metric("Nota Vendedor", f"{_cor_nota(nota_vend)} {int(nota_vend)}" if pd.notna(nota_vend) else "—")
                        kr2.metric("Score Lead", f"{int(lead_sc)}" if pd.notna(lead_sc) else "—")
                        kr3.metric("Classe Lead", lead_cl)
                        iqh_val = j.get('qualidade_entrada', {}).get('iqh_0_100')
                        kr4.metric("IQH", f"{iqh_val}" if iqh_val else "—")

                        st.divider()

                        # Disclaimers lado a lado
                        col_dv, col_dl = st.columns(2)
                        with col_dv:
                            st.markdown("##### 🏷️ Por que essa nota pro vendedor?")
                            if vd_disclaimer and vd_disclaimer.lower() not in ('nan', 'none', ''):
                                st.info(vd_disclaimer)
                            else:
                                # Fallback: montar resumo a partir dos dados existentes
                                val_vend = j.get('avaliacao_vendedor', {})
                                erro = val_vend.get('erro_mais_caro', {})
                                erro_txt = erro.get('descricao', '') if isinstance(erro, dict) else str(erro)
                                if erro_txt and erro_txt.lower() not in ('não mencionado', ''):
                                    st.warning(f"**Erro mais caro:** {erro_txt}")
                                else:
                                    st.caption("Disclaimer não disponível para este chat.")

                        with col_dl:
                            st.markdown("##### 🏷️ Por que essa classificação pro lead?")
                            if ld_disclaimer and ld_disclaimer.lower() not in ('nan', 'none', ''):
                                st.info(ld_disclaimer)
                            else:
                                sinais_q = j.get('avaliacao_lead', {}).get('sinais_quente', [])
                                if sinais_q and isinstance(sinais_q, list):
                                    top_sinal = sinais_q[0]
                                    if isinstance(top_sinal, dict):
                                        st.success(f"**Sinal principal:** {top_sinal.get('sinal', '')}")
                                else:
                                    st.caption("Disclaimer não disponível para este chat.")

                        # Resumo da conversa
                        resumo = j.get('resumo_da_conversa', [])
                        if resumo and isinstance(resumo, list):
                            st.divider()
                            st.markdown("##### 📋 Resumo da Conversa")
                            for item in resumo:
                                if isinstance(item, str) and item.strip() and item.lower() != 'não mencionado':
                                    st.write(f"→ {item}")

                        # Mensagem pronta
                        msg_pronta = j.get('recomendacao_final', {}).get('mensagem_pronta_para_enviar_agora')
                        if msg_pronta and str(msg_pronta).lower() not in ('não mencionado', 'none', ''):
                            st.divider()
                            st.markdown("##### ✉️ Mensagem Pronta (Copy-Paste)")
                            st.code(msg_pronta, language=None)

                    else:
                        st.info("Sem dados de avaliação para este chat.")

                # ── TAB FEEDBACK COMPLETO (detalhamento de competências) ─────────────────
                with t_feed:
                    if isinstance(j, dict) and bool(j):
                        val_vend = j.get('avaliacao_vendedor', {})

                        # Notas por categoria em formato visual
                        notas = val_vend.get('notas_por_categoria', {})
                        if notas and isinstance(notas, dict):
                            st.markdown("##### 📊 Notas por Categoria")
                            for cat_key, (cat_label, cat_max) in _CATS_VENDEDOR.items():
                                val = notas.get(cat_key)
                                if val is not None:
                                    try:
                                        pct = float(val) / cat_max
                                        emoji = "🟢" if pct >= 0.75 else ("🟡" if pct >= 0.5 else "🔴")
                                        st.write(f"{emoji} **{cat_label}:** {val}/{cat_max}")
                                    except (TypeError, ValueError):
                                        pass
                            st.divider()

                        col1, col2 = st.columns(2)
                        with col1:
                            st.success("**✅ Pontos Fortes do Vendedor**")
                            for p in val_vend.get('pontos_fortes', []):
                                if isinstance(p, dict):
                                    st.write(f"- {p.get('ponto', p)}")
                                    if p.get('evidencia'):
                                        st.caption(f"  _{p['evidencia']}_")
                                else:
                                    st.write(f"- {p}")

                            st.error("**❌ Erro Mais Caro**")
                            erro = val_vend.get('erro_mais_caro', {})
                            if isinstance(erro, dict):
                                st.write(erro.get('descricao', '—'))
                                if erro.get('evidencia'):
                                    st.caption(f"_{erro['evidencia']}_")
                            else:
                                st.write(str(erro) if erro else '—')

                        with col2:
                            st.warning("**🛠️ Sugestões de Melhoria**")
                            for m in val_vend.get('melhorias', []):
                                if isinstance(m, dict):
                                    st.write(f"▪ *{m.get('melhoria', '')}*")
                                    if m.get('como_fazer'):
                                        st.caption(f"💡 {m['como_fazer']}")
                                else:
                                    st.write(f"▪ {m}")

                        alertas_chat = val_vend.get('alertas', [])
                        if alertas_chat and not (len(alertas_chat) == 1 and str(alertas_chat[0]).lower() in ['não mencionado', 'não houve', 'nenhum']):
                            st.error("**🚨 Alertas de Compliance**")
                            for a in alertas_chat:
                                st.write(f"- {a}")

                        st.divider()

                        # Análise do Lead
                        avl = j.get('avaliacao_lead', {})
                        if avl and isinstance(avl, dict):
                            st.markdown("##### 🎯 Análise do Lead")
                            col_sq, col_sf = st.columns(2)
                            with col_sq:
                                st.markdown("**🔥 Sinais Quentes**")
                                for s in avl.get('sinais_quente', []):
                                    if isinstance(s, dict):
                                        st.write(f"🟢 {s.get('sinal', '')}")
                                        if s.get('evidencia'):
                                            st.caption(f"  _{s['evidencia']}_")
                                    elif isinstance(s, str) and s.strip():
                                        st.write(f"🟢 {s}")
                            with col_sf:
                                st.markdown("**🧊 Sinais Frios**")
                                for s in avl.get('sinais_frio', []):
                                    if isinstance(s, dict):
                                        st.write(f"🔴 {s.get('sinal', '')}")
                                        if s.get('evidencia'):
                                            st.caption(f"  _{s['evidencia']}_")
                                    elif isinstance(s, str) and s.strip():
                                        st.write(f"🔴 {s}")

                        st.divider()
                        st.markdown("##### 🔎 Dados Brutos (JSON)")
                        col_ext, col_rec = st.columns(2)
                        with col_ext:
                            st.markdown("**Extração**")
                            st.json(j.get('extracao', {}), expanded=False)
                        with col_rec:
                            st.markdown("**Recomendação Final**")
                            st.json(j.get('recomendacao_final', {}), expanded=False)
                    else:
                        st.info("Sem dados de avaliação comercial para este chat.")

                with t_trans:
                    if pd.notna(transcript) and str(transcript).strip():
                        st.text_area(
                            "Texto Integral do Chat",
                            value=str(transcript), height=500, disabled=True,
                        )
                    else:
                        st.warning("Transcrição não disponível para este chat.")


if __name__ == "__main__":
    run_page()

