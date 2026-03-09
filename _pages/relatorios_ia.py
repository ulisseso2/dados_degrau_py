import streamlit as st
import os
import json
import glob
import datetime as dt_module
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adsinsights import AdsInsights
from dotenv import load_dotenv
import yaml
import re
import io
from fpdf import FPDF

load_dotenv()
load_dotenv('.facebook_credentials.env', override=True)

HISTORICO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "historico")

# =====================================================
# GERAÇÃO DE PDF
# =====================================================

def gerar_pdf_relatorio(analise, dados_consolidados, data_ref, tipo="completo_ads"):
    """Gera um PDF formatado do relatório de análise."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Usa fonte built-in com suporte a caracteres latinos
    pdf.set_font("Helvetica", size=10)

    # --- Cabeçalho ---
    pdf.set_font("Helvetica", "B", 18)
    titulo_tipo = {
        "completo_ads": "Analise Completa de Ads",
        "alerta": "Alerta Diario",
        "seo": "Analise de SEO",
        "social": "Analise de Social Media",
    }.get(tipo, "Relatorio")
    pdf.cell(0, 12, _sanitize(titulo_tipo), new_x="LMARGIN", new_y="NEXT", align="C")

    pdf.set_font("Helvetica", size=10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6, f"Periodo: {data_ref}  |  Gerado em: {datetime.now().strftime('%d/%m/%Y as %H:%M')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(6)

    # Linha separadora
    pdf.set_draw_color(41, 128, 185)
    pdf.set_line_width(0.8)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(6)

    # --- Corpo da análise ---
    _render_markdown_to_pdf(pdf, analise)

    # --- Página de dados brutos ---
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Dados Brutos Enviados ao Claude", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Courier", size=7)
    for linha in dados_consolidados.split("\n"):
        pdf.cell(0, 4, _sanitize(linha[:120]), new_x="LMARGIN", new_y="NEXT")

    buffer = io.BytesIO()
    pdf.output(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def _sanitize(text):
    """Remove caracteres não suportados pela fonte Helvetica (latin-1)."""
    replacements = {
        "\u2014": "--", "\u2013": "-", "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u2022": "*",
        "\u2192": "->", "\u2190": "<-", "\u2265": ">=", "\u2264": "<=",
        "\u2260": "!=", "\u00b2": "2", "\u00b3": "3",
    }
    # Emojis e ícones comuns
    emoji_map = {
        "\U0001f680": "[ROCKET]", "\U0001f4ca": "[CHART]", "\U0001f4c1": "[FOLDER]",
        "\U0001f6a8": "[ALERT]", "\U0001f916": "[BOT]", "\U0001f3af": "[TARGET]",
        "\u2705": "[OK]", "\u274c": "[X]", "\u26a0\ufe0f": "[!]", "\u26a0": "[!]",
        "\U0001f4a1": "[IDEA]", "\U0001f525": "[FIRE]", "\U0001f4c8": "[UP]",
        "\U0001f4c9": "[DOWN]", "\u2b06\ufe0f": "[UP]", "\u2b07\ufe0f": "[DOWN]",
        "\U0001f4cb": "[LIST]", "\U0001f4dd": "[NOTE]",
    }
    replacements.update(emoji_map)
    for old, new in replacements.items():
        text = text.replace(old, new)
    # Remove qualquer caractere fora de latin-1
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _render_markdown_to_pdf(pdf, markdown_text):
    """Renderiza markdown básico (headers, bold, listas) no PDF."""
    lines = markdown_text.split("\n")
    for line in lines:
        stripped = line.strip()

        # Headers
        if stripped.startswith("### "):
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 6, _sanitize(stripped[4:]), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", size=10)
            continue
        if stripped.startswith("## "):
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", 13)
            pdf.cell(0, 7, _sanitize(stripped[3:]), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", size=10)
            continue
        if stripped.startswith("# "):
            pdf.ln(5)
            pdf.set_font("Helvetica", "B", 15)
            pdf.cell(0, 8, _sanitize(stripped[2:]), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", size=10)
            continue

        # Separadores
        if stripped in ("---", "***", "___"):
            pdf.ln(2)
            pdf.set_draw_color(200, 200, 200)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(3)
            continue

        # Lista
        if stripped.startswith("- ") or stripped.startswith("* "):
            texto = _sanitize(stripped[2:])
            texto = re.sub(r"\*\*(.+?)\*\*", r"\1", texto)  # remove bold markers
            left_margin = pdf.l_margin
            pdf.set_x(left_margin + 6)
            pdf.multi_cell(0, 5, f"* {texto}")
            continue

        # Linha vazia
        if not stripped:
            pdf.ln(3)
            continue

        # Texto normal (remove markdown bold)
        texto = _sanitize(stripped)
        texto = re.sub(r"\*\*(.+?)\*\*", r"\1", texto)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 5, texto)


# =====================================================
# CLASSIFICAÇÃO DE OBJETIVO (v2.0)
# =====================================================

OBJETIVO_MAP_META = {
    "OUTCOME_LEADS": "LEADS",
    "OUTCOME_TRAFFIC": "TRAFEGO",
    "OUTCOME_AWARENESS": "AWARENESS",
    "OUTCOME_ENGAGEMENT": "ENGAJAMENTO",
    "OUTCOME_SALES": "VENDAS",
    "LEAD_GENERATION": "LEADS",
    "LINK_CLICKS": "TRAFEGO",
    "REACH": "AWARENESS",
    "VIDEO_VIEWS": "VIDEO",
    "CONVERSIONS": "VENDAS",
    "POST_ENGAGEMENT": "ENGAJAMENTO",
}

OBJETIVO_MAP_GOOGLE = {
    "SEARCH": "LEADS",
    "PERFORMANCE_MAX": "LEADS",
    "DISPLAY": "AWARENESS",
    "VIDEO": "VIDEO",
}

def classificar_por_nome(nome_campanha):
    """Fallback: classifica objetivo pela convenção de nomenclatura."""
    nome = nome_campanha.upper()
    if any(tag in nome for tag in ["[RMKT]", "REMARKETING", "RETARGETING"]):
        return "REMARKETING"
    if any(tag in nome for tag in ["[TOFU]", "TRAFEGO", "BLOG", "AQUECIMENTO"]):
        return "TRAFEGO"
    if any(tag in nome for tag in ["[VSL]", "VIDEO", "THRUPLAY", "VVC"]):
        return "VIDEO"
    if any(tag in nome for tag in ["[AWARENESS]", "ALCANCE", "REACH"]):
        return "AWARENESS"
    if any(tag in nome for tag in ["[VENDA]", "MATRICULA", "CHECKOUT"]):
        return "VENDAS"
    return "LEADS"

# =====================================================
# FUNÇÕES DE COLETA
# =====================================================

def formatar_reais(valor):
    if pd.isna(valor) or valor == 0:
        return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def init_google_ads_client(yaml_file="google-ads.yaml"):
    try:
        google_ads_config = st.secrets["google_ads"]
        config_dict = {
            "developer_token": google_ads_config["developer_token"],
            "client_id": google_ads_config["client_id"],
            "client_secret": google_ads_config["client_secret"],
            "refresh_token": google_ads_config["refresh_token"],
            "login_customer_id": str(google_ads_config["login_customer_id"]),
            "use_proto_plus": google_ads_config.get("use_proto_plus", True)
        }
        return GoogleAdsClient.load_from_string(yaml.dump(config_dict))
    except (st.errors.StreamlitAPIException, KeyError):
        if os.path.exists(yaml_file):
            return GoogleAdsClient.load_from_storage(yaml_file)
    return None

def init_google_ads_client_central():
    try:
        google_ads_config = st.secrets["google_ads_central"]
        config_dict = {
            "developer_token": google_ads_config["developer_token"],
            "client_id": google_ads_config["client_id"],
            "client_secret": google_ads_config["client_secret"],
            "refresh_token": google_ads_config["refresh_token"],
            "login_customer_id": str(google_ads_config["login_customer_id"]),
            "use_proto_plus": google_ads_config.get("use_proto_plus", True)
        }
        return GoogleAdsClient.load_from_string(yaml.dump(config_dict))
    except (st.errors.StreamlitAPIException, KeyError):
        yaml_file = "google-ads_central.yaml"
        if os.path.exists(yaml_file):
            return GoogleAdsClient.load_from_storage(yaml_file)
    return None

def get_google_ads_data(client, customer_id, start_date, end_date):
    """Busca dados do Google Ads incluindo tipo de campanha para classificação de objetivo."""
    try:
        ga_service = client.get_service("GoogleAdsService")
        query = f"""
            SELECT
                campaign.name,
                campaign.id,
                campaign.status,
                campaign.advertising_channel_type,
                metrics.cost_micros,
                metrics.impressions,
                metrics.clicks,
                metrics.ctr,
                metrics.average_cpc,
                metrics.conversions,
                metrics.cost_per_conversion
            FROM campaign
            WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
                AND campaign.status = 'ENABLED'
            ORDER BY metrics.cost_micros DESC
        """
        response = ga_service.search(customer_id=customer_id, query=query)
        rows = []
        for row in response:
            custo = row.metrics.cost_micros / 1_000_000
            cpc = row.metrics.average_cpc / 1_000_000 if row.metrics.average_cpc else 0
            cpa = row.metrics.cost_per_conversion / 1_000_000 if row.metrics.cost_per_conversion else 0

            # Classificação de objetivo
            channel_type = str(row.campaign.advertising_channel_type).split(".")[-1]
            objetivo_api = OBJETIVO_MAP_GOOGLE.get(channel_type)
            objetivo = objetivo_api if objetivo_api else classificar_por_nome(row.campaign.name)

            rows.append({
                'Campanha': row.campaign.name,
                'Objetivo': objetivo,
                'Custo': round(custo, 2),
                'Impressões': row.metrics.impressions,
                'Cliques': row.metrics.clicks,
                'CTR (%)': round(row.metrics.ctr * 100, 2),
                'CPC': round(cpc, 2),
                'Conversões': round(row.metrics.conversions, 1),
                'CPA': round(cpa, 2),
            })
        return pd.DataFrame(rows)
    except Exception as e:
        st.error(f"Erro Google Ads: {e}")
        return pd.DataFrame()

def init_facebook_api():
    app_id, app_secret, access_token, ad_account_id = None, None, None, None
    try:
        creds = st.secrets["facebook_api"]
        app_id = creds["app_id"]
        app_secret = creds["app_secret"]
        access_token = creds["access_token"]
        ad_account_id = creds["ad_account_id"]
    except (st.errors.StreamlitAPIException, KeyError):
        app_id = os.getenv("FB_APP_ID")
        app_secret = os.getenv("FB_APP_SECRET")
        access_token = os.getenv("FB_ACCESS_TOKEN")
        ad_account_id = os.getenv("FB_AD_ACCOUNT_ID")
    if not all([app_id, app_secret, access_token, ad_account_id]):
        return None
    try:
        FacebookAdsApi.init(app_id=app_id, app_secret=app_secret, access_token=access_token)
        return AdAccount(ad_account_id)
    except Exception:
        return None

def get_facebook_data(account, start_date, end_date):
    """Busca dados do Meta Ads incluindo objetivo da campanha para classificação."""
    try:
        fields = [
            AdsInsights.Field.campaign_name,
            AdsInsights.Field.objective,
            AdsInsights.Field.spend,
            AdsInsights.Field.impressions,
            AdsInsights.Field.clicks,
            AdsInsights.Field.ctr,
            AdsInsights.Field.cpc,
            AdsInsights.Field.cpm,
            AdsInsights.Field.reach,
            AdsInsights.Field.frequency,
            AdsInsights.Field.actions,
            AdsInsights.Field.cost_per_action_type,
        ]
        params = {
            'level': 'campaign',
            'time_range': {'since': start_date, 'until': end_date},
        }
        insights = account.get_insights(fields=fields, params=params)
        rows = []
        for insight in insights:
            conversoes = 0
            cpa = 0
            if AdsInsights.Field.actions in insight:
                for action in insight[AdsInsights.Field.actions]:
                    if action['action_type'] in ['purchase', 'lead', 'omni_purchase', 'offsite_conversion.fb_pixel_purchase']:
                        conversoes += int(action.get('value', 0))
            if AdsInsights.Field.cost_per_action_type in insight:
                for cost_action in insight[AdsInsights.Field.cost_per_action_type]:
                    if cost_action['action_type'] in ['purchase', 'lead', 'omni_purchase', 'offsite_conversion.fb_pixel_purchase']:
                        cpa = float(cost_action.get('value', 0))
                        break

            # Classificação de objetivo via API
            obj_api = insight.get(AdsInsights.Field.objective, "")
            objetivo = OBJETIVO_MAP_META.get(obj_api)
            if not objetivo:
                objetivo = classificar_por_nome(insight[AdsInsights.Field.campaign_name])

            rows.append({
                'Campanha': insight[AdsInsights.Field.campaign_name],
                'Objetivo': objetivo,
                'Custo': float(insight[AdsInsights.Field.spend]),
                'Impressões': int(insight.get(AdsInsights.Field.impressions, 0)),
                'Cliques': int(insight.get(AdsInsights.Field.clicks, 0)),
                'CTR (%)': float(insight.get(AdsInsights.Field.ctr, 0)),
                'CPC': float(insight.get(AdsInsights.Field.cpc, 0)),
                'CPM': float(insight.get(AdsInsights.Field.cpm, 0)),
                'Alcance': int(insight.get(AdsInsights.Field.reach, 0)),
                'Frequência': float(insight.get(AdsInsights.Field.frequency, 0)),
                'Conversões': conversoes,
                'CPA': cpa,
            })
        return pd.DataFrame(rows)
    except Exception as e:
        st.error(f"Erro Meta Ads: {e}")
        return pd.DataFrame()

# =====================================================
# FORMATAÇÃO DOS DADOS POR OBJETIVO (v2.0)
# =====================================================

def formatar_dados_para_claude(df_google_degrau, df_google_central, df_facebook, data_ref, janela_dias):
    """Formata os dados agrupados por OBJETIVO para o Claude analisar corretamente."""
    hoje = datetime.now().date()
    inicio = hoje - timedelta(days=janela_dias)
    dia_semana = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"][hoje.weekday()]

    linhas = []
    linhas.append("=== METADADOS ===")
    linhas.append(f"Período: {inicio.strftime('%d/%m/%Y')} a {hoje.strftime('%d/%m/%Y')}")
    linhas.append(f"Janela: {janela_dias} dias")
    linhas.append(f"Tipo de relatório: {'Alerta diário' if janela_dias == 1 else 'Análise completa'}")
    linhas.append(f"Data de hoje: {hoje.strftime('%d/%m/%Y')} ({dia_semana})")
    linhas.append("")

    # Combina todos os dataframes com tag de origem
    dfs = []
    if not df_google_degrau.empty:
        df_gd = df_google_degrau.copy()
        df_gd['Origem'] = 'Google Ads (Degrau)'
        dfs.append(df_gd)
    if not df_google_central.empty:
        df_gc = df_google_central.copy()
        df_gc['Origem'] = 'Google Ads (Central)'
        dfs.append(df_gc)
    if not df_facebook.empty:
        df_fb = df_facebook.copy()
        df_fb['Origem'] = 'Meta Ads'
        dfs.append(df_fb)

    if not dfs:
        return "Nenhum dado coletado."

    df_all = pd.concat(dfs, ignore_index=True)

    # Totais gerais
    custo_total = df_all['Custo'].sum()
    conv_total = df_all['Conversões'].sum()
    linhas.append(f"=== TOTAIS GERAIS ===")
    linhas.append(f"Custo total: R${custo_total:.2f}")
    linhas.append(f"Conversões total: {conv_total}")
    linhas.append("")

    # Agrupa por objetivo
    objetivos_ordem = ["LEADS", "VENDAS", "REMARKETING", "TRAFEGO", "VIDEO", "AWARENESS", "ENGAJAMENTO"]
    objetivos_presentes = [obj for obj in objetivos_ordem if obj in df_all['Objetivo'].values]

    for obj in objetivos_presentes:
        df_obj = df_all[df_all['Objetivo'] == obj]
        custo_obj = df_obj['Custo'].sum()
        conv_obj = df_obj['Conversões'].sum()

        linhas.append(f"=== [OBJETIVO: {obj}] ===")
        linhas.append(f"Total de campanhas: {len(df_obj)} | Custo: R${custo_obj:.2f} | Conversões: {conv_obj}")

        if conv_obj > 0 and obj in ["LEADS", "VENDAS", "REMARKETING"]:
            cpa_medio = custo_obj / conv_obj
            linhas.append(f"CPA médio: R${cpa_medio:.2f} | Volume de conversões: {conv_obj} {'(ATENÇÃO: <30 conversões, dados insuficientes para decisão)' if conv_obj < 30 else ''}")

        # Cabeçalho de colunas por objetivo
        if obj in ["LEADS", "VENDAS"]:
            linhas.append("Origem | Campanha | Impress | Cliques | CTR | Gasto | Conv | CPA")
        elif obj == "TRAFEGO":
            linhas.append("Origem | Campanha | Impress | Cliques | CTR | CPC | CPM | Gasto")
        elif obj == "REMARKETING":
            has_freq = 'Frequência' in df_obj.columns and df_obj['Frequência'].sum() > 0
            linhas.append("Origem | Campanha | Impress | Freq | Cliques | CTR | Gasto | Conv | CPA")
        elif obj == "VIDEO":
            linhas.append("Origem | Campanha | Impress | Cliques | CTR | CPM | Gasto")
        else:
            linhas.append("Origem | Campanha | Impress | Cliques | CTR | CPC | Gasto")

        for _, r in df_obj.iterrows():
            origem = r.get('Origem', '')
            freq = f" | {r.get('Frequência', '-')}" if obj == "REMARKETING" else ""
            cpm_val = f" | R${r.get('CPM', 0):.2f}" if obj in ["TRAFEGO", "VIDEO"] else ""

            if obj in ["LEADS", "VENDAS"]:
                linhas.append(
                    f"{origem} | {r['Campanha']} | {r['Impressões']:,} | {r['Cliques']:,} | "
                    f"{r['CTR (%)']}% | R${r['Custo']:.2f} | {r['Conversões']} | R${r['CPA']:.2f}"
                )
            elif obj == "REMARKETING":
                freq_val = r.get('Frequência', 0)
                linhas.append(
                    f"{origem} | {r['Campanha']} | {r['Impressões']:,} | {freq_val} | {r['Cliques']:,} | "
                    f"{r['CTR (%)']}% | R${r['Custo']:.2f} | {r['Conversões']} | R${r['CPA']:.2f}"
                )
            elif obj == "TRAFEGO":
                cpm = r.get('CPM', 0)
                linhas.append(
                    f"{origem} | {r['Campanha']} | {r['Impressões']:,} | {r['Cliques']:,} | "
                    f"{r['CTR (%)']}% | R${r['CPC']:.2f} | R${cpm:.2f} | R${r['Custo']:.2f}"
                )
            else:
                cpm = r.get('CPM', 0)
                linhas.append(
                    f"{origem} | {r['Campanha']} | {r['Impressões']:,} | {r['Cliques']:,} | "
                    f"{r['CTR (%)']}% | R${cpm:.2f} | R${r['Custo']:.2f}"
                )
        linhas.append("")

    return "\n".join(linhas)

# =====================================================
# SYSTEM PROMPTS v2.0
# =====================================================

SYSTEM_PROMPT_ADS_V2 = """
Você é um analista sênior de tráfego pago especializado em
marketing educacional brasileiro para concursos públicos.
Você trabalha para Central de Concursos e Degrau Cultural.

