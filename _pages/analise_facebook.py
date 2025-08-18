import streamlit as st
import pandas as pd
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adsinsights import AdsInsights
from dotenv import load_dotenv
import os
import io
from datetime import datetime
import plotly.express as px
from utils.sql_loader import carregar_dados
from fbclid_db import (
    load_fbclid_cache,
    save_fbclid_cache_batch,
    get_campaign_for_fbclid,
)
from facebook_api_utils import (
    init_facebook_api,
    get_campaigns_for_fbclids,
)

# Carrega as variáveis do .env (só terá efeito no ambiente local)
load_dotenv()

def get_facebook_api_account():
    """
    Wrapper para a função init_facebook_api do módulo facebook_api_utils
    que retorna apenas a conta para manter compatibilidade com o código existente.
    """
    _, _, _, _, account = init_facebook_api()
    return account


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
            
        df = pd.DataFrame(rows)
        
        if not df.empty:
            # 1. Usa regex para extrair o conteúdo dentro de {}
            df['Curso Venda'] = df['Campanha'].str.extract(r'\{(.*?)\}')
            # 2. Limpa o nome do Curso Venda e preenche vazios
            df['Curso Venda'] = df['Curso Venda'].str.strip()
            # Corrigido para evitar FutureWarning - usando atribuição direta em vez de inplace=True
            df['Curso Venda'] = df['Curso Venda'].fillna('Não Especificado')

        return df

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
    
    account = get_facebook_api_account()

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

            ordem_das_colunas = [
                'Curso Venda',
                'Campanha',
                'Custo',
                'Impressões',
                'Cliques',
                'CPC',
                'CTR (%)'
            ]

            df_para_exibir = df_insights[ordem_das_colunas]

            # Exibe a tabela detalhada
            st.dataframe(
                df_para_exibir.sort_values("Custo", ascending=False),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "curso_venda": st.column_config.TextColumn("Curso Venda"),
                    "Campanha": st.column_config.TextColumn("Campanha"),
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

    # SEÇÃO: PERFIL DE PÚBLICO E PLATAFORMA

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

    # ==============================================================================
    # ANÁLISE DE CONVERSÕES COM FBCLID (Fonte: CRM)
    # ==============================================================================
    st.divider()
    TIMEZONE = 'America/Sao_Paulo'
    st.header("🕵️ Auditoria de Conversões com FBCLID (Fonte: CRM)")
    st.info("Esta tabela mostra as oportunidades do seu CRM que possuem um FBCLID registrado.")

    # Inicializa cache
    if 'fbclid_cache' not in st.session_state:
        try:
            st.session_state.fbclid_cache = load_fbclid_cache(empresa="degrau")
            
            # Adicione esta verificação
            if st.session_state.fbclid_cache is None:
                st.warning("⚠️ Cache de FBclids vazio - Execute o script check_fbclid_migration.py para inicializar o banco de dados")
                
        except Exception as e:
            st.error(f"❌ Falha ao carregar cache de FBclids: {str(e)}")
            st.stop()

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
            (df_conversoes_db['empresa'] == "Degrau") &
            (df_conversoes_db['fbclid'].notnull()) & 
            (df_conversoes_db['fbclid'] != '')
        ].copy()
        
        if not df_conversoes_filtrado.empty:
            # Preparando dados para exibição
            df_conversoes_filtrado['Curso Venda'] = df_conversoes_filtrado['concurso']
            # Evitando warning: usando atribuição direta em vez de inplace=True
            df_conversoes_filtrado['Curso Venda'] = df_conversoes_filtrado['Curso Venda'].fillna('Não Especificado')
            
            # Seleciona colunas relevantes
            colunas_display = [
                'oportunidade', 'criacao', 'name', 'telefone', 'email',
                'etapa', 'origem', 'campanha', 'Curso Venda', 'fbclid'
            ]
            
            df_display = df_conversoes_filtrado[colunas_display].copy()
            
            # Renomeia colunas para melhor visualização
            df_display.columns = [
                'ID', 'Data Criação', 'Nome', 'Telefone', 'Email',
                'Etapa', 'Origem', 'Campanha (UTM)', 'Curso Venda', 'FBCLID'
            ]
            
            # Adiciona coluna de campanha do Facebook
            df_display['Campanha (Facebook)'] = df_display['FBCLID'].apply(
                lambda x: get_campaign_for_fbclid(x, empresa="degrau")['campaign_name'] 
                if get_campaign_for_fbclid(x, empresa="degrau") is not None 
                else 'Não consultado'
            )
            
            # Exibe a tabela de conversões
            st.dataframe(
                df_display,
                hide_index=True,
                column_config={
                    "Data Criação": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
                    "FBCLID": st.column_config.TextColumn(width="large")
                },
                use_container_width=True
            )
            
            # Botão de consulta
            if st.button("📡 Consultar Campanhas no Facebook", type="primary"):
                _, _, _, _, account = init_facebook_api()
                if account:
                    fbclid_list = [
                        row['fbclid']
                        for _, row in df_conversoes_filtrado.iterrows()
                        if pd.notna(row['fbclid']) and row['fbclid'] != ''
                    ]
                    
                    with st.spinner(f"Consultando {len(fbclid_list)} FBclids..."):
                        result = get_campaigns_for_fbclids(
                            account, fbclid_list, empresa="degrau"
                        )
                        
                        if result is not None:
                            st.success("Consulta concluída! Atualizando tabela...")
                            st.rerun()
                else:
                    st.error("Falha na conexão com a API do Facebook")
            
            # Resumo das conversões
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total de Conversões com FBCLID", df_display.shape[0])
            
            with col2:
                origens_count = df_conversoes_filtrado['origem'].value_counts()
                if not origens_count.empty:
                    fig_origem = px.pie(
                        values=origens_count.values,
                        names=origens_count.index,
                        title="Conversões por Origem"
                    )
                    st.plotly_chart(fig_origem, use_container_width=True)
            
            st.divider()
            st.header("📊 Análise de Campanhas por Etapa do Funil")
            st.info("Esta análise utiliza os dados do CRM com FBCLID para mostrar a distribuição de oportunidades por etapa para cada campanha do Facebook. Campanhas com FBCLID não consultado ou não encontrado são omitidas.")

            # Filtra para usar apenas campanhas que foram encontradas no Facebook
            df_analise_etapas = df_display[df_display['Campanha (Facebook)'] != 'Não consultado'].copy()

            if not df_analise_etapas.empty:
                # Cria a tabela pivotada
                tabela_etapas = pd.pivot_table(
                    df_analise_etapas,
                    index='Campanha (Facebook)',
                    columns='Etapa',
                    values='FBCLID',
                    aggfunc='count',
                    fill_value=0
                )

                # Adiciona uma coluna de Total
                tabela_etapas['Total'] = tabela_etapas.sum(axis=1)

                # Ordena pela coluna Total, do maior para o menor
                tabela_etapas_ordenada = tabela_etapas.sort_values(by='Total', ascending=False)

                # --- ADICIONA A LINHA DE TOTAL GERAL ---
                # Calcula a soma de cada coluna
                total_geral = tabela_etapas_ordenada.sum().to_frame().T
                # Define o nome do índice para a linha de total
                total_geral.index = ['TOTAL GERAL']

                # Concatena a linha de total ao DataFrame
                tabela_final_com_total = pd.concat([tabela_etapas_ordenada, total_geral])

                # Exibe a tabela com o total geral
                st.dataframe(tabela_final_com_total, use_container_width=True)
            else:
                st.warning("Não há dados de campanhas consultadas no Facebook para gerar a análise por etapa. Clique no botão 'Consultar Campanhas no Facebook' acima.")
            
            # Exportação para Excel
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                # Cria uma cópia para exportação e remove o timezone
                df_export = df_display.copy()
                # Converte a coluna de data para timezone naive (remove o fuso horário)
                if 'Data Criação' in df_export.columns:
                    df_export['Data Criação'] = df_export['Data Criação'].dt.tz_localize(None)
                
                df_export.to_excel(writer, sheet_name='Conversões FBCLID', index=False)
            buffer.seek(0)
            
            st.download_button(
                label="📥 Baixar Dados em Excel",
                data=buffer,
                file_name=f"conversoes_fbclid_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("Não foram encontradas conversões com FBCLID no período selecionado.")
    
    except Exception as e:
        st.error(f"Erro ao carregar dados: {str(e)}")
