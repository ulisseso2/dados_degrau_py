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
import json
import requests
import pandas as pd
from datetime import datetime, timedelta
from fbclid_db import (
    load_fbclid_cache,
    save_fbclid_cache_batch,
    get_campaign_for_fbclid,
    format_fbclid,
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
    Busca informações de campanhas para uma lista de FBclids usando a API de Conversões
    
    Implementação conforme documentação da Meta:
    https://developers.facebook.com/docs/marketing-api/conversions-api/parameters/fbp-and-fbc/
    
    NOTA IMPORTANTE: A API do Facebook/Meta não permite busca direta por FBclid.
    Este método envia eventos para a API de Conversões com os FBclids formatados
    e registra as informações no banco de dados.
    """
    if not account or not fbclid_list:
        return {}
    
    # Recupera ID da conta (sem o prefixo act_)
    ad_account_id = account['id'] if isinstance(account, dict) else account.get_id()
    if ad_account_id.startswith('act_'):
        ad_account_id = ad_account_id[4:]
    
    # Inicializa cache existente
    try:
        cache = load_fbclid_cache(empresa)
    except Exception as e:
        st.error(f"Erro ao carregar cache de FBclids: {e}")
        return {}
    
    # Filtra apenas FBclids não consultados ou marcados como "Não encontrado"
    fbclids_to_query = [
        fbclid for fbclid in fbclid_list 
        if fbclid not in cache or cache[fbclid] == 'Não encontrado'
    ]
    
    if not fbclids_to_query:
        st.info("Todos os FBclids já foram consultados anteriormente.")
        return {}
    
    # Resultado das consultas
    fbclid_campaign_map = {}
    
    st.info("""
        🔄 Enviando FBclids para a API de Conversões da Meta...
        
        NOTA: A Meta não fornece uma API direta para consultar campanhas a partir de FBclids.
        Este processo envia eventos para a API de Conversões com os FBclids formatados.
        
        Para rastreamento completo de campanhas, considere:
        1. Usar parâmetros UTM em seus links
        2. Configurar o Facebook Pixel no seu site
        3. Implementar a API de Conversões diretamente no seu site
    """)
    
    _, _, access_token, _, _ = init_facebook_api()
    
    if not access_token:
        st.error("Não foi possível obter o access_token para a API do Facebook. Verifique suas credenciais.")
        return {}
    
    # Obtém o Pixel ID
    try:
        # Primeiro tenta obter dos secrets do Streamlit
        pixel_id = st.secrets["facebook_api"]["pixel_id"]
    except (KeyError, st.errors.StreamlitAPIException):
        # Se falhar, tenta obter da variável de ambiente
        pixel_id = os.getenv("FB_PIXEL_ID")
    
    if not pixel_id:
        st.error("Pixel ID não encontrado. Execute o script setup_pixel_id.py para configurar.")
        return {}
    
    # Processa os FBclids em lotes
    total_lotes = len(fbclids_to_query) // batch_size + (1 if len(fbclids_to_query) % batch_size > 0 else 0)
    
    for lote_idx in range(total_lotes):
        inicio = lote_idx * batch_size
        fim = min(inicio + batch_size, len(fbclids_to_query))
        
        lote_atual = fbclids_to_query[inicio:fim]
        st.write(f"Processando lote {lote_idx + 1}/{total_lotes} ({len(lote_atual)} FBclids)")
        
        # Consulta cada FBclid individualmente para aumentar chances de correspondência
        for i, fbclid in enumerate(lote_atual):
            # Garante que o FBclid esteja no formato correto
            formatted_fbclid = format_fbclid(fbclid)
            
            try:
                # Gera um ID de evento único
                import uuid
                event_id = str(uuid.uuid4())
                
                # Define o timestamp atual
                event_time = int(time.time())
                
                # Cria um evento para a API de Conversões
                event_data = {
                    "data": [{
                        "event_name": "PageView",
                        "event_time": event_time,
                        "event_id": event_id,
                        "action_source": "website",
                        "event_source_url": "https://degrauculturalidiomas.com.br/",
                        "user_data": {
                            "fbc": formatted_fbclid,
                            "client_ip_address": "127.0.0.1",
                            "client_user_agent": "Mozilla/5.0"
                        }
                    }]
                }
                
                # URL da API de Conversões
                url = f"https://graph.facebook.com/v18.0/{pixel_id}/events"
                
                # Envia o evento
                response = requests.post(
                    url, 
                    params={'access_token': access_token},
                    json=event_data
                )
                
                data = response.json()
                
                # Aguarda um momento para não sobrecarregar a API
                time.sleep(delay)
                
                # Verifica a resposta
                if 'events_received' in data and data['events_received'] > 0:
                    # Evento recebido com sucesso
                    # Não temos como saber a campanha diretamente, mas podemos
                    # tentar buscar campanhas ativas como alternativa
                    
                    try:
                        # Busca campanhas ativas
                        campaigns = account.get_campaigns(
                            fields=['name', 'id', 'status'],
                            params={'effective_status': ['ACTIVE', 'PAUSED']}
                        )
                        
                        if campaigns and len(campaigns) > 0:
                            # Pega a campanha mais recente como melhor suposição
                            # (Não é preciso, mas é melhor que nada)
                            campaign = campaigns[0]
                            
                            fbclid_campaign_map[fbclid] = {
                                'campaign_name': f"{campaign['name']} (possível)",
                                'campaign_id': campaign['id'],
                                'adset_name': None,
                                'ad_name': None
                            }
                        else:
                            # Não encontrou campanhas
                            fbclid_campaign_map[fbclid] = {
                                'campaign_name': 'Evento recebido, sem campanha identificada',
                                'campaign_id': None,
                                'adset_name': None,
                                'ad_name': None
                            }
                    except Exception as e:
                        # Erro ao buscar campanhas
                        fbclid_campaign_map[fbclid] = {
                            'campaign_name': 'Evento recebido, erro ao buscar campanhas',
                            'campaign_id': None,
                            'adset_name': None,
                            'ad_name': None
                        }
                else:
                    # Erro ao enviar evento
                    error_msg = data.get('error', {}).get('message', 'Erro desconhecido')
                    fbclid_campaign_map[fbclid] = {
                        'campaign_name': f'Erro: {error_msg}',
                        'campaign_id': None,
                        'adset_name': None,
                        'ad_name': None
                    }
                
            except Exception as e:
                st.error(f"Erro ao processar FBclid {fbclid}: {e}")
                # Marca como erro
                fbclid_campaign_map[fbclid] = {
                    'campaign_name': f'Erro: {str(e)[:50]}...',
                    'campaign_id': None,
                    'adset_name': None,
                    'ad_name': None
                }
            
            # Atualiza progresso
            progress = (lote_idx * batch_size + i + 1) / len(fbclids_to_query)
            st.progress(progress)
    
    # Salva todos os resultados no banco de dados
    save_fbclid_cache_batch(fbclid_campaign_map, empresa)
    
    # Mensagem de conclusão
    encontrados = sum(1 for v in fbclid_campaign_map.values() 
                     if isinstance(v, dict) and v.get('campaign_name') != 'Não encontrado' 
                     and not v.get('campaign_name', '').startswith('Erro:'))
    
    st.success(f"""
        ✅ Processamento concluído! 
        - Total de FBclids processados: {len(fbclid_campaign_map)}
        - Eventos enviados com sucesso: {encontrados}
        - Eventos com erro: {len(fbclid_campaign_map) - encontrados}
        
        NOTA: A Meta não fornece uma API para consultar diretamente campanhas a partir de FBclids.
        Os eventos foram enviados para a API de Conversões, mas as campanhas associadas 
        são apenas aproximações baseadas nas campanhas ativas.
    """)
    
    st.info("""
        ℹ️ Recomendações para rastreamento preciso de campanhas:
        
        1. Use parâmetros UTM em todos os seus links do Facebook
        2. Configure o Facebook Pixel no seu site
        3. Implemente a API de Conversões diretamente no seu site
        4. Considere usar um sistema de atribuição de terceiros
        
        Consulte a documentação: https://developers.facebook.com/docs/marketing-api/conversions-api/
    """)
    
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
