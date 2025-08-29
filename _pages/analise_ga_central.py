import streamlit as st
import pandas as pd
import plotly.express as px
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric, FilterExpression, Filter
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.oauth2 import service_account
from dotenv import load_dotenv
import yaml
import os
from datetime import datetime
from st_aggrid import GridOptionsBuilder, AgGrid
from utils.sql_loader import carregar_dados
import time
from gclid_db_central import (  # Usando o módulo específico para a Central
    load_gclid_cache,
    save_gclid_cache_batch,
    get_campaign_for_gclid,
)

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BATCH_SIZE = 1000  # Aumentamos o tamanho do lote
REQUEST_DELAY = 1  # Delay entre requests em segundos

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# 1. FUNÇÕES AUXILIARES

# Carrega as credenciais do Google Analytics de forma híbrida
def get_ga_credentials():
    """Carrega as credenciais de forma híbrida - específico para Central"""
    try:
        # Tenta carregar credenciais específicas da Central do Streamlit Secrets
        creds_dict = st.secrets["gcp_service_account_central"]
        return service_account.Credentials.from_service_account_info(creds_dict)
    except (st.errors.StreamlitAPIException, KeyError):
        # Usa o arquivo de credenciais específico para a Central
        file_path = "gcp_credentials_central.json"
        if file_path and os.path.exists(file_path):
            return service_account.Credentials.from_service_account_file(file_path)
    return None

@st.cache_resource
def get_google_ads_client():
    """
    Inicializa o cliente do Google Ads e retorna o cliente e o customer_id para consulta.
    Usa cache para evitar reinicializações repetidas.
    Retorna (client, query_customer_id) em caso de sucesso, e (None, None) em caso de falha.
    """
    config = None
    source = ""

    try:
        # Tenta carregar do Streamlit Secrets (usando a chave específica da Central)
        config_raw = st.secrets["google_ads_central"]
        # Converte para dict se necessário
        if hasattr(config_raw, 'to_dict'):
            config = config_raw.to_dict()
        else:
            config = dict(config_raw)
        source = "Streamlit Secrets (google_ads_central)"
        st.success(f"Credenciais do Google Ads encontradas no {source}.")
    except (st.errors.StreamlitAPIException, KeyError):
        # Fallback para o arquivo yaml local
        yaml_path = "google-ads_central.yaml"  # Arquivo específico para a Central
        if os.path.exists(yaml_path):
            try:
                with open(yaml_path, 'r') as f:
                    config = yaml.safe_load(f)
                source = "arquivo google-ads_central.yaml"
                st.success(f"Credenciais do Google Ads carregadas do {source}.")
                
            except Exception as e:
                st.error(f"Erro ao carregar ou processar o arquivo google-ads_central.yaml: {e}")
                return None, None
        else:
            st.error("Nenhuma fonte de credenciais do Google Ads foi encontrada (nem Secrets, nem google-ads_central.yaml).")
            return None, None

    # Validação unificada das credenciais
    if not isinstance(config, dict):
        st.error(f"Configuração inválida carregada de '{source}'. Esperado um dicionário.")
        return None, None
        
    login_customer_id = config.get("login_customer_id")
    if not login_customer_id:
        st.error(f"A chave 'login_customer_id' (MCC ID) está ausente em '{source}'.")
        return None, None

    query_customer_id = config.get("customer_id")
    if not query_customer_id:
        st.error(f"A chave 'customer_id' (ID da conta a ser consultada) está ausente em '{source}'.")
        return None, None

    try:
        # Inicializa o cliente com a configuração completa
        client = GoogleAdsClient.load_from_dict(config)
        
        # Informações adicionais para diagnóstico
        st.success(f"Cliente do Google Ads inicializado com sucesso!")
        
        # Retorna o cliente e o ID da conta a ser consultada
        return client, str(query_customer_id).replace("-", "")
    except Exception as e:
        st.error(f"Falha ao inicializar o cliente do Google Ads com as credenciais de '{source}': {e}")
        
        # Informações mais detalhadas sobre o erro
        if "API has not been used" in str(e) or "disabled" in str(e):
            st.warning("A API do Google Ads não está ativada. Clique no link abaixo para ativá-la:")
            st.markdown("[Ativar API do Google Ads](https://console.developers.google.com/apis/api/googleads.googleapis.com/overview?project=340986541746)")
        
        return None, None

