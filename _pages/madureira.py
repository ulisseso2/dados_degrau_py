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

    # ✅ Carrega os dados com cache (10 min por padrão, pode ajustar no sql_loader.py)
    df = carregar_dados("consultas/orders/orders.sql")

    # Filtro: empresa
    empresas = df["empresa"].dropna().unique().tolist()
    empresa_selecionada = st.sidebar.multiselect("Selecione as empresas:", empresas, default=["Degrau"])
    df_filtrado_empresa = df[df["empresa"].isin(empresa_selecionada)]

    df["data_pagamento"] = pd.to_datetime(df["data_pagamento"]).dt.tz_localize(TIMEZONE, ambiguous='infer')

    # Filtro: data (padrão: Hoje)
    hoje_aware = pd.Timestamp.now(tz=TIMEZONE).date() 
    periodo = st.sidebar.date_input("Data Pagamento", [hoje_aware, hoje_aware])

    # Filtro: status (padrão: "Pago")
    status_list = df["status"].dropna().unique().tolist()

    default_status_name = []
    if 2 in df['status_id'].values:
        default_status_name = df[df['status_id'].isin ([2, 3, 14, 15])]['status'].unique().tolist()

    status_selecionado = st.sidebar.multiselect(
        "Selecione o status do pedido:", 
        status_list, 
        default=default_status_name
    )

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


    # Aplica filtros finais
    df_filtrado = df[
        (df["empresa"].isin(empresa_selecionada)) &
        (df["unidade"] == "Madureira") &
        (df['categoria'].str.contains('|'.join(categoria_selecionada), na=False)) &
        (df["data_pagamento"] >= data_inicio_aware) &
        (df["data_pagamento"] < data_fim_aware) &
        (df["status"].isin(status_selecionado)) &
        (df["total_pedido"] != 0)
    ]

    df_cancelados = df_filtrado[df_filtrado["status_id"].isin([3, 15])]

    # Função para formatar valores em reais
    def formatar_reais(valor):
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


    # Tabela de resumo
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total de Pedidos", df_filtrado.shape[0])
    with col2:
        st.metric("Faturado no Período", formatar_reais(df_filtrado["total_pedido"].sum()))
    with col3:
        st.metric("Ticket Médio", formatar_reais(df_filtrado["total_pedido"].mean()))

    # Gráfico de pedidos por unidade e categoria
    st.subheader("Gráfico de Pedidos por Unidade e Categoria")
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
        title="Pedidos por Unidade (Detalhado por Categoria)",
        labels={"quantidade": "Qtd. Pedidos", "unidade": "Unidade"},
        barmode="group",
        text_auto=True,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Gráfico de pedidos por curso venda quantitativa
    st.subheader("Pedidos por Curso Venda")
    grafico2 = (
        df_filtrado.groupby(["curso_venda"])
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
    valor_pivot = df_filtrado.pivot_table(
        index="curso_venda",
        columns="categoria",
        values="total_pedido",
        aggfunc="sum",
        fill_value=0
    )

    # Agrupa quantidade por categoria
    qtd_pivot = df_filtrado.pivot_table(
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
    tabela_base = df_filtrado[[
        "nome_cliente", "email_cliente", "celular_cliente", "status", "curso_venda", "unidade", "total_pedido", "data_pagamento"
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

    if 'data_pagamento' in tabela_para_exportar.columns:
        tabela_para_exportar['data_pagamento'] = tabela_para_exportar['data_pagamento'].dt.tz_localize(None)
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

    st.divider()
    # --- Tabela cancelados---
    tabela_cancelados = df_cancelados[[
        "nome_cliente", "email_cliente", "status", "curso_venda", "total_pedido", "data_pagamento", "solicitacao_cancelamento", "estorno_cancelamento", "tipo_cancelamento" 
    ]]

    # Cria a VERSÃO PARA EXIBIÇÃO na tela (com R$ formatado)
    tabela_para_cancelados = tabela_cancelados.copy()
    tabela_para_cancelados["total_pedido"] = tabela_para_cancelados["total_pedido"].apply(formatar_reais)
    tabela_para_cancelados["estorno_cancelamento"] = tabela_para_cancelados["estorno_cancelamento"].apply(formatar_reais)



    st.subheader("Cancelamentos Detalhados")
        # Tabela de resumo
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total de Pedidos Cancelados", df_cancelados.shape[0])
    with col2:
        st.metric("Valor Total de Estornos", formatar_reais(df_cancelados["estorno_cancelamento"].sum()))

    st.subheader("Lista de Cancelados")
    st.dataframe(tabela_para_cancelados, use_container_width=True)

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