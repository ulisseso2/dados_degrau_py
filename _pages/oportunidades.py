import sys
import os
import io
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import streamlit as st
import plotly.express as px
from utils.sql_loader import carregar_dados
import plotly.graph_objects as go

def run_page():

    TIMEZONE = 'America/Sao_Paulo'

    st.title("🎯 Dashboard Oportunidades")

    df = carregar_dados("consultas/oportunidades/oportunidades.sql")

    # Pré-filtros
    df["criacao"] = pd.to_datetime(df["criacao"]).dt.tz_localize(TIMEZONE, ambiguous='infer')

    # Filtro: empresa
    empresas = df["empresa"].dropna().unique().tolist()
    empresa_selecionada = st.sidebar.radio("Selecione uma empresa:", empresas)
    df_filtrado_empresa = df[df["empresa"] == empresa_selecionada]

    # Filtro: data (padrão: dia atual)
    hoje_aware = pd.Timestamp.now(tz=TIMEZONE).date()
    periodo = st.sidebar.date_input(
        "Período de criação:", [hoje_aware, hoje_aware], key="date_oportunidades"
    )
    try:
        data_inicio_aware = pd.Timestamp(periodo[0], tz=TIMEZONE)
        data_fim_aware = pd.Timestamp(periodo[1], tz=TIMEZONE) + pd.Timedelta(days=1)
    except IndexError:
        # Caso o usuário limpe o campo de data, evita o erro
        st.warning("Por favor, selecione um período de datas.")
        st.stop() # Interrompe a execução para evitar erros abaixo

    # Filtros adicionais recolhidos

 

   
    unidades = sorted(df_filtrado_empresa["unidade"].dropna().unique())
    unidade_selecionada = st.sidebar.multiselect("Selecione a unidade:", unidades, default=unidades)

       
    etapas = sorted(df_filtrado_empresa["etapa"].dropna().unique()) # Ordenado
    etapa_selecionada = st.sidebar.multiselect("Selecione a etapa:", etapas, default=etapas)


    modalidades = sorted(df_filtrado_empresa["modalidade"].dropna().unique()) # Ordenado
    modalidade_selecionada = st.sidebar.multiselect("Selecione a modalidade:", modalidades, default=modalidades)

    hs_ligar = sorted(df_filtrado_empresa["h_ligar"].dropna().unique()) # Ordenado
    h_ligar_selecionada = st.sidebar.multiselect("Selecione a Hora", hs_ligar, default=hs_ligar)

    # 2. Inicia com o DataFrame completo
    df_filtrado = df

    # 3. Aplica os filtros sequencialmente
    if empresa_selecionada:
        df_filtrado = df_filtrado[df_filtrado["empresa"] == empresa_selecionada]

    if unidade_selecionada:
        # A lógica com .isna() é mantida para incluir valores nulos
        df_filtrado = df_filtrado[df_filtrado["unidade"].isin(unidade_selecionada) | df_filtrado["unidade"].isna()]

    if etapa_selecionada:
        df_filtrado = df_filtrado[df_filtrado["etapa"].isin(etapa_selecionada) | df_filtrado["etapa"].isna()]

    if modalidade_selecionada:
        df_filtrado = df_filtrado[df_filtrado["modalidade"].isin(modalidade_selecionada) | df_filtrado["modalidade"].isna()]

    if h_ligar_selecionada:
        df_filtrado = df_filtrado[df_filtrado["h_ligar"].isin(h_ligar_selecionada) | df_filtrado["h_ligar"].isna()]

    # Filtro de data sempre aplicado
    df_filtrado = df_filtrado[
        (df_filtrado["criacao"] >= data_inicio_aware) &
        (df_filtrado["criacao"] < data_fim_aware)
    ]

    # Métricas principais
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total de Oportunidades", df_filtrado.shape[0])
    
    with col2:
        oportunidades_online = df_filtrado[df_filtrado["modalidade"] == "Online"].shape[0]
        st.metric("Oportunidades Online", oportunidades_online)

    with col3:
        oportunidades_live = df_filtrado[df_filtrado["modalidade"] == "Live"].shape[0]
        st.metric("Oportunidades Live", oportunidades_live)

    with col4:
        oportunidades_presenciais = df_filtrado[df_filtrado["modalidade"] == "Presencial"].shape[0]
        st.metric("Oportunidades Presenciais", oportunidades_presenciais)

    df_diario = df_filtrado.groupby(df_filtrado["criacao"].dt.date)["oportunidade"].count().reset_index()

    #tabela concurso modalidade
    st.subheader("Oportunidades por Concurso / Modalidade")

    tabela_concurso_modalidade = df_filtrado.pivot_table(
        index="concurso",
        columns="modalidade",
        values="oportunidade",
        aggfunc="count",
        fill_value=0
    )

    # 4. Renomear colunas
    tabela_concurso_modalidade.columns = [f"{col} (Qtd)" for col in tabela_concurso_modalidade.columns]

    # 5. Adicionar coluna total
    tabela_concurso_modalidade["Total (Qtd)"] = tabela_concurso_modalidade.sum(axis=1)

    tabela_concurso_modalidade = tabela_concurso_modalidade.sort_values("Total (Qtd)", ascending=False)

    st.dataframe(tabela_concurso_modalidade, use_container_width=True)


    #pizza modalidades
    # Agrupa por modalidade e conta a quantidade de oportunidades
    df_modalidade = df_filtrado.groupby("modalidade")["oportunidade"].count().reset_index()

    # Cria o gráfico de pizza
    fig_modalidade = px.pie(
        df_modalidade,
        names="modalidade",
        values="oportunidade",
        title="Oportunidades por Modalidade",
        labels={"modalidade": "Modalidade", "oportunidade": "Quantidade"},
        )
    fig_modalidade.update_traces(textinfo='value+percent')
    st.plotly_chart(fig_modalidade, use_container_width=True)    

    # Renomeia coluna de data para 'Data' (opcional)
    df_diario.columns = ["Data", "Total"]

    oport_dia = px.bar(
        df_diario,
        x="Data",
        y="Total",
        title="Oportunidades por dia",
        labels={"quantidade": "Qtd. oportunidades", "unidade": "Unidade"},
        barmode="stack",
        text_auto=True,
    )
    st.plotly_chart(oport_dia, use_container_width=True)

    #pizza unidades
    # Agrupa por unidade e conta a quantidade de oportunidades
    df_unidade = df_filtrado.groupby("unidade")["oportunidade"].count().reset_index()

    # Cria o gráfico de pizza
    fig = px.pie(
        df_unidade,
        names="unidade",
        values="oportunidade",
        title="Oportunidades por Unidade",
        labels={"unidade": "Unidade", "oportunidade": "Quantidade"},
        )
    fig.update_traces(textinfo='value+percent')
    st.plotly_chart(fig, use_container_width=True)

    # --- INÍCIO DO CÓDIGO DO GRÁFICO DE FUNIL ---

    st.subheader("Funil de Oportunidades por Etapa")

    # 1. Preparar os dados
    df_funil = df_filtrado.groupby(['etapa', 'ordem_etapas']).agg(
        Quantidade=('oportunidade', 'count')
    ).reset_index()

    # 2. Ordenar as etapas
    df_funil = df_funil.sort_values('ordem_etapas')

    # 3. Verificar se há dados para exibir
    if not df_funil.empty:
        
        # O PONTO CHAVE: Calcula a SOMA de todas as quantidades no funil
        total_oportunidades_no_funil = df_funil['Quantidade'].sum()

        # Garante que não haverá divisão por zero
        if total_oportunidades_no_funil > 0:
            # Calcula o percentual de cada etapa em relação a essa SOMA
            percentual_calculado = (df_funil['Quantidade'] / total_oportunidades_no_funil) * 100
        else:
            # Se a soma for 0, todos os percentuais são 0.
            percentual_calculado = 0

        # FORMATA o texto para exibição
        texto_quantidade = df_funil['Quantidade'].map('{:.0f}'.format)
        texto_percentual = pd.Series(percentual_calculado).map('({:.1f}%)'.format)
        
        # Junta as duas partes para criar o texto final
        df_funil['texto_formatado'] = texto_percentual

        # 4. Gráfico de funil
        fig_funil = go.Figure(go.Funnel(
            y = df_funil['etapa'],
            x = df_funil['Quantidade'],
            textposition = "outside",
            text = df_funil['texto_formatado'],
            marker = {"color": px.colors.sequential.Blues_r}
        ))

        # 5. Layout
        fig_funil.update_layout(
            title={
                'text': "% e quantidade de oportunidades por etapa",
                'y':0.9, 'x':0.5, 'xanchor': 'center', 'yanchor': 'top'
            },
            yaxis_title="Etapas do Funil",
            xaxis_title="Quantidade de Oportunidades"
            
        )

        # 6. Exibir
        st.plotly_chart(fig_funil, use_container_width=True)

    else:
        st.info("Não há dados suficientes para exibir o funil de vendas com os filtros selecionados.")

    #Tabela de oportunidades por concurso e etapas
    st.subheader("Oportunidades por Concurso / Etapas")
    # 1. Obter ordem das etapas da query (sem duplicar e mantendo a ordem)
    ordem_etapas = (
        df_filtrado[['etapa', 'ordem_etapas']]
        .drop_duplicates()
        .sort_values('ordem_etapas')
        ['etapa']
        .tolist()
    )

    # 2. Criar a tabela pivotada
    tabela_concurso = df_filtrado.pivot_table(
        index="concurso",
        columns="etapa",
        values="oportunidade",
        aggfunc="count",
        fill_value=0
    )

    # 3. Aplicar a ordem correta (apenas colunas presentes)
    etapas_presentes = [etapa for etapa in ordem_etapas if etapa in tabela_concurso.columns]
    tabela_concurso = tabela_concurso[etapas_presentes]

    # 4. Renomear colunas
    tabela_concurso.columns = [f"{col} (Qtd)" for col in tabela_concurso.columns]

    # 5. Adicionar coluna total
    tabela_concurso["Total (Qtd)"] = tabela_concurso.sum(axis=1)

    tabela_concurso = tabela_concurso.sort_values("Total (Qtd)", ascending=False)

    st.dataframe(tabela_concurso, use_container_width=True)


    st.subheader("Principais Concursos por Oportunidades")

    # Define quantos concursos queremos mostrar no "Top N"
    TOP_N = 15

    # Agrupa e conta os dados
    df_concursos = df_filtrado.groupby("concurso")['oportunidade'].count().sort_values(ascending=False)

    # Verifica se há mais concursos do que o nosso limite TOP_N
    if len(df_concursos) > TOP_N:
        df_top_n = df_concursos.head(TOP_N)
        outros_soma = df_concursos.tail(len(df_concursos) - TOP_N).sum()
        df_outros = pd.Series([outros_soma], index=["Outros"])
        df_para_grafico = pd.concat([df_top_n, df_outros])
    else:
        df_para_grafico = df_concursos

    # Cria o gráfico de barras com os dados tratados
    fig_top_n = px.bar(
        df_para_grafico,
        x=df_para_grafico.values,
        y=df_para_grafico.index,
        orientation='h',
        title=f"Top {TOP_N} Concursos com Mais Oportunidades",
        labels={'x': 'Quantidade de Oportunidades', 'y': 'Concurso'},
        text=df_para_grafico.values
    )

    ordem_categorias = df_para_grafico.index.tolist()

    # 2. Inverte a lista para que o gráfico fique em ordem crescente (menor em cima)
    ordem_categorias.reverse() # ou use ordem_categorias[::-1]

    # 3. Aplica essa ordem customizada ao eixo Y do gráfico
    fig_top_n.update_layout(
        yaxis={
            'categoryorder': 'array',
            'categoryarray': ordem_categorias
        }
    )

    fig_top_n.update_traces(textposition='outside', marker_color='#457B9D')

    st.plotly_chart(fig_top_n, use_container_width=True)

    # pizza origens
    df_unidade = df_filtrado.groupby("origem")["oportunidade"].count().reset_index()

    # Cria o gráfico de pizza
    fig = px.pie(
        df_unidade,
        names="origem",
        values="oportunidade",
        title="Oportunidades por Origem",
        labels={"origem": "Origem", "oportunidade": "Quantidade"},
        )
    fig.update_traces(textinfo='value+percent')
    st.plotly_chart(fig, use_container_width=True)

    # Concurso por origem
    st.subheader("Oportunidades por Concurso / Origens")

    tabela_concurso_origens = df_filtrado.pivot_table(
        index="concurso",
        columns="origem",
        values="oportunidade",
        aggfunc="count",
        fill_value=0
    )

    # 4. Renomear colunas
    tabela_concurso_origens.columns = [f"{col} (Qtd)" for col in tabela_concurso_origens.columns]

    # 5. Adicionar coluna total
    tabela_concurso_origens["Total (Qtd)"] = tabela_concurso_origens.sum(axis=1)

    tabela_concurso_origens = tabela_concurso_origens.sort_values("Total (Qtd)", ascending=False)

    st.dataframe(tabela_concurso_origens, use_container_width=True)

    # Gráfico de barras de donos da oportunidade
    st.subheader("Oportunidades por Dono")

    df_dono = df_filtrado.groupby(df_filtrado["dono"])["oportunidade"].count().reset_index()

    df_dono.columns = ["Dono", "Total"]

    df_dono = df_dono.sort_values(by="Total", ascending=False)

    oport_dono = px.bar(
        df_dono,
        x="Dono",
        y="Total",
        title="Oportunidades por Dono",
        labels={"quantidade": "Qtd. oportunidades", "unidade": "Unidade"},
        barmode="stack",
        text_auto=True,
    )
    st.plotly_chart(oport_dono, use_container_width=True)

    #Tabela de oportunidade por campanha e etapas
    st.subheader("Oportunidades por Campanhas / Etapas")
    # 1. Obter ordem das etapas da query (sem duplicar e mantendo a ordem)
    tabela_campanha_origens = df_filtrado.pivot_table(
        index="campanha",
        columns="origem",
        values="oportunidade",
        aggfunc="count",
        fill_value=0
    )

    # 4. Renomear colunas
    tabela_campanha_origens.columns = [f"{col} (Qtd)" for col in tabela_campanha_origens.columns]

    # 5. Adicionar coluna total
    tabela_campanha_origens["Total (Qtd)"] = tabela_campanha_origens.sum(axis=1)

    tabela_campanha_origens = tabela_campanha_origens.sort_values("Total (Qtd)", ascending=False)

    st.dataframe(tabela_campanha_origens, use_container_width=True)


    # ==============================================================================
    # NOVA ANÁLISE: DESEMPENHO DE CONCURSOS POR UNIDADE E MODALIDADE
    # ==============================================================================
    st.divider()
    st.subheader("Análise de Concursos por Unidade e Modalidade")

    # --- 1. IDENTIFICAR OS TOP 15 CONCURSOS do período já filtrado ---
    # Usamos o df_filtrado que já contém os filtros da sidebar (data, empresa, etc.)
    if not df_filtrado.empty:
        top_15_concursos_list = df_filtrado['concurso'].value_counts().nlargest(15).index.tolist()

        # --- 2. CRIAR O FILTRO INTERATIVO para o usuário ---
        st.markdown("Selecione os concursos para análise:")
        concursos_selecionados = st.multiselect(
            label="Escolha um ou mais dos Top 15 concursos do período:",
            options=top_15_concursos_list,
            # Por padrão, seleciona os 5 primeiros da lista
            default=top_15_concursos_list[:5], 
            label_visibility="collapsed"
        )

        if not concursos_selecionados:
            st.warning("Por favor, selecione pelo menos um concurso para gerar a análise.")
            st.stop()

        # --- 3. PREPARAR OS DADOS para o gráfico com base na seleção ---
        # Filtra o DataFrame para conter apenas os concursos que o usuário selecionou
        df_para_grafico = df_filtrado[df_filtrado['concurso'].isin(concursos_selecionados)]

        # Agrupa os dados para obter a contagem por concurso, unidade e modalidade
        df_grafico_final = df_para_grafico.groupby(['concurso', 'unidade']) \
                                        .agg(Quantidade=('oportunidade', 'count')).reset_index()

        # --- 4. CRIAR O GRÁFICO DE BARRAS FACETADO ---
        if not df_grafico_final.empty:
            # Ordena os concursos pelo total de oportunidades para um gráfico mais limpo
            ordem_concursos = df_grafico_final.groupby('concurso')['Quantidade'].sum().sort_values(ascending=True).index

            fig_concurso_detalhado = px.bar(
                df_grafico_final,
                y='concurso',
                x='Quantidade',
                orientation='h',
                text='Quantidade',
                # A "mágica" acontece aqui: cria um gráfico para cada unidade
                facet_row='unidade', 
                labels={'Quantidade': 'Nº de Oportunidades', 'concurso': 'Concurso', 'unidade': 'Unidade'},
                title='Oportunidades por Concurso e Unidade',
                category_orders={'concurso': ordem_concursos} # Aplica a ordenação
            )
            
            # Aprimora o layout para remover os títulos repetidos do eixo Y e ajustar a altura
            fig_concurso_detalhado.update_yaxes(title_text=None) # Remove o título "concurso" de cada sub-gráfico
            fig_concurso_detalhado.update_layout(height=max(600, len(df_grafico_final['unidade'].unique()) * 200)) # Ajusta a altura dinamicamente

            st.plotly_chart(fig_concurso_detalhado, use_container_width=True)
        else:
            st.info("Não há dados para os concursos selecionados.")

    else:
        st.warning("Não há dados no período selecionado para gerar esta análise.")


    # ==============================================================================
    # ANÁLISE DINÂMICA COM FILTROS DE DRILL-DOWN
    # ==============================================================================
    st.divider()
    st.header("🔎 Análise Detalhada com Filtros Dinâmicos")
    st.info("Use os filtros abaixo para explorar os dados. Todos os gráficos e tabelas nesta seção serão atualizados com a sua seleção.")

    # --- 1. FILTROS DE DRILL-DOWN ---
    # Estes filtros agora controlam todo o conteúdo abaixo deles.
    drill_cols = st.columns(3)

    # Prepara as listas de opções para os filtros, incluindo uma opção "Todos"
    concursos_list = ["Todos"] + sorted(df_filtrado['concurso'].dropna().unique().tolist())
    etapas_list = ["Todas"] + sorted(df_filtrado['etapa'].dropna().unique().tolist())
    unidades_list = ["Todas"] + sorted(df_filtrado['unidade'].dropna().unique().tolist())

    # Cria os widgets de filtro
    concurso_selecionado_drill = drill_cols[0].selectbox("Filtrar por Concurso:", concursos_list)
    etapa_selecionada_drill = drill_cols[1].selectbox("Filtrar por Etapa:", etapas_list)
    unidade_selecionada_drill = drill_cols[2].selectbox("Filtrar por Unidade:", unidades_list)

    # --- 2. APLICAÇÃO DOS FILTROS ---
    # Começamos com os dados já filtrados pela sidebar
    df_dinamico = df_filtrado.copy()

    if concurso_selecionado_drill != "Todos":
        df_dinamico = df_dinamico[df_dinamico['concurso'] == concurso_selecionado_drill]
    if etapa_selecionada_drill != "Todas":
        df_dinamico = df_dinamico[df_dinamico['etapa'] == etapa_selecionada_drill]
    if unidade_selecionada_drill != "Todas":
        df_dinamico = df_dinamico[df_dinamico['unidade'] == unidade_selecionada_drill]

    # --- 3. EXIBIÇÃO DOS GRÁFICOS E TABELAS (AGORA REATIVOS) ---
    if not df_dinamico.empty:
        col1, col2 = st.columns(2)
        with col1:
            # Gráfico de Barras de Concursos (agora reativo)
            df_concursos = df_dinamico['concurso'].value_counts().nlargest(20).reset_index()
            df_concursos.columns = ['Concurso', 'Quantidade']
            fig_bar = px.bar(
                df_concursos.sort_values('Quantidade'),
                x='Quantidade', 
                y='Concurso', 
                orientation='h',
                text='Quantidade',
                title='Oportunidades por Concurso', 
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        with col2:
            # Gráfico de Pizza de Etapas (agora reativo)
            df_etapa = df_dinamico.groupby("etapa")['oportunidade'].count().reset_index()
            fig_pie = px.pie(
                df_etapa, names="etapa", values="oportunidade",
                title="Distribuição por Etapa",
            )
            fig_pie.update_traces(textinfo='value')
            st.plotly_chart(fig_pie, use_container_width=True)

        # Tabela de Unidades
        tabela_unidades = df_dinamico.groupby("unidade")["oportunidade"].count().reset_index()
        st.dataframe(tabela_unidades, use_container_width=True)

    else:
        st.warning("Nenhum dado encontrado para a combinação de filtros selecionada.")

    # ==============================================================================
    # SEÇÃO DE VALIDAÇÃO - COMPARAÇÃO ENTRE CAMPOS ORIGINAIS E TRATADOS
    # ==============================================================================
    # st.divider()
    # st.header("🔍 Validação das Regras de Negócio")
    # st.info("Esta seção mostra a comparação entre os dados originais e os dados tratados pelas regras de negócio.")

    # # Criar abas para diferentes análises
    # tab1, tab2, tab3 = st.tabs(["📊 Resumo das Transformações", "📋 Casos Específicos", "🔎 Análise Detalhada"])

    # with tab1:
    #     col1, col2 = st.columns(2)
        
    #     with col1:
    #         st.subheader("Unidades - Antes vs Depois")
    #         # Contagem de valores nulos/vazios antes do tratamento
    #         unidades_originais_nulas = df_filtrado['unidade'].isna().sum() + (df_filtrado['unidade'] == '').sum()
    #         unidades_tratadas_nulas = df_filtrado['unidade_tratada'].isna().sum() + (df_filtrado['unidade_tratada'] == '').sum()
            
    #         st.metric("Unidades nulas/vazias (Original)", unidades_originais_nulas)
    #         st.metric("Unidades nulas/vazias (Tratada)", unidades_tratadas_nulas)
    #         st.metric("Registros corrigidos", unidades_originais_nulas - unidades_tratadas_nulas)
            
    #         # Distribuição das unidades tratadas
    #         unidades_dist = df_filtrado['unidade_tratada'].value_counts()
    #         fig_unidades = px.bar(
    #             x=unidades_dist.values,
    #             y=unidades_dist.index,
    #             orientation='h',
    #             title="Distribuição das Unidades (Após Tratamento)",
    #             labels={'x': 'Quantidade', 'y': 'Unidade'}
    #         )
    #         st.plotly_chart(fig_unidades, use_container_width=True)

    #     with col2:
    #         st.subheader("Modalidades - Antes vs Depois")
    #         # Contagem de valores nulos/vazios antes do tratamento
    #         modalidades_originais_nulas = df_filtrado['modalidade'].isna().sum() + (df_filtrado['modalidade'] == '').sum()
    #         modalidades_tratadas_nulas = df_filtrado['modalidade_tratada'].isna().sum() + (df_filtrado['modalidade_tratada'] == '').sum()
            
    #         st.metric("Modalidades nulas/vazias (Original)", modalidades_originais_nulas)
    #         st.metric("Modalidades nulas/vazias (Tratada)", modalidades_tratadas_nulas)
    #         st.metric("Registros corrigidos", modalidades_originais_nulas - modalidades_tratadas_nulas)
            
    #         # Distribuição das modalidades tratadas
    #         modalidades_dist = df_filtrado['modalidade_tratada'].value_counts()
    #         fig_modalidades = px.bar(
    #             x=modalidades_dist.values,
    #             y=modalidades_dist.index,
    #             orientation='h',
    #             title="Distribuição das Modalidades (Após Tratamento)",
    #             labels={'x': 'Quantidade', 'y': 'Modalidade'}
    #         )
    #         st.plotly_chart(fig_modalidades, use_container_width=True)

    # with tab2:
    #     st.subheader("Exemplos de Transformações Aplicadas")
        
    #     # Filtrar apenas registros onde houve transformação para mostrar exemplos
    #     transformacoes_unidade = df_filtrado[
    #         (df_filtrado['unidade'].isna() | (df_filtrado['unidade'] == '')) & 
    #         (df_filtrado['unidade_tratada'].notna() & (df_filtrado['unidade_tratada'] != ''))
    #     ][['oportunidade', 'unidade', 'unidade_tratada', 'modalidade', 'modalidade_tratada']].head(20)
        
    #     transformacoes_modalidade = df_filtrado[
    #         (df_filtrado['modalidade'].isna() | (df_filtrado['modalidade'] == '')) & 
    #         (df_filtrado['modalidade_tratada'].notna() & (df_filtrado['modalidade_tratada'] != ''))
    #     ][['oportunidade', 'unidade', 'unidade_tratada', 'modalidade', 'modalidade_tratada']].head(20)
        
    #     if not transformacoes_unidade.empty:
    #         st.markdown("**Transformações de Unidade:**")
    #         st.dataframe(transformacoes_unidade, use_container_width=True)
        
    #     if not transformacoes_modalidade.empty:
    #         st.markdown("**Transformações de Modalidade:**")
    #         st.dataframe(transformacoes_modalidade, use_container_width=True)
            
    #     if transformacoes_unidade.empty and transformacoes_modalidade.empty:
    #         st.info("Não foram encontradas transformações no período/filtros selecionados.")

    # with tab3:
    #     st.subheader("Análise Completa de Transformações")
        
    #     # Criar tabela comparativa completa
    #     colunas_comparacao = ['oportunidade', 'concurso', 'unidade', 'unidade_tratada', 'modalidade', 'modalidade_tratada']
    #     df_comparacao = df_filtrado[colunas_comparacao].copy()
        
    #     # Adicionar colunas indicando se houve transformação
    #     df_comparacao['unidade_transformada'] = (
    #         (df_comparacao['unidade'].isna() | (df_comparacao['unidade'] == '')) & 
    #         (df_comparacao['unidade_tratada'].notna() & (df_comparacao['unidade_tratada'] != ''))
    #     )
        
    #     df_comparacao['modalidade_transformada'] = (
    #         (df_comparacao['modalidade'].isna() | (df_comparacao['modalidade'] == '')) & 
    #         (df_comparacao['modalidade_tratada'].notna() & (df_comparacao['modalidade_tratada'] != ''))
    #     )
        
    #     # Filtros para a análise detalhada
    #     col_filtro1, col_filtro2 = st.columns(2)
        
    #     with col_filtro1:
    #         mostrar_apenas_transformados = st.checkbox("Mostrar apenas registros transformados", value=True)
            
    #     with col_filtro2:
    #         concurso_filtro = st.selectbox(
    #             "Filtrar por concurso:",
    #             ["Todos"] + sorted(df_comparacao['concurso'].dropna().unique().tolist()),
    #             key="concurso_validacao"
    #         )
        
    #     # Aplicar filtros
    #     df_exibir = df_comparacao.copy()
        
    #     if mostrar_apenas_transformados:
    #         df_exibir = df_exibir[
    #             df_exibir['unidade_transformada'] | 
    #             df_exibir['modalidade_transformada']
    #         ]
            
    #     if concurso_filtro != "Todos":
    #         df_exibir = df_exibir[df_exibir['concurso'] == concurso_filtro]
        
    #     # Exibir tabela
    #     if not df_exibir.empty:
    #         st.dataframe(df_exibir, use_container_width=True)
            
    #         # Opção de download
    #         buffer = io.BytesIO()
    #         with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
    #             df_exibir.to_excel(writer, index=False, sheet_name='Validacao_Transformacoes')
    #         buffer.seek(0)
            
    #         st.download_button(
    #             label="📥 Baixar Análise Completa",
    #             data=buffer,
    #             file_name="validacao_transformacoes_oportunidades.xlsx",
    #             mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    #         )
    #     else:
    #         st.info("Nenhum registro encontrado com os filtros aplicados.")