=== REGRA FUNDAMENTAL ===
Cada campanha tem um OBJETIVO declarado nos dados. Você DEVE
avaliar cada campanha APENAS pelas métricas corretas para
seu objetivo. Nunca avalie uma campanha de tráfego por CPA.
Nunca avalie uma campanha de vídeo por custo por lead.

=== OBJETIVOS E SUAS MÉTRICAS ===

LEADS (captura de leads):
  - Métricas: CPL, taxa conversão LP, volume de leads, custo
    por lead qualificado
  - Benchmark interno: CPL alvo R$25-40 (varia por concurso)
  - Alerta: CPL >30% acima da média do concurso específico
  - Janela mínima para decisão: 3-5 dias OU 30+ conversões
  - Se tiver <30 conversões no período, SINALIZE que os dados
    são insuficientes para conclusões de CPA

TRAFEGO (aquecimento / TOFU):
  - Métricas: CPC, CTR, CPM, sessões geradas, tempo médio
    no site, páginas/sessão, tamanho do remarketing alimentado
  - NUNCA avalie por CPA ou CPL - não é o propósito
  - Sucesso = CPC baixo + tempo no site alto + remarketing crescendo
  - Janela mínima: 5-7 dias

REMARKETING (retargeting):
  - Métricas: CPA, taxa conversão, frequência, ROAS
  - Alerta: frequência >4.0 (fadiga de audiência)
  - Alerta: audiência <1.000 pessoas (volume insuficiente)
  - Janela mínima: 7 dias (audiência limitada = flutuação alta)
  - Nunca recomende pausar remarketing por CPA alto em <7 dias

