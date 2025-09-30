#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Interface de página para o Dashboard de FBclids
Esta página permite acessar o dashboard de FBclids através do sistema de páginas principal
"""

import streamlit as st
import os
import time
import json
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from dotenv import load_dotenv
import requests
import uuid

# Carregar variáveis de ambiente do arquivo principal e depois do arquivo específico do Facebook
load_dotenv()
load_dotenv('.facebook_credentials.env')  # Carrega as credenciais específicas do Facebook

# Configurações da API do Facebook
FB_ACCESS_TOKEN = os.getenv('FB_ACCESS_TOKEN')
PIXEL_ID = os.getenv('FB_PIXEL_ID')
DB_FILE = "fbclid_cache.db"  # Banco de dados específico para FBclids

def format_fbclid(fbclid, created_at=None):
    """
    Formata o FBclid conforme especificação da Meta:
    fb.subdomainIndex.creationTime.fbclid
    
    Onde:
    - fb é sempre o prefixo
    - subdomainIndex é 1 (para domínio principal)
    - creationTime é o timestamp em segundos
    - fbclid é o valor original do parâmetro
    
    Se o FBclid já estiver formatado, retorna-o como está.
    """
    # Verifica se já está no formato correto (fb.1.timestamp.fbclid)
    if fbclid and isinstance(fbclid, str):
        # Verifica se já está no formato fb.1.timestamp.fbclid
        import re
        if re.match(r'^fb\.\d+\.\d+\.', fbclid):
            return fbclid
        
        # Determina o timestamp a usar
        if created_at:
            try:
                # Se created_at for string, converte para datetime
                if isinstance(created_at, str):
                    dt = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                else:
                    dt = created_at
                    
                # Converte para timestamp em segundos
                timestamp = int(dt.timestamp())
            except Exception as e:
                st.error(f"Erro ao converter data de criação, usando timestamp atual: {str(e)}")
                timestamp = int(time.time())
        else:
            # Usa o timestamp atual com um pequeno incremento aleatório para garantir unicidade
            import random
            timestamp = int(time.time()) + random.randint(1, 100)
        
        # Formata o FBclid
        formatted = f"fb.1.{timestamp}.{fbclid}"
        return formatted
    
    return fbclid

def ensure_db_structure():
    """Garante que o banco de dados e a tabela existam"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Cria a tabela se não existir
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS fbclid_cache (
        fbclid TEXT PRIMARY KEY,
        campaign_name TEXT,
        campaign_id TEXT,
        adset_name TEXT,
        ad_name TEXT,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.commit()
    conn.close()

def get_fbclids_from_db(limit=1000, days=None, status=None):
    """
    Carrega FBclids do banco de dados
    
    Args:
        limit: Limite de registros a retornar
        days: Se fornecido, retorna apenas FBclids atualizados há X dias
        status: Filtro por status (encontrado, não encontrado, erro)
    """
    conn = sqlite3.connect(DB_FILE)
    query = "SELECT * FROM fbclid_cache"
    where_clauses = []
    
    if days:
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        where_clauses.append(f"last_updated < '{cutoff_date}'")
    
    if status:
        if status == "encontrado":
            where_clauses.append("campaign_name != 'Não encontrado' AND campaign_name NOT LIKE 'Erro:%'")
        elif status == "não encontrado":
            where_clauses.append("campaign_name = 'Não encontrado'")
        elif status == "erro":
            where_clauses.append("campaign_name LIKE 'Erro:%'")
    
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    
    query += " ORDER BY last_updated DESC LIMIT ?"
    
    df = pd.read_sql_query(query, conn, params=(limit,))
    conn.close()
    
    return df

def get_fbclids_stats():
    """Obtém estatísticas sobre os FBclids no banco de dados"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Total de FBclids
    cursor.execute("SELECT COUNT(*) FROM fbclid_cache")
    total = cursor.fetchone()[0]
    
    # FBclids com campanha encontrada
    cursor.execute("""
        SELECT COUNT(*) FROM fbclid_cache 
        WHERE campaign_name != 'Não encontrado' AND campaign_name NOT LIKE 'Erro:%'
    """)
    found = cursor.fetchone()[0]
    
    # FBclids não encontrados
    cursor.execute("SELECT COUNT(*) FROM fbclid_cache WHERE campaign_name = 'Não encontrado'")
    not_found = cursor.fetchone()[0]
    
    # FBclids com erro
    cursor.execute("SELECT COUNT(*) FROM fbclid_cache WHERE campaign_name LIKE 'Erro:%'")
    error = cursor.fetchone()[0]
    
    # FBclids por data (últimos 30 dias)
    cursor.execute("""
        SELECT DATE(last_updated) as date, COUNT(*) as count
        FROM fbclid_cache
        WHERE last_updated >= date('now', '-30 days')
        GROUP BY DATE(last_updated)
        ORDER BY date
    """)
    daily_data = cursor.fetchall()
    daily_df = pd.DataFrame(daily_data, columns=['date', 'count'])
    
    # FBclids por campanha (top 10)
    cursor.execute("""
        SELECT campaign_name, COUNT(*) as count
        FROM fbclid_cache
        WHERE campaign_name != 'Não encontrado' AND campaign_name NOT LIKE 'Erro:%'
        GROUP BY campaign_name
        ORDER BY count DESC
        LIMIT 10
    """)
    campaign_data = cursor.fetchall()
    campaign_df = pd.DataFrame(campaign_data, columns=['campaign', 'count'])
    
    conn.close()
    
    return {
        'total': total,
        'found': found,
        'not_found': not_found,
        'error': error,
        'daily': daily_df,
        'campaigns': campaign_df
    }

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
    
    # Formata o FBclid se necessário
    formatted_fbclid = format_fbclid(fbclid)
    
    # Gera um ID de evento único
    event_id = str(uuid.uuid4())
    
    # Define o timestamp atual
    if not event_time:
        event_time = int(time.time())
    
    # Cria um evento para a API de Conversões
    event_data = {
        "data": [{
            "event_name": event_name,
            "event_time": event_time,
            "event_id": event_id,
            "action_source": "website",
            "event_source_url": "https://degrauculturalidiomas.com.br/",
            "user_data": {
                "fbc": formatted_fbclid,
                "client_ip_address": "127.0.0.1",
                "client_user_agent": "Mozilla/5.0"
            }
        }]
    }
    
    # URL da API de Conversões
    url = f"https://graph.facebook.com/v18.0/{PIXEL_ID}/events"
    
    try:
        # Envia o evento
        response = requests.post(
            url, 
            params={'access_token': FB_ACCESS_TOKEN},
            json=event_data
        )
        
        return response.json()
    
    except Exception as e:
        return {"error": str(e)}

def process_fbclid_batch(fbclids, batch_size=50, delay=1):
    """
    Processa um lote de FBclids enviando-os para a API de Conversões
    
    Args:
        fbclids: Lista de FBclids
        batch_size: Tamanho do lote
        delay: Tempo de espera entre requisições
        
    Returns:
        Estatísticas sobre o processamento
    """
    total = len(fbclids)
    success = 0
    error = 0
    results = []
    
    # Processa em lotes
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i in range(0, total, batch_size):
        batch = fbclids[i:i+batch_size]
        status_text.text(f"Processando lote {i//batch_size + 1}/{(total+batch_size-1)//batch_size} ({len(batch)} FBclids)")
        
        for j, fbclid in enumerate(batch):
            # Envia o evento
            response = send_conversion_event(fbclid)
            
            # Registra o resultado
            result = {
                'fbclid': fbclid,
                'response': response
            }
            results.append(result)
            
            # Verifica o resultado
            if 'events_received' in response and response['events_received'] > 0:
                success += 1
            else:
                error += 1
            
            # Atualiza o progresso
            progress = (i + j + 1) / total
            progress_bar.progress(progress)
            
            # Aguarda um pouco para não sobrecarregar a API
            time.sleep(delay)
    
    status_text.text(f"Processamento concluído! {success} sucessos, {error} erros")
    
    return {
        'total': total,
        'success': success,
        'error': error,
        'results': results
    }

def add_fbclid_to_db(fbclid, campaign_info=None):
    """Adiciona ou atualiza um FBclid no banco de dados"""
    if not campaign_info:
        campaign_info = {
            'campaign_name': 'Não consultado',
            'campaign_id': None,
            'adset_name': None,
            'ad_name': None
        }
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        # Verifica se já existe
        cursor.execute("SELECT fbclid FROM fbclid_cache WHERE fbclid = ?", (fbclid,))
        if cursor.fetchone():
            # Atualiza o registro existente
            cursor.execute("""
                UPDATE fbclid_cache 
                SET campaign_name = ?, campaign_id = ?, adset_name = ?, ad_name = ?, last_updated = CURRENT_TIMESTAMP
                WHERE fbclid = ?
            """, (
                campaign_info.get('campaign_name', 'Não encontrado'),
                campaign_info.get('campaign_id'),
                campaign_info.get('adset_name'),
                campaign_info.get('ad_name'),
                fbclid
            ))
        else:
            # Insere novo registro
            cursor.execute("""
                INSERT INTO fbclid_cache (fbclid, campaign_name, campaign_id, adset_name, ad_name)
                VALUES (?, ?, ?, ?, ?)
            """, (
                fbclid,
                campaign_info.get('campaign_name', 'Não encontrado'),
                campaign_info.get('campaign_id'),
                campaign_info.get('adset_name'),
                campaign_info.get('ad_name')
            ))
        
        conn.commit()
        conn.close()
        return True, "FBclid adicionado/atualizado com sucesso"
    
    except Exception as e:
        conn.close()
        return False, f"Erro ao adicionar/atualizar FBclid: {str(e)}"

def run_page():
    """Função principal que exibe o dashboard"""
    st.title("📊 Dashboard de FBclids")
    
    # Garante que o banco de dados exista
    ensure_db_structure()
    
    # Verifica credenciais
    if not FB_ACCESS_TOKEN or not PIXEL_ID:
        st.error("""
        ⚠️ Credenciais do Facebook não encontradas! 
        
        Configure as variáveis FB_ACCESS_TOKEN e PIXEL_ID no arquivo .facebook_credentials.env
        """)
        
        with st.expander("Como configurar as credenciais"):
            st.markdown("""
            ### Configurando as credenciais
            
            1. Crie um arquivo `.facebook_credentials.env` na raiz do projeto com o seguinte conteúdo:
            ```
            FB_ACCESS_TOKEN=seu_token_aqui
            FB_PIXEL_ID=seu_pixel_id_aqui
            FB_APP_ID=seu_app_id_aqui
            FB_APP_SECRET=seu_app_secret_aqui
            FB_AD_ACCOUNT_ID=seu_ad_account_id_aqui
            ```
            
            2. Você pode obter estas credenciais no painel de desenvolvedores do Facebook:
               - https://developers.facebook.com
            """)
        
        return
    
    # Abas principais
    tab1, tab2, tab3, tab4 = st.tabs(["Visão Geral", "Consultar FBclids", "Processar em Lote", "Adicionar FBclids"])
    
    # --- Aba 1: Visão Geral ---
    with tab1:
        st.header("📈 Visão Geral")
        
        # Estatísticas
        stats = get_fbclids_stats()
        
        # Métricas principais
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total de FBclids", stats['total'])
        
        with col2:
            st.metric("Campanhas Encontradas", stats['found'])
        
        with col3:
            st.metric("Não Encontrados", stats['not_found'])
        
        with col4:
            st.metric("Erros", stats['error'])
        
        # Gráficos
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("FBclids por Status")
            status_data = {
                'Status': ['Encontrados', 'Não Encontrados', 'Erros'],
                'Quantidade': [stats['found'], stats['not_found'], stats['error']]
            }
            status_df = pd.DataFrame(status_data)
            fig = px.pie(status_df, values='Quantidade', names='Status', 
                        color_discrete_sequence=px.colors.qualitative.Safe)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("FBclids por Campanha (Top 10)")
            if not stats['campaigns'].empty:
                fig = px.bar(stats['campaigns'], x='count', y='campaign', orientation='h',
                            color='count', color_continuous_scale='Viridis')
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Nenhuma campanha encontrada")
        
        # Gráfico de linha - FBclids por dia
        st.subheader("FBclids por Dia (Últimos 30 dias)")
        if not stats['daily'].empty:
            fig = px.line(stats['daily'], x='date', y='count', markers=True)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Nenhum dado diário disponível")
        
        # Dados recentes
        st.subheader("FBclids Mais Recentes")
        recent_data = get_fbclids_from_db(limit=10)
        if not recent_data.empty:
            st.dataframe(recent_data, use_container_width=True)
        else:
            st.info("Nenhum FBclid encontrado no banco de dados")
    
    # --- Aba 2: Consultar FBclids ---
    with tab2:
        st.header("🔍 Consultar FBclids")
        
        # Filtros
        col1, col2, col3 = st.columns(3)
        
        with col1:
            limit = st.number_input("Limite de registros", min_value=1, max_value=1000, value=100)
        
        with col2:
            days = st.number_input("Dias para atualização", min_value=0, value=0, 
                                help="Mostrar apenas FBclids atualizados há X dias (0 = todos)")
        
        with col3:
            status_options = ["Todos", "Encontrado", "Não Encontrado", "Erro"]
            status = st.selectbox("Status", status_options)
        
        # Busca
        search_text = st.text_input("Buscar por FBclid ou campanha", "")
        
        # Obtém dados
        status_filter = None
        if status == "Encontrado":
            status_filter = "encontrado"
        elif status == "Não Encontrado":
            status_filter = "não encontrado"
        elif status == "Erro":
            status_filter = "erro"
        
        days_filter = days if days > 0 else None
        
        df = get_fbclids_from_db(limit=limit, days=days_filter, status=status_filter)
        
        # Filtra por texto de busca
        if search_text and not df.empty:
            mask = (
                df['fbclid'].str.contains(search_text, case=False, na=False) | 
                df['campaign_name'].str.contains(search_text, case=False, na=False)
            )
            df = df[mask]
        
        # Exibe resultados
        if not df.empty:
            st.write(f"Exibindo {len(df)} registros de um total de {stats['total']}")
            
            # Adiciona coluna de ações
            df['Ações'] = False
            
            # Exibe tabela
            edited_df = st.data_editor(
                df,
                column_config={
                    "fbclid": st.column_config.TextColumn("FBclid", width="large"),
                    "campaign_name": st.column_config.TextColumn("Campanha"),
                    "campaign_id": st.column_config.TextColumn("ID da Campanha"),
                    "adset_name": st.column_config.TextColumn("Conjunto de Anúncios"),
                    "ad_name": st.column_config.TextColumn("Anúncio"),
                    "last_updated": st.column_config.DatetimeColumn("Atualizado em"),
                    "Ações": st.column_config.CheckboxColumn("Selecionar")
                },
                use_container_width=True,
                hide_index=True
            )
            
            # Botões de ação
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("Atualizar Selecionados", type="primary"):
                    selected_fbclids = edited_df[edited_df['Ações'] == True]['fbclid'].tolist()
                    
                    if not selected_fbclids:
                        st.warning("Nenhum FBclid selecionado")
                    else:
                        st.info(f"Atualizando {len(selected_fbclids)} FBclids...")
                        results = process_fbclid_batch(selected_fbclids)
                        st.success(f"Processamento concluído! {results['success']} sucessos, {results['error']} erros")
            
            with col2:
                if st.button("Excluir Selecionados", type="secondary"):
                    selected_fbclids = edited_df[edited_df['Ações'] == True]['fbclid'].tolist()
                    
                    if not selected_fbclids:
                        st.warning("Nenhum FBclid selecionado")
                    else:
                        confirm_delete = st.checkbox("Confirmar exclusão")
                        
                        if confirm_delete:
                            conn = sqlite3.connect(DB_FILE)
                            cursor = conn.cursor()
                            
                            for fbclid in selected_fbclids:
                                cursor.execute("DELETE FROM fbclid_cache WHERE fbclid = ?", (fbclid,))
                            
                            conn.commit()
                            conn.close()
                            
                            st.success(f"{len(selected_fbclids)} FBclids excluídos com sucesso")
                            st.rerun()
        else:
            st.info("Nenhum FBclid encontrado com os filtros selecionados")
    
    # --- Aba 3: Processar em Lote ---
    with tab3:
        st.header("⚙️ Processar em Lote")
        
        # Configurações de processamento
        st.subheader("Configurações")
        
        col1, col2 = st.columns(2)
        
        with col1:
            batch_size = st.number_input("Tamanho do lote", min_value=1, max_value=100, value=50, key="batch_size")
        
        with col2:
            delay = st.number_input("Atraso entre requisições (segundos)", min_value=0.1, max_value=5.0, value=1.0, step=0.1, key="delay")
        
        # Seleção de FBclids
        st.subheader("Selecionar FBclids para Processamento")
        
        option = st.radio(
            "Fonte de FBclids",
            ["Todos", "Não Encontrados", "Erros", "Desatualizados"]
        )
        
        fbclids_to_process = []
        
        if option == "Todos":
            df = get_fbclids_from_db(limit=1000)
            fbclids_to_process = df['fbclid'].tolist()
        elif option == "Não Encontrados":
            df = get_fbclids_from_db(limit=1000, status="não encontrado")
            fbclids_to_process = df['fbclid'].tolist()
        elif option == "Erros":
            df = get_fbclids_from_db(limit=1000, status="erro")
            fbclids_to_process = df['fbclid'].tolist()
        elif option == "Desatualizados":
            days = st.number_input("Dias para considerar desatualizado", min_value=1, max_value=365, value=7)
            df = get_fbclids_from_db(limit=1000, days=days)
            fbclids_to_process = df['fbclid'].tolist()
        
        # Limitar quantidade
        limit = st.number_input("Limitar quantidade", min_value=1, max_value=1000, value=min(100, len(fbclids_to_process) if fbclids_to_process else 100))
        fbclids_to_process = fbclids_to_process[:limit]
        
        # Botão de processamento
        if st.button("Processar FBclids", type="primary", key="process_button"):
            if not fbclids_to_process:
                st.warning("Nenhum FBclid para processar")
            else:
                st.info(f"Processando {len(fbclids_to_process)} FBclids...")
                
                results = process_fbclid_batch(fbclids_to_process, batch_size=batch_size, delay=delay)
                
                # Exibe resultados
                st.success(f"Processamento concluído!")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.metric("Sucessos", results['success'])
                
                with col2:
                    st.metric("Erros", results['error'])
                
                # Exibe detalhes
                if results.get('results'):
                    st.subheader("Detalhes dos Resultados")
                    results_data = []
                    
                    for item in results['results']:
                        fbclid = item.get('fbclid', '')
                        response = item.get('response', {})
                        
                        status = "Sucesso" if response.get('events_received', 0) > 0 else "Falha"
                        events_received = response.get('events_received', 0)
                        error_message = response.get('error', {}).get('message', '') if 'error' in response else ''
                        
                        results_data.append({
                            'FBclid': fbclid,
                            'Status': status,
                            'Eventos Recebidos': events_received,
                            'Mensagem de Erro': error_message
                        })
                    
                    results_df = pd.DataFrame(results_data)
                    st.dataframe(results_df, use_container_width=True)
    
    # --- Aba 4: Adicionar FBclids ---
    with tab4:
        st.header("📝 Adicionar FBclids")
        
        tab4_1, tab4_2, tab4_3 = st.tabs(["Adicionar Individual", "Importar Lista", "De Arquivo CSV"])
        
        # Sub-aba: Adicionar Individual
        with tab4_1:
            st.subheader("Adicionar FBclid Individual")
            
            fbclid = st.text_input("Digite o FBclid")
            
            if st.button("Adicionar FBclid", type="primary"):
                if not fbclid:
                    st.warning("Digite um FBclid válido")
                else:
                    success, message = add_fbclid_to_db(fbclid)
                    
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
        
        # Sub-aba: Importar Lista
        with tab4_2:
            st.subheader("Importar Lista de FBclids")
            
            fbclids_text = st.text_area("Cole uma lista de FBclids (um por linha)")
            
            if st.button("Importar Lista", type="primary"):
                if not fbclids_text.strip():
                    st.warning("Nenhum FBclid para importar")
                else:
                    fbclids_list = [f.strip() for f in fbclids_text.split('\n') if f.strip()]
                    
                    if not fbclids_list:
                        st.warning("Nenhum FBclid válido encontrado")
                    else:
                        st.info(f"Importando {len(fbclids_list)} FBclids...")
                        
                        success_count = 0
                        error_count = 0
                        
                        for fbclid in fbclids_list:
                            success, _ = add_fbclid_to_db(fbclid)
                            
                            if success:
                                success_count += 1
                            else:
                                error_count += 1
                        
                        st.success(f"Importação concluída: {success_count} adicionados, {error_count} erros")
        
        # Sub-aba: De Arquivo CSV
        with tab4_3:
            st.subheader("Importar de Arquivo CSV")
            
            uploaded_file = st.file_uploader("Escolha um arquivo CSV", type="csv")
            
            if uploaded_file is not None:
                try:
                    df = pd.read_csv(uploaded_file)
                    
                    # Tenta identificar a coluna de FBclid
                    fbclid_column = None
                    for col in df.columns:
                        if 'fbclid' in col.lower() or 'fb_clid' in col.lower() or 'fb clid' in col.lower():
                            fbclid_column = col
                            break
                    
                    if not fbclid_column:
                        st.warning("Não foi possível identificar a coluna de FBclid automaticamente.")
                        fbclid_column = st.selectbox("Selecione a coluna que contém os FBclids", df.columns)
                    
                    # Exibe os primeiros registros
                    st.write("Visualização dos dados:")
                    st.dataframe(df.head())
                    
                    # Botão para importar
                    if st.button("Importar do CSV", type="primary"):
                        fbclids_list = df[fbclid_column].dropna().unique().tolist()
                        
                        if not fbclids_list:
                            st.warning("Nenhum FBclid válido encontrado")
                        else:
                            st.info(f"Importando {len(fbclids_list)} FBclids únicos...")
                            
                            success_count = 0
                            error_count = 0
                            
                            progress_bar = st.progress(0)
                            
                            for i, fbclid in enumerate(fbclids_list):
                                if pd.isna(fbclid) or fbclid == '':
                                    error_count += 1
                                    continue
                                    
                                success, _ = add_fbclid_to_db(str(fbclid))
                                
                                if success:
                                    success_count += 1
                                else:
                                    error_count += 1
                                
                                # Atualiza progresso
                                progress_bar.progress((i + 1) / len(fbclids_list))
                            
                            st.success(f"Importação concluída: {success_count} adicionados, {error_count} erros")
                
                except Exception as e:
                    st.error(f"Erro ao processar o arquivo: {str(e)}")

if __name__ == "__main__":
    run_page()
