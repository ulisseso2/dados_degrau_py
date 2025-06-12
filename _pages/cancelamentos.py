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
    st.title("📉 Dashboard de Matrículas por Unidade")

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

    # Filtro: data (padrão: Hoje)
    hoje = datetime.today().date()
    periodo = st.sidebar.date_input("Data Pagamento", [hoje, hoje])

    # Filtros adicionais recolhidos
    with st.expander("Filtros Avançados: Unidades e Categoria"):
        col1, col2 = st.columns(2)

        with col1:
            unidades = df_filtrado_empresa["unidade"].dropna().unique().tolist()
            unidade_selecionada = st.multiselect("Selecione a unidade:", unidades, default=unidades)

        with col2:
            categorias = df_filtrado_empresa["categoria"].dropna().unique().tolist()
            categoria_selecionada = st.multiselect("Selecione a categoria:", categorias, default=categorias)

    # Aplica filtros finais
    df_filtrado = df[
        (df["empresa"].isin(empresa_selecionada)) &
        (df["unidade"].isin(unidade_selecionada)) &
        (df["categoria"].isin(categoria_selecionada)) &
        (df["data_referencia"] >= pd.to_datetime(periodo[0])) &
        (df["data_referencia"] <= pd.to_datetime(periodo[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))
    ]
    def formatar_reais(valor):
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    # Pré-filtros Pago > Não grátis > Apenas Passaporte, Live e Presencial e Data de PAGAMENTO
    df_pagos = df_filtrado.copy()
    df_pagos = df_pagos[df_pagos["status_id"] == 2]
    df_pagos = df_pagos[df_pagos["total_pedido"] != 0]
    df_pagos = df_pagos[df_pagos["categoria"].isin(["Passaporte", "Curso Live", "Curso Presencial"])]
    df_pagos["data_referencia"] = pd.to_datetime(df_pagos["data_referencia"])

    df_cancelados = df_filtrado.copy()
    df_cancelados = df_cancelados[df_filtrado["status_id"].isin([3, 15])]
    df_cancelados = df_cancelados[df_cancelados["total_pedido"] != 0]
    df_cancelados = df_cancelados[df_cancelados["categoria"].isin(["Passaporte", "Curso Live", "Curso Presencial"])]
    df_cancelados["data_referencia"] = pd.to_datetime(df_pagos["data_referencia"])

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total de Cancelados", df_cancelados.shape[0])
    with col2:
        st.metric("Total de Cancelados", formatar_reais(df_cancelados["estorno_cancelamento"].sum()))


    tabela_cancelados = (
        df_cancelados.groupby("unidade")
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
        df_cancelados.groupby(["unidade", "categoria"])
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
    df_cancelados['estorno_cancelamento'] = pd.to_numeric(df_cancelados['estorno_cancelamento'], errors='coerce')

    grafico2 = (
        df_cancelados.groupby(["categoria", "unidade"])
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
        textposition='inside',
        hovertemplate="<b>%{y}</b><br>Categoria: %{customdata[0]}<br>Valor: %{x:,.2f}<extra></extra>",
        customdata=grafico2[['categoria']]
    )

    st.plotly_chart(fig2, use_container_width=True)

    ## Gráfico de estornos por categoria
    st.subheader("Estornos por Categoria")
    df_cancelados['estorno_cancelamento'] = pd.to_numeric(df_cancelados['estorno_cancelamento'], errors='coerce')

    grafico3 = (
        df_cancelados.groupby("categoria")
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
        textposition='inside',
        hovertemplate="<b>%{y}</b><br>Categoria: %{customdata[0]}<br>Valor: %{x:,.2f}<extra></extra>",
        customdata=grafico3[['categoria']]
    )

    st.plotly_chart(fig3, use_container_width=True)

    # Tabela de Cencelamentos por Unidade e Categoria
    # Agrupa total vendido por categoria
    valor_pivot = df_cancelados.pivot_table(
        index="unidade",
        columns="categoria",
        values="estorno_cancelamento",
        aggfunc="sum",
        fill_value=0
    )

    # Agrupa quantidade por categoria
    qtd_pivot = df_cancelados.pivot_table(
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

    # Tabela detalhada de Cancelamento
    tabela2 = df_cancelados[[
        "solicitacao_cancelamento","data_pagamento","nome_cliente", "email_cliente", "celular_cliente", "curso_venda", "unidade", "estorno_cancelamento"
    ]]
    tabela_alunos = tabela2.copy()
    tabela_alunos["estorno_cancelamento"] = tabela_alunos["estorno_cancelamento"].apply(formatar_reais)

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


