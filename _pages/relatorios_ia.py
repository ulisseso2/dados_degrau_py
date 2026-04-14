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
from sqlalchemy import text as sql_text

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
    "MULTI_CHANNEL": "LEADS",   # Performance Max no enum da API
    "DISPLAY": "AWARENESS",
    "VIDEO": "VIDEO",
}

# ---- Lookup dicts para resolver enums numéricos da API ----
_CHANNEL_TYPE_MAP = {
    2: "SEARCH", 3: "DISPLAY", 4: "SHOPPING", 5: "HOTEL",
    6: "VIDEO", 7: "MULTI_CHANNEL", 9: "DISCOVERY",
}
_STATUS_MAP = {
    2: "ENABLED", 3: "PAUSED", 4: "REMOVED",
}
_BIDDING_MAP = {
    2: "ENHANCED_CPC", 5: "MANUAL_CPC", 6: "MANUAL_CPM", 7: "MANUAL_CPV",
    8: "MAXIMIZE_CONVERSIONS", 9: "MAXIMIZE_CONVERSION_VALUE",
    12: "TARGET_CPA", 13: "TARGET_CPM", 14: "TARGET_IMPRESSION_SHARE",
    16: "TARGET_ROAS", 17: "TARGET_SPEND",
}
_SUB_TYPE_MAP = {
    10: "VIDEO_OUTSTREAM", 11: "VIDEO_ACTION", 12: "VIDEO_NON_SKIPPABLE",
    18: "VIDEO_SEQUENCE", 20: "VIDEO_REACH_TARGET_FREQUENCY",
}

def _resolve_enum(val, lookup=None):
    """Resolve enum da Google Ads API para string. 
    Funciona com proto-plus (que retorna int ou enum com .name) e com enums numéricos."""
    if hasattr(val, 'name'):
        return val.name
    name = str(val).split(".")[-1]
    if lookup:
        try:
            return lookup.get(int(name), name)
        except (ValueError, TypeError):
            pass
    return name

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
    """Busca dados do Google Ads incluindo métricas completas para análise."""
    try:
        ga_service = client.get_service("GoogleAdsService")
        query = f"""
            SELECT
                campaign.name,
                campaign.id,
                campaign.status,
                campaign.advertising_channel_type,
                campaign.advertising_channel_sub_type,
                campaign.bidding_strategy_type,
                campaign.target_cpa.target_cpa_micros,
                campaign.maximize_conversions.target_cpa_micros,
                metrics.cost_micros,
                metrics.impressions,
                metrics.clicks,
                metrics.ctr,
                metrics.average_cpc,
                metrics.average_cpm,
                metrics.conversions,
                metrics.cost_per_conversion,
                metrics.conversions_from_interactions_rate,
                metrics.search_budget_lost_impression_share,
                metrics.search_rank_lost_impression_share,
                metrics.search_impression_share,
                metrics.video_view_rate,
                metrics.video_views,
                metrics.average_cpv,
                metrics.engagements,
                metrics.engagement_rate,
                metrics.interaction_rate,
                metrics.unique_users,
                metrics.average_impression_frequency_per_user,
                metrics.video_quartile_p25_rate,
                metrics.video_quartile_p50_rate,
                metrics.video_quartile_p75_rate,
                metrics.video_quartile_p100_rate
            FROM campaign
            WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
                AND metrics.cost_micros > 0
            ORDER BY metrics.cost_micros DESC
        """
        response = ga_service.search(customer_id=customer_id, query=query)
        rows = []
        for row in response:
            custo = row.metrics.cost_micros / 1_000_000
            cpc = row.metrics.average_cpc / 1_000_000 if row.metrics.average_cpc else 0
            cpm = row.metrics.average_cpm / 1_000_000 if row.metrics.average_cpm else 0
            cpa = row.metrics.cost_per_conversion / 1_000_000 if row.metrics.cost_per_conversion else 0
            cpv = row.metrics.average_cpv / 1_000_000 if row.metrics.average_cpv else 0

            # tCPA: verifica TARGET_CPA e MAXIMIZE_CONVERSIONS (com CPA-alvo)
            tcpa_target = row.campaign.target_cpa.target_cpa_micros / 1_000_000 if row.campaign.target_cpa.target_cpa_micros else 0
            tcpa_maxconv = row.campaign.maximize_conversions.target_cpa_micros / 1_000_000 if row.campaign.maximize_conversions.target_cpa_micros else 0
            tcpa = tcpa_target or tcpa_maxconv

            # Parcelas de impressão (None quando não aplicável, ex: PMax/YouTube)
            imp_lost_budget = row.metrics.search_budget_lost_impression_share
            imp_lost_rank = row.metrics.search_rank_lost_impression_share

            # Resolve enums para nomes legíveis (API pode retornar inteiros ou proto-plus enums)
            channel_type = _resolve_enum(row.campaign.advertising_channel_type, _CHANNEL_TYPE_MAP)
            status = _resolve_enum(row.campaign.status, _STATUS_MAP)
            sub_type_raw = _resolve_enum(row.campaign.advertising_channel_sub_type, _SUB_TYPE_MAP)
            bidding_type = _resolve_enum(row.campaign.bidding_strategy_type, _BIDDING_MAP)

            objetivo_api = OBJETIVO_MAP_GOOGLE.get(channel_type)
            objetivo = objetivo_api if objetivo_api else classificar_por_nome(row.campaign.name)

            # Rec/Cons para YouTube — baseado em sub_type e estratégia de lance
            _REC = {"VIDEO_NON_SKIPPABLE", "VIDEO_OUTSTREAM", "VIDEO_REACH_TARGET_FREQUENCY"}
            _ACT = {"VIDEO_ACTION"}
            if sub_type_raw in _REC or bidding_type in {"TARGET_CPM", "MANUAL_CPM"}:
                rec_cons = "Reconhecimento"
            elif sub_type_raw in _ACT or bidding_type == "MAXIMIZE_CONVERSIONS":
                rec_cons = "Ação/Conversão"
            elif channel_type == "VIDEO":
                rec_cons = "Consideração"  # TrueView / VVC (sub_type UNSPECIFIED + MANUAL_CPV)
            else:
                rec_cons = "-"

            # Métricas exclusivas de YouTube
            unique_users = row.metrics.unique_users if row.metrics.unique_users else 0
            avg_freq = row.metrics.average_impression_frequency_per_user if row.metrics.average_impression_frequency_per_user else 0
            interaction_rate = round(row.metrics.interaction_rate * 100, 2) if row.metrics.interaction_rate else 0

            q25 = round(row.metrics.video_quartile_p25_rate * 100, 1) if row.metrics.video_quartile_p25_rate else 0
            q50 = round(row.metrics.video_quartile_p50_rate * 100, 1) if row.metrics.video_quartile_p50_rate else 0
            q75 = round(row.metrics.video_quartile_p75_rate * 100, 1) if row.metrics.video_quartile_p75_rate else 0
            q100 = round(row.metrics.video_quartile_p100_rate * 100, 1) if row.metrics.video_quartile_p100_rate else 0

            rows.append({
                'Campanha': row.campaign.name,
                'Status': status,
                'Objetivo': objetivo,
                'Canal': channel_type,
                'Subtipo': sub_type_raw,
                'Rec/Cons': rec_cons,
                'Tipo Lance': bidding_type,
                'Custo': round(custo, 2),
                'Impressões': row.metrics.impressions,
                'Usuários Exclusivos': int(unique_users),
                'Freq Méd Imp/Usuário': round(avg_freq, 2),
                'Cliques': row.metrics.clicks,
                'CTR (%)': round(row.metrics.ctr * 100, 2),
                'CPC': round(cpc, 2),
                'CPM': round(cpm, 2),
                'Conversões': round(row.metrics.conversions, 1),
                'CPA': round(cpa, 2),
                'tCPA': round(tcpa, 2),
                'Taxa Conv (%)': round(row.metrics.conversions_from_interactions_rate * 100, 2) if row.metrics.conversions_from_interactions_rate else 0,
                'Imp Lost Budget (%)': round(imp_lost_budget * 100, 1) if imp_lost_budget else None,
                'Imp Lost Rank (%)': round(imp_lost_rank * 100, 1) if imp_lost_rank else None,
                'Video Views': row.metrics.video_views,
                'Video View Rate (%)': round(row.metrics.video_view_rate * 100, 2) if row.metrics.video_view_rate else 0,
                'Taxa de Interação (%)': interaction_rate,
                'CPV': round(cpv, 4),
                'Engajamentos': row.metrics.engagements,
                'Engagement Rate (%)': round(row.metrics.engagement_rate * 100, 2) if row.metrics.engagement_rate else 0,
                '% Assistido 25': q25,
                '% Assistido 50': q50,
                '% Assistido 75': q75,
                '% Assistido 100': q100,
            })
        return pd.DataFrame(rows)
    except Exception as e:
        st.error(f"Erro Google Ads: {e}")
        return pd.DataFrame()

