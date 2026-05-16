import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
import re
from collections import Counter
from datetime import datetime

import anthropic
import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from utils.sql_loader import carregar_dados

load_dotenv()

# ══════════════════════════════════════════════════════════════════════════════
# CARREGAMENTO — reutiliza os mesmos SQLs dos dashboards individuais
# ══════════════════════════════════════════════════════════════════════════════

def _parse_json(v):
    if not v or (isinstance(v, float) and pd.isna(v)):
        return {}
    txt = str(v).strip()
    if not txt:
        return {}
    try:
        return json.loads(txt)
    except Exception:
        return {}


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


@st.cache_data(ttl=3600, show_spinner=False)
def _carregar_whatsapp() -> pd.DataFrame:
    # Mesmo SQL do analise_chats.py — sem filtros restritivos no banco
    df = carregar_dados("consultas/analise_chats/analise_chats.sql")
    if df is None or df.empty:
        return pd.DataFrame()

    df['avaliada'] = df.get('avaliada', pd.Series(0, index=df.index)).astype(bool)
    df['evaluation_ia'] = pd.to_numeric(df.get('evaluation_ia'), errors='coerce')
    df['lead_score'] = pd.to_numeric(df.get('lead_score'), errors='coerce')

    # Só registros efetivamente avaliados com nota válida
    df = df[df['avaliada'] & df['evaluation_ia'].notna() & (df['evaluation_ia'] > 0)].copy()
    if df.empty:
        return pd.DataFrame()

    # Data unificada tz-naive
    col = pd.to_datetime(df['data_chat'], errors='coerce', utc=True)
    df['data_avaliacao'] = col.dt.tz_convert(None)
    df['canal'] = 'WhatsApp'

    # Parse JSON de avaliação (mesmo padrão do analise_chats.py)
    parsed = df['ai_evaluation'].apply(_parse_json)

    df['strengths'] = parsed.apply(
        lambda j: _join_list(j.get('avaliacao_vendedor', {}).get('pontos_fortes', []), 'ponto')
        if isinstance(j, dict) else ''
    )
    df['improvements'] = parsed.apply(
        lambda j: _join_list(j.get('avaliacao_vendedor', {}).get('melhorias', []), 'melhoria')
        if isinstance(j, dict) else ''
    )
    df['most_expensive_mistake'] = parsed.apply(
        lambda j: (
            j.get('avaliacao_vendedor', {}).get('erro_mais_caro', {}).get('descricao', '')
            if isinstance(j.get('avaliacao_vendedor', {}).get('erro_mais_caro'), dict)
            else str(j.get('avaliacao_vendedor', {}).get('erro_mais_caro', ''))
        ) if isinstance(j, dict) else ''
    )
    df['lead_classification'] = parsed.apply(
        lambda j: j.get('avaliacao_lead', {}).get('classificacao', '—') if isinstance(j, dict) else '—'
    ).fillna('—')
    # Garantir que valores inválidos viram '—'
    df.loc[~df['lead_classification'].isin(['A', 'B', 'C', 'D']), 'lead_classification'] = '—'

    df['contest_area'] = parsed.apply(
        lambda j: str(j.get('extracao', {}).get('concurso_area', '')).strip() if isinstance(j, dict) else ''
    )

    # Disclaimers: coluna do banco primeiro, fallback no JSON
    if 'vendedor_disclaimer' not in df.columns:
        df['vendedor_disclaimer'] = ''
    if 'lead_disclaimer' not in df.columns:
        df['lead_disclaimer'] = ''
    mask_vd = df['vendedor_disclaimer'].fillna('').str.strip() == ''
    df.loc[mask_vd, 'vendedor_disclaimer'] = parsed[mask_vd].apply(
        lambda j: str(j.get('vendedor_disclaimer', '')).strip() if isinstance(j, dict) else ''
    )
    mask_ld = df['lead_disclaimer'].fillna('').str.strip() == ''
    df.loc[mask_ld, 'lead_disclaimer'] = parsed[mask_ld].apply(
        lambda j: str(j.get('lead_disclaimer', '')).strip() if isinstance(j, dict) else ''
    )

    return df[[
        'agente', 'empresa', 'canal', 'data_avaliacao', 'evaluation_ia', 'lead_score',
        'lead_classification', 'vendedor_disclaimer', 'lead_disclaimer',
        'strengths', 'improvements', 'most_expensive_mistake', 'contest_area',
    ]]


