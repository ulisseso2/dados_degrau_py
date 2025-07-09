# _pages/analise_ga.py - Versão Final Refatorada e Unificada

import streamlit as st
import pandas as pd
import plotly.express as px
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric, OrderBy
from google.oauth2 import service_account
from dotenv import load_dotenv
import os
from datetime import datetime

# Carrega as variáveis do .env (só terá efeito no ambiente local)
load_dotenv()

# ==============================================================================
# 1. FUNÇÕES AUXILIARES
# ==============================================================================

def get_ga_credentials():
    """Carrega as credenciais de forma híbrida e segura."""
    try:
        creds_dict = st.secrets["gcp_service_account"]
        return service_account.Credentials.from_service_account_info(creds_dict)
    except (st.errors.StreamlitAPIException, KeyError):
        file_path = os.getenv("GCP_SERVICE_ACCOUNT_FILE")
        if file_path and os.path.exists(file_path):
            return service_account.Credentials.from_service_account_file(file_path)
    return None

def run_ga_report(client, property_id, dimensions, metrics, start_date, end_date, limit=15, order_bys=None):
    """Função ÚNICA e robusta para executar qualquer relatório no GA4."""
    try:
        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=dimensions,
            metrics=metrics,
            date_ranges=[DateRange(start_date=start_date.strftime('%Y-%m-%d'), end_date=end_date.strftime('%Y-%m-%d'))],
            limit=limit, # <-- PARÂMETRO ADICIONADO DE VOLTA
            order_bys=order_bys if order_bys else []
        )
        return client.run_report(request)
    except Exception as e:
        st.warning(f"Atenção: A consulta ao Google Analytics falhou. Erro: {e}")
        return None

def formatar_reais(valor):
    """Formata um número para o padrão monetário brasileiro."""
    if pd.isna(valor) or valor == 0: return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ==============================================================================
# 2. FUNÇÃO PRINCIPAL DA PÁGINA (run_page)
# ==============================================================================

def run_page():
    st.title("📊 Análise de Performance Digital (GA4)")
    
    # Adicionamos a função auxiliar aqui para ficar disponível para as métricas
    def formatar_reais(valor):
        if pd.isna(valor) or valor == 0: return "R$ 0,00"
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    PROPERTY_ID = "327463413"
    credentials = get_ga_credentials()

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

    # --- ANÁLISE 1: CUSTO E PERFORMANCE DE CAMPANHAS ---
    st.header("💸 Análise de Custo e Performance de Campanhas")
    
    cost_response = run_ga_report(
        client, PROPERTY_ID,
        dimensions=[Dimension(name="sessionCampaignName")],
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
        st.metric("Custo Total no Período", formatar_reais(custo_total_periodo))
        
        st.info("CPA (Custo por Conversão) mostra quanto você investiu em média para gerar uma conversão registrada no GA4.")
        st.dataframe(df_performance, use_container_width=True, hide_index=True,
            column_config={
                "Custo": st.column_config.NumberColumn("Custo Total", format="R$ %.2f"),
                "CPA (Custo por Conversão)": st.column_config.NumberColumn("CPA (R$)", format="R$ %.2f"),
                "Conversões": st.column_config.NumberColumn("Nº de Conversões", format="%d")
            })
    else:
        st.info("Não foram encontrados dados de custo para o período selecionado.")

    st.divider()

    # --- ADICIONADO: ANÁLISE 2: PÁGINAS MAIS ACESSADAS ---
    st.header("📄 Análise de Páginas Mais Acessadas")

    pages_response = run_ga_report(
        client, PROPERTY_ID,
        dimensions=[Dimension(name="pageTitle")],
        metrics=[Metric(name="screenPageViews")],
        start_date=start_date, end_date=end_date,
        limit=15, # Limita às Top 15 páginas
        order_bys=[{'metric': {'metric_name': 'screenPageViews'}, 'desc': True}]
    )

    if pages_response and pages_response.rows:
        page_rows = [{'Página': r.dimension_values[0].value, 'Visualizações': int(r.metric_values[0].value)} for r in pages_response.rows]
        df_pages = pd.DataFrame(page_rows)
        
        fig_pages = px.bar(
            df_pages.sort_values("Visualizações", ascending=True),
            x="Visualizações",
            y="Página",
            orientation='h',
            text="Visualizações",
            title="Top 15 Páginas Mais Vistas no Período"
        )
        fig_pages.update_traces(textposition='outside', marker_color='#2ca02c')
        fig_pages.update_layout(yaxis_title=None, height=500)
        st.plotly_chart(fig_pages, use_container_width=True)
    else:
        st.info("Não há dados de visualização de páginas para o período.")