def init_facebook_api(secrets_key="facebook_api", env_suffix=""):
    """Inicializa a API do Facebook. Use env_suffix='_CENTRAL' para Central."""
    app_id, app_secret, access_token, ad_account_id = None, None, None, None
    try:
        creds = st.secrets[secrets_key]
        app_id = creds["app_id"]
        app_secret = creds["app_secret"]
        access_token = creds["access_token"]
        ad_account_id = creds["ad_account_id"]
    except (st.errors.StreamlitAPIException, KeyError):
        app_id = os.getenv(f"FB_APP_ID{env_suffix}")
        app_secret = os.getenv(f"FB_APP_SECRET{env_suffix}")
        access_token = os.getenv(f"FB_ACCESS_TOKEN{env_suffix}")
        ad_account_id = os.getenv(f"FB_AD_ACCOUNT_ID{env_suffix}")
    if not all([app_id, app_secret, access_token, ad_account_id]):
        return None
    try:
        FacebookAdsApi.init(app_id=app_id, app_secret=app_secret, access_token=access_token)
        return AdAccount(ad_account_id)
    except Exception:
        return None

def init_facebook_api_central():
    """Inicializa a API do Facebook para a conta Central de Concursos."""
    return init_facebook_api(secrets_key="facebook_api_central", env_suffix="_CENTRAL")


def get_facebook_data(account, start_date, end_date):
    """Busca dados do Meta Ads com métricas completas.
    - Cliques = inline_link_clicks (cliques no link, não cliques totais)
    - CTR/CPC baseados em inline_link_clicks
    - Leads primários = lead_presencial + lead_live (Custom Conversions)
    """
    try:
        fields = [
            AdsInsights.Field.campaign_name,
            AdsInsights.Field.objective,
            AdsInsights.Field.spend,
            AdsInsights.Field.impressions,
            AdsInsights.Field.reach,
            AdsInsights.Field.frequency,
            AdsInsights.Field.cpm,
            # Cliques no link (não cliques totais)
            'inline_link_clicks',
            'inline_link_click_ctr',
            'cost_per_inline_link_click',
            AdsInsights.Field.actions,
            AdsInsights.Field.cost_per_action_type,
            # Conversions traz eventos pixel por nome (lead_presencial, lead_live, lead_online)
            'conversions',
        ]
        params = {
            'level': 'campaign',
            'time_range': {'since': start_date, 'until': end_date},
            # Usa a configuração de atribuição da conta (igual ao Gerenciador de Anúncios)
            'use_account_attribution_setting': True,
        }
        insights = account.get_insights(fields=fields, params=params)

        rows = []

        # Eventos de venda para campanhas de e-commerce (do campo actions)
        VENDA_ACTIONS = {
            'purchase', 'omni_purchase',
            'offsite_conversion.fb_pixel_purchase',
        }
        # Nomes dos eventos pixel de lead (do campo conversions)
        LEAD_EVENTS = {
            'offsite_conversion.fb_pixel_custom.lead_presencial': 'lead_presencial',
            'offsite_conversion.fb_pixel_custom.lead_live': 'lead_live',
            'offsite_conversion.fb_pixel_custom.lead_online': 'lead_online',
        }

        for insight in insights:
            custo = float(insight.get(AdsInsights.Field.spend, 0))

            # Cliques no link
            cliques_link = int(insight.get('inline_link_clicks', 0))
            ctr_link = float(insight.get('inline_link_click_ctr', 0))
            cpc_link = float(insight.get('cost_per_inline_link_click', 0))

            # Leads primários via campo 'conversions' (eventos pixel por nome)
            lead_presencial = 0
            lead_live = 0
            lead_online = 0
            conversions = insight.get('conversions', [])
            for conv in conversions:
                atype = conv.get('action_type', '')
                val = int(conv.get('value', 0))
                target = LEAD_EVENTS.get(atype)
                if target == 'lead_presencial':
                    lead_presencial = val
                elif target == 'lead_live':
                    lead_live = val
                elif target == 'lead_online':
                    lead_online = val

            # Vendas via campo 'actions'
            vendas = 0
            actions = insight.get(AdsInsights.Field.actions, [])
            for action in actions:
                atype = action.get('action_type', '')
                val = int(action.get('value', 0))
                if atype in VENDA_ACTIONS:
                    vendas += val

            leads_primarios = lead_presencial + lead_live
            cpl_primario = custo / leads_primarios if leads_primarios > 0 else 0

            # Classificação de objetivo
            obj_api = insight.get(AdsInsights.Field.objective, "")
            objetivo = OBJETIVO_MAP_META.get(obj_api)
            if not objetivo:
                objetivo = classificar_por_nome(insight[AdsInsights.Field.campaign_name])

            rows.append({
                'Campanha': insight[AdsInsights.Field.campaign_name],
                'Objetivo': objetivo,
                'Custo': custo,
                'Impressões': int(insight.get(AdsInsights.Field.impressions, 0)),
                'Alcance': int(insight.get(AdsInsights.Field.reach, 0)),
                'Frequência': float(insight.get(AdsInsights.Field.frequency, 0)),
                'CPM': float(insight.get(AdsInsights.Field.cpm, 0)),
                'Cliques Link': cliques_link,
                'CTR Link (%)': round(ctr_link, 2),
                'CPC Link': round(cpc_link, 2),
                'lead_presencial': lead_presencial,
                'lead_live': lead_live,
                'lead_online': lead_online,
                'Resultado Presencial + Live': leads_primarios,
                'CPL Primário': round(cpl_primario, 2),
                'Vendas': vendas,
            })
        return pd.DataFrame(rows)
    except Exception as e:
        st.error(f"Erro Meta Ads: {e}")
        return pd.DataFrame()

# =====================================================
# FORMATAÇÃO DOS DADOS POR OBJETIVO (v2.0)
# =====================================================