def get_google_ads_campaign_performance(client, customer_id, start_date, end_date):
    """
    Função para buscar dados de desempenho de campanhas diretamente do Google Ads.
    Retorna informações de campanhas, incluindo custo e conversões.
    """
    try:
        # Inicializa o serviço
        ga_service = client.get_service("GoogleAdsService")
        
        # Formata as datas para o formato esperado pelo Google Ads (YYYY-MM-DD)
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')
        
        # Query GAQL (Google Ads Query Language)
        query = f"""
            SELECT 
                campaign.name, 
                campaign.id, 
                metrics.cost_micros, 
                metrics.conversions,
                metrics.conversions_value
            FROM campaign
            WHERE 
                segments.date >= '{start_date_str}' 
                AND segments.date <= '{end_date_str}'
                AND campaign.status != 'REMOVED'
            ORDER BY metrics.cost_micros DESC
        """
        
        # Executa a consulta
        response = ga_service.search_stream(customer_id=customer_id, query=query)
        
        # Processa os resultados
        campaigns_data = []
        
        for batch in response:
            for row in batch.results:
                # Converte micros (millionths) para valores reais e arredonda para 2 casas decimais
                cost = round(float(row.metrics.cost_micros) / 1000000, 2)
                conversions = float(row.metrics.conversions)
                conversion_value = float(row.metrics.conversions_value)
                
                # Calcula CPA (Custo por Conversão) e arredonda para 2 casas decimais
                cpa = round(cost / conversions, 2) if conversions > 0 else 0
                
                # Extrai nome do curso venda do nome da campanha (se existir no formato {Curso})
                campaign_name = row.campaign.name
                
                campaigns_data.append({
                    'Campanha': campaign_name,
                    'ID da Campanha': row.campaign.id,
                    'Custo': cost,
                    'Conversões': conversions,
                    'Valor de Conversões': conversion_value,
                    'CPA (Custo por Conversão)': cpa
                })
        
        # Retorna como DataFrame
        return pd.DataFrame(campaigns_data)
    
    except GoogleAdsException as ex:
        error_messages = []
        for error in ex.failure.errors:
            error_messages.append(f"Erro {error.error_code.error_code}: {error.message}")
        st.error("\n".join(error_messages))
        return pd.DataFrame()
    
    except Exception as e:
        st.error(f"Erro na consulta do Google Ads: {str(e)}")
        return pd.DataFrame()

