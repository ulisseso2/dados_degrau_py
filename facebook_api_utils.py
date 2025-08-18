# facebook_api_utils.py
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.campaign import Campaign
from facebook_business.adobjects.adset import AdSet
from facebook_business.adobjects.ad import Ad
from facebook_business.adobjects.customconversion import CustomConversion
from dotenv import load_dotenv
import streamlit as st
import os
import time
import pandas as pd
from datetime import datetime, timedelta
from fbclid_db import (
    load_fbclid_cache,
    save_fbclid_cache_batch,
    get_campaign_for_fbclid,
)

# Carrega as variáveis do .env (só terá efeito no ambiente local)
load_dotenv()

def init_facebook_api():
    """
    Inicializa a API do Facebook de forma híbrida, lendo de st.secrets ou .env.
    Retorna (app_id, app_secret, access_token, ad_account_id) e objeto da conta
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
        return None, None, None, None, None

    try:
        FacebookAdsApi.init(app_id=app_id, app_secret=app_secret, access_token=access_token)
        account = AdAccount(ad_account_id)
        return app_id, app_secret, access_token, ad_account_id, account
    except Exception as e:
        st.error(f"Falha ao inicializar a API do Facebook: {e}")
        return None, None, None, None, None

def get_campaign_data_from_facebook(account, campaign_id):
    """
    Obtém dados detalhados de uma campanha específica do Facebook
    """
    try:
        campaign = Campaign(campaign_id)
        campaign.api_get(fields=[
            'name',
            'objective',
            'status',
            'lifetime_budget',
            'daily_budget',
            'bid_strategy',
            'created_time',
            'start_time',
            'stop_time'
        ])
        return campaign
    except Exception as e:
        st.warning(f"Erro ao obter dados da campanha {campaign_id}: {e}")
        return None

def get_ad_data_from_facebook(account, ad_id):
    """
    Obtém dados detalhados de um anúncio específico do Facebook
    """
    try:
        ad = Ad(ad_id)
        ad.api_get(fields=[
            'name', 
            'creative',
            'status',
            'adset_id',
            'campaign_id'
        ])
        return ad
    except Exception as e:
        st.warning(f"Erro ao obter dados do anúncio {ad_id}: {e}")
        return None

def get_campaigns_for_fbclids(account, fbclid_list, empresa="degrau", batch_size=100, delay=1):
    """
    Busca informações de campanhas para uma lista de FBclids
    
    LIMITAÇÃO ATUAL: A API do Facebook/Meta não permite busca direta por FBclid.
    Esta função marca todos os FBclids como "Não encontrado" e serve como placeholder
    para quando a Meta disponibilizar uma API para consulta de FBclids no futuro.
    
    ALTERNATIVAS:
    1. Use parâmetros UTM em seus links do Facebook para rastrear campanhas
    2. Configure o Facebook Pixel para rastreamento avançado de conversões
    3. Exporte relatórios da plataforma do Facebook Ads e faça o cruzamento manual
    
    Nota: Não utilize o script simulate_fbclid_lookup.py em produção, pois ele
    gera dados simulados que não refletem as campanhas reais.
    """
    if not account or not fbclid_list:
        return {}
    
    # Carrega cache existente
    cache = load_fbclid_cache(empresa)
    
    # Filtra apenas FBclids não consultados
    fbclids_to_query = [
        fbclid for fbclid in fbclid_list 
        if fbclid not in cache or cache[fbclid] == 'Não encontrado'
    ]
    
    if not fbclids_to_query:
        st.info("Todos os FBclids já foram consultados anteriormente.")
        return {}
    
    # Resultados - sempre "Não encontrado" pois não há API para consulta
    fbclid_campaign_map = {}
    
    # Aviso para o usuário sobre a limitação atual
    st.warning("""
        ⚠️ LIMITAÇÃO DA API: Atualmente, o Facebook/Meta não disponibiliza uma API 
        para consulta direta de informações de campanha a partir de FBclids. 
        Todos os FBclids serão marcados como "Não encontrado".
        
        Para rastreamento de campanhas, considere utilizar parâmetros UTM em seus links.
    """)
    
    # Marca todos os FBclids como "Não encontrado"
    for fbclid in fbclids_to_query:
        fbclid_campaign_map[fbclid] = {
            'campaign_name': 'Não encontrado',
            'campaign_id': None,
            'adset_name': None,
            'ad_name': None
        }
    
    # Salva no banco de dados
    save_fbclid_cache_batch(fbclid_campaign_map, empresa)
    
    return fbclid_campaign_map

def search_fbclid_conversions(account, start_date, end_date, empresa="degrau"):
    """
    Busca conversões que possuem um FBclid registrado durante um período
    
    Obs: Esta função é um placeholder. A API do Facebook não permite buscar diretamente
    por FBclids, então precisaremos implementar uma solução alternativa ou integrar
    com os dados do seu CRM.
    """
    try:
        # Placeholder para chamar a API - esta é uma função a ser implementada quando
        # uma solução estiver disponível
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro ao buscar conversões com FBclid: {e}")
        return pd.DataFrame()

def format_fbclid_data(raw_data):
    """
    Formata os dados brutos de FBclids para exibição
    """
    if raw_data.empty:
        return pd.DataFrame()
    
    df = raw_data.copy()
    
    # Processamento e formatação de dados
    # Será implementado de acordo com a estrutura real dos dados
    
    return df
