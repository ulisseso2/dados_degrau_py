import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from conexao.mongo_connection import (
    get_streamlit_cached_subjects, 
    get_streamlit_cached_subject_details, 
    get_streamlit_cached_all_subjects_with_topics,
    get_cache_stats,
    clear_cache,
    get_system_stats,
    get_mongodb_health
)

def run_page():
    st.title("📚 Análise de Disciplinas e Tópicos")
    st.markdown("### Dashboard de Questões por Subject e Topics")
    
    # Carrega todos os dados
    with st.spinner("Carregando dados do JSON local..."):
        subjects_data = get_streamlit_cached_subjects()
        all_subjects_with_topics = get_streamlit_cached_all_subjects_with_topics()
    
    if not subjects_data:
        st.error("❌ Não foi possível carregar os dados do arquivo JSON. Verifique o arquivo.")
        st.stop()
    
    # Sidebar com filtros
    st.sidebar.header("🔍 Filtros")
    
    # ============================================================================
    # SEÇÃO 1: VISÃO GERAL
    # ============================================================================
    st.header("📊 Visão Geral")
    
    # Métricas principais
    total_subjects = len(subjects_data)
    total_questions = sum(subject.get('total', 0) for subject in subjects_data)
    avg_questions_per_subject = total_questions / total_subjects if total_subjects > 0 else 0
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total de Disciplinas", total_subjects)
    with col2:
        st.metric("Total de Questões", f"{total_questions:,}")
    with col3:
        st.metric("Média por Disciplina", f"{avg_questions_per_subject:.1f}")
    
    # Preparar dados para gráficos
    df_subjects = pd.DataFrame(subjects_data)
    df_subjects = df_subjects.sort_values('total', ascending=False)
    
    # Gráfico de barras das top 20 disciplinas
    st.subheader("🏆 Top 20 Disciplinas por Número de Questões")
    
    top_20 = df_subjects.head(20)
    
    fig_top20 = px.bar(
        top_20,
        x='total',
        y='name',
        orientation='h',
        title="Top 20 Disciplinas",
        labels={'total': 'Número de Questões', 'name': 'Disciplina'},
        color='total',
        color_continuous_scale='viridis'
    )
    fig_top20.update_layout(
        yaxis={'categoryorder': 'total ascending'},
        height=600
    )
    st.plotly_chart(fig_top20, use_container_width=True)
    
    # ============================================================================
    # SEÇÃO 2: ANÁLISE DETALHADA POR DISCIPLINA
    # ============================================================================
    st.header("🔍 Análise Detalhada por Disciplina")
    
    # Filtro para selecionar disciplina
    subject_names = [subject['name'] for subject in subjects_data]
    subject_names.sort()
    
    selected_subject = st.selectbox(
        "📖 Selecione uma disciplina para análise detalhada:",
        options=subject_names,
        index=0 if subject_names else None
    )
    
    if selected_subject:
        # Busca detalhes da disciplina selecionada
        subject_details = get_streamlit_cached_subject_details(selected_subject)
        
        if subject_details and 'topics' in subject_details:
            # Informações gerais da disciplina
            st.subheader(f"📋 Disciplina: {selected_subject}")
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total de Questões", subject_details.get('total', 0))
            with col2:
                st.metric("Número de Tópicos", len(subject_details['topics']))
            
            # Preparar dados dos tópicos
            topics_data = subject_details['topics']
            df_topics = pd.DataFrame(topics_data)
            df_topics = df_topics.sort_values('total', ascending=False)
            
            # Gráfico de pizza dos tópicos
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("🥧 Distribuição por Tópicos")
                fig_pie = px.pie(
                    df_topics,
                    values='total',
                    names='name',
                    title=f"Distribuição de Questões - {selected_subject}"
                )
                fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_pie, use_container_width=True)
            
            with col2:
                st.subheader("📊 Tópicos por Quantidade")
                fig_topics_bar = px.bar(
                    df_topics,
                    x='total',
                    y='name',
                    orientation='h',
                    title=f"Questões por Tópico - {selected_subject}",
                    labels={'total': 'Número de Questões', 'name': 'Tópico'},
                    color='total',
                    color_continuous_scale='blues'
                )
                fig_topics_bar.update_layout(
                    yaxis={'categoryorder': 'total ascending'},
                    height=400
                )
                st.plotly_chart(fig_topics_bar, use_container_width=True)
            
            # Tabela detalhada dos tópicos
            st.subheader("📝 Tabela Detalhada dos Tópicos")
            
            # Adicionar estatísticas aos dados da tabela
            df_topics_display = df_topics.copy()
            total_questions_subject = df_topics_display['total'].sum()
            df_topics_display['percentual'] = (df_topics_display['total'] / total_questions_subject * 100).round(2)
            df_topics_display['percentual_str'] = df_topics_display['percentual'].astype(str) + '%'
            
            # Renomear colunas para exibição
            df_topics_display = df_topics_display.rename(columns={
                'name': 'Tópico',
                'total': 'Questões',
                'percentual_str': 'Percentual'
            })
            
            st.dataframe(
                df_topics_display[['Tópico', 'Questões', 'Percentual']],
                use_container_width=True,
                hide_index=True
            )
            
        else:
            st.warning(f"⚠️ Não foram encontrados detalhes para a disciplina: {selected_subject}")
    
    # ============================================================================
    # SEÇÃO 3: ANÁLISE COMPARATIVA
    # ============================================================================
    st.header("🔄 Análise Comparativa")
    
    # Filtro para comparar múltiplas disciplinas
    st.subheader("📊 Comparação entre Disciplinas")
    
    selected_subjects_compare = st.multiselect(
        "Selecione disciplinas para comparar:",
        options=subject_names,
        default=subject_names[:5] if len(subject_names) >= 5 else subject_names
    )
    
    if selected_subjects_compare:
        # Criar dados para comparação
        compare_data = []
        for subject_name in selected_subjects_compare:
            subject_info = next((s for s in subjects_data if s['name'] == subject_name), None)
            if subject_info:
                compare_data.append({
                    'Disciplina': subject_name,
                    'Total_Questoes': subject_info['total']
                })
        
        df_compare = pd.DataFrame(compare_data)
        df_compare = df_compare.sort_values('Total_Questoes', ascending=True)
        
        # Gráfico de comparação
        fig_compare = px.bar(
            df_compare,
            x='Total_Questoes',
            y='Disciplina',
            orientation='h',
            title="Comparação entre Disciplinas Selecionadas",
            labels={'Total_Questoes': 'Número de Questões', 'Disciplina': 'Disciplina'},
            color='Total_Questoes',
            color_continuous_scale='plasma'
        )
        fig_compare.update_layout(height=max(400, len(selected_subjects_compare) * 30))
        st.plotly_chart(fig_compare, use_container_width=True)
        
        # Estatísticas da comparação
        st.subheader("📈 Estatísticas da Comparação")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Maior", f"{df_compare['Total_Questoes'].max():,}")
        with col2:
            st.metric("Menor", f"{df_compare['Total_Questoes'].min():,}")
        with col3:
            st.metric("Média", f"{df_compare['Total_Questoes'].mean():.1f}")
        with col4:
            st.metric("Mediana", f"{df_compare['Total_Questoes'].median():.1f}")
    
    # ============================================================================
    # SEÇÃO 4: TABELA COMPLETA E EXPORTAÇÃO
    # ============================================================================
    st.header("📋 Dados Completos")
    
    # Filtros para a tabela completa
    col1, col2 = st.columns(2)
    
    with col1:
        min_questions = st.number_input(
            "Filtrar disciplinas com pelo menos X questões:",
            min_value=0,
            max_value=total_questions,
            value=0,
            step=1
        )
    
    with col2:
        sort_options = ["Alfabética", "Mais Questões", "Menos Questões"]
        sort_by = st.selectbox("Ordenar por:", sort_options, index=1)
    
    # Aplicar filtros
    df_filtered = df_subjects[df_subjects['total'] >= min_questions].copy()
    
    # Aplicar ordenação
    if sort_by == "Alfabética":
        df_filtered = df_filtered.sort_values('name')
    elif sort_by == "Mais Questões":
        df_filtered = df_filtered.sort_values('total', ascending=False)
    else:  # Menos Questões
        df_filtered = df_filtered.sort_values('total', ascending=True)
    
    # Renomear colunas para exibição
    df_display = df_filtered.rename(columns={
        'name': 'Disciplina',
        'total': 'Total de Questões'
    })
    
    st.subheader(f"📚 Lista de Disciplinas ({len(df_display)} disciplinas)")
    st.dataframe(df_display, use_container_width=True, hide_index=True)
    
    # Botão de download
    csv_data = df_display.to_csv(index=False)
    st.download_button(
        label="📥 Baixar dados em CSV",
        data=csv_data,
        file_name="disciplinas_questoes.csv",
        mime="text/csv"
    )
    
    # ============================================================================
    # INFORMAÇÕES ADICIONAIS E CACHE
    # ============================================================================
    st.header("ℹ️ Informações e Cache")
    
    col1, col2 = st.columns(2)
    
    with col1:
        with st.expander("📊 Sobre os Dados"):
            st.markdown("""
            **Fonte dos Dados:** Arquivo JSON Local - `eduqc.subjects_topics_summary.json`
            
            **Estrutura dos Dados:**
            - **Disciplinas (Subjects):** Cada item representa uma disciplina
            - **Tópicos (Topics):** Lista de tópicos dentro de cada disciplina
            - **Total:** Número total de questões por disciplina e por tópico
            
            **Atualização:** Os dados são atualizados automaticamente com cache inteligente
            """)
    
    with col2:
        with st.expander("🔧 Funcionalidades"):
            st.markdown("""
            - ✅ Visão geral com métricas principais
            - ✅ Top 20 disciplinas por número de questões
            - ✅ Análise detalhada por disciplina com gráficos de pizza e barras
            - ✅ Tabela detalhada dos tópicos com percentuais
            - ✅ Comparação entre múltiplas disciplinas
            - ✅ Filtros e ordenação personalizados
            - ✅ Exportação de dados em CSV
            - ✅ Cache otimizado para melhor performance
            """)
    
    # Seção de cache para administradores
    if st.sidebar.button("🔧 Mostrar Info Cache (Admin)"):
        st.subheader("🗄️ Informações do Sistema")
        
        try:
            # Health check do JSON local
            health = get_mongodb_health()  # Função retorna info do JSON agora
            
            # Métricas de saúde
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                status_color = "🟢" if health['status'] == 'healthy' else "🔴"
                st.metric("Status JSON", f"{status_color} {health['status'].title()}")
            
            with col2:
                ping_time = health.get('ping_time_ms', 'N/A')
                st.metric("Acesso (ms)", ping_time)
            
            with col3:
                doc_count = health.get('document_count', 0)
                st.metric("Documentos", f"{doc_count:,}")
            
            with col4:
                if st.button("🗑️ Limpar Cache"):
                    clear_cache()
                    st.success("Cache limpo com sucesso!")
                    st.rerun()
            
            # Informações detalhadas do cache
            cache_stats = get_cache_stats()
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("� Cache")
                st.metric("Itens em Cache", cache_stats['cache_size'])
                
                if cache_stats['cache_size'] > 0:
                    st.write("**Chaves em Cache:**")
                    for key in cache_stats['keys']:
                        # Simplifica o nome da chave para exibição
                        simplified_key = key.split('_')[1] if '_' in key else key
                        st.text(f"• {simplified_key}")
            
            with col2:
                st.subheader("🗃️ Fonte de Dados")
                if health['status'] == 'healthy':
                    st.write("**Arquivo JSON Carregado**")
                    if 'data_source' in health:
                        st.text(f"Tipo: {health.get('data_source', 'JSON Local')}")
                    if 'file_path' in health:
                        st.text(f"Arquivo: eduqc.subjects_topics_summary.json")
                else:
                    st.error(f"**Erro:** {health.get('error', 'Arquivo não disponível')}")
                    
        except Exception as e:
            st.error(f"Erro ao buscar informações do sistema: {e}")
    
    # Indicador de status na sidebar
    try:
        health = get_mongodb_health()
        status_indicator = "🟢 Disponível" if health['status'] == 'healthy' else "🔴 Indisponível"
        st.sidebar.caption(f"JSON Local: {status_indicator}")
    except:
        st.sidebar.caption("JSON Local: ⚪ Desconhecido")
