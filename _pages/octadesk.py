# _pages/octadesk.py - Versão Estável (sem filtro de data na API)

import streamlit as st
import pandas as pd
import requests
from dotenv import load_dotenv
import os
from datetime import datetime
import plotly.express as px

load_dotenv()
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
        st.error("Token da API do Octadesk não encontrado.")
    return token

@st.cache_data(ttl=1800)
def get_recent_octadesk_chats(api_token):
    """
    Busca os 100 chats mais recentes, ignorando o filtro de data para garantir o funcionamento.
    """
    base_url = "https://o198470-a5c.api001.octadesk.services"
    url = f"{base_url}/chat"
    headers = {"accept": "application/json", "X-API-KEY": api_token}
    
    # Parâmetros simplificados, sem filtro de data, que sabemos que funciona.
    params = {
        "limit": 100,
        "sort[direction]": "desc"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if data:
            return pd.json_normalize(data)
        return pd.DataFrame()

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
        st.stop()

    # --- FILTRO DE DATA (VISUAL) ---
    st.sidebar.header("Filtro de Período (Octadesk)")
    hoje = datetime.now().date()
    data_inicio_padrao = hoje - pd.Timedelta(days=6)
    
    st.sidebar.date_input(
        "Selecione o Período de Análise:",
        [data_inicio_padrao, hoje],
        key="octadesk_date_range",
        # Desabilitamos o filtro por enquanto
        disabled=True
    )
    
    st.warning("Atenção: O filtro por período de datas para o Octadesk está temporariamente desativado. A análise abaixo sempre mostrará os dados mais recentes.", icon="⚠️")
    st.divider()

    # --- Tabela de Validação ---
    df_chats = get_recent_octadesk_chats(api_token)

    if df_chats is not None and not df_chats.empty:
        st.success(f"Sucesso! {len(df_chats)} chats recentes encontrados e analisados.")
        
        # --- Seção de KPIs de Status ---
        st.header("Status dos Atendimentos Recentes")
        status_counts = df_chats['status'].value_counts()
        
        # Garante que as chaves existem antes de acessá-las
        chats_abertos = status_counts.get('open', 0)
        chats_pendentes = status_counts.get('pending', 0)
        chats_resolvidos = status_counts.get('closed', 0)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Chats Abertos", f"{chats_abertos}")
        col2.metric("Chats Pendentes", f"{chats_pendentes}")
        col3.metric("Chats Resolvidos", f"{chats_resolvidos}")
        st.divider()

        # --- Seção de Gráficos de Distribuição ---
        st.header("Distribuição dos Atendimentos")
        col_graf1, col_graf2 = st.columns(2)

        with col_graf1:
            st.subheader("Volume por Grupo de Atendimento")
            # Verifica se a coluna existe antes de usar
            if 'group.name' in df_chats.columns:
                df_grupo = df_chats['group.name'].dropna().value_counts().reset_index()
                df_grupo.columns = ['Grupo', 'Quantidade']
                fig_grupo = px.bar(
                    df_grupo.sort_values('Quantidade'),
                    y='Grupo', x='Quantidade', orientation='h', text_auto=True
                )
                fig_grupo.update_layout(yaxis_title=None, xaxis_title="Nº de Chats", height=400)
                st.plotly_chart(fig_grupo, use_container_width=True)

        with col_graf2:
            st.subheader("Volume por Canal")
            if 'channel' in df_chats.columns:
                df_canal = df_chats['channel'].value_counts().reset_index()
                df_canal.columns = ['Canal', 'Quantidade']
                fig_canal = px.pie(df_canal, names='Canal', values='Quantidade', hole=0.4, title="Proporção de Canais")
                st.plotly_chart(fig_canal, use_container_width=True)

        st.divider()

        # --- Tabela de Detalhes no Final ---
        st.header("Detalhamento dos Últimos Chats")
        # ... (seu código para a tabela detalhada st.dataframe pode continuar aqui) ...
        
    else:
        st.info("Nenhum chat encontrado ou ocorreu um erro na busca.")