def formatar_dados_para_claude(df_google_degrau, df_google_central, df_facebook, janela_dias, df_facebook_central=None, start_date=None, end_date=None):
    """Formata os dados organizados por MARCA (Central vs Degrau) e dentro de cada marca por
    plataforma, conforme exigido pelo system prompt v3.0."""
    hoje = datetime.now().date()
    inicio = start_date if start_date is not None else hoje - timedelta(days=janela_dias)
    fim = end_date if end_date is not None else hoje
    dia_semana = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"][hoje.weekday()]
    janela_real = (fim - inicio).days + 1

    linhas = []
    linhas.append("=== METADADOS ===")
    linhas.append(f"Período: {inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}")
    linhas.append(f"Janela: {janela_real} dias")
    linhas.append(f"Tipo de relatório: {'Alerta diário' if janela_real == 1 else 'Análise completa'}")
    linhas.append(f"Data de hoje: {hoje.strftime('%d/%m/%Y')} ({dia_semana})")
    linhas.append("")

    def _bloco_campanhas(df, origem_label):
        """Retorna linhas formatadas para um conjunto de campanhas de uma plataforma/marca."""
        if df is None or df.empty:
            return [f"  [{origem_label}]: sem dados no período"]

        eh_meta = "Meta" in origem_label
        custo_total = df['Custo'].sum()
        bloco = []
        bloco.append(f"  [{origem_label}]")
        bloco.append(f"  Total campanhas: {len(df)} | Custo total: R${custo_total:.2f}")
        bloco.append("")

        for _, r in df.iterrows():
            obj = r.get('Objetivo', 'LEADS')
            status = r.get('Status', '')
            bloco.append(f"  Campanha: {r['Campanha']}" + (f" [{status}]" if status else ""))
            bloco.append(f"  Objetivo: {obj} | Custo: R${r['Custo']:.2f} | Impressões: {r['Impressões']:,}")

            if eh_meta:
                # Métricas Meta com cliques no link
                cliques = r.get('Cliques Link', 0)
                ctr = r.get('CTR Link (%)', 0)
                cpc = r.get('CPC Link', 0)
                cpm = r.get('CPM', 0)
                alcance = r.get('Alcance', 0)
                freq = r.get('Frequência', 0)
                lead_p = r.get('lead_presencial', 0)
                lead_l = r.get('lead_live', 0)
                lead_o = r.get('lead_online', 0)
                leads = r.get('Resultado Presencial + Live', 0)
                cpl = r.get('CPL Primário', 0)
                vendas = r.get('Vendas', 0)

                bloco.append(f"  Cliques no link: {cliques:,} | CTR link: {ctr:.2f}% | CPC link: R${cpc:.2f} | CPM: R${cpm:.2f}")
                bloco.append(f"  Alcance: {alcance:,} | Frequência: {freq:.1f}")
                if leads > 0 or lead_p > 0 or lead_l > 0 or lead_o > 0:
                    aviso = " ⚠️ <30, dados insuficientes" if leads < 30 else ""
                    bloco.append(f"  lead_presencial: {lead_p} | lead_live: {lead_l} | lead_online: {lead_o} | Resultado Presencial + Live: {leads} | CPL Primário: R${cpl:.2f}{aviso}")
                if vendas > 0:
                    bloco.append(f"  Vendas: {vendas}")
            else:
                # Métricas Google Ads
                canal = r.get('Canal', '')
                cliques = r.get('Cliques', 0)
                ctr = r.get('CTR (%)', 0)
                cpc = r.get('CPC', 0)
                cpm = r.get('CPM', 0)
                conv = r.get('Conversões', 0)
                cpa = r.get('CPA', 0)
                tcpa = r.get('tCPA', 0)
                taxa_conv = r.get('Taxa Conv (%)', 0)
                imp_budget = r.get('Imp Lost Budget (%)', None)
                imp_rank = r.get('Imp Lost Rank (%)', None)
                cpv = r.get('CPV', 0)
                video_views = r.get('Video Views', 0)
                view_rate = r.get('Video View Rate (%)', 0)
                engajamentos = r.get('Engajamentos', 0)
                eng_rate = r.get('Engagement Rate (%)', 0)

                if canal == "VIDEO":
                    # ── YouTube: apenas métricas de vídeo, sem Conversões/CPA/Parcelas ──
                    rec_cons = r.get('Rec/Cons', '-')
                    tipo_lance = r.get('Tipo Lance', '-')
                    unique_users = r.get('Usuários Exclusivos', 0)
                    avg_freq = r.get('Freq Méd Imp/Usuário', 0)
                    q25 = r.get('% Assistido 25', 0)
                    q50 = r.get('% Assistido 50', 0)
                    q75 = r.get('% Assistido 75', 0)
                    q100 = r.get('% Assistido 100', 0)
                    taxa_interacao = r.get('Taxa de Interação (%)', 0)
                    bloco.append(f"  Tipo: {rec_cons} | Estratégia de Lance: {tipo_lance}")
                    bloco.append(f"  Custo: R${r['Custo']:.2f} | Impressões: {r['Impressões']:,} | CPM: R${cpm:.2f} | CPC: R${cpc:.2f} | CPV: R${cpv:.4f}")
                    bloco.append(f"  Usuários Exclusivos: {unique_users:,} | Freq. Méd. Imp./Usuário: {avg_freq:.2f}")
                    bloco.append(f"  Video Views: {video_views:,} | View Rate: {view_rate:.2f}%")
                    bloco.append(f"  % Assistido: 25%={q25:.1f}% | 50%={q50:.1f}% | 75%={q75:.1f}% | 100%={q100:.1f}%")
                    bloco.append(f"  Taxa de Interação: {taxa_interacao:.2f}% | Engajamentos: {engajamentos:,}")
                else:
                    # ── Search, PMax, Display: métricas de conversão e parcelas ──
                    tcpa_str = f"R${tcpa:.2f}" if tcpa > 0 else "não configurado"
                    bloco.append(f"  Canal: {canal} | Cliques: {cliques:,} | CTR: {ctr:.2f}% | CPC: R${cpc:.2f} | CPM: R${cpm:.2f}")
                    bloco.append(f"  Conversões: {conv} | CPA: R${cpa:.2f} | CPA Desejado: {tcpa_str} | Taxa conv: {taxa_conv:.2f}%")

                    if imp_budget is not None or imp_rank is not None:
                        ib = f"{imp_budget:.1f}%" if imp_budget is not None else "N/A"
                        ir = f"{imp_rank:.1f}%" if imp_rank is not None else "N/A"
                        bloco.append(f"  Parc impr perd (orç): {ib} | Parc impr perd (class): {ir}")

                    if conv > 0 and conv < 30:
                        bloco.append(f"  ⚠️ <30 conversões — CPA não é estatisticamente confiável")

            bloco.append("")
        return bloco

    def _soma(df, col):
        return df[col].sum() if df is not None and not df.empty and col in df.columns else 0

    # ─── CENTRAL DE CONCURSOS ───────────────────────────────────────────────
    linhas.append("=" * 60)
    linhas.append("MARCA: CENTRAL DE CONCURSOS (São Paulo)")
    linhas.append("=" * 60)

    custo_gc  = _soma(df_google_central, 'Custo')
    custo_fbc = _soma(df_facebook_central, 'Custo')
    conv_gc   = _soma(df_google_central, 'Conversões')
    leads_fbc = _soma(df_facebook_central, 'Resultado Presencial + Live')
    cpl_fbc   = custo_fbc / leads_fbc if leads_fbc > 0 else 0

    linhas.append(f"Investimento total Central: R${(custo_gc + custo_fbc):.2f}")
    linhas.append(f"  Google Ads (Central): R${custo_gc:.2f} | Conversões: {int(conv_gc)}")
    linhas.append(f"  Meta Ads (Central):   R${custo_fbc:.2f} | Resultado Presencial + Live: {int(leads_fbc)}" +
                  (f" | CPL: R${cpl_fbc:.2f}" if leads_fbc > 0 else ""))
    linhas.append("")

    linhas.extend(_bloco_campanhas(df_google_central, "Google Ads (Central)"))
    linhas.extend(_bloco_campanhas(df_facebook_central, "Meta Ads (Central)"))

    # ─── DEGRAU CULTURAL ────────────────────────────────────────────────────
    linhas.append("=" * 60)
    linhas.append("MARCA: DEGRAU CULTURAL (Rio de Janeiro)")
    linhas.append("=" * 60)

    custo_gd  = _soma(df_google_degrau, 'Custo')
    custo_fb  = _soma(df_facebook, 'Custo')
    conv_gd   = _soma(df_google_degrau, 'Conversões')
    leads_fb  = _soma(df_facebook, 'Resultado Presencial + Live')
    cpl_fb    = custo_fb / leads_fb if leads_fb > 0 else 0

    linhas.append(f"Investimento total Degrau: R${(custo_gd + custo_fb):.2f}")
    linhas.append(f"  Google Ads (Degrau): R${custo_gd:.2f} | Conversões: {int(conv_gd)}")
    linhas.append(f"  Meta Ads (Degrau):   R${custo_fb:.2f} | Resultado Presencial + Live: {int(leads_fb)}" +
                  (f" | CPL: R${cpl_fb:.2f}" if leads_fb > 0 else ""))
    linhas.append("")

    linhas.extend(_bloco_campanhas(df_google_degrau, "Google Ads (Degrau)"))
    linhas.extend(_bloco_campanhas(df_facebook, "Meta Ads (Degrau)"))

    # ─── TOTAIS CONSOLIDADOS ────────────────────────────────────────────────
    custo_all = custo_gc + custo_fbc + custo_gd + custo_fb
    conv_all  = int(conv_gc + conv_gd)
    leads_all = int(leads_fbc + leads_fb)
    linhas.append("=" * 60)
    linhas.append("TOTAIS CONSOLIDADOS (ambas as marcas)")
    linhas.append("=" * 60)
    linhas.append(f"Custo total: R${custo_all:.2f} | Conversões Google: {conv_all} | Resultado Presencial + Live (Meta): {leads_all}")

    return "\n".join(linhas)

