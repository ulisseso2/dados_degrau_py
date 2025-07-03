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
    st.title("Cancelamentos")
    TIMEZONE = 'America/Sao_Paulo'

    # ✅ Carrega os dados com cache (10 min por padrão, pode ajustar no sql_loader.py)
    df = carregar_dados("consultas/orders/orders.sql")

    # UNIDADE FILTRADA
    unidade_filtrada = "Niterói"

    # Filtro: empresa
    empresas = df["empresa"].dropna().unique().tolist()
    empresa_selecionada = st.sidebar.multiselect("Selecione as empresas:", empresas, default=["Degrau"])
    df_filtrado_empresa = df[df["empresa"].isin(empresa_selecionada)]

    df["data_referencia"] = pd.to_datetime(df["data_referencia"]).dt.tz_localize(TIMEZONE, ambiguous='infer')

    # Filtro: data (padrão: Hoje)
    hoje_aware = pd.Timestamp.now(tz=TIMEZONE).date() 
    periodo = st.sidebar.date_input("Data Referência", [hoje_aware, hoje_aware])

    # Filtro: status (padrão: "Pago")
    status_list = df["status"].dropna().unique().tolist()

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
        (df["unidade"] == unidade_filtrada) &
        (df['categoria'].str.contains('|'.join(categoria_selecionada), na=False)) &
        (df["data_referencia"] >= data_inicio_aware) &
        (df["data_referencia"] < data_fim_aware) &
        (df["status_id"].isin([3, 15])) &
        (df["total_pedido"] != 0)
    ]

    # Função para formatar valores em reais
    def formatar_reais(valor):
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


    # --- Tabela cancelados---
    tabela_cancelados = df_filtrado[[
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
        st.metric("Total de Pedidos Cancelados", df_filtrado.shape[0])
    with col2:
        st.metric("Valor Total de Estornos", formatar_reais(df_filtrado["estorno_cancelamento"].sum()))

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