VIDEO (awareness / VSL):
  - Métricas: CPV, ThruPlay rate, retenção média, custo por
    ThruPlay, tamanho da audiência de video viewers criada
  - Sucesso = retenção >50% no hook (3s) e >25% no total
  - Janela mínima: 5-7 dias
  - NUNCA avalie por CPA - não é o propósito

VENDAS (matrícula / fundo de funil):
  - Métricas: CPA, ROAS, ticket médio, volume de vendas
  - Janela mínima: 5-7 dias OU 30+ conversões
  - Se tiver <30 conversões, SINALIZE insuficiência

=== ESTRUTURA DO RELATÓRIO ===

1. RESUMO EXECUTIVO (3-5 linhas)
   - Gasto total, resultado geral por objetivo
   - Destaque positivo e destaque negativo da semana

2. ANÁLISE POR OBJETIVO
   Para cada grupo de objetivo, apresente:

   2a. CAMPANHAS DE LEADS
       - Top 3 por CPL (melhor performance)
       - Bottom 3 por CPL (pior performance)
       - Volume total de leads e CPL médio
       - Campanhas com <30 conversões: listar mas SINALIZAR
         que dados são insuficientes para decisão

   2b. CAMPANHAS DE TRÁFEGO
       - CPC médio e CTR médio
       - Melhores e piores por custo/qualidade de sessão
       - Impacto no remarketing (audiência gerada)
       - NUNCA mencione CPA aqui

   2c. CAMPANHAS DE REMARKETING
       - CPA, taxa conversão, frequência
       - Alertas de fadiga de audiência
       - Se dados <7 dias: sinalizar incerteza

   2d. CAMPANHAS DE VÍDEO
       - Retenção, ThruPlay rate, CPV
       - Criativos com retenção <30% (hook fraco)
       - NUNCA mencione CPA aqui

   2e. CAMPANHAS DE VENDAS
       - CPA, ROAS, volume
       - Mesmas regras de volume mínimo de LEADS