def get_campaigns_for_gclids_with_date(client, customer_id, gclid_date_dict):
    """
    Versão otimizada com:
    - Rate limiting
    - Cache integrado
    - Batch processing eficiente
    """
    if not isinstance(gclid_date_dict, dict) or not gclid_date_dict:
        return {}

    ga_service = client.get_service("GoogleAdsService")
    gclid_campaign_map = {}
    batches_processed = 0
    total_gclids = len(gclid_date_dict)

    # Carrega cache existente
    cache = st.session_state.gclid_cache
    
    # Filtra apenas GCLIDs não consultados
    gclids_to_query = {
        gclid: date for gclid, date in gclid_date_dict.items() 
        if gclid not in cache or cache[gclid] == 'Não encontrado'
    }
    
    if not gclids_to_query:
        return {}

    # Agrupa por data para otimizar consultas
    date_groups = {}
    for gclid, date in gclids_to_query.items():
        date_str = date.strftime('%Y-%m-%d')
        date_groups.setdefault(date_str, []).append(gclid)

    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        # Teste de conexão com uma consulta simples antes de prosseguir
        try:
            test_query = "SELECT campaign.id FROM campaign LIMIT 1"
            test_stream = ga_service.search_stream(
                customer_id=customer_id, 
                query=test_query
            )
            
            # Consumir o resultado para verificar se funciona
            for _ in test_stream:
                pass
                
        except GoogleAdsException as test_ex:
            error_details = [error.message for error in test_ex.failure.errors]
            st.error(f"Falha na conexão com Google Ads: {' '.join(error_details)}")
            
            # Mostrar mais detalhes sobre o erro
            st.warning("Detalhes da conta do Google Ads:")
            st.json({
                "customer_id": customer_id,
                "login_customer_id": client._login_customer_id
            })
            
            # Se o erro for sobre API desativada, mostrar um link direto
            if any("SERVICE_DISABLED" in error.message for error in test_ex.failure.errors):
                st.warning("A API do Google Ads parece estar desativada. Clique no link abaixo para ativá-la:")
                st.markdown("[Ativar API do Google Ads](https://console.developers.google.com/apis/api/googleads.googleapis.com/overview)")
                
            return None

        for date_str, gclids in date_groups.items():
            for i in range(0, len(gclids), BATCH_SIZE):
                batch = gclids[i:i + BATCH_SIZE]
                unique_gclids = list(set(filter(None, batch)))
                
                if not unique_gclids:
                    continue

                # Rate limiting
                if batches_processed > 0 and batches_processed % 50 == 0:
                    time.sleep(60)  # Pausa a cada 50 batches
                
                # Atualiza UI
                progress = (batches_processed * BATCH_SIZE) / total_gclids
                progress_bar.progress(min(progress, 1.0))
                status_text.text(f"Processando {batches_processed * BATCH_SIZE}/{total_gclids} GCLIDs...")
                
                query = f"""
                    SELECT 
                        campaign.name, 
                        click_view.gclid
                    FROM click_view
                    WHERE click_view.gclid IN ('{"','".join(unique_gclids)}')
                    AND segments.date = '{date_str}'
                    LIMIT {len(unique_gclids)}
                """

                try:
                    stream = ga_service.search_stream(
                        customer_id=customer_id, 
                        query=query
                    )

                    for response in stream:
                        for row in response.results:
                            gclid = row.click_view.gclid
                            campaign_name = row.campaign.name
                            if gclid and campaign_name:  # Validação adicional
                                gclid_campaign_map[gclid] = campaign_name
                                st.session_state.gclid_cache[gclid] = campaign_name  # Atualiza cache

                    batches_processed += 1
                    time.sleep(REQUEST_DELAY)  # Delay entre requests

                except GoogleAdsException as ex:
                    st.error(f"Erro no lote {batches_processed}:")
                    for error in ex.failure.errors:
                        st.error(f"{error.message}")
                    continue

        # Atualiza cache para GCLIDs não encontrados
        for gclid in gclids_to_query:
            if gclid not in gclid_campaign_map:
                cache[gclid] = 'Não encontrado'

        # Salva cache no banco de dados
        if gclid_campaign_map:
            save_gclid_cache_batch(gclid_campaign_map)
            
        not_found = {
            gclid: 'Não encontrado' 
            for gclid in gclids_to_query 
            if gclid not in gclid_campaign_map
        }
        if not_found:
            save_gclid_cache_batch(not_found)
            for gclid in not_found:
                st.session_state.gclid_cache[gclid] = 'Não encontrado'

        return gclid_campaign_map

    except Exception as e:
        logger.error(f"Erro na consulta: {str(e)}", exc_info=True)
        st.error(f"Erro na consulta: {str(e)}")
        return None
    finally:
        progress_bar.empty()
        status_text.empty()