# =====================================================
# SYSTEM PROMPTS v4.0 (Março 2026)
# =====================================================

SYSTEM_PROMPT_ADS_V2 = """
SYSTEM PROMPT — SISTEMA DE INTELIGÊNCIA DE MARKETING
Degrau Cultural / Central de Concursos
Versão 2.1 — Março 2026

1. IDENTIDADE E PAPEL

Você é o analista sênior de tráfego pago da operação Degrau Cultural / Central de Concursos.
Seu trabalho é receber dados de campanhas diretamente das plataformas (Google Ads API e Meta
Marketing API), analisar performance e entregar dois outputs:

RESUMO DIRETORIA: visão executiva, clara, sem jargão técnico excessivo, focada em investimento,
retorno, tendências e decisões necessárias.

ANÁLISE COMPLETA PARA O GESTOR DE TRÁFEGO: diagnóstico técnico campanha a campanha, com
gargalos identificados e plano de ação prático.

Idioma de saída: português brasileiro. Tom: técnico, direto, sem enrolação. Pode usar tom
coloquial quando necessário, mas nunca genérico. Toda recomendação deve ter: (a) o que está
acontecendo, (b) por que é problema, (c) o que fazer.

2. CONTEXTO DO NEGÓCIO

2.1 Marcas
- Central de Concursos — São Paulo (conta Google Ads: "Google Ads (Central)", Meta: "Meta Ads (Central)")
- Degrau Cultural — Rio de Janeiro (conta Google Ads: "Google Ads (Degrau)", Meta: "Meta Ads (Degrau)")

2.2 Segmento
Cursos preparatórios para concursos públicos no Brasil. Três modalidades de ensino:
- Presencial: aulas em unidades físicas.
- Live: aulas ao vivo remotas com horário fixo.
- Online: acesso assíncrono, sem horário fixo.

2.3 Modelo de negócio e funil
- Presencial e Live: o site NÃO vende. O objetivo das campanhas é GERAR LEADS via formulário.
  O lead é atendido por um consultor que explica modalidades, unidades, valores e condições.
- Online: o curso online PODE ser comprado direto no site. Campanhas Meta específicas de venda
  online devem ser analisadas como campanhas de conversão/venda, não como campanhas de lead.
- PMax Google: leva para página do concurso com as 3 modalidades. O lead pode converter como
  lead presencial/live OU comprar online direto. É uma campanha "indireta" para venda online.

2.4 Concorrentes principais
Estratégia Concursos e Gran Cursos Online. Modelo deles: venda de curso online direto no site.
Competem nas mesmas palavras-chave no leilão do Google, mas o modelo de negócio é diferente.

2.5 Concursos ativos
Os concursos ativos mudam constantemente. Identificar os concursos a partir dos nomes das
campanhas. Exemplos recorrentes: INSS, TJ SP, Banco do Brasil, PM SP, PC SP, GCM SP, PM RJ,
DETRAN RJ, MP SP, SEFAZ SP, entre outros.

3. SEGMENTAÇÃO GEOGRÁFICA DAS CAMPANHAS

3.1 Central de Concursos (São Paulo)
- Google Ads: Barueri, Carapicuíba, Diadema, Guarulhos, Jandira, Mauá, Santo André, São Bernardo
  do Campo, São Caetano do Sul, São Paulo, Taboão da Serra.
- Meta Ads: majoritariamente cidade de São Paulo com raio de 50 km.

3.2 Degrau Cultural (Rio de Janeiro)
- Google Ads: Duque de Caxias, Mesquita, Nilópolis, Niterói, Nova Iguaçu, Rio de Janeiro, São
  Gonçalo, São João de Meriti.
- Meta Ads: majoritariamente cidade do Rio de Janeiro com raio de 50 km + Niterói.

REGRA OBRIGATÓRIA: análises SEMPRE separadas por marca. Nunca misturar Central de Concursos
com Degrau Cultural na mesma seção.

4. MÉTRICAS POR PLATAFORMA

4.1 Google Ads — Campanhas de Search e PMax
Métricas obrigatórias:
- Impressões, Cliques, CTR, Custo, CPM médio, CPC médio
- Conversões (primárias: Lead Presencial + Lead Live), CPA real
- tCPA configurado (se disponível — comparar com CPA real)
- Taxa de conversão
- Parcela de impressões perdida por orçamento (campo: Imp Lost Budget %)
- Parcela de impressões perdida por classificação (campo: Imp Lost Rank %)
  Nos dados: "Parc impr perd (orç)" e "Parc impr perd (class)"

4.2 Google Ads — Campanhas de YouTube
CRÍTICO: distinguir por objetivo.
- Campanhas de CONVERSÃO → avaliar por CPA normalmente.
- Campanhas VVC (Video View / Visualização / Engajamento) → avaliar por:
  CPV (Custo por View), Taxa de visualização (Video View Rate %), Engajamentos,
  Engagement Rate, Video Views. NUNCA julgar campanha VVC por CPA.

4.3 Meta Ads — Campanhas de Lead
Métricas obrigatórias:
- Custo (Valor usado), Impressões, Alcance, Frequência, CPM
- Cliques no link (campo: Cliques Link — inline_link_clicks, NÃO cliques totais)
- CTR link (inline_link_click_ctr), CPC link (cost_per_inline_link_click)
- Lead Presencial (evento lead_presencial), Lead Live (evento lead_live)
- Leads Primários = Lead Presencial + Lead Live
- CPL Primário = Custo / Leads Primários

4.4 Meta Ads — Campanhas de Venda Online
Analisar como e-commerce: ROAS, custo por compra, volume de vendas.
NÃO misturar métricas de campanha de lead com campanha de venda online.

4.5 Conversões — hierarquia
- Primárias (meta de negócio): Lead Presencial + Lead Live.
- Secundárias (apoio ao algoritmo): Lead Online + microconversões.
- Venda direta: compra de curso online (apenas campanhas específicas de venda).

5. REGRAS DE ANÁLISE — GOOGLE ADS

5.1 Fluxo obrigatório de análise

PASSO 1 — Leitura fria dos números:
Custo total, conversões primárias, CPA real, taxa de conversão, CPC médio, CPM.
Comparar CPA real vs tCPA. Se tCPA não informado, PERGUNTAR antes de julgar.

PASSO 2 — Análise por tipo de campanha:
Search:
- Taxa de conversão e CPA.
- Parcela perdida por classificação alta → problema é qualidade/lance, NÃO orçamento.
  Diagnosticar ANTES de recomendar aumento de budget.
- Parcela perdida por orçamento alta → há espaço para mais volume com o CPA atual.

PMax:
- CPA geral e distribuição por canal (Pesquisa, Discover, YouTube, Gmail, Display).
- Taxa de conversão em PMax é naturalmente menor que Search — o que manda é CPA e volume.
- Quando PMax tiver CPA menor que Search do mesmo concurso: APONTAR a diferença percentual
  mas NÃO recomendar realocação diretamente. Registrar como ponto de análise para o gestor.
  Formato: "PMax CPA R$ X,XX vs. Search CPA R$ Y,YY (diferença de Z%). Ponto de análise:
  gestor deve avaliar qualidade dos leads antes de realocar orçamento."

YouTube VVC:
- Avaliar por CPV, Video View Rate, Engajamentos, Engagement Rate. Tratar como awareness.
- NUNCA julgar por CPA.

PASSO 3 — Diagnóstico antes da solução:
Sempre identificar primeiro: "O maior problema está em: [Lances/tCPA? Orçamento? Estrutura?
Canais da PMax? Landing page? Segmentação? Criativos?]" — só depois sugerir ajustes.

5.2 Filosofia de otimização — Google Ads
Toda sugestão: (a) o que mudar, (b) por que mudar com base nos dados, (c) resultado esperado.

5.3 Campanhas z{} (genéricas / marca / topo de funil)
Campanhas com prefixo z{} (ex: z{Concursos}, z{Institucional}, z{Branding}, z{DSA}) são topo
de funil ou marca. CPA estruturalmente baixo — NÃO usar como benchmark para campanhas de
concurso específico. NÃO listar como "destaque positivo" no Resumo Diretoria por CPA baixo.
Na Análise do Gestor: analisar normalmente mas sempre contextualizar que o CPA baixo é
estrutural da posição no funil, não mérito de otimização.

6. REGRAS DE ANÁLISE — META ADS

6.1 Fluxo obrigatório — campanhas de lead

PASSO 1 — Leitura dos números:
Custo, Impressões, Alcance, Frequência, CPM.
Cliques no link, CTR link, CPC link.
Leads Primários (Lead Presencial + Lead Live) e CPL Primário.
Frequência > 3.0 em prospecção → possível saturação.

PASSO 2 — Análise por posição no funil:
- Topo de funil (prospecção): CPM, CTR link, CPL Primário.
  CPM alto + CTR baixo → criativo fraco ou público saturado.
  CTR bom + CPL alto → problema na LP ou no formulário.
- Retargeting: CPL menor esperado. Frequência > 4-5 → público esgotando.
- Venda online: ROAS, custo por compra, volume. Nunca misturar com métricas de lead.

PASSO 3 — Criativos:
Avaliar caso a caso: concurso, público, momento do edital, posição no funil.
Apontar o que melhorar e por quê — sem regras genéricas para todas as campanhas.

6.2 Métrica customizada — CPL Primário
Fórmula: Custo / (lead_presencial + lead_live)
Prioridade máxima. Lead Online é métrica secundária. Sempre diferenciar.

7. REGRAS CRÍTICAS — APLICAR SEMPRE

- NUNCA avaliar campanha de tráfego/awareness por CPA.
- NUNCA concluir sobre CPA com menos de 30 conversões — sinalizar explicitamente.
- NUNCA presumir CPA target. Se não informado, perguntar.
- Parcela perdida por classificação: verificar ANTES de recomendar aumento de orçamento.
- SEMPRE separar análise por marca. Blocos separados, nunca misturar.
- YouTube VVC: NUNCA avaliar por CPA.
- Meta venda online: e-commerce (ROAS, custo por compra). Nunca tratar como lead.
- Campanhas z{}: NÃO listar como destaque por CPA baixo — é estrutural.
- PMax vs Search: apontar diferença de CPA, não recomendar realocação diretamente.

8. FORMATO DE SAÍDA

Análise SEMPRE separada por marca: primeiro Central de Concursos, depois Degrau Cultural.

8.0 Período e comparativo WoW
Relatório semanal cobre DOMINGO a SÁBADO. Confirmar que o período está correto.
Quando houver dados da semana anterior: incluir comparativo WoW obrigatório.
Métricas WoW: Custo (R$ e %), Conversões/Leads (qtd e %), CPA/CPL (R$ e %), Frequência Meta.

─────────────────────────────────────────────────────
BLOCO 1 — RESUMO DIRETORIA
─────────────────────────────────────────────────────

PERÍODO: [extrair dos dados]

═══ CENTRAL DE CONCURSOS ═══

INVESTIMENTO TOTAL: R$ X.XXX,XX
  Google Ads: R$ X.XXX,XX | Meta Ads: R$ X.XXX,XX

LEADS PRIMÁRIOS GERADOS: XXX
  Google Ads: XXX conversões (CPA médio: R$ XX,XX)
  Meta Ads: XXX leads primários (CPL primário médio: R$ XX,XX)

[Se houver dados WoW, incluir comparação aqui]

DESTAQUES POSITIVOS:
  Listar apenas campanhas de concurso específico acima da meta.
  NÃO incluir campanhas z{} como destaque por CPA baixo.

PONTOS DE ATENÇÃO:
  [Campanha com CPA/CPL acima da meta, frequência alta, etc.]

DECISÕES NECESSÁRIAS:
  [Aumentar orçamento? Há perda por budget? Pausar campanha?]

═══ DEGRAU CULTURAL ═══
[Mesma estrutura]

─────────────────────────────────────────────────────
BLOCO 2 — ANÁLISE COMPLETA PARA O GESTOR DE TRÁFEGO
─────────────────────────────────────────────────────

═══ CENTRAL DE CONCURSOS ═══

CAMPANHA: [nome]
PLATAFORMA: [Google Ads / Meta Ads]
TIPO: [Search / PMax / YouTube Conversão / YouTube VVC / Meta Lead / Meta Venda Online]
STATUS: [Ativa / Pausada / Limitada por orçamento]

NÚMEROS (semana atual vs. anterior se disponível):
  [Google Search/PMax]
  Custo: R$ X.XXX,XX | Impressões: XX.XXX | Cliques: X.XXX | CTR: X,XX% | CPM: R$ X,XX
  Conversões: XX | CPA: R$ XX,XX | tCPA: R$ XX,XX | Taxa conv: X,XX%
  Parc impr perd (orç): X% | Parc impr perd (class): X%

  [Meta Lead]
  Custo: R$ X.XXX,XX | Impressões: XX.XXX | Alcance: XX.XXX | Frequência: X,X | CPM: R$ X,XX
  Cliques link: X.XXX | CTR link: X,XX% | CPC link: R$ X,XX
  Lead Presencial: XX | Lead Live: XX | Leads Primários: XX | CPL Primário: R$ XX,XX

  [Meta Venda Online]
  Custo: R$ X.XXX,XX | Vendas: XX | ROAS: X,XX | Custo por compra: R$ XX,XX

  [YouTube VVC]
  Custo: R$ X.XXX,XX | Video Views: XX.XXX | View Rate: X,XX% | CPV: R$ X,XXXX
  Engajamentos: XX.XXX | Engagement Rate: X,XX%

DIAGNÓSTICO:
  O maior problema está em: [gargalo principal]
  [Explicação concisa]

PLANO DE AÇÃO:
  1. [O que fazer] → [Por que] → [Resultado esperado]
  2. [Ação secundária] → [Justificativa] → [Resultado esperado]

⚠️ [Alertas: <30 conversões, parcela perdida por classificação alta, frequência crítica, etc.]

[Para z{}: "CPA baixo é estrutural — posição de topo de funil/marca, não mérito de otimização."]
[Para PMax vs Search: apontar diferença % de CPA como ponto de análise, não recomendação direta.]

═══ DEGRAU CULTURAL ═══
[Mesma análise campanha a campanha]

─────────────────────────────────────────────────────
BLOCO 3 — ALOCAÇÃO DE BUDGET (quando necessário)
─────────────────────────────────────────────────────

RECOMENDAÇÃO DE REDISTRIBUIÇÃO:
  [De campanha X → para campanha Y: R$ XXX/dia | Justificativa | Risco]

NOTA: NÃO incluir sugestões de migração Search → PMax como recomendação direta.
Diferenças de CPA entre Search e PMax do mesmo concurso: listar como "PONTOS PARA AVALIAÇÃO
DO GESTOR", não como recomendações de redistribuição.

9. PROCESSAMENTO DOS DADOS

- cost_micros: dividir por 1.000.000.
- YouTube VVC: nome contém "VVC", "view", "visualização" ou "engajamento" → tratar como VVC.
- Meta venda: objetivo vendas ou nome contém "venda"/"online"/"e-commerce" → venda online.
- Incluir TODA campanha com custo > 0 OU impressões > 0, mesmo que pausada no período.
  Para campanhas pausadas com gasto: "Pausada durante o período. Custo: R$ X,XX | Conv: X."
- Campanhas com custo = R$0 e impressões = 0: listar em bloco resumido ao final da seção.
- Campos ausentes ou zerados: sinalizar, nunca inventar dados.
- Origem dos dados está rotulada: usar para separar marcas.

10. O QUE NUNCA FAZER

- Recomendação genérica. Sempre: o que está errado, por que, e o que fazer especificamente.
- Presumir CPA target. Se não informado, perguntar.
- Avaliar campanha de tráfego/awareness por CPA.
- Concluir sobre CPA com menos de 30 conversões.
- Misturar análise de lead com venda online.
- Diagnosticar "problema é LP" sem dados que comprovem (taxa conv ruim + CPA alto).
- Recomendar aumento de orçamento sem verificar parcela perdida por classificação.
- Misturar campanhas da Central com campanhas da Degrau.
- Listar campanhas z{} como destaques positivos por CPA baixo.
- Recomendar diretamente realocação Search → PMax baseada só em CPA.

11. COMPORTAMENTO QUANDO DADOS SÃO INSUFICIENTES

Fazer a análise com o que tem. Listar métricas faltantes e impacto:
"Sem parcela perdida por classificação, não consigo diagnosticar se o gargalo é orçamento ou
qualidade/lance." Sugerir como obter a métrica faltante.
Se dados WoW ausentes: solicitar para próxima rodada e realizar análise sem comparativo.

12. TIKTOK ADS (SECUNDÁRIO — apenas Degrau Cultural)

Analisar como campanha de tráfego/awareness. Métricas: impressões, cliques, CTR, CPC, custo,
visualizações de vídeo. NÃO esperar conversões rastreadas. Sinalizar limitações de rastreamento.

Versão do prompt: 2.1 | Última atualização: Março 2026
"""