3. ALERTAS E ANOMALIAS
   - Campanhas que pararam de entregar
   - Gasto disparou sem proporção de resultado
   - Frequência >4 em remarketing
   - CPA >50% acima do benchmark do concurso
   - IMPORTANTE: só alerte sobre CPA em campanhas de
     LEADS ou VENDAS com 30+ conversões

4. VISÃO DE FUNIL
   - Quanto tráfego TOFU está alimentando o remarketing?
   - O remarketing está convertendo esse tráfego?
   - Há gargalos no funil? (muito TOFU e pouco RMKT,
     ou RMKT com audiência pequena)

5. RECOMENDAÇÕES ACIONÁVEIS
   - Separar por objetivo
   - Incluir NÍVEL DE CONFIANÇA da recomendação:
     [ALTA] = 50+ conversões, dados claros
     [MÉDIA] = 30-50 conversões, tendência visível
     [BAIXA] = <30 conversões, sugestão preliminar
   - O que pausar, escalar ou testar
   - Sugestões de copy/criativo quando pertinente

6. COMPARAÇÃO COM PERÍODO ANTERIOR
   - Variações % das métricas-chave de cada objetivo
   - Tendências em formação (3 períodos consecutivos)

=== REGRAS GERAIS ===
- Nunca invente dados. Se faltam métricas, sinalize.
- Valores monetários em R$ (reais).
- Seja direto e acionável, sem corporativês.
- Considere o nicho de concursos públicos.
- NUNCA recomende pausar uma campanha que não é de LEADS
  ou VENDAS por "não estar gerando conversões".
