import streamlit as st
import os
from datetime import datetime
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

load_dotenv()
load_dotenv('.facebook_credentials.env', override=True)

# Função auxiliar para formatar valores monetários
def formatar_reais(valor):
    """Formata um número para o padrão monetário brasileiro."""
    if pd.isna(valor) or valor == 0:
        return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# Inicializa o cliente do Google Ads
def init_google_ads_client(empresa="Degrau"):
    """
    Inicializa o cliente do Google Ads de forma híbrida,
    lendo de st.secrets ou do arquivo google-ads.yaml.
    Suporta Degrau e Central.
    """
    secrets_key = "google_ads" if empresa == "Degrau" else "google_ads_central"
    yaml_file = "google-ads.yaml" if empresa == "Degrau" else "google-ads_central.yaml"

    try:
        google_ads_config = st.secrets[secrets_key]
        config_dict = {
            "developer_token": google_ads_config["developer_token"],
            "client_id": google_ads_config["client_id"],
            "client_secret": google_ads_config["client_secret"],
            "refresh_token": google_ads_config["refresh_token"],
            "login_customer_id": str(google_ads_config["login_customer_id"]),
            "use_proto_plus": google_ads_config.get("use_proto_plus", True)
        }
        config_str = yaml.dump(config_dict)
        return GoogleAdsClient.load_from_string(config_str)
    except (st.errors.StreamlitAPIException, KeyError):
        if os.path.exists(yaml_file):
            return GoogleAdsClient.load_from_storage(yaml_file)
    return None

# Função para buscar dados do Google Ads
def get_google_ads_campaign_data(client, customer_id, start_date, end_date):
    """
    Busca métricas de campanhas do Google Ads incluindo CTR, CPC, CPA e conversões.
    """
    try:
        ga_service = client.get_service("GoogleAdsService")
        
        query = f"""
            SELECT
                campaign.name,
                campaign.id,
                metrics.cost_micros,
                metrics.impressions,
                metrics.clicks,
                metrics.ctr,
                metrics.average_cpc,
                metrics.conversions,
                metrics.cost_per_conversion
            FROM campaign
            WHERE segments.date BETWEEN '{start_date.strftime('%Y-%m-%d')}' 
                AND '{end_date.strftime('%Y-%m-%d')}'
                AND campaign.status = 'ENABLED'
            ORDER BY metrics.cost_micros DESC
        """
        
        response = ga_service.search(customer_id=customer_id, query=query)
        
        rows = []
        for row in response:
            campaign = row.campaign
            metrics = row.metrics
            
            # Converte micros para valor real (Google Ads usa micros = valor * 1.000.000)
            custo = metrics.cost_micros / 1_000_000
            cpc = metrics.average_cpc / 1_000_000 if metrics.average_cpc else 0
            cpa = metrics.cost_per_conversion / 1_000_000 if metrics.cost_per_conversion else 0
            
            rows.append({
                'Campanha': campaign.name,
                'ID': campaign.id,
                'Custo': custo,
                'Impressões': metrics.impressions,
                'Cliques': metrics.clicks,
                'CTR (%)': metrics.ctr * 100,  # Converte para percentual
                'CPC': cpc,
                'Conversões': metrics.conversions,
                'CPA': cpa
            })
        
        df = pd.DataFrame(rows)
        
        if not df.empty:
            # Extrai o curso/produto do nome da campanha (conteúdo entre {})
            df['Curso Venda'] = df['Campanha'].str.extract(r'\{(.*?)\}')[0]
            df['Curso Venda'] = df['Curso Venda'].fillna('Não Especificado')
        
        return df
    
    except GoogleAdsException as ex:
        st.error(f"Erro ao buscar dados do Google Ads: {ex}")
        for error in ex.failure.errors:
            st.error(f"Erro: {error.message}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro inesperado ao buscar dados do Google Ads: {e}")
        return pd.DataFrame()

