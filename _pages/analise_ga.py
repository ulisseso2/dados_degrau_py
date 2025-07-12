import streamlit as st
import pandas as pd
import plotly.express as px
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric
from google.oauth2 import service_account
from dotenv import load_dotenv
import os
from datetime import datetime
from st_aggrid import GridOptionsBuilder, AgGrid

load_dotenv()

# ==============================================================================
# 1. FUNÇÕES AUXILIARES
# ==============================================================================
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

def formatar_reais(valor):
    """Formata um número para o padrão monetário brasileiro."""
    if pd.isna(valor) or valor == 0: return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ==============================================================================
# 2. FUNÇÃO PRINCIPAL DA PÁGINA (run_page)
# ==============================================================================

def run_page():
    st.title("📊 Análise de Performance Digital (GA4)")

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
 
    # --- ANÁLISE 1: PERFORMANCE DE CAMPANHAS ---
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
        st.metric("Custo Total no Período", formatar_reais(custo_total_periodo))


    st.header("📈 Performance de Campanhas por Curso Venda")

    if not df_performance.empty:
        # --- 1. EXTRAÇÃO DO "CURSO VENDA" ---
        df_agrupado = df_performance.copy()
        
        # Usa regex para extrair o conteúdo dentro de {}
        df_agrupado['Curso Venda'] = df_agrupado['Campanha'].str.extract(r'\{(.*?)\}')
        
        # Se alguma campanha não tiver o padrão, preenche com um valor padrão
        df_agrupado['Curso Venda'].fillna('Não Especificado', inplace=True)
        
        st.info("Esta tabela agrupa as campanhas pelo 'Curso Venda' extraído do nome. Clique na seta (▶) para expandir e ver os detalhes.")

        # --- 2. CONFIGURAÇÃO DA TABELA HIERÁRQUICA AG-GRID ---
        gb = GridOptionsBuilder.from_dataframe(df_agrupado)

        # Configura a coluna "Curso Venda" para ser o grupo
        gb.configure_column("Curso Venda", rowGroup=True, hide=True)
        
        # Configura as outras colunas
        gb.configure_column("Campanha", header_name="Nome da Campanha")
        gb.configure_column(
            "Custo", header_name="Custo", type=["numericColumn", "numberColumnFilter", "customNumericFormat"],
            aggFunc='sum',
        )
        gb.configure_column(
            "Conversões", header_name="Conversões", type=["numericColumn", "numberColumnFilter", "customNumericFormat"],
            aggFunc='sum',

        )
        gb.configure_column(
            "CPA (Custo por Conversão)", header_name="CPA", type=["numericColumn", "numberColumnFilter", "customNumericFormat"],
            # Calcula o CPA agregado para o grupo
            valueGetter='(params.node.aggData.Custo && params.node.aggData.Conversões) ? params.node.aggData.Custo / params.node.aggData.Conversões : null',
            valueFormatter="data['CPA (Custo por Conversão)'] ? data['CPA (Custo por Conversão)'].toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'}) : ''"
        )
        
        grid_options = gb.build()
        
        # Define a aparência da coluna de grupo
        grid_options["autoGroupColumnDef"] = {
            "headerName": "Curso Venda (Produto)",
            "minWidth": 250,
            "cellRendererParams": {"suppressCount": True}
        }
        

        # --- 3. EXIBIÇÃO DA TABELA ---
        AgGrid(
            df_agrupado,
            gridOptions=grid_options,
            width='100%',
            theme='streamlit',
            allow_unsafe_jscode=True,
            enable_enterprise_modules=True
        )
    else:
        st.info("Não há dados de performance para agrupar por Curso Venda.")

    st.divider()

        # --- NOVA SEÇÃO: KPIs GERAIS DE ENGAJAMENTO ---
    st.header("Visão Geral do Período")
    
    kpi_response = run_ga_report(client, PROPERTY_ID, [], 
        [Metric(name="activeUsers"), Metric(name="newUsers"), Metric(name="screenPageViews"), Metric(name="eventCount"), Metric(name="userEngagementDuration")],
        start_date, end_date, limit=1)

    if kpi_response and kpi_response.rows:
        row = kpi_response.rows[0]
        usuarios_ativos = int(row.metric_values[0].value)
        novos_usuarios = int(row.metric_values[1].value)
        visualizacoes = int(row.metric_values[2].value)
        eventos = int(row.metric_values[3].value)
        duracao_total_engajamento = float(row.metric_values[4].value)

        # Calcula o tempo médio de engajamento por usuário
        tempo_medio_engajamento = (duracao_total_engajamento / usuarios_ativos) if usuarios_ativos > 0 else 0
        minutos = int(tempo_medio_engajamento // 60)
        segundos = int(tempo_medio_engajamento % 60)
        
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Usuários Ativos", f"{usuarios_ativos:,}".replace(",", "."))
        col2.metric("Novos Usuários", f"{novos_usuarios:,}".replace(",", "."))
        col3.metric("Visualizações", f"{visualizacoes:,}".replace(",", "."))
        col4.metric("Total de Eventos", f"{eventos:,}".replace(",", "."))
        col5.metric("Tempo Médio de Engajamento", f"{minutos:02d}:{segundos:02d} min")
    else:
        st.info("Não foi possível carregar os KPIs.")

    st.divider()

    # --- NOVA SEÇÃO: TABELA DE AQUISIÇÃO DE TRÁFEGO ---
    st.header("📈 Aquisição de Tráfego por Canal")

    acq_response = run_ga_report(client, PROPERTY_ID, 
        [Dimension(name="sessionDefaultChannelGroup")], 
        [Metric(name="sessions"), Metric(name="activeUsers"), Metric(name="conversions"), Metric(name="purchaseRevenue")], 
        start_date, end_date)
 
    if acq_response and acq_response.rows:
        rows = []
        for r in acq_response.rows:
            rows.append({
                'Canal': r.dimension_values[0].value,
                'Sessões': int(r.metric_values[0].value),
                'Usuários': int(r.metric_values[1].value),
                'Conversões': int(r.metric_values[2].value),
                'Receita (R$)': float(r.metric_values[3].value)
            })
        
        df_acquisition = pd.DataFrame(rows).sort_values("Sessões", ascending=False)
        
        st.dataframe(df_acquisition, use_container_width=True, hide_index=True,
            column_config={
                "Receita (R$)": st.column_config.NumberColumn(format="R$ %.2f")
            })
    else:
        st.info("Não há dados de aquisição para o período.")
    

    # Em _pages/analise_ga.py, dentro de run_page()

    st.header("Demografia do Público")
    col1, col2, col3 = st.columns(3)

    # --- Gráfico 1: Gênero (Rosca) ---
    with col1:
        gender_response = run_ga_report(client, PROPERTY_ID,
            [Dimension(name="userGender")], [Metric(name="activeUsers")],
            start_date, end_date)
        
        if gender_response and gender_response.rows:
            df_gender = pd.DataFrame([{'Gênero': r.dimension_values[0].value, 'Usuários': int(r.metric_values[0].value)} for r in gender_response.rows])

            df_gender = df_gender[df_gender['Gênero'] != 'unknown']    

            fig_gender = px.pie(df_gender, names='Gênero', values='Usuários', title='Distribuição por Gênero', hole=0.4)
            st.plotly_chart(fig_gender, use_container_width=True)

    # --- Gráfico 2: Idade (Barras) ---
    with col2:
        age_response = run_ga_report(client, PROPERTY_ID,
            [Dimension(name="userAgeBracket")], [Metric(name="activeUsers")],
            start_date, end_date)
            
        if age_response and age_response.rows:
            df_age = pd.DataFrame([{'Faixa Etária': r.dimension_values[0].value, 'Usuários': int(r.metric_values[0].value)} for r in age_response.rows])

            # Remove a faixa etária desconhecida, se existir
            df_age = df_age[df_age['Faixa Etária'] != 'unknown']

            fig_age = px.bar(
                df_age.sort_values("Usuários", ascending=True), 
                y='Faixa Etária', 
                x='Usuários', 
                orientation='h', 
                title='Distribuição por Idade',
                text='Usuários',
                labels={'Usuários': 'Número de Usuários', 'Faixa Etária': 'Faixa Etária'}
            )
            fig_age.update_traces(texttemplate='%{text:.2s}', textposition='inside')
            fig_age.update_layout(yaxis_title=None)
            st.plotly_chart(fig_age, use_container_width=True)

    # --- Gráfico 3: Cidade (Barras) ---
    with col3:
        city_response = run_ga_report(client, PROPERTY_ID,
            [Dimension(name="city")], [Metric(name="activeUsers")],
            start_date, end_date, limit=10, order_bys=[{'metric': {'metric_name': 'activeUsers'}, 'desc': True}])
            
        if city_response and city_response.rows:
            df_city = pd.DataFrame([{'Cidade': r.dimension_values[0].value, 'Usuários': int(r.metric_values[0].value)} for r in city_response.rows])
            fig_city = px.bar(
                df_city.sort_values("Usuários", ascending=True), 
                y='Cidade', 
                x='Usuários', 
                orientation='h', 
                title='Top 10 Cidades',
                text='Usuários',
                labels={'Usuários': 'Número de Usuários', 'Cidade': 'Cidade'}
            )
            fig_city.update_traces(texttemplate='%{text:.2s}')
            fig_city.update_layout(yaxis_title=None)
            st.plotly_chart(fig_city, use_container_width=True)

    st.divider()
    st.header("📄 Engajamento por Página")

    # Pede as métricas necessárias para o cálculo
    page_response = run_ga_report(client, PROPERTY_ID,
        [Dimension(name="pageTitle")],
        [Metric(name="screenPageViews"), Metric(name="userEngagementDuration"), Metric(name="activeUsers")],
        start_date, end_date, limit=20, # Top 20 páginas
        order_bys=[{'metric': {'metric_name': 'screenPageViews'}, 'desc': True}])

    if page_response and page_response.rows:
        page_rows = []
        for r in page_response.rows:
            views = int(r.metric_values[0].value)
            total_engagement = float(r.metric_values[1].value)
            users = int(r.metric_values[2].value)
            # Calcula o tempo médio e formata
            avg_time = (total_engagement / users) if users > 0 else 0
            minutos, segundos = divmod(int(avg_time), 60)
            
            page_rows.append({
                'Título da Página': r.dimension_values[0].value,
                'Visualizações': views,
                'Tempo Médio de Engajamento': f"{minutos:02d}:{segundos:02d}"
            })
            
        df_pages = pd.DataFrame(page_rows)
        st.dataframe(df_pages, use_container_width=True, hide_index=True)

    st.divider()
    st.header("Tecnologia de Acesso")
    col1, col2 = st.columns(2)

    # --- Gráfico 1: Categoria de Dispositivo (Rosca) ---
    with col1:
        device_response = run_ga_report(client, PROPERTY_ID,
            [Dimension(name="deviceCategory")], [Metric(name="activeUsers")],
            start_date, end_date)
        
        if device_response and device_response.rows:
            df_device = pd.DataFrame([{'Dispositivo': r.dimension_values[0].value, 'Usuários': int(r.metric_values[0].value)} for r in device_response.rows])
            fig_device = px.pie(df_device, names='Dispositivo', values='Usuários', title='Acessos por Dispositivo', hole=0.4)
            st.plotly_chart(fig_device, use_container_width=True)

    # --- Gráfico 2: Sistema Operacional (Barras) ---
    with col2:
        os_response = run_ga_report(client, PROPERTY_ID,
            [Dimension(name="operatingSystem")], [Metric(name="activeUsers")],
            start_date, end_date, limit=10, order_bys=[{'metric': {'metric_name': 'activeUsers'}, 'desc': True}])
            
        if os_response and os_response.rows:
            df_os = pd.DataFrame([{'Sistema': r.dimension_values[0].value, 'Usuários': int(r.metric_values[0].value)} for r in os_response.rows])
            fig_os = px.bar(
                df_os.sort_values("Usuários", ascending=True), 
                y='Sistema', 
                x='Usuários', 
                orientation='h', 
                title='Top 10 Sistemas Operacionais',
                text='Usuários',
                labels={'Usuários': 'Número de Usuários', 'Sistema': 'Sistema Operacional'}
            )
            fig_os.update_traces(texttemplate='%{text:.2s}')
            fig_os.update_layout(yaxis_title=None)
            st.plotly_chart(fig_os, use_container_width=True)