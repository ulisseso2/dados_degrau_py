import streamlit as st
import pandas as pd
import plotly.express as px
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric
from google.oauth2 import service_account
from dotenv import load_dotenv
import os

# Carrega as variáveis do .env (só terá efeito no ambiente local)
load_dotenv()


# ==============================================================================
# 2. FUNÇÕES DE DADOS (LÓGICA DE ACESSO À API)
# ==============================================================================

def get_ga_credentials():
    """
    Carrega as credenciais de forma híbrida: de st.secrets (produção) 
    ou de um arquivo JSON local (desenvolvimento).
    """
    try:
        # Tenta carregar do Streamlit Secrets (para produção)
        creds_dict = st.secrets["gcp_service_account"]
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
    except (st.errors.StreamlitAPIException, KeyError):
        # Se falhar (ambiente local), carrega do arquivo .env
        file_path = os.getenv("GCP_SERVICE_ACCOUNT_FILE")
        if file_path and os.path.exists(file_path):
            credentials = service_account.Credentials.from_service_account_file(file_path)
        else:
            credentials = None
    return credentials

def run_ga_report(client, property_id, dimensions, metrics, date_ranges, limit=10):
    """Função genérica para executar um relatório na API do GA4."""
    try:
        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=dimensions,
            metrics=metrics,
            date_ranges=date_ranges,
            limit=limit
        )
        response = client.run_report(request)
        return response
    except Exception as e:
        st.warning(f"Atenção: A consulta ao Google Analytics falhou. Erro: {e}")
        return None

def mostrar_kpis_validacao(client, property_id):
    """Busca as métricas principais do GA4 para um período e as exibe em cards."""
    st.subheader("Métricas Principais (Últimos 28 dias)")
    
    response = run_ga_report(
        client=client,
        property_id=property_id,
        dimensions=[], # Sem dimensão para totais
        metrics=[Metric(name="activeUsers"), Metric(name="sessions"), Metric(name="screenPageViews"), Metric(name="conversions")],
        date_ranges=[DateRange(start_date="28daysAgo", end_date="today")],
        limit=1
    )
    
    if response and response.rows:
        row = response.rows[0]
        usuarios = int(row.metric_values[0].value)
        sessoes = int(row.metric_values[1].value)
        visualizacoes = int(row.metric_values[2].value)
        conversoes = int(row.metric_values[3].value)
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Usuários Ativos", f"{usuarios:,}".replace(",", "."))
        col2.metric("Sessões", f"{sessoes:,}".replace(",", "."))
        col3.metric("Visualizações de Página", f"{visualizacoes:,}".replace(",", "."))
        col4.metric("Conversões", f"{conversoes:,}".replace(",", "."))
    else:
        st.info("Não foi possível carregar os KPIs de validação.")

def get_top_pages(client, property_id, days):
    """Busca e formata as 10 páginas mais vistas."""
    response = run_ga_report(
        client, property_id,
        dimensions=[Dimension(name="pageTitle")],
        metrics=[Metric(name="screenPageViews")],
        date_ranges=[DateRange(start_date=days, end_date="today")],
        limit=10
    )
    if response:
        rows = [{'Título da Página': r.dimension_values[0].value, 'Visualizações': int(r.metric_values[0].value)} for r in response.rows]
        return pd.DataFrame(rows)
    return pd.DataFrame()

def get_sessions_by_campaign(client, property_id, days):
    """Busca e formata as 15 campanhas com mais sessões."""
    response = run_ga_report(
        client, property_id,
        dimensions=[Dimension(name="sessionCampaignName")],
        metrics=[Metric(name="sessions")],
        date_ranges=[DateRange(start_date=days, end_date="today")],
        limit=15
    )
    if response:
        rows = []
        for r in response.rows:
            name = r.dimension_values[0].value
            name = "Acesso Direto / Desconhecido" if name in ["(not set)", "(direct)"] else name
            rows.append({'Campanha': name, 'Sessões': int(r.metric_values[0].value)})
        
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.groupby('Campanha')['Sessões'].sum().sort_values(ascending=False).reset_index()
        return df
    return pd.DataFrame()

# ==============================================================================
# 3. FUNÇÃO PRINCIPAL DA PÁGINA (run_page)
# ==============================================================================

def run_page():
    st.title("📊 Análise do Google Analytics (GA4)")
    st.markdown("Visão geral de aquisição e engajamento de usuários.")

    PROPERTY_ID = "327463413"
    credentials = get_ga_credentials()

    if not credentials:
        st.error("Falha na autenticação com o Google. Verifique as configurações de segredos ou o arquivo .env.")
        st.stop()
        
    client = BetaAnalyticsDataClient(credentials=credentials)
    
    st.success("🎉 Conexão com a API do Google Analytics bem-sucedida!")
    
    # --- Seção de Validação ---
    mostrar_kpis_validacao(client, PROPERTY_ID)
    st.divider()

    # --- Seção de Análises de Aquisição e Engajamento ---
    st.header("Visão Geral de Aquisição e Engajamento")
    
    periodo_dias = st.selectbox(
        "Selecione o período para as análises abaixo:",
        options=[7, 28, 90],
        format_func=lambda x: f"Últimos {x} dias",
        index=1
    )
    periodo_ga = f"{periodo_dias}daysAgo"
    
    # --- Análise de Páginas Populares ---
    st.subheader("Top 10 Páginas Mais Vistas")
    df_pages = get_top_pages(client, PROPERTY_ID, days=periodo_ga)
    if not df_pages.empty:
        st.dataframe(df_pages, use_container_width=True, hide_index=True)
    else:
        st.info("Não há dados de páginas para o período selecionado.")

    st.divider()

    # --- Análise de Sessões por Campanha ---
    st.subheader("Top 15 Campanhas por Sessões")
    df_campaigns = get_sessions_by_campaign(client, PROPERTY_ID, days=periodo_ga)
    if not df_campaigns.empty:
        fig_campaigns = px.bar(
            df_campaigns.sort_values("Sessões", ascending=True),
            x="Sessões", y="Campanha", orientation='h', text="Sessões",
            title="Sessões por Campanha"
        )
        fig_campaigns.update_traces(textposition='outside', marker_color='#ff7f0e')
        fig_campaigns.update_layout(yaxis_title=None, height=500, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_campaigns, use_container_width=True)
    else:
        st.info("Não há dados de campanhas para o período selecionado.")