- NUNCA tire conclusões de CPA com <30 conversões.
- Quando dados forem insuficientes, diga explicitamente
  "dados insuficientes para decisão — aguardar mais X dias".
"""

SYSTEM_PROMPT_ALERTA_DIARIO = """
Você é um monitor de tráfego pago e orgânico para
Central de Concursos e Degrau Cultural.

Seu objetivo é APENAS identificar anomalias que exigem
ação imediata. NÃO faça análise completa.

=== ALERTAR APENAS SE ===

ADS:
- Campanha ativa com 0 impressões (possível reprovação)
- Gasto diário >2x o gasto médio diário da campanha
- CPA diário >3x o CPA médio (só para LEADS/VENDAS)
- Campanha de REMARKETING com frequência >5 no dia
- Erro de pixel/tracking (conversões = 0 em todas campanhas)

ORGÂNICO:
- Post/vídeo viralizando (>5x média de views em 24h)
- Queda de sessões do blog >40% vs mesmo dia semana passada
- Página desindexada (impressões caem a 0)
- Comentários negativos em volume incomum

=== FORMATO DA RESPOSTA ===

Se NÃO houver anomalias:
"✅ Tudo normal. Nenhuma anomalia detectada."

Se houver anomalias:
"🚨 ALERTA [TIPO]: [descrição curta]
Ação sugerida: [o que fazer agora]"

Máximo 5 alertas. Priorize por gravidade.
NÃO inclua análises, recomendações estratégicas ou
comentários gerais. Só alertas acionáveis.
"""

SYSTEM_PROMPT_SOCIAL_V2 = """
Você é um analista sênior de social media especializado em
marketing educacional brasileiro para concursos públicos.
Você analisa Central de Concursos e Degrau Cultural.

=== PERIODICIDADE E CONTEXTO ===
Os dados que você recebe cobrem uma semana completa
(segunda a domingo). Compare SEMPRE com a semana anterior
quando dados estiverem disponíveis.

Ciclos naturais por plataforma:
- Instagram: post performa em 48-72h; Reels até 7 dias
- TikTok: 24h a 7 dias (redistribuição algorítmica)
- YouTube: 7-14 dias (algoritmo lento, long tail)
- Facebook: 48-72h (alcance orgânico decrescente)

Não compare vídeos de 2 dias com vídeos de 7 dias.
Ao listar performance de posts, SEMPRE inclua a idade
do post (quantos dias desde publicação) para contextualizar.

=== MÉTRICAS POR TIPO DE CONTEÚDO ===

REELS / TIKTOK (vídeo curto):
  - Métrica primordial: Completion Rate (% que assistiu até o fim)
  - Secundárias: shares (viralidade), saves (valor), views
  - Completion <30% = hook fraco
  - Completion >60% = conteúdo excelente
  - Shares alto + saves alto = conteúdo viral E útil

FEED / CARROSSEL:
  - Métrica primordial: Taxa de Salvamento (saves/alcance)
  - Secundárias: engajamento, comentários, shares
  - Para concursos, saves > likes em importância
    (salvar = "vou estudar isso depois")

STORIES:
  - Respostas e taps back (indicam interesse)
  - Exits e taps forward (indicam desinteresse)
  - Taxa de saída por story para identificar onde perde atenção

YOUTUBE (vídeo longo):
  - CTR de thumbnail (benchmark: >5% bom, >8% excelente)
  - Retenção média (benchmark: >40% bom, >50% excelente)
  - Watch time total (mais importante que views)
  - Inscritos ganhos por vídeo

=== ESTRUTURA DO RELATÓRIO ===

1. RESUMO EXECUTIVO
   - Visão cross-platform em 3-5 linhas
   - Destaque da semana (melhor conteúdo + por quê)
   - Crescimento de seguidores (todas as plataformas)

2. INSTAGRAM
   - Alcance e impressões (% vs semana anterior)
   - Top 3 posts por engajamento (com idade do post)
   - Taxa de salvamento média
   - Performance Reels vs Feed vs Carrossel vs Stories
   - Melhor horário de publicação (se dado disponível)

3. TIKTOK
   - Views totais e média por vídeo
   - Completion rate médio
   - Top 3 vídeos por share rate (viralidade)
   - Temas/formatos que mais performaram

4. YOUTUBE
   - Watch time total da semana
   - CTR média de thumbnails
   - Retenção média
   - Inscritos ganhos vs perdidos
   - ATENÇÃO: vídeos recentes (<7 dias) podem não ter
     dados maduros. Sinalize quando for o caso.

5. FACEBOOK
   - Alcance orgânico e engajamento
   - Comparação com semana anterior

6. ALERTAS
   - Post/vídeo viralizando (>3x média de views)
   - Queda de alcance >20% sem mudança de frequência
   - Vídeos com retenção <30% (hook fraco)
   - Engajamento negativo (comentários críticos em alta)

7. RECOMENDAÇÕES DE CONTEÚDO
   - Formatos para REPLICAR (com justificativa em dados)
   - Formatos para EVITAR (com justificativa em dados)
   - 3-5 sugestões de temas baseadas em:
     a) O que performou esta semana
     b) Concursos com editais próximos (se informado)
     c) Dores do público evidenciadas nos comentários/saves
   - Cross-posting: conteúdo do IG que pode ir pro TikTok
     e vice-versa (com adaptações)

=== REGRAS ===
- Nunca invente dados.
- Sempre contextualize a idade do post ao avaliar performance.
- Para concursos, conteúdo de VALOR (dicas, resumos, mapas
  mentais) tende a performar melhor que conteúdo motivacional
  genérico. Favoreça recomendações nessa direção.
- Recomendações devem ser específicas, não genéricas.
  Em vez de "poste mais Reels", diga "Reels de 15-20s
  com dicas rápidas de [tema X] tiveram 2x mais completion."
"""

SYSTEM_PROMPT_SEO_V2 = """
Você é um analista de SEO e conteúdo especializado em
marketing educacional brasileiro para concursos públicos.

