# _pages/relatorio_macro.py
# Relatório Macro de Performance do Time de Vendas
# Visão estratégica: WhatsApp vs Telefone, gaps coletivos, plano de ação

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import pandas as pd
import json
import anthropic
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from collections import Counter
from dotenv import load_dotenv

load_dotenv()

# ══════════════════════════════════════════════════════════════════════════════
# SQL — mesmas queries do treinamento_vendedor.py
# ══════════════════════════════════════════════════════════════════════════════

SQL_CHATS = """
SELECT
    c.chat_id,
    c.classification,
    c.ai_evaluation,
    c.lead_score,
    c.vendor_score AS evaluation_ia,
    c.main_product,
    c.vendedor_disclaimer,
    c.lead_disclaimer,
    c.octa_agent AS agente,
    c.octa_created_at AS data_avaliacao,
    c.octa_group AS grupo,
    CASE
        WHEN c.octa_origin LIKE '%Degrau%' THEN 'Degrau'
        WHEN c.octa_origin LIKE '%Central%' THEN 'Central'
        ELSE 'Outros'
    END AS empresa,
    'WhatsApp' AS canal
FROM seducar.chat_ai_evaluations c
WHERE c.classification = 'venda'
  AND c.vendor_score IS NOT NULL
  AND c.vendor_score > 0
"""

SQL_TRANSCRICOES = """
SELECT
    s.transcription_id,
    s.ai_insight AS ai_evaluation,
    s.ai_evaluation AS evaluation_ia,
    s.lead_score,
    s.lead_classification,
    s.strengths,
    s.improvements,
    s.most_expensive_mistake,
    s.contest_area,
    s.main_product,
    s.vendedor_disclaimer,
    s.lead_disclaimer,
    t.agent AS agente,
    t.date AS data_avaliacao,
    CASE
        WHEN t.school_id = 1 THEN 'Central'
        WHEN t.school_id = 2 THEN 'Degrau'
        ELSE 'Outros'
    END AS empresa,
    'Telefone' AS canal
FROM seducar.transcription_ai_summaries s
JOIN seducar.opportunity_transcripts t ON s.transcription_id = t.id
WHERE s.ai_evaluation IS NOT NULL
  AND s.ai_evaluation > 0
"""

# ══════════════════════════════════════════════════════════════════════════════
# CARREGAMENTO
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600, show_spinner=False)
def _carregar_avaliacoes():
    from conexao.mysql_connector import conectar_mysql
    engine = conectar_mysql()
    if not engine:
        return pd.DataFrame()

    frames = []
    for sql, label in [(SQL_CHATS, 'WhatsApp'), (SQL_TRANSCRICOES, 'Telefone')]:
        try:
            df = pd.read_sql(sql, engine)
            if not df.empty:
                df['evaluation_ia'] = pd.to_numeric(df['evaluation_ia'], errors='coerce')
                df['lead_score'] = pd.to_numeric(df['lead_score'], errors='coerce')
                df['data_avaliacao'] = pd.to_datetime(df['data_avaliacao'], errors='coerce')

                if label == 'WhatsApp':
                    def _parse(v):
                        if not v or (isinstance(v, float) and pd.isna(v)):
                            return {}
                        try:
                            return json.loads(str(v).strip()) if isinstance(v, str) else v
                        except:
                            return {}

                    parsed = df['ai_evaluation'].apply(_parse)

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

                    df['strengths'] = parsed.apply(
                        lambda j: _join_list(j.get('avaliacao_vendedor', {}).get('pontos_fortes', []), 'ponto') if isinstance(j, dict) else ''
                    )
                    df['improvements'] = parsed.apply(
                        lambda j: _join_list(j.get('avaliacao_vendedor', {}).get('melhorias', []), 'melhoria') if isinstance(j, dict) else ''
                    )
                    df['most_expensive_mistake'] = parsed.apply(
                        lambda j: j.get('avaliacao_vendedor', {}).get('erro_mais_caro', {}).get('descricao', '')
                        if isinstance(j, dict) and isinstance(j.get('avaliacao_vendedor', {}).get('erro_mais_caro'), dict) else ''
                    )
                    df['lead_classification'] = parsed.apply(
                        lambda j: j.get('avaliacao_lead', {}).get('classificacao', '—') if isinstance(j, dict) else '—'
                    )
                    df['contest_area'] = parsed.apply(
                        lambda j: j.get('extracao', {}).get('concurso_area', '') if isinstance(j, dict) else ''
                    )

                frames.append(df)
        except Exception as e:
            st.warning(f"Erro ao carregar {label}: {e}")

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _top_items(series, n=10):
    """Conta itens separados por ; numa Series."""
    items = []
    for v in series.fillna(''):
        items.extend([t.strip() for t in str(v).split(';') if t.strip()])
    return Counter(items).most_common(n)