# action_types que contam como conversão
CONVERSION_ACTIONS = {
    'purchase', 'lead', 'omni_purchase',
    'offsite_conversion.fb_pixel_purchase',
    'offsite_conversion.fb_pixel_lead',
    'submit_application_total',
    'onsite_conversion.lead_grouped',
}

# Função para inicializar a API do Facebook
def init_facebook_api(empresa="Degrau"):
    """
    Inicializa a API do Facebook de forma híbrida, lendo de st.secrets ou .env.
    Suporta Degrau e Central.
    """
    secrets_key = "facebook_api" if empresa == "Degrau" else "facebook_api_central"
    env_suffix = "" if empresa == "Degrau" else "_CENTRAL"

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

# Função para buscar insights de campanhas do Facebook
def get_facebook_campaign_insights(account, start_date, end_date):
    """
    Busca insights de performance para todas as campanhas em um período,
    incluindo CTR, CPC, CPA e conversões (com submit_application_total).
    """
    try:
        fields = [
            AdsInsights.Field.campaign_name,
            AdsInsights.Field.spend,
            AdsInsights.Field.impressions,
            AdsInsights.Field.clicks,
            AdsInsights.Field.ctr,
            AdsInsights.Field.cpc,
            AdsInsights.Field.actions,
            AdsInsights.Field.cost_per_action_type,
            AdsInsights.Field.conversions,
        ]
        params = {
            'level': 'campaign',
            'time_range': {
                'since': start_date.strftime('%Y-%m-%d'),
                'until': end_date.strftime('%Y-%m-%d'),
            },
        }

        insights = account.get_insights(fields=fields, params=params)
        rows = []
        for insight in insights:
            conversoes = 0

            # 1) Tenta campo 'conversions' (submit_application_total)
            if 'conversions' in insight:
                for conv in insight['conversions']:
                    if conv['action_type'] == 'submit_application_total':
                        conversoes += int(conv.get('value', 0))

            # 2) Fallback: busca em 'actions'
            if conversoes == 0 and AdsInsights.Field.actions in insight:
                for action in insight[AdsInsights.Field.actions]:
                    if action['action_type'] in CONVERSION_ACTIONS:
                        conversoes += int(action.get('value', 0))

            custo = float(insight[AdsInsights.Field.spend])
            cpa = custo / conversoes if conversoes > 0 else 0

            ctr_value = float(insight.get(AdsInsights.Field.ctr, 0))
            cpc_value = float(insight.get(AdsInsights.Field.cpc, 0))

            rows.append({
                'Campanha': insight[AdsInsights.Field.campaign_name],
                'Custo': custo,
                'Impressões': int(insight.get(AdsInsights.Field.impressions, 0)),
                'Cliques': int(insight.get(AdsInsights.Field.clicks, 0)),
                'CTR (%)': ctr_value,
                'CPC': cpc_value,
                'Conversões': conversoes,
                'CPA': cpa,
            })

        df = pd.DataFrame(rows)
        if not df.empty:
            df['Curso Venda'] = df['Campanha'].str.extract(r'\{(.*?)\}')[0]
            df['Curso Venda'] = df['Curso Venda'].fillna('Não Especificado')

        return df

    except Exception as e:
        st.error(f"Erro ao buscar insights de campanhas do Facebook: {e}")
        return pd.DataFrame()