def get_individual_conversion_report(client, property_id, start_date, end_date):
    """
    Busca uma lista de eventos individuais que possuem um ID de Transação,
    mostrando o ID da Transação e a campanha, origem e mídia associadas.
    """
    try:
        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=[
                Dimension(name="dateHourMinute"),
                Dimension(name="transactionId"),
                Dimension(name="campaignName"),
                Dimension(name="source"),
                Dimension(name="medium"),
            ],
            metrics=[Metric(name="eventCount")],
            date_ranges=[DateRange(start_date=start_date.strftime('%Y-%m-%d'), end_date=end_date.strftime('%Y-%m-%d'))],
            # Filtro para pegar apenas eventos que tenham um transaction_id
            dimension_filter=FilterExpression(
                filter=Filter(
                    field_name="transactionId",
                    string_filter=Filter.StringFilter(
                        value="",
                        match_type=Filter.StringFilter.MatchType.FULL_REGEXP,
                        case_sensitive=False
                    ),
                    not_expression=True # Pega onde transactionId NÃO é ""
                )
            ),
            limit=25000 # Um limite alto para capturar todos os eventos com ID de transação do período
        )
        response = client.run_report(request)
        
        if response and response.rows:
            rows = []
            for r in response.rows:
                datetime_str = r.dimension_values[0].value
                datetime_obj = datetime.strptime(datetime_str, '%Y%m%d%H%M')

                rows.append({
                    'Data (GA4)': datetime_obj,
                    'ID da Transação': r.dimension_values[1].value,
                    'Campanha (GA4)': r.dimension_values[2].value,
                    'Origem (GA4)': r.dimension_values[3].value,
                    'Mídia (GA4)': r.dimension_values[4].value,
                })
            # Remove duplicatas, mantendo a primeira ocorrência (a mais provável de ser a correta)
            df = pd.DataFrame(rows)
            return df.drop_duplicates(subset=['ID da Transação'], keep='first')

    except Exception as e:
        st.warning(f"Erro ao buscar o relatório de conversões individuais: {e}")
        
    return pd.DataFrame()
# Função para executar relatórios no GA4
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
        # Mostra detalhes da conta de serviço
        creds_info = getattr(client._credentials, "service_account_email", "Informação não disponível")
        st.warning(f"Conta de serviço utilizada: {creds_info}")
        return None

def formatar_reais(valor):
    """Formata um número para o padrão monetário brasileiro."""
    if pd.isna(valor) or valor == 0: return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# 2. FUNÇÃO PRINCIPAL DA PÁGINA (run_page)