def _agregar_time(df):
    """Agrega métricas de um grupo (time/canal/empresa)."""
    if df.empty:
        return {}
    return {
        'nota_media': round(df['evaluation_ia'].mean(), 1),
        'nota_mediana': round(df['evaluation_ia'].median(), 1),
        'nota_min': int(df['evaluation_ia'].min()),
        'nota_max': int(df['evaluation_ia'].max()),
        'desvio_padrao': round(df['evaluation_ia'].std(), 1),
        'volume': len(df),
        'lead_score_medio': round(df.loc[df['lead_score'] > 0, 'lead_score'].mean(), 1) if (df['lead_score'] > 0).any() else 0,
        'lead_dist': df['lead_classification'].value_counts().to_dict() if 'lead_classification' in df.columns else {},
        'agentes': df['agente'].nunique(),
        'pontos_fortes': _top_items(df.get('strengths', pd.Series(dtype=str)), 10),
        'melhorias': _top_items(df.get('improvements', pd.Series(dtype=str)), 10),
        'erros_caros': _top_items(df.get('most_expensive_mistake', pd.Series(dtype=str)), 8),
        'concursos': _top_items(df.get('contest_area', pd.Series(dtype=str)), 8),
    }


# ══════════════════════════════════════════════════════════════════════════════
# DIAGNÓSTICO EXECUTIVO VIA CLAUDE
# ══════════════════════════════════════════════════════════════════════════════

