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
# Carrega credenciais específicas do Facebook, se existirem
load_dotenv('.facebook_credentials.env', override=True)

# action_types que contam como conversão
CONVERSION_ACTIONS = {
    'purchase', 'lead', 'omni_purchase',
    'offsite_conversion.fb_pixel_purchase',
    'offsite_conversion.fb_pixel_lead',
    'submit_application_total',
    'onsite_conversion.lead_grouped',
}

def get_facebook_api_account(empresa="Degrau"):
    """
    Inicializa a API do Facebook para a empresa selecionada.
    Retorna o objeto AdAccount ou None.
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


def get_facebook_campaign_insights(account, start_date, end_date):
    """
    Busca insights de performance para todas as campanhas em um período,
    incluindo conversões, CPA, alcance e frequência.
    """
    try:
        fields = [
            AdsInsights.Field.campaign_name,
            AdsInsights.Field.objective,
            AdsInsights.Field.spend,
            AdsInsights.Field.impressions,
            AdsInsights.Field.clicks,
            AdsInsights.Field.ctr,
            AdsInsights.Field.cpc,
            AdsInsights.Field.cpm,
            AdsInsights.Field.reach,
            AdsInsights.Field.frequency,
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

            rows.append({
                'Campanha': insight[AdsInsights.Field.campaign_name],
                'Objetivo': insight.get(AdsInsights.Field.objective, 'N/A'),
                'Custo': custo,
                'Impressões': int(insight.get(AdsInsights.Field.impressions, 0)),
                'Cliques': int(insight.get(AdsInsights.Field.clicks, 0)),
                'CTR (%)': float(insight.get(AdsInsights.Field.ctr, 0)),
                'CPC': float(insight.get(AdsInsights.Field.cpc, 0)),
                'CPM': float(insight.get(AdsInsights.Field.cpm, 0)),
                'Alcance': int(insight.get(AdsInsights.Field.reach, 0)),
                'Frequência': float(insight.get(AdsInsights.Field.frequency, 0)),
                'Conversões': conversoes,
                'CPA': cpa,
            })

        df = pd.DataFrame(rows)
        if not df.empty:
            df['Curso Venda'] = df['Campanha'].str.extract(r'\{(.*?)\}')
            df['Curso Venda'] = df['Curso Venda'].str.strip()
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

    # --- FILTROS NA BARRA LATERAL ---
    st.sidebar.header("Filtros (Facebook)")

    empresa = st.sidebar.selectbox(
        "Empresa:",
        ["Degrau", "Central de Concursos"],
        key="fb_empresa"
    )
    empresa_key = "Degrau" if empresa == "Degrau" else "Central"

    hoje = datetime.now().date()
    data_inicio_padrao = hoje - pd.Timedelta(days=27)

    periodo_selecionado = st.sidebar.date_input(
        "Período de Análise:",
        [data_inicio_padrao, hoje],
        key="fb_date_range"
    )

    if len(periodo_selecionado) != 2:
        st.warning("Por favor, selecione um período de datas válido.")
        st.stop()

    start_date, end_date = periodo_selecionado

    account = get_facebook_api_account(empresa_key)

    if not account:
        st.warning(f"A conexão com a API do Facebook ({empresa}) não pôde ser estabelecida.")
        st.stop()

    st.info(f"📅 **{empresa}** — {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}")
    st.divider()

    # --- ANÁLISE DE PERFORMANCE DE CAMPANHAS ---
    st.header("Desempenho Geral das Campanhas")
    df_insights = get_facebook_campaign_insights(account, start_date, end_date)

    if not df_insights.empty:
        total_custo = df_insights['Custo'].sum()
        total_cliques = df_insights['Cliques'].sum()
        total_conv = int(df_insights['Conversões'].sum())
        total_alcance = int(df_insights['Alcance'].sum())

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Custo Total", formatar_reais(total_custo))
        col2.metric("Cliques", f"{total_cliques:,}".replace(",", "."))
        col3.metric("Conversões", f"{total_conv:,}".replace(",", "."))
        col4.metric("Alcance", f"{total_alcance:,}".replace(",", "."))

        if total_conv > 0:
            st.metric("CPA Médio", formatar_reais(total_custo / total_conv))

        ordem_das_colunas = [
            'Curso Venda', 'Campanha', 'Objetivo',
            'Custo', 'Impressões', 'Cliques', 'CTR (%)',
            'CPC', 'CPM', 'Alcance', 'Frequência',
            'Conversões', 'CPA',
        ]

        st.dataframe(
            df_insights[ordem_das_colunas].sort_values("Custo", ascending=False),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Custo": st.column_config.NumberColumn("Custo (R$)", format="R$ %.2f"),
                "CPC": st.column_config.NumberColumn("CPC (R$)", format="R$ %.2f"),
                "CPM": st.column_config.NumberColumn("CPM (R$)", format="R$ %.2f"),
                "CPA": st.column_config.NumberColumn("CPA (R$)", format="R$ %.2f"),
                "CTR (%)": st.column_config.NumberColumn("CTR", format="%.2f%%"),
                "Frequência": st.column_config.NumberColumn("Freq.", format="%.1f"),
            }
        )
    else:
        st.info("Não foram encontrados dados de campanhas para o período selecionado.")

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

    fbclid_empresa = empresa_key.lower()

    # Inicializa cache
    if 'fbclid_cache' not in st.session_state:
        try:
            st.session_state.fbclid_cache = load_fbclid_cache(empresa=fbclid_empresa)
            
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
            (df_conversoes_db['empresa'] == empresa_key) &
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
                lambda x: get_campaign_for_fbclid(x, empresa=fbclid_empresa)['campaign_name'] 
                if get_campaign_for_fbclid(x, empresa=fbclid_empresa) is not None 
                else 'Não consultado'
            )
            
            # Adiciona coluna de FBclid formatado conforme especificação da Meta
            from fbclid_db import format_fbclid
            df_display['FBCLID Formatado'] = df_display['FBCLID'].apply(
                lambda x: format_fbclid(x) if x else ''
            )
            
            # Exibe a tabela de conversões
            st.dataframe(
                df_display,
                hide_index=True,
                column_config={
                    "Data Criação": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
                    "FBCLID": st.column_config.TextColumn(width="large"),
                    "FBCLID Formatado": st.column_config.TextColumn(width="large")
                },
                use_container_width=True
            )
            
            # Botão de consulta
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("📡 Consultar Campanhas no Facebook", type="primary"):
                    account_fbclid = get_facebook_api_account(empresa_key)
                    if account_fbclid:
                        fbclid_list = [
                            row['fbclid']
                            for _, row in df_conversoes_filtrado.iterrows()
                            if pd.notna(row['fbclid']) and row['fbclid'] != ''
                        ]
                        
                        with st.spinner(f"Consultando {len(fbclid_list)} FBclids..."):
                            result = get_campaigns_for_fbclids(
                                account_fbclid, fbclid_list, empresa=fbclid_empresa
                            )
                            
                            if result is not None:
                                st.success("Consulta concluída! Atualizando tabela...")
                                st.rerun()
                    else:
                        st.error("Falha na conexão com a API do Facebook")
            
            with col2:
                # Botão para migrar os FBclids para o formato da Meta
                if st.button("🔄 Converter FBclids para Formato Meta", help="Converte os FBclids para o formato recomendado pela Meta"):
                    from fbclid_db import format_fbclid
                    
                    with st.spinner("Convertendo FBclids para o formato da Meta..."):
                        # Executa a migração diretamente aqui
                        fbclid_list = [
                            row['fbclid']
                            for _, row in df_conversoes_filtrado.iterrows()
                            if pd.notna(row['fbclid']) and row['fbclid'] != ''
                        ]
                        
                        # Para cada FBclid, formata e atualiza no banco
                        updated_count = 0
                        for fbclid in fbclid_list:
                            try:
                                formatted_fbclid = format_fbclid(fbclid)
                                
                                # Conecta ao banco para atualizar
                                import sqlite3
                                conn = sqlite3.connect("fbclid_cache.db")
                                cursor = conn.cursor()
                                
                                cursor.execute("""
                                UPDATE fbclid_cache SET formatted_fbclid = ? WHERE fbclid = ?
                                """, (formatted_fbclid, fbclid))
                                
                                # Se não existir, insere
                                if cursor.rowcount == 0:
                                    cursor.execute("""
                                    INSERT OR IGNORE INTO fbclid_cache (fbclid, formatted_fbclid, empresa)
                                    VALUES (?, ?, ?)
                                    """, (fbclid, formatted_fbclid, fbclid_empresa))
                                
                                conn.commit()
                                conn.close()
                                
                                updated_count += 1
                            except Exception as e:
                                st.error(f"Erro ao processar FBclid {fbclid}: {e}")
                        
                        st.success(f"Conversão concluída! {updated_count} FBclids foram convertidos.")
                        st.rerun()
            
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
