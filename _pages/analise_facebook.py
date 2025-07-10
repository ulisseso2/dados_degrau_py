# _pages/analise_facebook.py

import streamlit as st
import pandas as pd
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adsinsights import AdsInsights
from dotenv import load_dotenv
import os
from datetime import datetime
import plotly.express as px

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

    st.divider()
    # ==============================================================================
    # NOVA SEÇÃO: PERFIL DE PÚBLICO E PLATAFORMA
    # ==============================================================================
    st.header("👤 Perfil do Público e Plataformas")

    # --- Análise Demográfica ---
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("##### Gênero")
        df_gender = get_facebook_breakdown_insights(account, start_date, end_date, 'gender')
        if not df_gender.empty:
            fig_gender = px.pie(df_gender, names='Segmento', values='Custo', hole=0.4)
            st.plotly_chart(fig_gender, use_container_width=True)

    with col2:
        st.markdown("##### Faixa Etária")
        df_age = get_facebook_breakdown_insights(account, start_date, end_date, 'age')
        if not df_age.empty:
            fig_age = px.bar(df_age, x='Custo', y='Segmento', orientation='h', text_auto='.2s')
            fig_age.update_layout(yaxis_title=None, xaxis_title="Custo (R$)")
            st.plotly_chart(fig_age, use_container_width=True)

    with col3:
        st.markdown("##### Top 5 Regiões (Estados)")
        df_region = get_facebook_breakdown_insights(account, start_date, end_date, 'region')
        if not df_region.empty:
            fig_region = px.bar(df_region.head(5).sort_values("Custo", ascending=True), x='Custo', y='Segmento', orientation='h', text_auto='.2s')
            fig_region.update_layout(yaxis_title=None, xaxis_title="Custo (R$)")
            st.plotly_chart(fig_region, use_container_width=True)

    st.divider()

    # --- Análise de Tecnologia e Plataforma ---
    colA, colB = st.columns(2)
    with colA:
        st.markdown("##### Plataforma (Facebook, Instagram, etc.)")
        df_platform = get_facebook_breakdown_insights(account, start_date, end_date, 'publisher_platform')
        if not df_platform.empty:
            fig_platform = px.pie(df_platform, names='Segmento', values='Custo', hole=0.4)
            st.plotly_chart(fig_platform, use_container_width=True)

    with colB:
        st.markdown("##### Tipo de Dispositivo")
        df_device = get_facebook_breakdown_insights(account, start_date, end_date, 'impression_device')
        if not df_device.empty:
            fig_device = px.pie(df_device, names='Segmento', values='Custo', hole=0.4)
            st.plotly_chart(fig_device, use_container_width=True)