_PROMPT_DIAGNOSTICO = """Você é um diretor comercial analisando a performance do time de vendas de um curso preparatório para concursos (+30 anos, +100 mil aprovações).

METODOLOGIA DE AVALIAÇÃO:
Venda Consultiva Adaptada. Categorias: Rapport(10), Qualificação/Leitura(15), CONSTRUÇÃO DE VALOR(30, maior peso), Persuasão(10), Objeções(10), Fechamento(20), Clareza(5).
Hierarquia: Presencial > Passaporte > Live > Smart > EAD.

DADOS DO PERÍODO ({periodo}):

VISÃO GERAL:
- Empresa: {empresa}
- Canais avaliados: {canais}
- Volume total: {volume_total} avaliações
- Vendedores ativos: {n_agentes}

MÉTRICAS POR CANAL:
{metricas_canal}

RANKING DE VENDEDORES (nota média):
{ranking_vendedores}

TOP PONTOS FORTES DO TIME (frequência):
{pontos_fortes}

TOP MELHORIAS DO TIME (frequência):
{melhorias}

TOP ERROS MAIS CAROS (frequência):
{erros_caros}

DISTRIBUIÇÃO DE LEADS POR CLASSE:
{lead_dist}

DISCLAIMERS RECENTES (resumos das últimas avaliações):
{disclaimers}

GERE UM DIAGNÓSTICO EXECUTIVO (retorne JSON):
{{
  "titulo": "Diagnóstico de Performance — [Empresa] — [Período]",
  "resumo_executivo": "3-4 frases resumindo o estado do time. Nota média, dispersão, destaque positivo, gap principal. Tom direto pro gestor.",

  "saude_do_time": {{
    "nota_geral": "A|B|C|D (A=excelente, B=bom, C=precisa atenção, D=crítico)",
    "justificativa": "2 frases explicando a nota"
  }},

  "comparativo_canais": {{
    "canal_mais_forte": "WhatsApp|Telefone",
    "por_que": "2 frases com dados",
    "canal_mais_fraco": "WhatsApp|Telefone",
    "gap_principal": "qual competência está pior nesse canal",
    "recomendacao": "o que fazer pra nivelar"
  }},

  "gaps_coletivos": [
    {{
      "gap": "nome do gap (ex: Construção de Valor)",
      "gravidade": "alta|media|baixa",
      "frequencia": "em X de Y avaliações",
      "impacto_estimado": "se corrigido, nota média subiria ~X pontos",
      "causa_raiz": "por que isso está acontecendo (1-2 frases)",
      "acao": "o que o gestor deve fazer (1-2 frases concretas)"
    }}
  ],

  "destaques_positivos": [
    {{
      "destaque": "o que o time faz bem",
      "quem_puxa": "vendedor(es) que mais contribuem",
      "recomendacao": "como replicar pro resto do time"
    }}
  ],

  "vendedores_atencao": [
    {{
      "nome": "vendedor",
      "nota_media": 0,
      "gap_principal": "qual competência está pior",
      "acao_imediata": "o que fazer essa semana"
    }}
  ],

  "plano_de_acao_30_dias": [
    {{
      "semana": "Semana 1-2",
      "acao": "ação concreta e mensurável",
      "responsavel": "gestor|vendedor|time",
      "meta": "como medir sucesso"
    }},
    {{
      "semana": "Semana 3-4",
      "acao": "...",
      "responsavel": "...",
      "meta": "..."
    }}
  ],

  "meta_proxima_rodada": {{
    "nota_media_alvo": 0,
    "gap_foco": "qual competência atacar",
    "como_medir": "critério objetivo"
  }}
}}

REGRAS:
- Use dados reais, não genéricos. Cite números.
- Gaps coletivos = problemas que aparecem em MÚLTIPLOS vendedores (não é individual).
- Se um gap aparece em 50%+ das avaliações, é sistêmico — precisa de treinamento coletivo, não 1:1.
- Plano de ação deve ser executável pelo gestor esta semana.
- NUNCA use "SPIN" ou "perguntas de implicação". Use linguagem do framework: leitura de contexto, ancoragem de valor, condução ao fechamento.
- Retorne APENAS JSON válido."""