@st.cache_data(ttl=3600, show_spinner=False)
def _carregar_telefone() -> pd.DataFrame:
    # Mesmo SQL do analise_transcricoes.py — sem filtros restritivos no banco
    df = carregar_dados("consultas/transcricoes/transcricoes.sql")
    if df is None or df.empty:
        return pd.DataFrame()

    df['evaluation_ia'] = pd.to_numeric(df.get('evaluation_ia'), errors='coerce')
    df['lead_score'] = pd.to_numeric(df.get('lead_score'), errors='coerce')

    # Só registros com nota válida (evaluation_ia = 0 significa não avaliado)
    df = df[df['evaluation_ia'].notna() & (df['evaluation_ia'] > 0)].copy()
    if df.empty:
        return pd.DataFrame()

    # Data unificada tz-naive
    col = pd.to_datetime(df['data_ligacao'], errors='coerce', utc=True)
    df['data_avaliacao'] = col.dt.tz_convert(None)
    df['canal'] = 'Telefone'

    df['lead_classification'] = df.get('lead_classification', pd.Series(dtype=str)).fillna('—')
    df.loc[~df['lead_classification'].isin(['A', 'B', 'C', 'D']), 'lead_classification'] = '—'

    # transcricoes.sql usa 'concurso_area', unificamos para 'contest_area'
    if 'concurso_area' in df.columns:
        df['contest_area'] = df['concurso_area'].fillna('')
    else:
        df['contest_area'] = ''

    for col_name in ('vendedor_disclaimer', 'lead_disclaimer', 'strengths', 'improvements', 'most_expensive_mistake'):
        if col_name not in df.columns:
            df[col_name] = ''
        else:
            df[col_name] = df[col_name].fillna('')

    return df[[
        'agente', 'empresa', 'canal', 'data_avaliacao', 'evaluation_ia', 'lead_score',
        'lead_classification', 'vendedor_disclaimer', 'lead_disclaimer',
        'strengths', 'improvements', 'most_expensive_mistake', 'contest_area',
    ]]


@st.cache_data(ttl=3600, show_spinner=False)
def _carregar_avaliacoes() -> pd.DataFrame:
    frames = []
    for fn in [_carregar_whatsapp, _carregar_telefone]:
        df = fn()
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _top_items(series, n=10):
    items = []
    for v in series.fillna(''):
        items.extend([t.strip() for t in str(v).split(';') if t.strip()])
    return Counter(items).most_common(n)


