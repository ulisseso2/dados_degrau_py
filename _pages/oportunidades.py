import sys
import os
import io
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime
from utils.sql_loader import carregar_dados  # agora usamos a função com cache
import plotly.graph_objects as go

def run_page():

    TIMEZONE = 'America/Sao_Paulo'

    st.title("🎯 Dashboard Oportunidades")

    # ✅ Carrega os dados com cache (1h por padrão, pode ajustar no sql_loader.py)
    df = carregar_dados("consultas/oportunidades/oportunidades.sql")

    # Pré-filtros
    df["criacao"] = pd.to_datetime(df["criacao"]).dt.tz_localize(TIMEZONE, ambiguous='infer')

    # Filtro: empresa
    empresas = df["empresa"].dropna().unique().tolist()
    empresa_selecionada = st.sidebar.multiselect("Selecione as empresas:", empresas, default=["Degrau"])
    df_filtrado_empresa = df[df["empresa"].isin(empresa_selecionada)]

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
    with st.expander("Filtros Avançados: Unidades, Etapas, Modalidade e H. Ligar"):
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            unidades = sorted(df_filtrado_empresa["unidade"].dropna().unique())
            unidade_selecionada = st.multiselect("Selecione a unidade:", unidades, default=unidades)

        with col2:
            etapas = sorted(df_filtrado_empresa["etapa"].dropna().unique()) # Ordenado
            etapa_selecionada = st.multiselect("Selecione a etapa:", etapas, default=etapas)
        
        with col3:
            modalidades = sorted(df_filtrado_empresa["modalidade"].dropna().unique()) # Ordenado
            modalidade_selecionada = st.multiselect("Selecione a modalidade:", modalidades, default=modalidades)

        with col4:
            hs_ligar = sorted(df_filtrado_empresa["h_ligar"].dropna().unique()) # Ordenado
            h_ligar_selecionada = st.multiselect("Selecione a Hora", hs_ligar, default=hs_ligar)

    # 2. Inicia com o DataFrame completo
    df_filtrado = df

    # 3. Aplica os filtros sequencialmente
    if empresa_selecionada:
        df_filtrado = df_filtrado[df_filtrado["empresa"].isin(empresa_selecionada)]

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

    st.metric("Total de Oportunidades", df_filtrado.shape[0])

    df_diario = df_filtrado.groupby(df_filtrado["criacao"].dt.date)["oportunidade"].count().reset_index()

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
    # --- FIM DA MUDANÇA ---

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