def run_page():
    st.title("📊 Análise de Performance Digital (GA4) - Central")

    PROPERTY_ID = "327461202"  # Property ID da Central
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

        # Métrica de Custo Total ---
        custo_total_periodo = df_performance['Custo'].sum()
        st.metric("Custo Total no Período", formatar_reais(custo_total_periodo))


    st.header("📈 Performance de Campanhas por Curso Venda (Dados do GA4)")

    if not df_performance.empty:
        # --- 1. EXTRAÇÃO DO "CURSO VENDA" ---
        df_agrupado = df_performance.copy()
        
        # Usa regex para extrair o conteúdo dentro de {}
        df_agrupado['Curso Venda'] = df_agrupado['Campanha'].str.extract(r'\{(.*?)\}')
        
        # Se alguma campanha não tiver o padrão, preenche com um valor padrão
        df_agrupado['Curso Venda'] = df_agrupado['Curso Venda'].fillna('Não Especificado')

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
        
    # --- NOVA SEÇÃO: TABELA DO GOOGLE ADS ---
    st.header("📊 Performance de Campanhas por Curso Venda (Dados do Google Ads)")
    
    # Obtém cliente do Google Ads
    gads_client, customer_id = get_google_ads_client()
    
    if gads_client and customer_id:
        # Busca dados diretamente do Google Ads
        with st.spinner("Buscando dados de campanhas no Google Ads..."):
            df_gads = get_google_ads_campaign_performance(gads_client, customer_id, start_date, end_date)
            
        if not df_gads.empty:
            # Filtra apenas campanhas com valor investido (Custo > 0)
            df_gads = df_gads[df_gads['Custo'] > 0].copy()
            # Extrai o "Curso Venda" do nome da campanha (similar ao GA4)
            df_gads['Curso Venda'] = df_gads['Campanha'].str.extract(r'\{(.*?)\}')
            df_gads['Curso Venda'] = df_gads['Curso Venda'].fillna('Não Especificado')
            # Formata o custo para duas casas decimais com ponto
            df_gads['Custo'] = df_gads['Custo'].map(lambda x: float(f"{x:.2f}"))
            
            # Formatamos os dados agregados (somas por grupo) para garantir duas casas decimais
            df_gads_grouped = df_gads.groupby('Curso Venda')['Custo'].sum().reset_index()
            df_gads_grouped['Custo'] = df_gads_grouped['Custo'].map(lambda x: float(f"{x:.2f}"))
            
            # Configuração da tabela hierárquica AG-GRID
            gb_gads = GridOptionsBuilder.from_dataframe(df_gads)
            # Configura a coluna "Curso Venda" para ser o grupo
            gb_gads.configure_column("Curso Venda", rowGroup=True, hide=True)
            # Configura as outras colunas
            gb_gads.configure_column("Campanha", header_name="Nome da Campanha")
            gb_gads.configure_column("ID da Campanha", hide=True)
            gb_gads.configure_column(
                "Custo", header_name="Custo", type=["numericColumn", "numberColumnFilter", "customNumericFormat"],
                aggFunc='sum',
                valueFormatter="Number(data.Custo).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})"
            )
            gb_gads.configure_column(
                "Conversões", header_name="Conversões", type=["numericColumn", "numberColumnFilter", "customNumericFormat"],
                aggFunc='sum'
            )
            gb_gads.configure_column(
                "CPA (Custo por Conversão)", header_name="CPA", type=["numericColumn", "numberColumnFilter", "customNumericFormat"],
                # Calcula o CPA agregado para o grupo
                valueGetter='(params.node.aggData.Custo && params.node.aggData.Conversões && params.node.aggData.Conversões > 0) ? Math.round((params.node.aggData.Custo / params.node.aggData.Conversões) * 100) / 100 : null',
                valueFormatter="data['CPA (Custo por Conversão)'] ? Number(data['CPA (Custo por Conversão)']).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : ''"
            )
            grid_options_gads = gb_gads.build()
            # Define a aparência da coluna de grupo
            grid_options_gads["autoGroupColumnDef"] = {
                "headerName": "Curso Venda (Produto)",
                "minWidth": 250,
                "cellRendererParams": {"suppressCount": True}
            }
            # Exibição da tabela
            AgGrid(
                df_gads,
                gridOptions=grid_options_gads,
                width='100%',
                theme='streamlit',
                allow_unsafe_jscode=True,
                enable_enterprise_modules=True
            )
            # Adiciona uma exibição de dados brutos das campanhas
            st.header("📊 Performance de Campanhas (Dados Brutos do Google Ads)")
            
            # Formata as colunas de valor para garantir exatamente 2 casas decimais
            df_bruto = df_gads.copy()
            df_bruto['Custo'] = df_bruto['Custo'].apply(lambda x: round(x, 2))
            df_bruto['CPA (Custo por Conversão)'] = df_bruto['CPA (Custo por Conversão)'].apply(lambda x: round(x, 2) if x > 0 else 0)
            
            st.dataframe(
                df_bruto.sort_values("Custo", ascending=False),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Custo": st.column_config.NumberColumn(format="%.2f"),
                    "CPA (Custo por Conversão)": st.column_config.NumberColumn(format="%.2f")
                }
            )
        else:
            st.warning("Não foi possível obter dados de campanhas do Google Ads para o período selecionado.")
    else:
        st.error("Não foi possível conectar ao Google Ads. Verifique as credenciais.")

    st.divider()

    # SEÇÃO: KPIs GERAIS DE ENGAJAMENTO ---
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

    # SEÇÃO: TABELA DE AQUISIÇÃO DE TRÁFEGO ---
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

    st.divider()

    # ==============================================================================
    # NOVA ANÁLISE: AUDITORIA DE CAMPANHAS (CRM vs GA4)
    # ==============================================================================
    TIMEZONE = 'America/Sao_Paulo'
    st.header("🕵️ Auditoria de Conversões com GCLID (Fonte: CRM)")
    st.info("Esta tabela mostra as oportunidades do seu CRM que possuem um GCLID registrado.")

    # Inicializa cache
    if 'gclid_cache' not in st.session_state:
        try:
            st.session_state.gclid_cache = load_gclid_cache()
            
            # Informativo, mas não para a execução
            if not st.session_state.gclid_cache:
                pass  # Cache vazio, será preenchido conforme necessário
                
        except Exception as e:
            st.warning(f"❌ Aviso ao carregar cache: {str(e)}")
            # Inicializa como dicionário vazio em caso de erro
            st.session_state.gclid_cache = {}

    try:
        # 1. Carrega os dados do banco de dados
        df_conversoes_db = carregar_dados("consultas/oportunidades/oportunidades.sql")
        df_conversoes_db['criacao'] = pd.to_datetime(df_conversoes_db['criacao']).dt.tz_localize(TIMEZONE, ambiguous='infer')

        # 2. Aplica filtros
        start_date_aware = pd.Timestamp(start_date, tz=TIMEZONE)
        end_date_aware = pd.Timestamp(end_date, tz=TIMEZONE) + pd.Timedelta(days=1)

        df_conversoes_filtrado = df_conversoes_db[
            (df_conversoes_db['criacao'] >= start_date_aware) &
            (df_conversoes_db['criacao'] < end_date_aware) &
            (df_conversoes_db['empresa'] == "Central") &  # Filtra apenas para a Central
            (df_conversoes_db['gclid'].notnull()) & 
            (df_conversoes_db['gclid'] != '')
        ].copy()
        
        # Sempre exibir o botão de consulta, mesmo se não houver dados
        if df_conversoes_filtrado.empty:
            st.info("Não há conversões com GCLID para o período selecionado. Você pode tentar ampliar o período de datas ou usar o botão abaixo para consultar GCLIDs diretamente.")
            
            # Adiciona botão para consulta direta de GCLIDs
            with st.expander("Consulta direta de GCLIDs"):
                gclid_input = st.text_area(
                    "Digite os GCLIDs que deseja consultar (um por linha):",
                    height=150
                )
                
                if st.button("📡 Consultar GCLIDs Digitados", type="primary"):
                    if gclid_input.strip():
                        gclids = [g.strip() for g in gclid_input.split('\n') if g.strip()]
                        if gclids:
                            hoje = datetime.now().date()
                            gclid_date_dict = {gclid: hoje for gclid in gclids}
                            
                            gads_client, customer_id = get_google_ads_client()
                            if gads_client:
                                with st.spinner(f"Consultando {len(gclid_date_dict)} GCLIDs..."):
                                    result = get_campaigns_for_gclids_with_date(
                                        gads_client, customer_id, gclid_date_dict
                                    )
                                    
                                    if result is not None:
                                        st.success(f"Consulta concluída! {len(result)} GCLIDs encontrados.")
                                        
                                        # Exibe resultado direto
                                        if result:
                                            df_result = pd.DataFrame(
                                                [(gclid, campanha) for gclid, campanha in result.items()],
                                                columns=['GCLID', 'Campanha']
                                            )
                                            st.dataframe(df_result, use_container_width=True)
                                        else:
                                            st.warning("Nenhuma campanha encontrada para os GCLIDs consultados.")
                                        
                                        st.rerun()
                            else:
                                st.error("Falha na conexão com Google Ads")
                    else:
                        st.warning("Por favor, digite pelo menos um GCLID para consultar.")
            
        else:
            # Prepara DataFrame para exibição
            df_display = df_conversoes_filtrado[[
                'criacao', 'campanha', 'gclid', 'etapa', 
                'oportunidade', 'cliente_id', 'name',
                'telefone', 'email', 'origem',
                'modalidade', 'unidade'
            ]].rename(columns={
                'criacao': 'Data da Conversão',
                'campanha': 'Campanha (UTM)',
                'gclid': 'GCLID',
                'etapa': 'Etapa',
                'oportunidade': 'ID Oportunidade',
                'name': 'Nome Cliente',
                'unidade': 'Unidade'
            })
            
            # Adiciona coluna de campanha do Google Ads
            df_display['Campanha (Google Ads)'] = df_display['GCLID'].map(
                lambda x: get_campaign_for_gclid(x) or 'Não consultado'
            )
            
            # Exibe tabela
            st.dataframe(
                df_display.sort_values('Data da Conversão', ascending=False),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Data da Conversão": st.column_config.DatetimeColumn(
                        format="D/MM/YYYY HH:mm"
                    )
                }
            )
            
            # Botão de consulta
            if st.button("📡 Consultar Campanhas no Google Ads", type="primary"):
                gclid_date_dict = {
                    row['gclid']: row['criacao'].date()
                    for _, row in df_conversoes_filtrado.iterrows()
                    if pd.notna(row['gclid']) and row['gclid'] != ''
                }
                
                gads_client, customer_id = get_google_ads_client()
                if gads_client:
                    with st.spinner(f"Consultando {len(gclid_date_dict)} GCLIDs..."):
                        result = get_campaigns_for_gclids_with_date(
                            gads_client, customer_id, gclid_date_dict
                        )
                        
                        if result is not None:
                            st.success("Consulta concluída! Atualizando tabela...")
                            st.rerun()
                else:
                    st.error("Falha na conexão com Google Ads")

            st.divider()
            st.header("📊 Análise de Campanhas por Etapa do Funil")

            # Filtra para usar apenas campanhas que foram encontradas no Google Ads
            df_analise_etapas = df_display.copy()

            if not df_analise_etapas.empty:
                # Cria a tabela pivotada
                tabela_etapas = pd.pivot_table(
                    df_analise_etapas,
                    index='Campanha (Google Ads)',
                    columns='Etapa',
                    values='GCLID',
                    aggfunc='count',
                    fill_value=0
                )

                # Adiciona uma coluna de Total
                tabela_etapas['Total'] = tabela_etapas.sum(axis=1)

                # Ordena pela coluna Total, do maior para o menor
                tabela_etapas_ordenada = tabela_etapas.sort_values(by='Campanha (Google Ads)', ascending=False)

                # --- ADICIONA A LINHA DE TOTAL GERAL ---
                # Calcula a soma de cada coluna
                total_geral = tabela_etapas_ordenada.sum().to_frame().T
                # Define o nome do índice para a linha de total
                total_geral.index = ['TOTAL GERAL']

                # Concatena a linha de total ao DataFrame
                tabela_final_com_total = pd.concat([tabela_etapas_ordenada, total_geral])

                # Exibe a tabela com o total geral
                st.dataframe(tabela_final_com_total, use_container_width=True)

                # NOVA SEÇÃO: ANÁLISES DETALHADAS DE CAMPANHAS E ETAPAS
                # ===============================================================================
                st.divider()
                st.header("🔍 Análises Detalhadas de Campanhas e Etapas")
                
                # Filtra para usar apenas campanhas e etapas que existem no período selecionado
                df_periodo = df_display.copy()
                
                # Lista de campanhas disponíveis no período (excluindo o total geral)
                campanhas_disponiveis_periodo = list(tabela_etapas.index)
                campanhas_disponiveis_periodo = [c for c in campanhas_disponiveis_periodo if c != 'TOTAL GERAL']
                
                # Lista de etapas disponíveis no período (todas as colunas exceto 'Total')
                etapas_disponiveis_periodo = list(df_periodo['Etapa'].unique())
                
                # --- FILTROS EM EXPANDER ---
                with st.expander("📋 Filtros para Análise Detalhada", expanded=True):
                    col1, col2 = st.columns(2)
                    
                    # Filtro de Campanhas (multi-select)
                    with col1:
                        campanhas_selecionadas = st.multiselect(
                            "Selecione as Campanhas:",
                            options=campanhas_disponiveis_periodo,
                            default=campanhas_disponiveis_periodo[:20] if len(campanhas_disponiveis_periodo) > 20 else campanhas_disponiveis_periodo
                        )
                    
                    # Filtro de Etapas (multi-select)
                    with col2:
                        etapas_selecionadas = st.multiselect(
                            "Selecione as Etapas:",
                            options=etapas_disponiveis_periodo,
                            default=etapas_disponiveis_periodo
                        )
                
                # Aplicar filtros ao dataframe
                if campanhas_selecionadas and etapas_selecionadas:
                    # Filtra apenas as campanhas e etapas selecionadas
                    df_filtro_campanhas = df_periodo[
                        (df_periodo['Campanha (Google Ads)'].isin(campanhas_selecionadas)) &
                        (df_periodo['Etapa'].isin(etapas_selecionadas))
                    ]
                    
                    # --- GRÁFICOS ---
                    col1, col2 = st.columns(2)
                    
                    # 1. Gráfico de Barras para Campanhas (sem segmentação por etapa)
                    with col1:
                        # Conta oportunidades por campanha
                        contagem_campanhas = df_filtro_campanhas.groupby('Campanha (Google Ads)').size().reset_index(name='Contagem')
                        contagem_campanhas = contagem_campanhas.sort_values('Contagem', ascending=True)
                        
                        # Cria o gráfico de barras
                        fig_campanhas = px.bar(
                            contagem_campanhas,
                            x='Contagem',
                            y='Campanha (Google Ads)',
                            orientation='h',
                            title="Distribuição de Campanhas",
                            labels={'Contagem': 'Número de Oportunidades', 'Campanha (Google Ads)': 'Campanha'},
                            color_discrete_sequence=['#2E86C1']  # Cor azul para todas as barras
                        )
                        
                        # Ajusta o layout
                        fig_campanhas.update_layout(
                            showlegend=False,
                            height=400 + (len(campanhas_selecionadas) * 30)  # Ajusta altura baseado no número de campanhas
                        )
                        
                        st.plotly_chart(fig_campanhas, use_container_width=True)
                    
                    # 2. Gráfico de Pizza para Etapas
                    with col2:
                        # Filtra os dados
                        df_filtro_etapas = df_periodo[
                            (df_periodo['Campanha (Google Ads)'].isin(campanhas_selecionadas)) &
                            (df_periodo['Etapa'].isin(etapas_selecionadas))
                        ]
                        
                        # Conta oportunidades por etapa
                        contagem_etapas = df_filtro_etapas.groupby('Etapa').size().reset_index(name='Contagem')
                        
                        # Cria o gráfico de pizza
                        fig_etapas = px.pie(
                            contagem_etapas,
                            names='Etapa',
                            values='Contagem',
                            title="Distribuição de Oportunidades por Etapa",
                            hole=0.4  # Cria um gráfico de rosca
                        )
                        
                        # Ajusta o layout
                        fig_etapas.update_layout(
                            legend_title_text='Etapa',
                            height=500
                        )
                        
                        st.plotly_chart(fig_etapas, use_container_width=True)
                else:
                    st.warning("Selecione pelo menos uma campanha e uma etapa para visualizar os gráficos.")
            else:
                st.warning("Não há dados de campanhas consultadas no Google Ads para gerar a análise por etapa. Clique no botão 'Consultar Campanhas no Google Ads' acima.")

    except Exception as e:
        st.error(f"Erro ao carregar dados: {str(e)}")