def _agregar_time(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    notas = df['evaluation_ia'].dropna()
    if notas.empty:
        return {}
    return {
        'nota_media': round(notas.mean(), 1),
        'nota_mediana': round(notas.median(), 1),
        'nota_min': int(notas.min()),
        'nota_max': int(notas.max()),
        'desvio_padrao': round(notas.std(), 1),
        'volume': len(df),
        'lead_score_medio': round(df.loc[df['lead_score'] > 0, 'lead_score'].mean(), 1)
            if (df['lead_score'] > 0).any() else 0,
        'lead_dist': df['lead_classification'].value_counts().to_dict()
            if 'lead_classification' in df.columns else {},
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


def _gerar_diagnostico(df_filtrado: pd.DataFrame, empresa: str, periodo_str: str, canais_str: str) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {'erro': 'ANTHROPIC_API_KEY não configurada'}

    metricas_canal = ""
    for canal in df_filtrado['canal'].unique():
        d = _agregar_time(df_filtrado[df_filtrado['canal'] == canal])
        if not d:
            continue
        metricas_canal += (
            f"\n{canal}: nota média {d['nota_media']}, mediana {d['nota_mediana']}, "
            f"min {d['nota_min']}, max {d['nota_max']}, desvio {d['desvio_padrao']}, "
            f"volume {d['volume']}, agentes {d['agentes']}, lead score médio {d['lead_score_medio']}"
        )

    ranking = df_filtrado.groupby('agente').agg(
        nota_media=('evaluation_ia', 'mean'),
        volume=('evaluation_ia', 'count')
    ).sort_values('nota_media', ascending=False).reset_index()
    ranking_str = '\n'.join(
        f"  {i+1}. {r['agente']}: {r['nota_media']:.1f} ({int(r['volume'])} avaliações)"
        for i, r in ranking.iterrows()
    )

    dados_geral = _agregar_time(df_filtrado)

    disclaimers = [
        str(v).strip()
        for v in df_filtrado.sort_values('data_avaliacao', ascending=False)
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

    model = "claude-opus-4-6"
    max_tokens = int(os.getenv("CLAUDE_MAX_TOKENS", "8000"))

    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0.3,
            system="Você é um diretor comercial sênior. Retorne sempre JSON válido.",
            messages=[{"role": "user", "content": prompt}],
        )

        print(
            f"[Avaliacao Global] model={response.model} | "
            f"input_tokens={response.usage.input_tokens} | "
            f"output_tokens={response.usage.output_tokens} | "
            f"stop_reason={response.stop_reason} | "
            f"max_tokens_config={max_tokens}"
        )

        if response.stop_reason == 'max_tokens':
            return {'erro': 'Resposta truncada (max_tokens atingido). Reduza o período ou o número de vendedores e tente novamente.'}

        content = (response.content[0].text if response.content else "").strip()

        if not content:
            return {'erro': 'API retornou resposta vazia.'}

        print(f"[Avaliacao Global] content_length={len(content)} | preview={content[:120]!r}")

        match = re.match(r'^```(?:json)?\s*\n?(.*?)\n?```$', content, re.DOTALL)
        if match:
            content = match.group(1).strip()

        return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"[Avaliacao Global] JSON parse error: {e} | content={content!r}")
        return {'erro': f'Erro ao interpretar JSON da resposta: {e}'}
    except Exception as e:
        print(f"[Avaliacao Global] Exception: {type(e).__name__}: {e}")
        return {'erro': str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA
# ══════════════════════════════════════════════════════════════════════════════

def run_page():
    st.title("📊 Avaliação Global — Performance do Time")
    st.caption("Visão estratégica: gaps coletivos, comparativo por canal, plano de ação")

    with st.spinner("Carregando avaliações..."):
        df_all = _carregar_avaliacoes()

    if df_all.empty:
        st.warning("Nenhuma avaliação encontrada.")
        st.stop()

    # ── Filtros ───────────────────────────────────────────────────────────────
    st.sidebar.header("🔍 Filtros")

    empresas = sorted([str(e) for e in df_all['empresa'].dropna().unique() if str(e).strip()])
    empresa = st.sidebar.radio("Empresa:", empresas, key="ag_empresa")

    canais_disp = sorted([str(c) for c in df_all['canal'].dropna().unique() if str(c).strip()])
    canais_sel = st.sidebar.multiselect("Canal:", canais_disp, default=canais_disp, key="ag_canal")
    if not canais_sel:
        canais_sel = canais_disp

    hoje = pd.Timestamp.now().date()
    periodo = st.sidebar.date_input(
        "Período:", [hoje - pd.Timedelta(days=30), hoje], key="ag_periodo"
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

    # ── KPIs ──────────────────────────────────────────────────────────────────
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Nota Média", f"{dados['nota_media']}")
    k2.metric("Mediana", f"{dados['nota_mediana']}")
    k3.metric("Desvio", f"{dados['desvio_padrao']}")
    k4.metric("Volume", f"{dados['volume']}")
    k5.metric("Vendedores", f"{dados['agentes']}")
    k6.metric("Lead Score", f"{dados['lead_score_medio']}")

    st.divider()

    # ── Comparativo por Canal ─────────────────────────────────────────────────
    canais_com_dados = [c for c in canais_sel if not df_f[df_f['canal'] == c].empty]
    if len(canais_com_dados) > 1:
        st.markdown("### 📡 Comparativo por Canal")
        col_canais = st.columns(len(canais_com_dados))
        for i, canal in enumerate(canais_com_dados):
            dc = df_f[df_f['canal'] == canal]
            d = _agregar_time(dc)
            with col_canais[i]:
                st.markdown(f"**{canal}**")
                st.metric("Nota Média", f"{d['nota_media']}")
                st.metric("Volume", f"{d['volume']}")
                st.metric("Vendedores", f"{d['agentes']}")
                st.metric("Lead Score", f"{d['lead_score_medio']}")

        canal_comp = (
            df_f.groupby('canal')['evaluation_ia']
            .agg(['mean', 'median', 'std', 'count'])
            .reset_index()
        )
        canal_comp.columns = ['Canal', 'Média', 'Mediana', 'Desvio', 'Volume']
        fig_comp = px.bar(
            canal_comp, x='Canal', y='Média', color='Canal',
            text_auto='.1f', title='Nota Média por Canal',
            color_discrete_map={'WhatsApp': '#25D366', 'Telefone': '#636EFA'},
        )
        fig_comp.update_layout(showlegend=False, yaxis_range=[0, 100])
        st.plotly_chart(fig_comp, use_container_width=True)

        st.divider()

    # ── Ranking de Vendedores ─────────────────────────────────────────────────
    st.markdown("### 🏆 Ranking do Time")
    ranking = (
        df_f.groupby(['agente', 'canal'])
        .agg(nota_media=('evaluation_ia', 'mean'), volume=('evaluation_ia', 'count'), lead_score=('lead_score', 'mean'))
        .reset_index()
        .sort_values('nota_media', ascending=False)
    )
    ranking['nota_media'] = ranking['nota_media'].round(1)
    ranking['lead_score'] = ranking['lead_score'].round(1)
    ranking.index = range(1, len(ranking) + 1)
    ranking.columns = ['Vendedor', 'Canal', 'Nota Média', 'Volume', 'Lead Score']
    st.dataframe(ranking, use_container_width=True, height=min(400, 35 * len(ranking) + 40))

    st.divider()

    # ── Distribuição de Notas e Qualidade de Leads ───────────────────────────
    col_dist1, col_dist2 = st.columns(2)
    with col_dist1:
        st.markdown("### 📊 Distribuição de Notas")
        fig_hist = px.histogram(
            df_f, x='evaluation_ia', nbins=20, color='canal',
            color_discrete_map={'WhatsApp': '#25D366', 'Telefone': '#636EFA'},
            title='Distribuição de Notas dos Vendedores',
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
            title='Distribuição de Leads por Classe',
        )
        st.plotly_chart(fig_lead, use_container_width=True)

    st.divider()

    # ── Gaps Coletivos ────────────────────────────────────────────────────────
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
            st.session_state['ag_diag'] = diag
            st.success("Diagnóstico gerado!")

    if 'ag_diag' in st.session_state:
        diag = st.session_state['ag_diag']

        st.markdown(f"## {diag.get('titulo', 'Diagnóstico')}")
        st.info(diag.get('resumo_executivo', ''))

        saude = diag.get('saude_do_time', {})
        if saude:
            nota_cor = {'A': '🟢', 'B': '🔵', 'C': '🟡', 'D': '🔴'}.get(saude.get('nota_geral', ''), '⚪')
            st.markdown(
                f"**Saúde do Time:** {nota_cor} **{saude.get('nota_geral', '—')}** — {saude.get('justificativa', '')}"
            )

        st.divider()

        comp = diag.get('comparativo_canais', {})
        if comp and len(canais_com_dados) > 1:
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

        gaps = diag.get('gaps_coletivos', [])
        if gaps:
            st.markdown("#### 🚨 Gaps Coletivos (problemas sistêmicos)")
            for g in gaps:
                gravidade_emoji = {'alta': '🔴', 'media': '🟡', 'baixa': '🟢'}.get(g.get('gravidade', ''), '⚪')
                with st.expander(
                    f"{gravidade_emoji} {g.get('gap', '')} — {g.get('frequencia', '')}", expanded=True
                ):
                    st.write(f"**Impacto:** {g.get('impacto_estimado', '')}")
                    st.write(f"**Causa raiz:** {g.get('causa_raiz', '')}")
                    st.write(f"**Ação:** {g.get('acao', '')}")

        destaques = diag.get('destaques_positivos', [])
        if destaques:
            st.markdown("#### ✅ Destaques Positivos")
            for d in destaques:
                st.success(f"**{d.get('destaque', '')}** — Puxado por: {d.get('quem_puxa', '')}")
                st.caption(f"Como replicar: {d.get('recomendacao', '')}")

        atencao = diag.get('vendedores_atencao', [])
        if atencao:
            st.markdown("#### ⚠️ Vendedores que Precisam de Atenção")
            for v in atencao:
                st.warning(f"**{v.get('nome', '')}** (nota {v.get('nota_media', '—')}) — Gap: {v.get('gap_principal', '')}")
                st.caption(f"Ação imediata: {v.get('acao_imediata', '')}")

        st.divider()

        plano = diag.get('plano_de_acao_30_dias', [])
        if plano:
            st.markdown("#### 📋 Plano de Ação — Próximos 30 Dias")
            for p in plano:
                st.markdown(f"**{p.get('semana', '')}** — {p.get('acao', '')}")
                st.caption(f"Responsável: {p.get('responsavel', '')} | Meta: {p.get('meta', '')}")

        meta = diag.get('meta_proxima_rodada', {})
        if meta:
            st.divider()
            st.markdown(f"### 🎯 Meta da Próxima Rodada: nota média **{meta.get('nota_media_alvo', '—')}**")
            st.write(f"Foco: **{meta.get('gap_foco', '')}**")
            st.write(f"Como medir: {meta.get('como_medir', '')}")

        st.divider()
        st.download_button(
            "📥 Baixar Diagnóstico (JSON)",
            data=json.dumps(diag, ensure_ascii=False, indent=2),
            file_name=f"diagnostico_global_{empresa}_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json",
            use_container_width=True,
        )


if __name__ == "__main__":
    run_page()
