# _pages/octadesk.py - Versão Final, Completa e Corrigida

import streamlit as st
import pandas as pd
import requests
from dotenv import load_dotenv
import os
from datetime import datetime

# Carrega as variáveis do .env (só terá efeito no ambiente local)
load_dotenv()

# Define o fuso horário padrão para a página
TIMEZONE = 'America/Sao_Paulo'

# ==============================================================================
# 1. FUNÇÕES AUXILIARES
# ==============================================================================

def get_octadesk_token():
    """Carrega o token da API do Octadesk de forma híbrida e segura."""
    try:
        token = st.secrets["octadesk_api"]["token"]
    except (st.errors.StreamlitAPIException, KeyError):
        token = os.getenv("OCTADESK_API_TOKEN")
    
    if not token:
        st.error("Token da API do Octadesk não encontrado. Verifique seus Secrets ou o arquivo .env.")
    return token

@st.cache_data(ttl=1800) # Adiciona cache de 30 minutos para performance
def get_octadesk_chats(api_token, start_date, end_date):
    """
    Busca os chats do Octadesk para um período, usando o método GET correto
    e tratando o fuso horário.
    """
    # Converte as datas locais para Timestamps conscientes do fuso horário
    start_ts = pd.Timestamp(start_date, tz=TIMEZONE)
    end_ts = pd.Timestamp(end_date, tz=TIMEZONE)

    url = "https://api.octadesk.com/chats/filter"
    headers = {"X-Api-Token": api_token}
    
    # Formata as datas para o padrão UTC (com 'Z') esperado pela API
    params = {
        "page": 1,
        "limit": 500, # Um limite razoável para a quantidade de chats
        "date[start]": start_ts.strftime('%Y-%m-%dT00:00:00.000Z'),
        "date[end]": end_ts.strftime('%Y-%m-%dT23:59:59.999Z')
    }
    
    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status() # Gera um erro para respostas 4xx ou 5xx
        data = response.json()
        
        if data and data.get('results'):
            # Usa json_normalize para achatar o JSON e criar colunas como 'requester.name'
            return pd.json_normalize(data['results'])
        else:
            return pd.DataFrame()

    except requests.exceptions.HTTPError as http_err:
        st.error(f"Erro na API do Octadesk: {http_err.response.status_code} - {http_err.response.text}")
    except Exception as e:
        st.error(f"Ocorreu um erro ao buscar dados do Octadesk: {e}")
        
    return pd.DataFrame()

# ==============================================================================
# 2. FUNÇÃO PRINCIPAL DA PÁGINA (run_page)
# ==============================================================================

def run_page():
    st.title("💬 Análise de Atendimento (Octadesk)")

    api_token = get_octadesk_token()

    if not api_token:
        st.stop() # Interrompe a execução se não houver token

    # --- FILTRO DE DATA NA BARRA LATERAL ---
    st.sidebar.header("Filtro de Período (Octadesk)")
    hoje = datetime.now(tz=pd.Timestamp(0, tz=TIMEZONE).tz).date() # Pega o "hoje" consciente do fuso horário
    data_inicio_padrao = hoje - pd.Timedelta(days=6)
    
    periodo_selecionado = st.sidebar.date_input(
        "Selecione o Período de Análise:",
        [data_inicio_padrao, hoje],
        key="octadesk_date_range"
    )

    if len(periodo_selecionado) != 2:
        st.warning("Por favor, selecione um período de datas válido.")
        st.stop()

    start_date, end_date = periodo_selecionado
    st.info(f"Exibindo dados de **{start_date.strftime('%d/%m/%Y')}** a **{end_date.strftime('%d/%m/%Y')}**")
    st.divider()

    # --- Tabela de Validação ---
    st.header("Chats Recebidos no Período")
    
    df_chats = get_octadesk_chats(api_token, start_date, end_date)

    if df_chats is not None and not df_chats.empty:
        st.success(f"Sucesso! {len(df_chats)} chats encontrados.")
        
        # Seleciona e renomeia colunas para uma exibição inicial mais limpa
        colunas_para_exibir = {
            'number': 'Número',
            'status': 'Status',
            'createdAt': 'Data de Criação',
            'requester.name': 'Cliente',
            'assignee.name': 'Agente Responsável',
            'group.name': 'Grupo de Atendimento'
        }
        
        colunas_existentes = [col for col in colunas_para_exibir.keys() if col in df_chats.columns]
        df_display = df_chats[colunas_existentes].rename(columns=colunas_para_exibir)

        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Data de Criação": st.column_config.DatetimeColumn(format="D/MM/YYYY HH:mm")
            }
        )
    else:
        st.info("Nenhum chat encontrado para o período selecionado ou ocorreu um erro na busca.")