import sys
import os
import io
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime
from utils.sql_loader import carregar_dados  # agora usamos a função com cache


def run_page():
    st.title("📉 Dashboard de Cancelamentos por Unidade")
    TIMEZONE = 'America/Sao_Paulo'

    # ✅ Carrega os dados com cache (1h por padrão, pode ajustar no sql_loader.py)
    df = carregar_dados("consultas/orders/orders.sql")

    # Definição de Cores
    cores_padronizadas = {
        'Live': '#FF0000',        # Vermelho
        'Passaporte': '#1F77B4',  # Azul padrão do Plotly
        'Presencial': '#2CA02C',  # Verde padrão do Plotly
        # Adicione outras categorias conforme necessário
    }

    # Filtro: empresa
    empresas = df["empresa"].dropna().unique().tolist()
    empresa_selecionada = st.sidebar.multiselect("Selecione as empresas:", empresas, default=["Degrau"])
    df_filtrado_empresa = df[df["empresa"].isin(empresa_selecionada)]


    df["data_referencia"] = pd.to_datetime(df["data_referencia"]).dt.tz_localize(TIMEZONE, ambiguous='infer')

    # Filtro: data (padrão: Hoje)
   
    hoje_aware = pd.Timestamp.now(tz=TIMEZONE).date() 
    periodo = st.sidebar.date_input("Data Referência", [hoje_aware, hoje_aware])


    try:
        data_inicio_aware = pd.Timestamp(periodo[0], tz=TIMEZONE)
        data_fim_aware = pd.Timestamp(periodo[1], tz=TIMEZONE) + pd.Timedelta(days=1)
    except IndexError:
        # Se o usuário limpar o campo de data, mostramos o aviso
        st.warning("👈 Por favor, selecione um período de datas na barra lateral para exibir a análise.")
        st.stop()

    st.sidebar.subheader("Filtro de Categoria")
    categorias_disponiveis = df_filtrado_empresa['categoria'].str.split(', ').explode().str.strip().dropna().unique().tolist()

    categoria_selecionada = st.sidebar.multiselect(
        "Selecione a(s) categoria(s):",
        options=sorted(categorias_disponiveis),
        default=["Curso Presencial", "Curso Live", "Passaporte"]
    )

    st.sidebar.subheader("Tipos de Cancelamento")
    tipos_disponiveis = df_filtrado_empresa['tipo_cancelamento'].dropna().unique().tolist()

    opcoes_ordenadas = sorted(tipos_disponiveis)

    tipo_selecionado = st.sidebar.multiselect(
        "Selecione o(s) tipo(s) de cancelamento:",
        options=opcoes_ordenadas,
        default=opcoes_ordenadas
    )

    # Filtros adicionais recolhidos
    # O filtro de Unidades agora fica dentro de seu próprio expander
    with st.sidebar.expander("Filtrar por Unidade"):
        unidades_list = sorted(df_filtrado_empresa["unidade"].dropna().unique())
        unidade_selecionada = st.multiselect(
            "Selecione a(s) unidade(s):", 
            unidades_list, 
            default=unidades_list
        )

    def formatar_reais(valor):
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    


    df_filtrado = df[
        (df["empresa"].isin(empresa_selecionada)) &
        (df["unidade"].isin(unidade_selecionada)) &
        (df['categoria'].str.contains('|'.join(categoria_selecionada), na=False)) &
        (df['tipo_cancelamento'].isin(tipo_selecionado)) &
        (df["data_referencia"] >= data_inicio_aware) &
        (df["data_referencia"] < data_fim_aware) &
        (df["status_id"].isin([3, 15])) &
        (~df["metodo_pagamento"].isin([5, 8])) & 
        (df["total_pedido"] != 0)
    ]

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total de Cancelados", df_filtrado.shape[0])
    with col2:
        st.metric("Total de Cancelados", formatar_reais(df_filtrado["estorno_cancelamento"].sum()))


    tabela_cancelados = (
        df_filtrado.groupby("unidade")
        .agg(
            quantidade=pd.NamedAgg(column="ordem_id", aggfunc="count"),
            total_estornado=pd.NamedAgg(column="estorno_cancelamento", aggfunc="sum")
        )
        .reset_index()
        .sort_values("total_estornado", ascending=False)
    )
    total_geral_c = pd.DataFrame({
        "unidade": ["TOTAL GERAL"],
        "quantidade": [tabela_cancelados["quantidade"].sum()],
        "total_estornado": [tabela_cancelados["total_estornado"].sum()]
    })
    tabela_com_total_c = pd.concat([tabela_cancelados, total_geral_c], ignore_index=True)
    tabela_cancelados["total_estornado"] = tabela_cancelados["total_estornado"].apply(formatar_reais)
    tabela_com_total_c["total_estornado"] = tabela_com_total_c["total_estornado"].apply(formatar_reais)
    st.subheader("Estornos por Unidade")
    st.dataframe(tabela_com_total_c, use_container_width=True)

    # Gráficos
    st.subheader("Gráfico de Estorno por Unidade e Categoria")
    grafico = (
        df_filtrado.groupby(["unidade", "categoria"])
        .size()
        .reset_index(name="quantidade")
    )
    fig = px.bar(
        grafico,
        x="unidade",
        y="quantidade",
        color="categoria",
        title="Estornos por Unidade (Detalhado por Categoria)",
        labels={"quantidade": "Qtd. Estornos", "unidade": "Unidade"},
        color_discrete_map=cores_padronizadas,
        barmode="stack",
        text_auto=True,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Gráfico de estornos por categoria e unidade
    st.subheader("Estornos por Categoria e Unidade")
    df_filtrado['estorno_cancelamento'] = pd.to_numeric(df_filtrado['estorno_cancelamento'], errors='coerce')

    grafico2 = (
        df_filtrado.groupby(["categoria", "unidade"])
        .agg({'estorno_cancelamento': 'sum'})  # Forma explícita de agregação
        .reset_index()
    )
    grafico2['valor_numerico'] = grafico2['estorno_cancelamento']
    grafico2["estorno_formatado"] = grafico2["valor_numerico"].apply(formatar_reais)
    max_value = float(grafico2["valor_numerico"].max())

    fig2 = px.bar(
        grafico2,
        y="valor_numerico",
        x="unidade",
        color="categoria",
        title="Cancelamento por Unidade (Detalhado por categoria)",
        labels={"valor_numerico": "Valor Estornado", "unidade": "Unidade"},
        orientation="v",
        barmode="stack",
        color_discrete_map=cores_padronizadas,
        text="estorno_formatado",  # Use o texto formatado aqui
        range_y=[0, max_value * 1.1]  # Agora pode multiplicar pois max_value é float
    )

    fig2.update_traces(
        textposition='outside',
        textfont_size=14,  # Aumenta o tamanho da fonte dos textos
        hovertemplate="<b>%{y}</b><br>Categoria: %{customdata[0]}<br>Valor: %{x:,.2f}<extra></extra>",
        customdata=grafico2[['categoria']]
    )

    st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    ## Gráfico de estornos por categoria
    st.subheader("Estornos por Categoria")
    df_filtrado['estorno_cancelamento'] = pd.to_numeric(df_filtrado['estorno_cancelamento'], errors='coerce')

    grafico3 = (
        df_filtrado.groupby("categoria")
        .agg({'estorno_cancelamento': 'sum'})  # Forma explícita de agregação
        .reset_index()
    )
    grafico3['valor_numerico'] = grafico3['estorno_cancelamento']

    grafico3["estorno_formatado"] = grafico3["valor_numerico"].apply(formatar_reais)

    max_value = float(grafico3["valor_numerico"].max())

    fig3 = px.bar(
        grafico3,
        x="valor_numerico",
        y="categoria",
        title="Cancelamento por Categoria",
        labels={"valor_numerico": "Valor Estornado", "categoria": "Categoria"},
        orientation="h",
        barmode="stack",
        text="estorno_formatado",  # Use o texto formatado aqui
        color_discrete_map=cores_padronizadas,
        range_x=[0, max_value * 1.1]  # Agora pode multiplicar pois max_value é float
    )

    fig3.update_traces(
        textposition='outside',
        textfont_size=14,  # Aumenta o tamanho da fonte dos textos
        hovertemplate="<b>%{y}</b><br>Categoria: %{customdata[0]}<br>Valor: %{x:,.2f}<extra></extra>",
        customdata=grafico3[['categoria']]
    )

    st.plotly_chart(fig3, use_container_width=True)

    # ==============================================================================
    # GRÁFICO DE ESTORNOS POR CURSO VENDA E TIPO DE CANCELAMENTO
    # ==============================================================================
    st.divider()
    st.subheader("Estornos por Curso Venda e Tipo de Cancelamento")

    # Garante que a coluna de estorno é numérica, tratando possíveis erros
    df_filtrado['estorno_cancelamento'] = pd.to_numeric(df_filtrado['estorno_cancelamento'], errors='coerce')

    # 1. CORREÇÃO: Agrupamos por 'curso_venda' E 'tipo_cancelamento'
    grafico_estornos = (
        df_filtrado.groupby(["curso_venda", "tipo_cancelamento"])
        .agg(Valor_Estornado=('estorno_cancelamento', 'sum'))
        .reset_index()
    )

    # Remove valores zerados ou nulos para um gráfico mais limpo
    grafico_estornos = grafico_estornos[grafico_estornos['Valor_Estornado'] > 0]

    if not grafico_estornos.empty:
        # Ordena os cursos pelo valor total de estorno para um gráfico mais organizado
        ordem_cursos = grafico_estornos.groupby('curso_venda')['Valor_Estornado'].sum().sort_values(ascending=True).index

        # 2. CRIA O GRÁFICO com os dados já preparados
        fig_estornos = px.bar(
            grafico_estornos,
            x="Valor_Estornado",
            y="curso_venda",
            color="tipo_cancelamento", # Agora esta coluna existe nos dados!
            title="Valor de Cancelamento por Curso e Tipo",
            labels={"Valor_Estornado": "Valor Total Estornado (R$)", "curso_venda": "Curso Venda"},
            orientation='h',
            barmode='stack', # Empilha as barras pela dimensão de cor
            text_auto='.2s', # Deixa o Plotly formatar o texto dos segmentos de forma inteligente
            category_orders={'curso_venda': ordem_cursos} # Aplica a ordenação
        )

        # Melhora a aparência do gráfico
        fig_estornos.update_layout(
            yaxis_title=None, 
            height=600,
            legend_title_text='Tipo de Cancelamento'
        )
        
        st.plotly_chart(fig_estornos, use_container_width=True)
    else:
        st.info("Não há dados de estorno para os filtros selecionados.")

    # Tabela de Cancelamentos por Unidade e Categoria
    # Agrupa total vendido por categoria
    valor_pivot = df_filtrado.pivot_table(
        index="unidade",
        columns="categoria",
        values="estorno_cancelamento",
        aggfunc="sum",
        fill_value=0
    )

    # Agrupa quantidade por categoria
    qtd_pivot = df_filtrado.pivot_table(
        index="unidade",
        columns="categoria",
        values="ordem_id",
        aggfunc="count",
        fill_value=0
    )

    # Formata valores em reais (depois de fazer a junção)
    valor_formatado = valor_pivot.copy()
    for col in valor_formatado.columns:
        valor_formatado[col] = valor_formatado[col].apply(formatar_reais)

    # Renomeia colunas com sufixo
    valor_formatado.columns = [f"{col} (Valor)" for col in valor_formatado.columns]
    qtd_pivot.columns = [f"{col} (Qtd)" for col in qtd_pivot.columns]

    # Junta horizontalmente (eixo=1)
    tabela_completa = pd.concat([valor_formatado, qtd_pivot], axis=1).reset_index()

    # Mostra a tabela final
    st.subheader("Cancelamento por Unidade e Categoria (Valor e Quantidade)")
    st.dataframe(tabela_completa, use_container_width=True)


    st.divider()

    st.subheader("Cancelamento por Tipo")

    # 1. Prepara os dados: agrupa por situação e soma o valor
    df_cancelados = df_filtrado.groupby('tipo_cancelamento')['estorno_cancelamento'].sum().reset_index()
    # 3. Cria o gráfico de pizza
    if not df_cancelados.empty:
        fig_pizza_cancelados = px.pie(
            df_cancelados,
            names='tipo_cancelamento',
            values='estorno_cancelamento',
            title='Valor de Cancelamentos por Tipo',
            color='tipo_cancelamento',
        )
        
        # Atualiza para mostrar o valor (R$) e o percentual
        fig_pizza_cancelados.update_traces(
            textinfo='percent+value',
            texttemplate='%{percent:,.1%} <br>R$ %{value:,.2f}' # Formata o texto
        )

        st.plotly_chart(fig_pizza_cancelados, use_container_width=True)
    else:
        st.info("Não há dados de cancelamento para exibir com os filtros atuais.")

    # Tabela detalhada de Cancelamento
    tabela2 = df_filtrado[[
        "unidade","turma","nome_cliente", "email_cliente", "status", "curso_venda", "total_pedido", "data_pagamento", "solicitacao_cancelamento", "estorno_cancelamento", "tipo_cancelamento" 
    ]]
    tabela_alunos = tabela2.copy()
    tabela_alunos["estorno_cancelamento"] = tabela_alunos["estorno_cancelamento"].apply(formatar_reais)
    tabela_alunos["data_pagamento"] = pd.to_datetime(tabela_alunos["data_pagamento"]).dt.strftime('%d/%m/%Y')
    tabela_alunos["solicitacao_cancelamento"] = pd.to_datetime(tabela_alunos["solicitacao_cancelamento"], format='%d/%m/%Y').dt.strftime('%d/%m/%Y')

    st.subheader("Lista de Cancelamentos Detalhada")
    st.dataframe(tabela_alunos, use_container_width=True)

    # Exportar como Excel
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        tabela2.to_excel(writer, index=False, sheet_name='Cancelamentos Detalhados')

    # Resetar o ponteiro do buffer para o início
    buffer.seek(0)

    st.download_button(
        label="📥 Lista de Cancelamentos",
        data=buffer,
        file_name="cancelamentos_detalhados.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


