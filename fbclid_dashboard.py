#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Dashboard para visualização e envio de FBclids para a API de Conversões da Meta.

Este dashboard permite:
1. Visualizar FBclids armazenados no banco de dados
2. Enviar FBclids para a API de Conversões da Meta
3. Analisar resultados e estatísticas do envio
"""

import os
import time
import json
import sqlite3
import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime, timedelta
from dotenv import load_dotenv
import requests

# Carregar variáveis de ambiente do arquivo principal e depois do arquivo específico do Facebook
load_dotenv()
load_dotenv('.facebook_credentials.env')  # Carrega as credenciais específicas do Facebook

# Configurações da API do Facebook
FB_ACCESS_TOKEN = os.getenv('FB_ACCESS_TOKEN')
PIXEL_ID = os.getenv('FB_PIXEL_ID')

# Funções para manipulação de FBclids
def format_fbclid(fbclid):
    """
    Garante que o FBclid esteja no formato correto (fb.1.timestamp.fbclid)
    """
    if fbclid is None or fbclid == "":
        return None

    # Verifica se já está no formato correto (fb.número.timestamp.valor)
    if fbclid.startswith('fb.') and len(fbclid.split('.')) >= 4:
        return fbclid
    
    # Se não tiver o formato correto, assume que é apenas o valor do fbclid
    # e formata como fb.1.timestamp_atual.fbclid
    timestamp = int(time.time())
    return f"fb.1.{timestamp}.{fbclid}"

def get_fbclids_from_db(db_path='gclid_cache.db', days_ago=30, limit=1000):
    """
    Extrai FBclids do banco de dados SQLite
    
    Args:
        db_path: Caminho para o banco de dados SQLite
        days_ago: Número de dias para trás a considerar
        limit: Limite de registros a retornar
        
    Returns:
        DataFrame com FBclids e dados relacionados
    """
    try:
        conn = sqlite3.connect(db_path)
        
        # Verifica se a coluna fbclid existe na tabela
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(ad_clicks)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'fbclid' not in columns:
            st.error(f"Coluna 'fbclid' não encontrada no banco de dados {db_path}")
            return pd.DataFrame()
        
        # Calcula a data de corte
        cutoff_date = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m-%d')
        
        # Consulta os FBclids mais recentes
        query = """
        SELECT fbclid, created_at, client_id, url
        FROM ad_clicks
        WHERE fbclid IS NOT NULL AND fbclid != ''
        AND created_at >= ?
        ORDER BY created_at DESC
        LIMIT ?
        """
        
        df = pd.read_sql_query(query, conn, params=(cutoff_date, limit))
        conn.close()
        
        # Adiciona a coluna de FBclid formatado
        df['formatted_fbclid'] = df['fbclid'].apply(format_fbclid)
        
        return df
    
    except Exception as e:
        st.error(f"Erro ao extrair FBclids do banco de dados: {str(e)}")
        return pd.DataFrame()

# Funções para interação com a API do Facebook
def send_conversion_event(fbclid, event_name="PageView", event_time=None):
    """
    Envia um evento para a API de Conversões do Facebook
    
    Args:
        fbclid: FBclid formatado para envio
        event_name: Nome do evento (default: PageView)
        event_time: Timestamp do evento (default: agora)
        
    Returns:
        Resposta da API de Conversões
    """
    if not fbclid:
        return {"error": "FBclid não fornecido"}
    
    if not event_time:
        event_time = int(time.time())
    
    formatted_fbclid = format_fbclid(fbclid)
    
    # Prepara o payload do evento
    event_data = {
        "data": [
            {
                "event_name": event_name,
                "event_time": event_time,
                "action_source": "website",
                "event_source_url": "https://degrauculturalidiomas.com.br/",
                "user_data": {
                    "fbc": formatted_fbclid
                }
            }
        ]
    }
    
    # URL da API de Conversões
    url = f"https://graph.facebook.com/v17.0/{PIXEL_ID}/events"
    
    # Parâmetros da requisição
    params = {
        "access_token": FB_ACCESS_TOKEN
    }
    
    try:
        # Envia o evento para a API
        response = requests.post(url, params=params, json=event_data)
        return response.json()
    
    except Exception as e:
        return {"error": str(e)}

def send_selected_fbclids(df_selected, progress_bar=None):
    """
    Envia FBclids selecionados para a API de Conversões
    
    Args:
        df_selected: DataFrame com FBclids selecionados
        progress_bar: Barra de progresso Streamlit (opcional)
        
    Returns:
        Resultados do envio
    """
    results = {
        'total': len(df_selected),
        'success': 0,
        'failed': 0,
        'responses': []
    }
    
    for idx, row in df_selected.iterrows():
        # Atualiza a barra de progresso
        if progress_bar:
            progress_bar.progress((idx + 1) / len(df_selected))
        
        fbclid = row.get('formatted_fbclid') or row.get('fbclid')
        
        # Tenta extrair a data de criação para o event_time
        event_time = None
        try:
            if 'created_at' in row and row['created_at']:
                created_date = pd.to_datetime(row['created_at'])
                event_time = int(created_date.timestamp())
        except:
            # Se falhar, usa o tempo atual
            pass
        
        # Envia o evento
        response = send_conversion_event(fbclid, event_time=event_time)
        
        # Registra o resultado
        results['responses'].append({
            'fbclid': fbclid,
            'response': response
        })
        
        if response.get('events_received', 0) > 0:
            results['success'] += 1
        else:
            results['failed'] += 1
        
        # Pequena pausa para não sobrecarregar a API
        time.sleep(0.5)
    
    return results

# Interface Streamlit
def main():
    st.set_page_config(
        page_title="Dashboard de FBclids - Degrau Cultural",
        page_icon="📊",
        layout="wide"
    )
    
    st.title("📊 Dashboard de FBclids - Degrau Cultural")
    
    # Verifica se as credenciais estão configuradas
    if not FB_ACCESS_TOKEN or not PIXEL_ID:
        st.error("""
        ⚠️ Credenciais não encontradas! 
        
        Configure as variáveis FB_ACCESS_TOKEN e PIXEL_ID no arquivo .env ou nas configurações do Streamlit.
        """)
        
        with st.expander("Como configurar as credenciais"):
            st.markdown("""
            ### Configurando as credenciais
            
            1. Crie um arquivo `.env` na raiz do projeto com o seguinte conteúdo:
            ```
            FB_ACCESS_TOKEN=seu_token_aqui
            PIXEL_ID=seu_pixel_id_aqui
            ```
            
            2. Ou configure nas secrets do Streamlit:
            ```toml
            [facebook]
            access_token = "seu_token_aqui"
            pixel_id = "seu_pixel_id_aqui"
            ```
            """)
        
        return
    
    # Sidebar com configurações
    st.sidebar.header("Configurações")
    
    db_path = st.sidebar.text_input("Caminho do banco de dados", value="gclid_cache.db")
    days_ago = st.sidebar.slider("Dias para trás", min_value=1, max_value=180, value=30)
    limit = st.sidebar.slider("Limite de registros", min_value=10, max_value=5000, value=500)
    
    # Botão para carregar os dados
    if st.sidebar.button("Carregar FBclids"):
        with st.spinner("Carregando FBclids do banco de dados..."):
            df = get_fbclids_from_db(db_path=db_path, days_ago=days_ago, limit=limit)
            
            if df.empty:
                st.warning("Nenhum FBclid encontrado no banco de dados.")
            else:
                st.session_state['fbclids_df'] = df
                st.success(f"Carregados {len(df)} FBclids do banco de dados.")
    
    # Exibe os FBclids carregados
    if 'fbclids_df' in st.session_state:
        df = st.session_state['fbclids_df']
        
        # Exibe estatísticas
        st.header("Estatísticas de FBclids")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total de FBclids", len(df))
        
        with col2:
            # Calcula registros por dia
            df['day'] = pd.to_datetime(df['created_at']).dt.date
            clicks_per_day = df.groupby('day').size().reset_index(name='count')
            avg_clicks = clicks_per_day['count'].mean()
            st.metric("Média de cliques por dia", f"{avg_clicks:.1f}")
        
        with col3:
            # Contagem de URLs únicas
            unique_urls = df['url'].nunique()
            st.metric("URLs únicas", unique_urls)
        
        # Gráfico de cliques por dia
        if not clicks_per_day.empty:
            st.subheader("Cliques por dia")
            fig = px.bar(
                clicks_per_day, 
                x='day', 
                y='count',
                title="Distribuição de cliques por dia",
                labels={'day': 'Data', 'count': 'Número de cliques'}
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Tabela de FBclids
        st.subheader("Lista de FBclids")
        
        # Opções de filtro
        st.markdown("### Filtros")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Filtro por data
            min_date = pd.to_datetime(df['created_at']).min().date()
            max_date = pd.to_datetime(df['created_at']).max().date()
            
            date_range = st.date_input(
                "Intervalo de datas",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date
            )
        
        with col2:
            # Filtro por URL
            all_urls = ['Todas'] + sorted(df['url'].unique().tolist())
            selected_url = st.selectbox("Filtrar por URL", all_urls)
        
        # Aplicar filtros
        filtered_df = df.copy()
        
        if len(date_range) == 2:
            start_date, end_date = date_range
            filtered_df = filtered_df[
                (pd.to_datetime(filtered_df['created_at']).dt.date >= start_date) &
                (pd.to_datetime(filtered_df['created_at']).dt.date <= end_date)
            ]
        
        if selected_url != 'Todas':
            filtered_df = filtered_df[filtered_df['url'] == selected_url]
        
        # Exibe a tabela com os dados filtrados
        st.dataframe(
            filtered_df,
            column_config={
                "fbclid": st.column_config.TextColumn("FBclid", width="large"),
                "formatted_fbclid": st.column_config.TextColumn("FBclid Formatado", width="large"),
                "created_at": "Data de Criação",
                "client_id": "ID do Cliente",
                "url": "URL"
            },
            use_container_width=True
        )
        
        # Seleção de FBclids para envio
        st.subheader("Enviar FBclids para API de Conversões")
        
        # Opções para seleção de FBclids
        selection_option = st.radio(
            "Selecionar FBclids para envio",
            ["Todos filtrados", "Amostra aleatória", "Selecionar manualmente"]
        )
        
        if selection_option == "Todos filtrados":
            selected_df = filtered_df
        elif selection_option == "Amostra aleatória":
            sample_size = st.slider("Tamanho da amostra", 1, len(filtered_df), min(10, len(filtered_df)))
            selected_df = filtered_df.sample(sample_size)
        else:  # Selecionar manualmente
            selected_indices = st.multiselect(
                "Selecione os FBclids para envio",
                range(len(filtered_df)),
                format_func=lambda i: f"{filtered_df.iloc[i]['fbclid']} ({filtered_df.iloc[i]['created_at']})"
            )
            selected_df = filtered_df.iloc[selected_indices] if selected_indices else pd.DataFrame()
        
        # Exibe quantidade selecionada
        st.info(f"Selecionados {len(selected_df)} FBclids para envio")
        
        # Botão para enviar os FBclids selecionados
        if st.button("Enviar FBclids para API de Conversões", disabled=len(selected_df) == 0):
            if 'results' not in st.session_state:
                st.session_state['results'] = {}
            
            with st.spinner("Enviando FBclids para a API de Conversões..."):
                progress_bar = st.progress(0)
                
                results = send_selected_fbclids(selected_df, progress_bar)
                st.session_state['results'] = results
                
                progress_bar.empty()
                st.success(f"Processo concluído: {results['success']} eventos enviados com sucesso, {results['failed']} falhas.")
        
        # Exibe resultados do envio
        if 'results' in st.session_state and st.session_state['results']:
            results = st.session_state['results']
            
            st.subheader("Resultados do Envio")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Total enviado", results['total'])
            
            with col2:
                st.metric("Sucesso", results['success'])
            
            with col3:
                st.metric("Falhas", results['failed'])
            
            # Tabela com respostas da API
            if results.get('responses'):
                st.subheader("Respostas da API")
                
                responses_data = []
                for item in results['responses']:
                    fbclid = item.get('fbclid', '')
                    response = item.get('response', {})
                    
                    status = "Sucesso" if response.get('events_received', 0) > 0 else "Falha"
                    events_received = response.get('events_received', 0)
                    error_message = response.get('error', {}).get('message', '') if 'error' in response else ''
                    
                    responses_data.append({
                        'FBclid': fbclid,
                        'Status': status,
                        'Eventos Recebidos': events_received,
                        'Mensagem de Erro': error_message
                    })
                
                responses_df = pd.DataFrame(responses_data)
                st.dataframe(responses_df, use_container_width=True)
                
                # Opção para baixar resultados
                st.download_button(
                    label="Baixar resultados como JSON",
                    data=json.dumps(results, indent=2),
                    file_name="fbclid_conversions_results.json",
                    mime="application/json"
                )

if __name__ == "__main__":
    main()