def _gerar_diagnostico(df_filtrado, empresa, periodo_str, canais_str):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {'erro': 'ANTHROPIC_API_KEY não configurada'}

    # Métricas por canal
    metricas_canal = ""
    for canal in df_filtrado['canal'].unique():
        d = _agregar_time(df_filtrado[df_filtrado['canal'] == canal])
        metricas_canal += (
            f"\n{canal}: nota média {d['nota_media']}, mediana {d['nota_mediana']}, "
            f"min {d['nota_min']}, max {d['nota_max']}, desvio {d['desvio_padrao']}, "
            f"volume {d['volume']}, agentes {d['agentes']}, lead score médio {d['lead_score_medio']}"
        )

    # Ranking vendedores
    ranking = df_filtrado.groupby('agente').agg(
        nota_media=('evaluation_ia', 'mean'),
        volume=('evaluation_ia', 'count')
    ).sort_values('nota_media', ascending=False).reset_index()
    ranking_str = '\n'.join(
        f"  {i+1}. {r['agente']}: {r['nota_media']:.1f} ({int(r['volume'])} avaliações)"
        for i, r in ranking.iterrows()
    )

    # Agregados gerais
    dados_geral = _agregar_time(df_filtrado)

    # Disclaimers recentes
    disclaimers = [
        str(v).strip() for v in df_filtrado.sort_values('data_avaliacao', ascending=False)
        .head(15)['vendedor_disclaimer'].fillna('')
        if str(v).strip() and str(v).lower() not in ('nan', 'none', '')
    ][:8]

    prompt = _PROMPT_DIAGNOSTICO.format(
        periodo=periodo_str,
        empresa=empresa,
        canais=canais_str,
        volume_total=dados_geral['volume'],
        n_agentes=dados_geral['agentes'],
        metricas_canal=metricas_canal,
        ranking_vendedores=ranking_str,
        pontos_fortes='\n'.join(f"  - {txt} ({n}x)" for txt, n in dados_geral['pontos_fortes']),
        melhorias='\n'.join(f"  - {txt} ({n}x)" for txt, n in dados_geral['melhorias']),
        erros_caros='\n'.join(f"  - {txt} ({n}x)" for txt, n in dados_geral['erros_caros']),
        lead_dist=json.dumps(dados_geral['lead_dist'], ensure_ascii=False),
        disclaimers='\n'.join(f"  - {d}" for d in disclaimers) or 'Nenhum disponível',
    )

    import re
    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
            max_tokens=4096,
            temperature=0.3,
            system="Você é um diretor comercial sênior. Retorne sempre JSON válido.",
            messages=[{"role": "user", "content": prompt}],
        )
        content = (response.content[0].text if response.content else "").strip()
        match = re.match(r'^```(?:json)?\s*\n?(.*?)\n?```$', content, re.DOTALL)
        if match:
            content = match.group(1).strip()
        return json.loads(content)
    except Exception as e:
        return {'erro': str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA STREAMLIT
# ══════════════════════════════════════════════════════════════════════════════

def run_page():
    st.title("📊 Relatório Macro — Performance do Time")
    st.caption("Visão estratégica: gaps coletivos, comparativo por canal, plano de ação")

    with st.spinner("Carregando avaliações..."):
        df_all = _carregar_avaliacoes()

    if df_all.empty:
        st.warning("Nenhuma avaliação encontrada.")
        st.stop()

    # ── Filtros ──────────────────────────────────────────────────────────────
    st.sidebar.header("🔍 Filtros")

    empresas = sorted([str(e) for e in df_all['empresa'].dropna().unique() if str(e).strip()])
    empresa = st.sidebar.radio("Empresa:", empresas, key="macro_empresa")

    canais_disp = sorted([str(c) for c in df_all['canal'].dropna().unique() if str(c).strip()])
    canais_sel = st.sidebar.multiselect("Canal:", canais_disp, default=canais_disp, key="macro_canal")
    if not canais_sel:
        canais_sel = canais_disp

    hoje = pd.Timestamp.now().date()
    periodo = st.sidebar.date_input(
        "Período:", [hoje - pd.Timedelta(days=30), hoje], key="macro_periodo"
    )
    try:
        d_ini = pd.Timestamp(periodo[0])
        d_fim = pd.Timestamp(periodo[1]) + pd.Timedelta(days=1)
    except (IndexError, TypeError):
        st.sidebar.warning("Selecione um período completo.")
        st.stop()

    df_f = df_all[
        (df_all['empresa'] == empresa) &
        (df_all['canal'].isin(canais_sel)) &
        (df_all['data_avaliacao'] >= d_ini) &
        (df_all['data_avaliacao'] < d_fim)
    ].copy()

    if df_f.empty:
        st.warning("Nenhuma avaliação neste filtro.")
        st.stop()

    periodo_str = f"{periodo[0].strftime('%d/%m/%Y')} – {periodo[1].strftime('%d/%m/%Y')}"
    canais_str = ' + '.join(canais_sel)
    dados = _agregar_time(df_f)

    # ══════════════════════════════════════════════════════════════════════════
    # DASHBOARD VISUAL
    # ══════════════════════════════════════════════════════════════════════════

    st.markdown(f"### {empresa} — {periodo_str} — {canais_str}")

    # ── KPIs ─────────────────────────────────────────────────────────────────
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Nota Média", f"{dados['nota_media']}")
    k2.metric("Mediana", f"{dados['nota_mediana']}")
    k3.metric("Desvio", f"{dados['desvio_padrao']}")
    k4.metric("Volume", f"{dados['volume']}")
    k5.metric("Vendedores", f"{dados['agentes']}")
    k6.metric("Lead Score", f"{dados['lead_score_medio']}")

    st.divider()

    # ── Comparativo por Canal ────────────────────────────────────────────────
    if len(canais_sel) > 1:
        st.markdown("### 📡 Comparativo por Canal")
        col_canais = st.columns(len(canais_sel))
        for i, canal in enumerate(canais_sel):
            dc = df_f[df_f['canal'] == canal]
            d = _agregar_time(dc)
            with col_canais[i]:
                st.markdown(f"**{canal}**")
                st.metric("Nota Média", f"{d['nota_media']}")
                st.metric("Volume", f"{d['volume']}")
                st.metric("Vendedores", f"{d['agentes']}")
                st.metric("Lead Score", f"{d['lead_score_medio']}")

        # Gráfico comparativo
        canal_comp = df_f.groupby('canal')['evaluation_ia'].agg(['mean', 'median', 'std', 'count']).reset_index()
        canal_comp.columns = ['Canal', 'Média', 'Mediana', 'Desvio', 'Volume']
        fig_comp = px.bar(
            canal_comp, x='Canal', y='Média', color='Canal',
            text_auto='.1f', title='Nota Média por Canal',
            color_discrete_map={'WhatsApp': '#25D366', 'Telefone': '#636EFA'}
        )
        fig_comp.update_layout(showlegend=False, yaxis_range=[0, 100])
        st.plotly_chart(fig_comp, use_container_width=True)

        st.divider()

    # ── Ranking de Vendedores ────────────────────────────────────────────────
    st.markdown("### 🏆 Ranking do Time")
    ranking = df_f.groupby(['agente', 'canal']).agg(
        nota_media=('evaluation_ia', 'mean'),
        volume=('evaluation_ia', 'count'),
        lead_score=('lead_score', 'mean'),
    ).reset_index().sort_values('nota_media', ascending=False)
    ranking['nota_media'] = ranking['nota_media'].round(1)
    ranking['lead_score'] = ranking['lead_score'].round(1)
    ranking.index = range(1, len(ranking) + 1)
    ranking.columns = ['Vendedor', 'Canal', 'Nota Média', 'Volume', 'Lead Score']
    st.dataframe(ranking, use_container_width=True, height=min(400, 35 * len(ranking) + 40))

    st.divider()

    # ── Distribuição de Notas ────────────────────────────────────────────────
    col_dist1, col_dist2 = st.columns(2)
    with col_dist1:
        st.markdown("### 📊 Distribuição de Notas")
        fig_hist = px.histogram(
            df_f, x='evaluation_ia', nbins=20, color='canal',
            color_discrete_map={'WhatsApp': '#25D366', 'Telefone': '#636EFA'},
            title='Distribuição de Notas dos Vendedores'
        )
        fig_hist.update_layout(xaxis_title='Nota', yaxis_title='Frequência')
        st.plotly_chart(fig_hist, use_container_width=True)

    with col_dist2:
        st.markdown("### 🎯 Qualidade dos Leads")
        lead_df = df_f['lead_classification'].value_counts().reset_index()
        lead_df.columns = ['Classe', 'Quantidade']
        cores_lead = {'A': '#00CC96', 'B': '#636EFA', 'C': '#FFA15A', 'D': '#EF553B', '—': '#999'}
        fig_lead = px.pie(
            lead_df, names='Classe', values='Quantidade', hole=0.4,
            color='Classe', color_discrete_map=cores_lead,
            title='Distribuição de Leads por Classe'
        )
        st.plotly_chart(fig_lead, use_container_width=True)

    st.divider()

    # ── Gaps Coletivos (visual) ──────────────────────────────────────────────
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        st.markdown("### 🛠️ Top Melhorias do Time")
        for txt, n in dados['melhorias'][:7]:
            pct = n / dados['volume'] * 100
            st.write(f"• **{txt}** — {n}x ({pct:.0f}% das avaliações)")

    with col_g2:
        st.markdown("### 💸 Erros Mais Caros")
        for txt, n in dados['erros_caros'][:5]:
            pct = n / dados['volume'] * 100
            st.write(f"• **{txt}** — {n}x ({pct:.0f}%)")

    st.divider()

    # ══════════════════════════════════════════════════════════════════════════
    # DIAGNÓSTICO EXECUTIVO VIA IA
    # ══════════════════════════════════════════════════════════════════════════

    st.markdown("### 🧠 Diagnóstico Executivo (IA)")

    if st.button("Gerar Diagnóstico do Time", type="primary", use_container_width=True):
        with st.spinner("Claude está analisando os dados do time..."):
            diag = _gerar_diagnostico(df_f, empresa, periodo_str, canais_str)

        if 'erro' in diag:
            st.error(f"Erro: {diag['erro']}")
        else:
            st.session_state['diag_macro'] = diag
            st.success("Diagnóstico gerado!")

    if 'diag_macro' in st.session_state:
        diag = st.session_state['diag_macro']

        st.markdown(f"## {diag.get('titulo', 'Diagnóstico')}")

        # Resumo executivo
        st.info(diag.get('resumo_executivo', ''))

        # Saúde do time
        saude = diag.get('saude_do_time', {})
        if saude:
            nota_cor = {'A': '🟢', 'B': '🔵', 'C': '🟡', 'D': '🔴'}.get(saude.get('nota_geral', ''), '⚪')
            st.markdown(f"**Saúde do Time:** {nota_cor} **{saude.get('nota_geral', '—')}** — {saude.get('justificativa', '')}")

        st.divider()

        # Comparativo canais
        comp = diag.get('comparativo_canais', {})
        if comp and len(canais_sel) > 1:
            st.markdown("#### 📡 Comparativo de Canais")
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                st.success(f"**Canal mais forte: {comp.get('canal_mais_forte', '')}**")
                st.write(comp.get('por_que', ''))
            with col_c2:
                st.warning(f"**Canal com gap: {comp.get('canal_mais_fraco', '')}**")
                st.write(f"Gap: {comp.get('gap_principal', '')}")
                st.write(f"Recomendação: {comp.get('recomendacao', '')}")
            st.divider()

        # Gaps coletivos
        gaps = diag.get('gaps_coletivos', [])
        if gaps:
            st.markdown("#### 🚨 Gaps Coletivos (problemas sistêmicos)")
            for g in gaps:
                gravidade_emoji = {'alta': '🔴', 'media': '🟡', 'baixa': '🟢'}.get(g.get('gravidade', ''), '⚪')
                with st.expander(f"{gravidade_emoji} {g.get('gap', '')} — {g.get('frequencia', '')}", expanded=True):
                    st.write(f"**Impacto:** {g.get('impacto_estimado', '')}")
                    st.write(f"**Causa raiz:** {g.get('causa_raiz', '')}")
                    st.write(f"**Ação:** {g.get('acao', '')}")

        # Destaques positivos
        destaques = diag.get('destaques_positivos', [])
        if destaques:
            st.markdown("#### ✅ Destaques Positivos")
            for d in destaques:
                st.success(f"**{d.get('destaque', '')}** — Puxado por: {d.get('quem_puxa', '')}")
                st.caption(f"Como replicar: {d.get('recomendacao', '')}")

        # Vendedores que precisam de atenção
        atencao = diag.get('vendedores_atencao', [])
        if atencao:
            st.markdown("#### ⚠️ Vendedores que Precisam de Atenção")
            for v in atencao:
                st.warning(f"**{v.get('nome', '')}** (nota {v.get('nota_media', '—')}) — Gap: {v.get('gap_principal', '')}")
                st.caption(f"Ação imediata: {v.get('acao_imediata', '')}")

        st.divider()

        # Plano de ação
        plano = diag.get('plano_de_acao_30_dias', [])
        if plano:
            st.markdown("#### 📋 Plano de Ação — Próximos 30 Dias")
            for p in plano:
                st.markdown(f"**{p.get('semana', '')}** — {p.get('acao', '')}")
                st.caption(f"Responsável: {p.get('responsavel', '')} | Meta: {p.get('meta', '')}")

        # Meta próxima rodada
        meta = diag.get('meta_proxima_rodada', {})
        if meta:
            st.divider()
            st.markdown(f"### 🎯 Meta da Próxima Rodada: nota média **{meta.get('nota_media_alvo', '—')}**")
            st.write(f"Foco: **{meta.get('gap_foco', '')}**")
            st.write(f"Como medir: {meta.get('como_medir', '')}")

        # Download JSON
        st.divider()
        st.download_button(
            "📥 Baixar Diagnóstico (JSON)",
            data=json.dumps(diag, ensure_ascii=False, indent=2),
            file_name=f"diagnostico_macro_{empresa}_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json",
            use_container_width=True,
        )


if __name__ == "__main__":
    run_page()
