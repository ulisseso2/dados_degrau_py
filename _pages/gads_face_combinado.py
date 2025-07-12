import streamlit as st
import os
from datetime import datetime
import pandas as pd
import plotly.express as px
from st_aggrid import GridOptionsBuilder, AgGrid
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric
from google.oauth2 import service_account
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adsinsights import AdsInsights
from dotenv import load_dotenv

load_dotenv()
#função auxiliar para formatar valores monetários
def formatar_reais(valor):
    """Formata um número para o padrão monetário brasileiro."""
    if pd.isna(valor) or valor == 0: return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

#chamada para a API do Google Analytics
def get_ga_credentials():
    """Carrega as credenciais de forma híbrida"""
    try:
        creds_dict = st.secrets["gcp_service_account"]
        return service_account.Credentials.from_service_account_info(creds_dict)
    except (st.errors.StreamlitAPIException, KeyError):
        file_path = os.getenv("GCP_SERVICE_ACCOUNT_FILE")
        if file_path and os.path.exists(file_path):
            return service_account.Credentials.from_service_account_file(file_path)
    return None

#função para inicializar o cliente do GA4
def run_ga_report(client, property_id, dimensions, metrics, start_date, end_date, limit=15, order_bys=None):
    """Função ÚNICA para executar qualquer relatório no GA4."""
    try:
        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=dimensions,
            metrics=metrics,
            date_ranges=[DateRange(start_date=start_date.strftime('%Y-%m-%d'), end_date=end_date.strftime('%Y-%m-%d'))],
            limit=limit,
            order_bys=order_bys if order_bys else []
        )
        return client.run_report(request)
    except Exception as e:
        st.warning(f"Atenção: A consulta ao Google Analytics falhou. Erro: {e}")
        return None

#função para inicializar a API do Facebook
def init_facebook_api():
    """
    Inicializa a API do Facebook de forma híbrida, lendo de st.secrets ou .env.
    Retorna o objeto da conta de anúncios se for bem-sucedido, senão None.
    """
    app_id, app_secret, access_token, ad_account_id = None, None, None, None
    
    try:
        # Tenta carregar do Streamlit Secrets (para produção)
        creds = st.secrets["facebook_api"]
        app_id = creds["app_id"]
        app_secret = creds["app_secret"]
        access_token = creds["access_token"]
        ad_account_id = creds["ad_account_id"]
        
    except (st.errors.StreamlitAPIException, KeyError):
        # Se falhar (ambiente local), carrega do arquivo .env
        app_id = os.getenv("FB_APP_ID")
        app_secret = os.getenv("FB_APP_SECRET")
        access_token = os.getenv("FB_ACCESS_TOKEN")
        ad_account_id = os.getenv("FB_AD_ACCOUNT_ID")

    # Verifica se as credenciais foram carregadas
    if not all([app_id, app_secret, access_token, ad_account_id]):
        st.error("As credenciais da API do Facebook não foram encontradas. Verifique seus Secrets ou o arquivo .env.")
        return None

    try:
        FacebookAdsApi.init(app_id=app_id, app_secret=app_secret, access_token=access_token)
        account = AdAccount(ad_account_id)
        return account
    except Exception as e:
        st.error(f"Falha ao inicializar a API do Facebook: {e}")
        return None

#função para buscar insights de campanhas do Facebook
def get_facebook_campaign_insights(account, start_date, end_date):
    """
    Busca insights de performance para todas as campanhas em um período.
    """
    try:
        # Define os campos e parâmetros para a chamada da API
        fields = [
            AdsInsights.Field.campaign_name,
            AdsInsights.Field.spend,
            AdsInsights.Field.impressions,
            AdsInsights.Field.clicks,
            AdsInsights.Field.ctr, # Taxa de Cliques (Click-Through Rate)
            AdsInsights.Field.cpc, # Custo por Clique
        ]
        params = {
            'level': 'campaign',
            'time_range': {
                'since': start_date.strftime('%Y-%m-%d'),
                'until': end_date.strftime('%Y-%m-%d'),
            },
        }

        # Faz a chamada à API
        insights = account.get_insights(fields=fields, params=params)
        
        # Processa a resposta em uma lista de dicionários
        rows = []
        for insight in insights:
            rows.append({
                'Campanha': insight[AdsInsights.Field.campaign_name],
                'Custo': float(insight[AdsInsights.Field.spend]),
                'Impressões': int(insight[AdsInsights.Field.impressions]),
                'Cliques': int(insight[AdsInsights.Field.clicks]),
                'CTR (%)': float(insight[AdsInsights.Field.ctr]),
                'CPC': float(insight[AdsInsights.Field.cpc]),
            })
            
        return pd.DataFrame(rows)

    except Exception as e:
        st.error(f"Erro ao buscar insights de campanhas do Facebook: {e}")
        return pd.DataFrame()
    
