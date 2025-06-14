import sys
import os
import io
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime
from utils.sql_loader import carregar_dados

def run_page():
    st.title("🎓 Dashboard de Matrículas por Unidade")
    TIMEZONE = 'America/Sao_Paulo'

    # ✅ Carrega os dados com cache (1h por padrão, pode ajustar no sql_loader.py)
    df = carregar_dados("consultas/orders/orders.sql")

    # Filtro: empresa
    empresas = df["empresa"].dropna().unique().tolist()
    empresa_selecionada = st.sidebar.multiselect("Selecione as empresas:", empresas, default=["Degrau"])
    df_filtrado_empresa = df[df["empresa"].isin(empresa_selecionada)]

    df["data_referencia"] = pd.to_datetime(df["data_referencia"]).dt.tz_localize(TIMEZONE, ambiguous='infer')

    # Filtro: data (padrão: Hoje)
    hoje_aware = pd.Timestamp.now(tz=TIMEZONE).date() 
    periodo = st.sidebar.date_input("Data Pagamento", [hoje_aware, hoje_aware])

    try:
        data_inicio_aware = pd.Timestamp(periodo[0], tz=TIMEZONE)
        data_fim_aware = pd.Timestamp(periodo[1], tz=TIMEZONE) + pd.Timedelta(days=1)
    except IndexError:
        # Se o usuário limpar o campo de data, mostramos o aviso
        st.warning("👈 Por favor, selecione um período de datas na barra lateral para exibir a análise.")
        st.stop()

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
        (df['categoria'].str.contains('|'.join(categoria_selecionada), na=False)) &
        (df["data_referencia"] >= data_inicio_aware) &
        (df["data_referencia"] < data_fim_aware)
    ]

    # Função para formatar valores em reais
    def formatar_reais(valor):
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    # Pré-filtros Pago > Não grátis > Apenas Passaporte, Live e Presencial e Data de PAGAMENTO
    df_pagos = df_filtrado.copy()
    df_pagos = df_pagos[df_pagos["status_id"] == 2]
    df_pagos = df_pagos[df_pagos["total_pedido"] != 0]
    df_pagos = df_pagos[df_pagos["categoria"].isin(["Passaporte", "Curso Live", "Curso Presencial"])]
 
    df_cancelados = df_filtrado.copy()
    df_cancelados = df_cancelados[df_filtrado["status_id"].isin([3, 15])]
    df_cancelados = df_cancelados[df_cancelados["total_pedido"] != 0]
    df_cancelados = df_cancelados[df_cancelados["categoria"].isin(["Passaporte", "Curso Live", "Curso Presencial"])]

    # Tabela de resumo
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total de Pedidos", df_pagos.shape[0])
    with col2:
        st.metric("Total Vendido", formatar_reais(df_pagos["total_pedido"].sum()))

    # Tabela por unidade
    tabela = (
        df_pagos.groupby("unidade")
        .agg(
            quantidade=pd.NamedAgg(column="ordem_id", aggfunc="count"),
            total_vendido=pd.NamedAgg(column="total_pedido", aggfunc="sum")
        )
        .reset_index()
        .sort_values("total_vendido", ascending=False)
    )
    tabela["ticket_medio"] = tabela["total_vendido"] / tabela["quantidade"]
    tabela["ticket_medio"] = tabela["ticket_medio"].apply(formatar_reais)
    tabela["total_vendido"] = tabela["total_vendido"].apply(formatar_reais)

    st.subheader("Vendas por Unidade")
    st.dataframe(tabela, use_container_width=True)

    # Gráfico de pedidos por unidade e categoria
    st.subheader("Gráfico de Pedidos por Unidade e Categoria")
    grafico = (
        df_pagos.groupby(["unidade", "categoria"])
        .size()
        .reset_index(name="quantidade")
    )
    fig = px.bar(
        grafico,
        x="unidade",
        y="quantidade",
        color="categoria",
        title="Pedidos por Unidade (Detalhado por Categoria)",
        labels={"quantidade": "Qtd. Pedidos", "unidade": "Unidade"},
        barmode="group",
        text_auto=True,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Gráfico de pedidos por curso venda quantitativa
    st.subheader("Pedidos por Curso Venda")
    grafico2 = (
        df_pagos.groupby(["curso_venda"])
        .agg({'total_pedido': 'sum'})
        .reset_index()
    )

    grafico2['valor_numerico'] = grafico2['total_pedido']
    grafico2["total_formatado"] = grafico2["valor_numerico"].apply(formatar_reais)
    max_value = float(grafico2["valor_numerico"].max())

    fig2 = px.bar(
        grafico2,
        x="total_pedido",
        y="curso_venda",
        title="Pedidos por Curso (Detalhado por Unidade)",
        labels={"total_pedido": "Qtd. Pedidos", "curso_venda": "Curso Venda"},
        orientation="h",
        barmode="group",
        text="total_formatado",
        range_x=[0, max_value * 1.1]
    )
    st.plotly_chart(fig2, use_container_width=True)

    # Tabela de venda por curso venda
    # Agrupa total vendido por categoria
    valor_pivot = df_pagos.pivot_table(
        index="curso_venda",
        columns="categoria",
        values="total_pedido",
        aggfunc="sum",
        fill_value=0
    )

    # Agrupa quantidade por categoria
    qtd_pivot = df_pagos.pivot_table(
        index="curso_venda",
        columns="categoria",
        values="ordem_id",
        aggfunc="count",
        fill_value=0
    )

    # Formata valores em reais (depois de fazer a junção)
    valor_formatado = valor_pivot.copy()
    for col in valor_formatado.columns:
        valor_formatado[col] = valor_formatado[col].apply(formatar_reais)

    valor_formatado.columns = [f"{col} (Valor)" for col in valor_formatado.columns]
    qtd_pivot.columns = [f"{col} (Qtd)" for col in qtd_pivot.columns]

    # Junta horizontalmente
    tabela_completa = pd.concat([valor_formatado, qtd_pivot], axis=1)

    # Adiciona total geral de valor (convertendo novamente para float)
    valor_total = valor_pivot.sum(axis=1)
    tabela_completa["Total Geral (Valor)"] = valor_total.apply(formatar_reais)

    # Adiciona total geral de quantidade
    qtd_total = qtd_pivot.sum(axis=1)
    tabela_completa["Total Geral (Qtd)"] = qtd_total

    # Reset index para mostrar curso_venda como coluna
    tabela_completa = tabela_completa.reset_index()

    # Mostra a tabela final
    st.subheader("Vendas por Curso e Categoria (Valor e Quantidade)")
    st.dataframe(tabela_completa, use_container_width=True)

    # --- Tabela detalhada de alunos ---
    tabela_base = df_pagos[[
        "nome_cliente", "email_cliente", "celular_cliente", "curso_venda", "unidade", "total_pedido", "data_referencia"
    ]]

    # Cria a VERSÃO PARA EXIBIÇÃO na tela (com R$ formatado)
    tabela_para_exibir = tabela_base.copy()
    tabela_para_exibir["total_pedido"] = tabela_para_exibir["total_pedido"].apply(formatar_reais)

    st.subheader("Lista de Alunos")
    st.dataframe(tabela_para_exibir, use_container_width=True)

    # --- Exportação para Excel ---
    st.subheader("Exportar Relatório Detalhado")

    # Cria a VERSÃO PARA EXPORTAÇÃO (com dados numéricos e sem timezone)
    tabela_para_exportar = tabela_base.copy()

    if 'data_referencia' in tabela_para_exportar.columns:
        tabela_para_exportar['data_referencia'] = tabela_para_exportar['data_referencia'].dt.tz_localize(None)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        tabela_para_exportar.to_excel(writer, index=False, sheet_name='Pedidos')
    buffer.seek(0)

    st.download_button(
        label="📥 Baixar Lista de Alunos",
        data=buffer,
        file_name="pedidos_detalhados.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