SYSTEM_PROMPT_ALERTA_DIARIO = """
Você é um monitor de tráfego pago para Central de Concursos e Degrau Cultural.

REGRA FUNDAMENTAL: os alertas devem ser SEMPRE separados por marca. Jamais misture campanhas
da Central de Concursos com campanhas da Degrau Cultural.

Seu objetivo é APENAS identificar anomalias que exigem ação imediata. NÃO faça análise completa.

=== ALERTAR APENAS SE ===

ADS:
- Campanha ativa com 0 impressões (possível reprovação)
- Gasto diário >2x o gasto médio diário da campanha
- CPA diário >3x o CPA médio (só para LEADS/VENDAS com 30+ conversões no histórico)
- Campanha de REMARKETING/Meta com frequência >5 no dia
- Erro de pixel/tracking (conversões = 0 em todas as campanhas de uma marca)

ORGÂNICO:
- Post/vídeo viralizando (>5x média de views em 24h)
- Queda de sessões do blog >40% vs mesmo dia semana passada
- Comentários negativos em volume incomum

=== FORMATO DA RESPOSTA ===

Se NÃO houver anomalias:
"✅ Tudo normal. Nenhuma anomalia detectada."

Se houver anomalias, organizar por marca:

"═══ CENTRAL DE CONCURSOS ═══
🚨 ALERTA [TIPO]: [descrição curta]
Ação sugerida: [o que fazer agora]

═══ DEGRAU CULTURAL ═══
🚨 ALERTA [TIPO]: [descrição curta]
Ação sugerida: [o que fazer agora]"

Máximo 5 alertas por marca. Priorize por gravidade.
NÃO inclua análises, recomendações estratégicas ou comentários gerais. Só alertas acionáveis.
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
        api_key = st.secrets["ANTHROPIC_API_KEY"]
    except (st.errors.StreamlitAPIException, KeyError, FileNotFoundError):
        pass
    if not api_key:
        api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None, "❌ API Key do Claude não configurada. Defina ANTHROPIC_API_KEY no .env ou Streamlit Secrets."

    # max_retries: o SDK faz retry automático com backoff exponencial para 529 (overloaded)
    return anthropic.Anthropic(api_key=api_key, max_retries=5), None

def analisar_com_claude(dados_consolidados, system_prompt=None, tipo_relatorio="completo_ads"):
    """Envia dados para o Claude e retorna a análise usando o prompt correto."""
    import time
    import anthropic as _anthropic

    client, erro = _get_anthropic_client()
    if erro:
        return erro

    if system_prompt is None:
        system_prompt = SYSTEM_PROMPT_ADS_V2

    if tipo_relatorio == "alerta":
        user_msg = f"Dados de ontem:\n\n{dados_consolidados}\n\nVerifique se há anomalias conforme as regras."
    else:
        user_msg = f"Segue o relatório de performance do período:\n\n{dados_consolidados}\n\nAnalise conforme a estrutura definida."

    max_tentativas = 4
    for tentativa in range(1, max_tentativas + 1):
        try:
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=64000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_msg}]
            ) as stream:
                texto = stream.get_final_text()
                final = stream.get_final_message()

            usage = final.usage
            print(
                f"[Claude API] tentativa={tentativa} | input_tokens={usage.input_tokens} | "
                f"output_tokens={usage.output_tokens} | stop_reason={final.stop_reason}"
            )
            return texto

        except _anthropic.APIStatusError as e:
            if e.status_code == 529:  # overloaded_error
                espera = 2 ** tentativa  # 2s, 4s, 8s, 16s
                print(f"[Claude API] Sobrecarga na tentativa {tentativa}. Aguardando {espera}s...")
                if tentativa < max_tentativas:
                    time.sleep(espera)
                else:
                    return f"❌ API do Claude sobrecarregada após {max_tentativas} tentativas. Tente novamente em alguns minutos."
            else:
                return f"❌ Erro na API do Claude ({e.status_code}): {e.message}"

        except Exception as e:
            return f"❌ Erro inesperado ao chamar o Claude: {e}"

# =====================================================
# HISTÓRICO DE RELATÓRIOS (MySQL)
# Tabela: seducar.ai_reports
# Colunas: id, uuid, reference_date, type, generated_at, raw_data, ai_analysis
# =====================================================

def _get_writer_engine():
    """Obtém engine de escrita via conexao/mysql_connector."""
    try:
        from conexao.mysql_connector import conectar_mysql_writer
        return conectar_mysql_writer()
    except ImportError:
        return None


def salvar_relatorio(analise, dados_consolidados, data_ref, tipo="completo_ads"):
    """Salva o relatório no banco de dados MySQL."""
    import uuid as uuid_mod

    engine = _get_writer_engine()
    if engine:
        try:
            with engine.connect() as conn:
                conn.execute(
                    sql_text("""
                        INSERT INTO ai_reports (uuid, reference_date, type, generated_at, raw_data, ai_analysis)
                        VALUES (:uuid, :reference_date, :type, :generated_at, :raw_data, :ai_analysis)
                    """),
                    {
                        "uuid": str(uuid_mod.uuid4()),
                        "reference_date": data_ref,
                        "type": tipo,
                        "generated_at": datetime.now(),
                        "raw_data": dados_consolidados,
                        "ai_analysis": analise,
                    }
                )
                conn.commit()
            return "db"
        except Exception as e:
            st.warning(f"Erro ao salvar no banco: {e}. Salvando localmente.")

    # Fallback: salva em arquivo local
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
    """Carrega relatórios do banco MySQL (com fallback para arquivos locais)."""
    relatorios = []

    # Tenta carregar do banco
    engine = _get_writer_engine()
    if engine:
        try:
            query = "SELECT id, uuid, reference_date, type, generated_at, raw_data, ai_analysis FROM ai_reports"
            params = {}
            if filtro_tipo:
                query += " WHERE type = :tipo"
                params["tipo"] = filtro_tipo
            query += " ORDER BY generated_at DESC LIMIT 50"

            with engine.connect() as conn:
                result = conn.execute(sql_text(query), params)
                for row in result:
                    gerado_em = row.generated_at.isoformat() if row.generated_at else ""
                    relatorios.append({
                        "id": row.id,
                        "uuid": row.uuid,
                        "data": row.reference_date,
                        "tipo": row.type,
                        "gerado_em": gerado_em,
                        "analise": row.ai_analysis or "",
                        "dados_brutos": row.raw_data or "",
                    })
            if relatorios:
                return relatorios
        except Exception as e:
            st.warning(f"Erro ao carregar do banco: {e}. Tentando arquivos locais.")

    # Fallback: arquivos locais
    if not os.path.exists(HISTORICO_DIR):
        return relatorios
    arquivos = sorted(glob.glob(os.path.join(HISTORICO_DIR, "relatorio_*.json")), reverse=True)
    for arq in arquivos:
        try:
            with open(arq, "r", encoding="utf-8") as f:
                data = json.load(f)
                tipo = data.get("tipo", "completo_ads")
                if filtro_tipo and tipo != filtro_tipo:
                    continue
                relatorios.append({
                    "id": None,
                    "uuid": None,
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
        ["Google Ads (Degrau)", "Google Ads (Central)", "Meta Ads (Degrau)", "Meta Ads (Central)"],
        default=["Google Ads (Degrau)", "Google Ads (Central)", "Meta Ads (Degrau)", "Meta Ads (Central)"],
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

        col_btn_ads1, col_btn_ads2 = st.columns(2)
        with col_btn_ads1:
            if st.button("🔍 Buscar Dados", type="primary", use_container_width=True, key="btn_ads_buscar"):
                _coletar_dados(contas, start_date, end_date, janela_dias, "ads_dados")
        with col_btn_ads2:
            dados_ads_prontos = "ads_dados" in st.session_state
            if st.button(
                "🤖 Analisar com IA",
                use_container_width=True,
                key="btn_ads_ia",
                disabled=not dados_ads_prontos,
            ):
                _enviar_para_ia("ads_dados", SYSTEM_PROMPT_ADS_V2, "completo_ads")

        if "ads_dados" in st.session_state:
            info = st.session_state["ads_dados"]
            st.info(f"📦 Dados prontos: **{info['data_ref']}** — clique em 'Analisar com IA' quando estiver pronto.")
            with st.expander("📋 Ver dados coletados"):
                st.code(info["dados_consolidados"], language="text")

    # =========================================================
    # ABA 2: ALERTA DIÁRIO
    # =========================================================
    with tab_alerta:
        st.header("🚨 Alerta Diário — Detecção de Anomalias")
        st.caption("Verifica apenas se há problemas que exigem ação imediata. Rápido e objetivo.")

        start_alerta = ontem
        end_alerta = ontem

        st.info(f"📅 Verificando dados de ontem: **{start_alerta.strftime('%d/%m/%Y')}**")

        col_btn_al1, col_btn_al2 = st.columns(2)
        with col_btn_al1:
            if st.button("🔍 Buscar Dados", type="primary", use_container_width=True, key="btn_alerta_buscar"):
                _coletar_dados(contas, start_alerta, end_alerta, 1, "alerta_dados")
        with col_btn_al2:
            dados_alerta_prontos = "alerta_dados" in st.session_state
            if st.button(
                "🚨 Analisar com IA",
                use_container_width=True,
                key="btn_alerta_ia",
                disabled=not dados_alerta_prontos,
            ):
                _enviar_para_ia("alerta_dados", SYSTEM_PROMPT_ALERTA_DIARIO, "alerta")

        if "alerta_dados" in st.session_state:
            info = st.session_state["alerta_dados"]
            st.info(f"📦 Dados prontos: **{info['data_ref']}** — clique em 'Analisar com IA' quando estiver pronto.")
            with st.expander("📋 Ver dados coletados"):
                st.code(info["dados_consolidados"], language="text")

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
            for idx, rel in enumerate(relatorios):
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
                        key=f"btn_pdf_hist_{idx}_{rel['tipo']}_{rel['data']}",
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
    df_facebook_central = pd.DataFrame()

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

    # Coleta Meta Ads (Degrau)
    if "Meta Ads (Degrau)" in contas:
        with st.spinner("🔄 Buscando Meta Ads (Degrau)..."):
            fb_account = init_facebook_api()
            if fb_account:
                df_facebook = get_facebook_data(fb_account, start_str, end_str)
            else:
                st.warning("⚠️ Não foi possível conectar ao Meta Ads (Degrau)")

    # Coleta Meta Ads (Central)
    if "Meta Ads (Central)" in contas:
        with st.spinner("🔄 Buscando Meta Ads (Central)..."):
            fb_account_central = init_facebook_api_central()
            if fb_account_central:
                df_facebook_central = get_facebook_data(fb_account_central, start_str, end_str)
            else:
                st.warning("⚠️ Não foi possível conectar ao Meta Ads (Central)")

    if df_google_degrau.empty and df_google_central.empty and df_facebook.empty and df_facebook_central.empty:
        st.error("❌ Nenhum dado coletado. Verifique as credenciais e o período.")
        return

    # Métricas rápidas
    st.subheader("📊 Dados Coletados")
    col1, col2, col3, col4 = st.columns(4)
    custo_gd = df_google_degrau['Custo'].sum() if not df_google_degrau.empty else 0
    custo_gc = df_google_central['Custo'].sum() if not df_google_central.empty else 0
    custo_fb = df_facebook['Custo'].sum() if not df_facebook.empty else 0
    custo_fbc = df_facebook_central['Custo'].sum() if not df_facebook_central.empty else 0
    col1.metric("Google Degrau", formatar_reais(custo_gd))
    col2.metric("Google Central", formatar_reais(custo_gc))
    col3.metric("Meta Degrau", formatar_reais(custo_fb))
    col4.metric("Meta Central", formatar_reais(custo_fbc))

    st.metric("💰 Total Investido", formatar_reais(custo_gd + custo_gc + custo_fb + custo_fbc))

    # Mostra distribuição por objetivo
    _mostrar_distribuicao_objetivos(df_google_degrau, df_google_central, df_facebook, df_facebook_central)

    # Tabelas detalhadas por conta Google Ads
    with st.expander("📋 Ver campanhas Google Ads por conta", expanded=False):
        if not df_google_degrau.empty:
            _mostrar_tabelas_google_ads(df_google_degrau, "Google Ads — Degrau")
        if not df_google_central.empty:
            _mostrar_tabelas_google_ads(df_google_central, "Google Ads — Central")

    # Formata e envia
    dados_consolidados = formatar_dados_para_claude(
        df_google_degrau, df_google_central, df_facebook, janela_dias,
        df_facebook_central=df_facebook_central,
        start_date=start_date, end_date=end_date
    )

    with st.spinner("🤖 Analisando com Claude..."):
        analise = analisar_com_claude(dados_consolidados, system_prompt, tipo)

    # Exibe
    icone = "🚨" if tipo == "alerta" else "🤖"
    st.subheader(f"{icone} Análise do Claude")
    st.markdown(analise)

    filepath = salvar_relatorio(analise, dados_consolidados, data_ref, tipo)
    if filepath == "db":
        st.success("✅ Relatório salvo no banco de dados!")
    else:
        st.success(f"✅ Relatório salvo localmente!")

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


def _mostrar_distribuicao_objetivos(df_gd, df_gc, df_fb, df_fbc=None):
    """Mostra um resumo visual da distribuição por objetivo de campanha."""
    dfs = []
    if not df_gd.empty:
        dfs.append(df_gd)
    if not df_gc.empty:
        dfs.append(df_gc)
    if not df_fb.empty:
        dfs.append(df_fb)
    if df_fbc is not None and not df_fbc.empty:
        dfs.append(df_fbc)

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


def _mostrar_tabelas_google_ads(df_google, label):
    """Exibe tabelas separadas para campanhas YouTube e demais campanhas do Google Ads."""
    if df_google is None or df_google.empty:
        return

    df_video = df_google[df_google['Canal'] == 'VIDEO'].copy()
    df_outros = df_google[df_google['Canal'] != 'VIDEO'].copy()

    # ── CAMPANHAS YOUTUBE ────────────────────────────────────────────────────
    if not df_video.empty:
        st.markdown(f"##### 📺 Campanhas YouTube — {label}")
        colunas_yt = [
            'Campanha', 'Status', 'Rec/Cons', 'Tipo Lance',
            'Custo', 'Impressões', 'Usuários Exclusivos', 'Freq Méd Imp/Usuário',
            'CPM', 'CPC', 'CPV',
            'Video Views', 'Video View Rate (%)',
            '% Assistido 25', '% Assistido 50', '% Assistido 75', '% Assistido 100',
            'Taxa de Interação (%)', 'Engajamentos',
        ]
        colunas_yt = [c for c in colunas_yt if c in df_video.columns]
        df_yt_display = df_video[colunas_yt].copy()

        # Formata colunas monetárias
        for col in ['Custo', 'CPM', 'CPC', 'CPV']:
            if col in df_yt_display.columns:
                df_yt_display[col] = df_yt_display[col].apply(
                    lambda v: f"R$ {v:,.4f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    if col == 'CPV' and pd.notna(v) else (
                        f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                        if pd.notna(v) and v > 0 else "-"
                    )
                )
        # Formata percentuais
        for col in ['Video View Rate (%)', '% Assistido 25', '% Assistido 50',
                    '% Assistido 75', '% Assistido 100', 'Taxa de Interação (%)']:
            if col in df_yt_display.columns:
                df_yt_display[col] = df_yt_display[col].apply(
                    lambda v: f"{v:.2f}%" if pd.notna(v) else "-"
                )
        for col in ['Freq Méd Imp/Usuário']:
            if col in df_yt_display.columns:
                df_yt_display[col] = df_yt_display[col].apply(
                    lambda v: f"{v:.2f}" if pd.notna(v) and v > 0 else "-"
                )
        st.dataframe(df_yt_display, use_container_width=True, hide_index=True)

    # ── DEMAIS CAMPANHAS (Search, PMax, Display) ─────────────────────────────
    if not df_outros.empty:
        st.markdown(f"##### 🔍 Demais Campanhas — {label}")
        colunas_std = [
            'Campanha', 'Status', 'Canal', 'Tipo Lance',
            'Custo', 'Impressões', 'Cliques', 'CTR (%)',
            'CPC', 'CPM', 'Conversões', 'CPA', 'tCPA',
            'Taxa Conv (%)', 'Imp Lost Budget (%)', 'Imp Lost Rank (%)',
        ]
        colunas_std = [c for c in colunas_std if c in df_outros.columns]
        df_std_display = df_outros[colunas_std].copy()
        df_std_display.rename(columns={'tCPA': 'CPA Desejado (Lead)'}, inplace=True)

        for col in ['Custo', 'CPC', 'CPM', 'CPA', 'CPA Desejado (Lead)']:
            if col in df_std_display.columns:
                df_std_display[col] = df_std_display[col].apply(
                    lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    if pd.notna(v) and v > 0 else "-"
                )
        for col in ['CTR (%)', 'Taxa Conv (%)']:
            if col in df_std_display.columns:
                df_std_display[col] = df_std_display[col].apply(
                    lambda v: f"{v:.2f}%" if pd.notna(v) else "-"
                )
        for col in ['Imp Lost Budget (%)', 'Imp Lost Rank (%)']:
            if col in df_std_display.columns:
                df_std_display[col] = df_std_display[col].apply(
                    lambda v: f"{v:.1f}%" if pd.notna(v) else "-"
                )
        st.dataframe(df_std_display, use_container_width=True, hide_index=True)


def _coletar_dados(contas, start_date, end_date, janela_dias, session_key):
    """Coleta dados das APIs, exibe métricas e salva no session_state para análise posterior."""
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    data_ref = start_str if start_str == end_str else f"{start_str}_a_{end_str}"

    df_google_degrau = pd.DataFrame()
    df_google_central = pd.DataFrame()
    df_facebook = pd.DataFrame()
    df_facebook_central = pd.DataFrame()

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

    if "Meta Ads (Degrau)" in contas:
        with st.spinner("🔄 Buscando Meta Ads (Degrau)..."):
            fb_account = init_facebook_api()
            if fb_account:
                df_facebook = get_facebook_data(fb_account, start_str, end_str)
            else:
                st.warning("⚠️ Não foi possível conectar ao Meta Ads (Degrau)")

    if "Meta Ads (Central)" in contas:
        with st.spinner("🔄 Buscando Meta Ads (Central)..."):
            fb_account_central = init_facebook_api_central()
            if fb_account_central:
                df_facebook_central = get_facebook_data(fb_account_central, start_str, end_str)
            else:
                st.warning("⚠️ Não foi possível conectar ao Meta Ads (Central)")

    if df_google_degrau.empty and df_google_central.empty and df_facebook.empty and df_facebook_central.empty:
        st.error("❌ Nenhum dado coletado. Verifique as credenciais e o período.")
        return

    st.subheader("📊 Dados Coletados")
    col1, col2, col3, col4 = st.columns(4)
    custo_gd = df_google_degrau['Custo'].sum() if not df_google_degrau.empty else 0
    custo_gc = df_google_central['Custo'].sum() if not df_google_central.empty else 0
    custo_fb = df_facebook['Custo'].sum() if not df_facebook.empty else 0
    custo_fbc = df_facebook_central['Custo'].sum() if not df_facebook_central.empty else 0
    col1.metric("Google Degrau", formatar_reais(custo_gd))
    col2.metric("Google Central", formatar_reais(custo_gc))
    col3.metric("Meta Degrau", formatar_reais(custo_fb))
    col4.metric("Meta Central", formatar_reais(custo_fbc))
    st.metric("💰 Total Investido", formatar_reais(custo_gd + custo_gc + custo_fb + custo_fbc))

    _mostrar_distribuicao_objetivos(df_google_degrau, df_google_central, df_facebook, df_facebook_central)

    # Tabelas detalhadas por conta Google Ads
    with st.expander("📋 Ver campanhas Google Ads por conta", expanded=False):
        if not df_google_degrau.empty:
            _mostrar_tabelas_google_ads(df_google_degrau, "Google Ads — Degrau")
        if not df_google_central.empty:
            _mostrar_tabelas_google_ads(df_google_central, "Google Ads — Central")

    dados_consolidados = formatar_dados_para_claude(
        df_google_degrau, df_google_central, df_facebook, janela_dias,
        df_facebook_central=df_facebook_central,
        start_date=start_date, end_date=end_date
    )

    st.session_state[session_key] = {
        "dados_consolidados": dados_consolidados,
        "data_ref": data_ref,
    }
    st.success("✅ Dados coletados! Revise abaixo e clique em 'Analisar com IA' quando estiver pronto.")
    with st.expander("📋 Ver dados que serão enviados à IA", expanded=True):
        st.code(dados_consolidados, language="text")


def _enviar_para_ia(session_key, system_prompt, tipo):
    """Lê os dados do session_state, envia ao Claude e exibe a análise."""
    if session_key not in st.session_state:
        st.warning("⚠️ Nenhum dado encontrado. Clique em 'Buscar Dados' primeiro.")
        return

    dados = st.session_state[session_key]
    dados_consolidados = dados["dados_consolidados"]
    data_ref = dados["data_ref"]

    with st.spinner("🤖 Analisando com Claude..."):
        analise = analisar_com_claude(dados_consolidados, system_prompt, tipo)

    icone = "🚨" if tipo == "alerta" else "🤖"
    st.subheader(f"{icone} Análise do Claude")
    st.markdown(analise)

    filepath = salvar_relatorio(analise, dados_consolidados, data_ref, tipo)
    if filepath == "db":
        st.success("✅ Relatório salvo no banco de dados!")
    else:
        st.success("✅ Relatório salvo localmente!")

    pdf_bytes = gerar_pdf_relatorio(analise, dados_consolidados, data_ref, tipo)
    st.download_button(
        label="📥 Exportar para PDF",
        data=pdf_bytes,
        file_name=f"relatorio_{tipo}_{data_ref}.pdf",
        mime="application/pdf",
        use_container_width=True,
        key=f"btn_pdf_{tipo}_{data_ref}",
    )
    with st.expander("📋 Ver dados brutos enviados ao Claude"):
        st.code(dados_consolidados, language="text")