#função para buscar insights com breakdowns do Facebook
def get_facebook_breakdown_insights(account, start_date, end_date, breakdown):
    """
    Busca insights de Custo segmentados por um 'breakdown' específico (ex: age, gender).
    """
    try:
        fields = [
            AdsInsights.Field.spend,
        ]
        params = {
            'level': 'campaign',
            'time_range': {
                'since': start_date.strftime('%Y-%m-%d'),
                'until': end_date.strftime('%Y-%m-%d'),
            },
            # O parâmetro chave que segmenta os dados
            'breakdowns': [breakdown],
        }

        insights = account.get_insights(fields=fields, params=params)
        
        rows = []
        for insight in insights:
            rows.append({
                'Segmento': insight[breakdown],
                'Custo': float(insight[AdsInsights.Field.spend]),
            })
        
        df = pd.DataFrame(rows)
        # Agrupa os resultados, pois a API retorna uma linha por dia por segmento
        if not df.empty:
            df = df.groupby('Segmento')['Custo'].sum().sort_values(ascending=False).reset_index()
        return df

    except Exception as e:
        st.error(f"Erro ao buscar dados com breakdown '{breakdown}': {e}")
        return pd.DataFrame()
    
def run_page():
    st.title("📊 Análise Combinada de Campanhas GA4 e Facebook")

    # Credenciais do GA4
    PROPERTY_ID = "327463413"
    credentials = get_ga_credentials()

    # Inicializa a API do Facebook
    account = init_facebook_api()

    if not credentials:
        st.error("Falha na autenticação com o Google. Verifique as configurações de segredos ou o arquivo .env.")
        st.stop()

    client = BetaAnalyticsDataClient(credentials=credentials)

        # --- FILTRO DE DATA ÚNICO E GLOBAL PARA A PÁGINA ---
    st.sidebar.header("Filtro de Período")
    hoje = datetime.now().date()
    data_inicio_padrao = hoje - pd.Timedelta(days=27)
    
    periodo_selecionado = st.sidebar.date_input(
        "Selecione o Período de Análise:",
        [data_inicio_padrao, hoje],
        key="ga_date_range"
    )

    if len(periodo_selecionado) != 2:
        st.warning("Por favor, selecione um período de datas válido na barra lateral.")
        st.stop()
    
    start_date, end_date = periodo_selecionado
    st.info(f"Exibindo dados de **{start_date.strftime('%d/%m/%Y')}** a **{end_date.strftime('%d/%m/%Y')}**")

    st.divider()

    st.subheader("Valores investidos em Campanhas")

    # Chamada de insights do Facebook
    df_insights = get_facebook_campaign_insights(account, start_date, end_date)

    # --- ANÁLISE 1: PERFORMANCE DE CAMPANHAS GA4---
    cost_response = run_ga_report(
        client, PROPERTY_ID,
        dimensions=[Dimension(name="campaignName")],
        metrics=[Metric(name="advertiserAdCost"), Metric(name="conversions")],
        start_date=start_date, end_date=end_date,
        order_bys=[{'metric': {'metric_name': 'advertiserAdCost'}, 'desc': True}]
    )

    if cost_response and cost_response.rows:
        rows = []
        for r in cost_response.rows:
            cost = float(r.metric_values[0].value)
            conversions = float(r.metric_values[1].value)
            cpa = (cost / conversions) if conversions > 0 else 0
            rows.append({'Campanha': r.dimension_values[0].value, 'Custo': cost, 'Conversões': int(conversions), 'CPA (Custo por Conversão)': cpa})
        
        df_performance = pd.DataFrame(rows)
        df_performance = df_performance[df_performance['Custo'] > 0].reset_index(drop=True)

        # --- ADICIONADO: Métrica de Custo Total ---
        custo_total_periodo = df_performance['Custo'].sum()

    if not df_insights.empty and cost_response and cost_response.rows:
            # Exibe os totais em cards
            total_custo_fb = df_insights['Custo'].sum()
            custo_total_periodo = df_performance['Custo'].sum()
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Custo Total no Período (FB)", formatar_reais(total_custo_fb))
            col2.metric("Custo Total no Período (GA4)", formatar_reais(custo_total_periodo))
            col3.metric("Investimento Total", formatar_reais(total_custo_fb + custo_total_periodo))