def run_page():
    st.title("📊 Análise Combinada: Google Ads + Meta Ads")
    st.markdown("**Dados diretos das APIs do Google Ads e Meta (Facebook) para máxima precisão**")

    # --- FILTROS NA SIDEBAR ---
    st.sidebar.header("Filtros")

    empresa = st.sidebar.selectbox(
        "Empresa:",
        ["Degrau", "Central de Concursos", "Ambas"],
        key="combined_empresa"
    )

    hoje = datetime.now().date()
    data_inicio_padrao = hoje - pd.Timedelta(days=27)

    periodo_selecionado = st.sidebar.date_input(
        "Selecione o Período de Análise:",
        [data_inicio_padrao, hoje],
        key="combined_date_range"
    )

    if len(periodo_selecionado) != 2:
        st.warning("Por favor, selecione um período de datas válido na barra lateral.")
        st.stop()
    
    start_date, end_date = periodo_selecionado
    st.info(f"📅 **{empresa}** — Período: **{start_date.strftime('%d/%m/%Y')}** a **{end_date.strftime('%d/%m/%Y')}**")

    # --- INICIALIZAÇÃO DOS CLIENTES ---
    empresas_para_buscar = []
    if empresa == "Ambas":
        empresas_para_buscar = ["Degrau", "Central"]
    elif empresa == "Central de Concursos":
        empresas_para_buscar = ["Central"]
    else:
        empresas_para_buscar = ["Degrau"]

    # --- BUSCA DE DADOS ---
    df_google = pd.DataFrame()
    df_facebook = pd.DataFrame()

    for emp in empresas_para_buscar:
        customer_ids = {"Degrau": "4934481887", "Central": "1646681121"}
        customer_id_key = "google_ads" if emp == "Degrau" else "google_ads_central"

        google_client = init_google_ads_client(emp)
        if google_client:
            try:
                cid = st.secrets[customer_id_key]["customer_id"]
            except Exception:
                cid = customer_ids[emp]
            with st.spinner(f"🔄 Buscando dados do Google Ads ({emp})..."):
                df_g = get_google_ads_campaign_data(google_client, cid, start_date, end_date)
                if not df_g.empty:
                    df_g['Empresa'] = emp
                    df_google = pd.concat([df_google, df_g], ignore_index=True)

        fb_account = init_facebook_api(emp)
        if fb_account:
            with st.spinner(f"🔄 Buscando dados do Meta Ads ({emp})..."):
                df_f = get_facebook_campaign_insights(fb_account, start_date, end_date)
                if not df_f.empty:
                    df_f['Empresa'] = emp
                    df_facebook = pd.concat([df_facebook, df_f], ignore_index=True)

    if df_google.empty and df_facebook.empty:
        st.warning("⚠️ Nenhum dado encontrado para o período selecionado.")
        st.stop()

    # --- MÉTRICAS GERAIS ---
    st.header("📊 Visão Geral do Investimento")
    
    col1, col2, col3 = st.columns(3)
    
    custo_google = df_google['Custo'].sum() if not df_google.empty else 0
    custo_facebook = df_facebook['Custo'].sum() if not df_facebook.empty else 0
    custo_total = custo_google + custo_facebook
    
    col1.metric("💰 Google Ads", formatar_reais(custo_google))
    col2.metric("💰 Meta Ads", formatar_reais(custo_facebook))
    col3.metric("💰 Total Investido", formatar_reais(custo_total))
    
    # Métricas de performance
    col4, col5, col6 = st.columns(3)
    
    impressoes_google = df_google['Impressões'].sum() if not df_google.empty else 0
    impressoes_facebook = df_facebook['Impressões'].sum() if not df_facebook.empty else 0
    
    cliques_google = df_google['Cliques'].sum() if not df_google.empty else 0
    cliques_facebook = df_facebook['Cliques'].sum() if not df_facebook.empty else 0
    
    conversoes_google = df_google['Conversões'].sum() if not df_google.empty else 0
    conversoes_facebook = df_facebook['Conversões'].sum() if not df_facebook.empty else 0
    
    col4.metric("👁️ Total de Impressões", f"{int(impressoes_google + impressoes_facebook):,}".replace(",", "."))
    col5.metric("🖱️ Total de Cliques", f"{int(cliques_google + cliques_facebook):,}".replace(",", "."))
    col6.metric("🎯 Total de Conversões", f"{int(conversoes_google + conversoes_facebook):,}".replace(",", "."))
    
    st.divider()

    # --- TABELA CONSOLIDADA POR CURSO VENDA ---
    st.header("📈 Análise Consolidada por Curso/Produto")
    
    if not df_google.empty and not df_facebook.empty:
        # Agrupa Google Ads por Curso Venda
        df_google_agg = df_google.groupby('Curso Venda').agg({
            'Custo': 'sum',
            'Impressões': 'sum',
            'Cliques': 'sum',
            'Conversões': 'sum'
        }).reset_index()
        
        df_google_agg.columns = ['Curso Venda', 'Custo Google', 'Impressões Google', 'Cliques Google', 'Conversões Google']
        
        # Calcula métricas do Google
        df_google_agg['CTR Google (%)'] = (df_google_agg['Cliques Google'] / df_google_agg['Impressões Google'] * 100).fillna(0)
        df_google_agg['CPA Google'] = (df_google_agg['Custo Google'] / df_google_agg['Conversões Google']).replace([float('inf'), -float('inf')], 0).fillna(0)
        
        # Agrupa Facebook por Curso Venda
        df_facebook_agg = df_facebook.groupby('Curso Venda').agg({
            'Custo': 'sum',
            'Impressões': 'sum',
            'Cliques': 'sum',
            'Conversões': 'sum'
        }).reset_index()
        
        df_facebook_agg.columns = ['Curso Venda', 'Custo Facebook', 'Impressões Facebook', 'Cliques Facebook', 'Conversões Facebook']
        
        # Calcula métricas do Facebook
        df_facebook_agg['CTR Facebook (%)'] = (df_facebook_agg['Cliques Facebook'] / df_facebook_agg['Impressões Facebook'] * 100).fillna(0)
        df_facebook_agg['CPA Facebook'] = (df_facebook_agg['Custo Facebook'] / df_facebook_agg['Conversões Facebook']).replace([float('inf'), -float('inf')], 0).fillna(0)
        
        # Merge das duas tabelas
        df_consolidado = pd.merge(
            df_google_agg,
            df_facebook_agg,
            on='Curso Venda',
            how='outer'
        ).fillna(0)
        
        # Calcula totais consolidados
        df_consolidado['Custo Total'] = df_consolidado['Custo Google'] + df_consolidado['Custo Facebook']
        df_consolidado['Impressões Total'] = df_consolidado['Impressões Google'] + df_consolidado['Impressões Facebook']
        df_consolidado['Cliques Total'] = df_consolidado['Cliques Google'] + df_consolidado['Cliques Facebook']
        df_consolidado['Conversões Total'] = df_consolidado['Conversões Google'] + df_consolidado['Conversões Facebook']
        df_consolidado['CTR Combinado (%)'] = (df_consolidado['Cliques Total'] / df_consolidado['Impressões Total'] * 100).fillna(0)
        df_consolidado['CPA Combinado'] = (df_consolidado['Custo Total'] / df_consolidado['Conversões Total']).replace([float('inf'), -float('inf')], 0).fillna(0)
        
        # Ordena por custo total
        df_consolidado = df_consolidado.sort_values('Custo Total', ascending=False).reset_index(drop=True)
        
        # Exibe a tabela com formatação
        st.dataframe(
            df_consolidado,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Custo Google": st.column_config.NumberColumn("💰 Google Ads", format="R$ %.2f"),
                "Custo Facebook": st.column_config.NumberColumn("💰 Meta Ads", format="R$ %.2f"),
                "Custo Total": st.column_config.NumberColumn("💰 Total", format="R$ %.2f"),
                "CTR Google (%)": st.column_config.NumberColumn("📊 CTR Google", format="%.2f%%"),
                "CTR Facebook (%)": st.column_config.NumberColumn("📊 CTR Meta", format="%.2f%%"),
                "CTR Combinado (%)": st.column_config.NumberColumn("📊 CTR Combinado", format="%.2f%%"),
                "CPA Google": st.column_config.NumberColumn("🎯 CPA Google", format="R$ %.2f"),
                "CPA Facebook": st.column_config.NumberColumn("🎯 CPA Meta", format="R$ %.2f"),
                "CPA Combinado": st.column_config.NumberColumn("🎯 CPA Combinado", format="R$ %.2f"),
                "Conversões Google": st.column_config.NumberColumn("✅ Conv. Google", format="%d"),
                "Conversões Facebook": st.column_config.NumberColumn("✅ Conv. Meta", format="%d"),
                "Conversões Total": st.column_config.NumberColumn("✅ Total Conv.", format="%d"),
            }
        )
        
        # Gráfico de comparação
        st.subheader("📊 Comparação Visual: Google Ads vs Meta Ads")
        
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            name='Google Ads',
            x=df_consolidado['Curso Venda'],
            y=df_consolidado['Custo Google'],
            marker_color='#4285F4'
        ))
        
        fig.add_trace(go.Bar(
            name='Meta Ads',
            x=df_consolidado['Curso Venda'],
            y=df_consolidado['Custo Facebook'],
            marker_color='#1877F2'
        ))
        
        fig.update_layout(
            barmode='group',
            title='Investimento por Curso/Produto',
            xaxis_title='Curso',
            yaxis_title='Investimento (R$)',
            height=500
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Gráfico de CPA Combinado
        st.subheader("🎯 CPA Combinado por Curso")
        
        df_cpa_filtrado = df_consolidado[df_consolidado['CPA Combinado'] > 0].copy()
        
        if not df_cpa_filtrado.empty:
            fig_cpa = px.bar(
                df_cpa_filtrado,
                x='Curso Venda',
                y='CPA Combinado',
                title='Custo por Aquisição (CPA) por Curso',
                labels={'CPA Combinado': 'CPA (R$)', 'Curso Venda': 'Curso'},
                color='CPA Combinado',
                color_continuous_scale='RdYlGn_r'
            )
            
            fig_cpa.update_layout(height=400)
            st.plotly_chart(fig_cpa, use_container_width=True)
        else:
            st.info("Não há dados de CPA disponíveis para o período.")
        
        # Gráfico de CTR Combinado
        st.subheader("📊 CTR Combinado por Curso")
        
        fig_ctr = px.bar(
            df_consolidado,
            x='Curso Venda',
            y='CTR Combinado (%)',
            title='Taxa de Cliques (CTR) por Curso',
            labels={'CTR Combinado (%)': 'CTR (%)', 'Curso Venda': 'Curso'},
            color='CTR Combinado (%)',
            color_continuous_scale='Viridis'
        )
        
        fig_ctr.update_layout(height=400)
        st.plotly_chart(fig_ctr, use_container_width=True)
        
    else:
        st.info("Dados insuficientes para gerar análise consolidada.")
    
    st.divider()
    
    # --- TABELAS DETALHADAS POR PLATAFORMA ---
    tab1, tab2 = st.tabs(["🔍 Detalhes Google Ads", "🔍 Detalhes Meta Ads"])
    
    with tab1:
        st.subheader("Campanhas Google Ads - Detalhado")
        if not df_google.empty:
            st.dataframe(
                df_google.sort_values('Custo', ascending=False),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Custo": st.column_config.NumberColumn("Custo", format="R$ %.2f"),
                    "CPC": st.column_config.NumberColumn("CPC", format="R$ %.2f"),
                    "CPA": st.column_config.NumberColumn("CPA", format="R$ %.2f"),
                    "CTR (%)": st.column_config.NumberColumn("CTR", format="%.2f%%"),
                }
            )
        else:
            st.info("Nenhum dado do Google Ads disponível.")
    
    with tab2:
        st.subheader("Campanhas Meta Ads - Detalhado")
        if not df_facebook.empty:
            st.dataframe(
                df_facebook.sort_values('Custo', ascending=False),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Custo": st.column_config.NumberColumn("Custo", format="R$ %.2f"),
                    "CPC": st.column_config.NumberColumn("CPC", format="R$ %.2f"),
                    "CPA": st.column_config.NumberColumn("CPA", format="R$ %.2f"),
                    "CTR (%)": st.column_config.NumberColumn("CTR", format="%.2f%%"),
                }
            )
        else:
            st.info("Nenhum dado do Meta Ads disponível.")