=== PERIODICIDADE E CONTEXTO ===

Dados do Google Search Console têm delay de 2-3 dias.
Os dados que você recebe devem ser comparados com o período
equivalente anterior.

Regras de temporalidade:
- Mudanças de posição <2 posições em 1 semana = flutuação
  normal, NÃO sinalize como queda ou ganho
- Mudanças de posição >5 posições = tendência real, SINALIZE
- Mudanças de 2-5 posições = acompanhar na próxima semana
- CTR varia muito com sazonalidade de editais. Sempre
  considere se há edital recente influenciando buscas.

Para Blog (GA4): análise semanal é adequada.
Para SEO (GSC): análise quinzenal/mensal é ideal.
Se receber dados semanais de SEO, seja conservador nas
conclusões e sinalize quando a janela é curta demais.

=== CONTEXTO DO NICHO ===

Concursos públicos têm sazonalidade forte:
- Publicação de edital = pico de busca (dias)
- Próximo à prova = pico de busca (semanas antes)
- Pós-prova = pico de gabarito/resultado (1-2 dias)
- Entre editais = volume baixo, foco em evergreen

Tipos de conteúdo por intenção:
- TRANSACIONAL: "inscrição concurso X", "curso preparatorio X"
  -> Prioridade máxima, converter em lead/matrícula
- INFORMACIONAL-QUENTE: "edital concurso X", "vagas concurso X"
  -> Alta prioridade, público próximo da decisão
- INFORMACIONAL-FRIA: "o que faz um [cargo]", "como estudar para"
  -> Média prioridade, funil de topo
- NAVEGACIONAL: "central de concursos", "degrau cultural"
  -> Marca, monitorar mas não otimizar

=== ESTRUTURA DO RELATÓRIO ===

1. RESUMO DO BLOG (GA4)
   - Sessões totais, usuários, pageviews
   - Canal principal de aquisição (% por canal)
   - Mobile vs Desktop (% e diferenças de comportamento)
   - Taxa de conversão geral
   - Comparação vs período anterior (% variação)

2. TOP 10 PÁGINAS (por tráfego orgânico)
   - Cliques, impressões, CTR, posição média
   - Classificar por INTENÇÃO (transacional/informacional)
   - Sinalizar se há edital ativo influenciando

3. QUICK WINS DE SEO
   - Queries com posição 5-20 E >100 impressões/semana
   - Priorizar por INTENÇÃO: transacional > informacional-quente
     > informacional-fria
   - Para cada quick win, sugerir ação específica
   - NÍVEL DE CONFIANÇA: [ALTA] ou [MÉDIA]

4. PROBLEMAS DE CTR
   - Páginas com posição <5 e CTR <5%
   - Sugerir title tag e meta description otimizados
   - Usar gatilhos do nicho: vagas, salário, data da prova

5. CANIBALIZAÇÃO
   - Queries com 2+ páginas competindo
   - Só sinalize como canibalização se ambas estiverem
     na posição >5

6. OPORTUNIDADES DE CONTEÚDO
   - Queries com volume mas sem página dedicada
   - Artigos desatualizados (>6 meses sem update + queda)
   - Priorizar por potencial de conversão

7. COMPARAÇÃO COM PERÍODO ANTERIOR
   - Páginas que ganharam >5 posições (celebrar)
   - Páginas que perderam >5 posições (diagnosticar)
   - Flutuações de 1-2 posições: IGNORAR (ruído)

=== REGRAS ===
- Nunca invente dados ou posições.
- Priorize sempre conteúdo transacional sobre informacional.
- Considere sazonalidade de editais ao interpretar picos/quedas.
- Flutuações de 1-2 posições em 1 semana são NORMAIS.
- Se os dados cobrem <14 dias, sinalize que conclusões
  de SEO são PRELIMINARES.
- Sugestões de title/description devem ser específicas
  e prontas para implementar, não genéricas.
