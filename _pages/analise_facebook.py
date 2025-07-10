# _pages/analise_facebook.py

import streamlit as st
import pandas as pd
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adsinsights import AdsInsights
from dotenv import load_dotenv
import os
from datetime import datetime

# Carrega as variáveis do .env (só terá efeito no ambiente local)
load_dotenv()

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
        st.success("Conexão com a API do Facebook bem-sucedida!", icon="👍")
        return account
    except Exception as e:
        st.error(f"Falha ao inicializar a API do Facebook: {e}")
        return None


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
    
def formatar_reais(valor):
    """Formata um número para o padrão monetário brasileiro."""
    if pd.isna(valor) or valor == 0: return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def run_page():
    st.title("📢 Análise de Campanhas - Meta (Facebook Ads)")
    
    account = init_facebook_api()

    if account:
        # --- FILTRO DE DATA NA BARRA LATERAL ---
        st.sidebar.header("Filtro de Período (Facebook)")
        hoje = datetime.now().date()
        data_inicio_padrao = hoje - pd.Timedelta(days=27)
        
        periodo_selecionado = st.sidebar.date_input(
            "Selecione o Período de Análise:",
            [data_inicio_padrao, hoje],
            key="fb_date_range"
        )

        if len(periodo_selecionado) != 2:
            st.warning("Por favor, selecione um período de datas válido.")
            st.stop()

        start_date, end_date = periodo_selecionado
        st.info(f"Exibindo dados de **{start_date.strftime('%d/%m/%Y')}** a **{end_date.strftime('%d/%m/%Y')}**")
        st.divider()

        # --- ANÁLISE DE PERFORMANCE DE CAMPANHAS ---
        st.header("Desempenho Geral das Campanhas")
        
        # Chama a nova função para buscar os dados
        df_insights = get_facebook_campaign_insights(account, start_date, end_date)

        if not df_insights.empty:
            # Exibe os totais em cards
            total_custo = df_insights['Custo'].sum()
            total_cliques = df_insights['Cliques'].sum()
            
            col1, col2 = st.columns(2)
            col1.metric("Custo Total no Período", formatar_reais(total_custo))
            col2.metric("Total de Cliques", f"{total_cliques:,}".replace(",", "."))

            # Exibe a tabela detalhada
            st.dataframe(
                df_insights.sort_values("Custo", ascending=False),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Custo": st.column_config.NumberColumn("Custo (R$)", format="R$ %.2f"),
                    "CPC": st.column_config.NumberColumn("Custo por Clique (R$)", format="R$ %.2f"),
                    "CTR (%)": st.column_config.ProgressColumn(
                        "Taxa de Cliques (CTR)", format="%.2f%%", min_value=0, max_value=df_insights['CTR (%)'].max()
                    ),
                }
            )
        else:
            st.info("Não foram encontrados dados de campanhas para o período selecionado.")
            
    else:
        st.warning("A conexão com a API do Facebook não pôde ser estabelecida.")