"""

# =====================================================
# LÓGICA DE PERIODICIDADE (v2.0)
# =====================================================

def selecionar_config_automatica():
    """Seleciona prompt e janela baseado no dia da semana."""
    hoje = datetime.now().date()
    dia_semana = hoje.weekday()  # 0=segunda

    configs = []

    # Alerta diário (seg a sex)
    if dia_semana in [0, 1, 2, 3, 4]:
        configs.append({
            "nome": "Alerta Diário (Ads)",
            "prompt": SYSTEM_PROMPT_ALERTA_DIARIO,
            "janela": 1,
            "tipo": "alerta",
        })

    # Segunda: relatório completo de ads (7 dias)
    if dia_semana == 0:
        configs.append({
            "nome": "Relatório Semanal de Ads",
            "prompt": SYSTEM_PROMPT_ADS_V2,
            "janela": 7,
            "tipo": "completo_ads",
        })

    # Quarta: relatório de SEO (14 dias)
    if dia_semana == 2:
        configs.append({
            "nome": "Relatório Quinzenal de SEO",
            "prompt": SYSTEM_PROMPT_SEO_V2,
            "janela": 14,
            "tipo": "seo",
        })

    # Se não caiu em nenhum especial (sábado/domingo), padrão = alerta
    if not configs:
        configs.append({
            "nome": "Alerta Diário (Ads)",
            "prompt": SYSTEM_PROMPT_ALERTA_DIARIO,
            "janela": 1,
            "tipo": "alerta",
        })

    return configs

# =====================================================
# ANÁLISE VIA CLAUDE (v2.0)
# =====================================================

def _get_anthropic_client():
    """Inicializa o client Anthropic de forma segura."""
    try:
        import anthropic
    except ImportError:
        return None, "❌ Biblioteca `anthropic` não instalada. Execute: `pip install anthropic`"

    api_key = None
    try:
        api_key = st.secrets.get("ANTHROPIC_API_KEY")
    except (st.errors.StreamlitAPIException, KeyError):
        pass
    if not api_key:
        api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None, "❌ API Key do Claude não configurada. Defina ANTHROPIC_API_KEY no .env ou Streamlit Secrets."

    return anthropic.Anthropic(api_key=api_key), None

def analisar_com_claude(dados_consolidados, system_prompt=None, tipo_relatorio="completo_ads"):
    """Envia dados para o Claude e retorna a análise usando o prompt correto."""
    client, erro = _get_anthropic_client()
    if erro:
        return erro

    if system_prompt is None:
        system_prompt = SYSTEM_PROMPT_ADS_V2

    if tipo_relatorio == "alerta":
        user_msg = f"Dados de ontem:\n\n{dados_consolidados}\n\nVerifique se há anomalias conforme as regras."
    else:
        user_msg = f"Segue o relatório de performance do período:\n\n{dados_consolidados}\n\nAnalise conforme a estrutura definida."

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_msg}]
    )
    return message.content[0].text

# =====================================================
# HISTÓRICO DE RELATÓRIOS
# =====================================================

def salvar_relatorio(analise, dados_consolidados, data_ref, tipo="completo_ads"):
    """Salva o relatório gerado em data/historico/."""
    os.makedirs(HISTORICO_DIR, exist_ok=True)
    relatorio = {
        "data": data_ref,
        "tipo": tipo,
        "gerado_em": datetime.now().isoformat(),
        "dados_brutos": dados_consolidados,
        "analise_claude": analise,
    }
    filepath = os.path.join(HISTORICO_DIR, f"relatorio_{tipo}_{data_ref}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(relatorio, f, ensure_ascii=False, indent=2)
    return filepath

def carregar_relatorios_historico(filtro_tipo=None):
    """Carrega lista de relatórios do histórico."""
    if not os.path.exists(HISTORICO_DIR):
        return []
    arquivos = sorted(glob.glob(os.path.join(HISTORICO_DIR, "relatorio_*.json")), reverse=True)
    relatorios = []
    for arq in arquivos:
        try:
            with open(arq, "r", encoding="utf-8") as f:
                data = json.load(f)
                tipo = data.get("tipo", "completo_ads")
                if filtro_tipo and tipo != filtro_tipo:
                    continue
                relatorios.append({
                    "arquivo": arq,
                    "data": data.get("data", ""),
                    "tipo": tipo,
                    "gerado_em": data.get("gerado_em", ""),
                    "analise": data.get("analise_claude", ""),
                    "dados_brutos": data.get("dados_brutos", ""),
                })
        except (json.JSONDecodeError, KeyError):
            continue
    return relatorios

# =====================================================
# PÁGINA STREAMLIT (v2.0)
# =====================================================

def run_page():
    st.title("🤖 Relatórios IA — Análise de Campanhas com Claude")
    st.markdown("Análise estratégica automatizada por **objetivo de campanha** com níveis de confiança (v2.0)")

    tab_ads, tab_alerta, tab_historico = st.tabs([
        "📊 Análise Completa (Ads)",
        "🚨 Alerta Diário",
        "📁 Histórico",
    ])

    # ----- SIDEBAR GLOBAL -----
    st.sidebar.header("⚙️ Configurações")
    hoje = datetime.now().date()
    ontem = hoje - timedelta(days=1)

    contas = st.sidebar.multiselect(
        "Contas para incluir:",
        ["Google Ads (Degrau)", "Google Ads (Central)", "Meta Ads"],
        default=["Google Ads (Degrau)", "Google Ads (Central)", "Meta Ads"],
        key="ria_contas"
    )

    # Agenda automática
    configs_auto = selecionar_config_automatica()
    nomes_auto = [c["nome"] for c in configs_auto]
    st.sidebar.info(f"📅 Hoje ({hoje.strftime('%d/%m/%Y')}): {', '.join(nomes_auto)}")

    # =========================================================
    # ABA 1: ANÁLISE COMPLETA DE ADS
    # =========================================================
    with tab_ads:
        st.header("📊 Análise Completa de Tráfego Pago")
        st.caption("Avalia cada campanha pelo seu **objetivo real** (LEADS, TRAFEGO, REMARKETING, VIDEO, VENDAS)")

        modo = st.radio("Período:", ["Últimos 7 dias", "Personalizado"], key="ria_ads_modo", horizontal=True)

        if modo == "Últimos 7 dias":
            start_date = hoje - timedelta(days=7)
            end_date = ontem
            janela_dias = 7
        else:
            periodo = st.date_input("Selecione:", [hoje - timedelta(days=7), ontem], key="ria_ads_periodo")
            if len(periodo) != 2:
                st.warning("Selecione um período válido.")
                st.stop()
            start_date, end_date = periodo
            janela_dias = (end_date - start_date).days + 1

        st.info(f"📅 **{start_date.strftime('%d/%m/%Y')}** a **{end_date.strftime('%d/%m/%Y')}** ({janela_dias} dias)")

        if st.button("🚀 Gerar Análise Completa", type="primary", use_container_width=True, key="btn_ads"):
            _executar_analise(contas, start_date, end_date, janela_dias, SYSTEM_PROMPT_ADS_V2, "completo_ads")

    # =========================================================
    # ABA 2: ALERTA DIÁRIO
    # =========================================================
    with tab_alerta:
        st.header("🚨 Alerta Diário — Detecção de Anomalias")
        st.caption("Verifica apenas se há problemas que exigem ação imediata. Rápido e objetivo.")

        start_alerta = ontem
        end_alerta = ontem

        st.info(f"📅 Verificando dados de ontem: **{start_alerta.strftime('%d/%m/%Y')}**")

        if st.button("🔍 Verificar Anomalias", type="primary", use_container_width=True, key="btn_alerta"):
            _executar_analise(contas, start_alerta, end_alerta, 1, SYSTEM_PROMPT_ALERTA_DIARIO, "alerta")

    # =========================================================
    # ABA 3: HISTÓRICO
    # =========================================================
    with tab_historico:
        st.header("📁 Relatórios Anteriores")

        filtro = st.selectbox("Filtrar por tipo:", ["Todos", "completo_ads", "alerta"], key="ria_hist_filtro")
        filtro_tipo = None if filtro == "Todos" else filtro

        relatorios = carregar_relatorios_historico(filtro_tipo)

        if not relatorios:
            st.info("Nenhum relatório gerado ainda.")
        else:
            st.write(f"**{len(relatorios)} relatório(s)**")
            for rel in relatorios:
                gerado_em = ""
                if rel["gerado_em"]:
                    try:
                        dt_val = datetime.fromisoformat(rel["gerado_em"])
                        gerado_em = dt_val.strftime("%d/%m/%Y às %H:%M")
                    except ValueError:
                        gerado_em = rel["gerado_em"]

                icone = "🚨" if rel["tipo"] == "alerta" else "📊"
                with st.expander(f"{icone} {rel['data']} [{rel['tipo']}] — {gerado_em}"):
                    st.markdown(rel["analise"])
                    pdf_bytes = gerar_pdf_relatorio(
                        rel["analise"], rel["dados_brutos"], rel["data"], rel["tipo"]
                    )
                    st.download_button(
                        label="📥 Exportar para PDF",
                        data=pdf_bytes,
                        file_name=f"relatorio_{rel['tipo']}_{rel['data']}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        key=f"btn_pdf_hist_{rel['tipo']}_{rel['data']}",
                    )
                    with st.expander("📋 Dados brutos"):
                        st.code(rel["dados_brutos"], language="text")


def _executar_analise(contas, start_date, end_date, janela_dias, system_prompt, tipo):
    """Executa a coleta + análise e exibe resultados."""
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    data_ref = start_str if start_str == end_str else f"{start_str}_a_{end_str}"

    df_google_degrau = pd.DataFrame()
    df_google_central = pd.DataFrame()
    df_facebook = pd.DataFrame()

    # Coleta Google Ads Degrau
    if "Google Ads (Degrau)" in contas:
        with st.spinner("🔄 Buscando Google Ads (Degrau)..."):
            client_degrau = init_google_ads_client("google-ads.yaml")
            if client_degrau:
                try:
                    customer_id = str(st.secrets["google_ads"]["customer_id"])
                except Exception:
                    customer_id = "4934481887"
                df_google_degrau = get_google_ads_data(client_degrau, customer_id, start_str, end_str)
            else:
                st.warning("⚠️ Não foi possível conectar ao Google Ads (Degrau)")

    # Coleta Google Ads Central
    if "Google Ads (Central)" in contas:
        with st.spinner("🔄 Buscando Google Ads (Central)..."):
            client_central = init_google_ads_client_central()
            if client_central:
                try:
                    customer_id_c = str(st.secrets["google_ads_central"]["customer_id"])
                except Exception:
                    customer_id_c = "1646681121"
                df_google_central = get_google_ads_data(client_central, customer_id_c, start_str, end_str)
            else:
                st.warning("⚠️ Não foi possível conectar ao Google Ads (Central)")

    # Coleta Meta Ads
    if "Meta Ads" in contas:
        with st.spinner("🔄 Buscando Meta Ads..."):
            fb_account = init_facebook_api()
            if fb_account:
                df_facebook = get_facebook_data(fb_account, start_str, end_str)
            else:
                st.warning("⚠️ Não foi possível conectar ao Meta Ads")

    if df_google_degrau.empty and df_google_central.empty and df_facebook.empty:
        st.error("❌ Nenhum dado coletado. Verifique as credenciais e o período.")
        return

    # Métricas rápidas
    st.subheader("📊 Dados Coletados")
    col1, col2, col3, col4 = st.columns(4)
    custo_gd = df_google_degrau['Custo'].sum() if not df_google_degrau.empty else 0
    custo_gc = df_google_central['Custo'].sum() if not df_google_central.empty else 0
    custo_fb = df_facebook['Custo'].sum() if not df_facebook.empty else 0
    col1.metric("Google Degrau", formatar_reais(custo_gd))
    col2.metric("Google Central", formatar_reais(custo_gc))
    col3.metric("Meta Ads", formatar_reais(custo_fb))
    col4.metric("Total Investido", formatar_reais(custo_gd + custo_gc + custo_fb))

    # Mostra distribuição por objetivo
    _mostrar_distribuicao_objetivos(df_google_degrau, df_google_central, df_facebook)

    # Formata e envia
    dados_consolidados = formatar_dados_para_claude(
        df_google_degrau, df_google_central, df_facebook, data_ref, janela_dias
    )

    with st.spinner("🤖 Analisando com Claude..."):
        analise = analisar_com_claude(dados_consolidados, system_prompt, tipo)

    # Exibe
    icone = "🚨" if tipo == "alerta" else "🤖"
    st.subheader(f"{icone} Análise do Claude")
    st.markdown(analise)

    filepath = salvar_relatorio(analise, dados_consolidados, data_ref, tipo)
    st.success(f"✅ Relatório salvo!")

    # Botão de exportar para PDF
    pdf_bytes = gerar_pdf_relatorio(analise, dados_consolidados, data_ref, tipo)
    nome_pdf = f"relatorio_{tipo}_{data_ref}.pdf"
    st.download_button(
        label="📥 Exportar para PDF",
        data=pdf_bytes,
        file_name=nome_pdf,
        mime="application/pdf",
        use_container_width=True,
        key=f"btn_pdf_{tipo}_{data_ref}",
    )

    with st.expander("📋 Ver dados brutos enviados ao Claude"):
        st.code(dados_consolidados, language="text")


def _mostrar_distribuicao_objetivos(df_gd, df_gc, df_fb):
    """Mostra um resumo visual da distribuição por objetivo de campanha."""
    dfs = []
    if not df_gd.empty:
        dfs.append(df_gd)
    if not df_gc.empty:
        dfs.append(df_gc)
    if not df_fb.empty:
        dfs.append(df_fb)

    if not dfs:
        return

    df_all = pd.concat(dfs, ignore_index=True)
    if 'Objetivo' not in df_all.columns:
        return

    resumo = df_all.groupby('Objetivo').agg(
        Campanhas=('Campanha', 'count'),
        Custo=('Custo', 'sum'),
        Conversões=('Conversões', 'sum'),
    ).reset_index().sort_values('Custo', ascending=False)

    st.subheader("🎯 Distribuição por Objetivo")
    cols = st.columns(len(resumo))
    for i, (_, row) in enumerate(resumo.iterrows()):
        with cols[i % len(cols)]:
            st.metric(
                f"{row['Objetivo']}",
                f"{int(row['Campanhas'])} camp.",
                f"R$ {row['Custo']:,.0f}".replace(",", ".")
            )
