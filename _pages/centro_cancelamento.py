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
    unidade_filtrada = "Centro"

 
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

    cores_padronizadas = {
        'Curso Live': '#FF0000',        # Vermelho
        'Curso Presencial': '#1F77B4',  # Azul padrão do Plotly
        'Passaporte': '#2CA02C',  # Verde padrão do Plotly
        # Adicione outras categorias conforme necessário
    }

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
    tipos_cancelamentos = (
        df_filtrado.groupby(['tipo_cancelamento'])
        .agg(
            total_estornado=('estorno_cancelamento', 'sum'),
            quantidade=('ordem_id', 'count')
        )
        .reset_index()
    )

    tipos_cancelamentos["texto_barra"] = tipos_cancelamentos.apply(
        lambda row: f"{formatar_reais(row['total_estornado'])} | {row['quantidade']} pedidos",
        axis=1
    )

    # 3. Cria o gráfico de barra
    if not tipos_cancelamentos.empty:
        fig_barra_cancelados = px.bar(
            tipos_cancelamentos,
            y='tipo_cancelamento',
            x='total_estornado',
            orientation="h",
            text='texto_barra',
            title='Valor e Quantidade de Cancelamentos por Tipo',
            labels={
                "tipo_cancelamento": "Tipo de Cancelamento",
                "total_estornado": "Valor Estornado"
            },
            range_x=[0, tipos_cancelamentos["total_estornado"].max() * 1.1]
        )

        # 4. Aumentar tamanho da fonte dos textos nas barras
        fig_barra_cancelados.update_traces(
            textfont_size=14,  # aumenta o tamanho da fonte
            textposition="outside"  # coloca o texto fora da barra,
        )

        fig_barra_cancelados.update_layout(
            yaxis_title=None,
            xaxis_title="Valor Estornado (R$)",
            margin=dict(l=0, r=0, t=40, b=0)
        )
        st.plotly_chart(fig_barra_cancelados, use_container_width=True)
    else:
        st.info("Não há dados de cancelamento para exibir com os filtros atuais.")


    st.divider()

    st.subheader("Cancelamento por Produto")

    # 1. Prepara os dados: agrupa por situação e soma o valor
    tipos_cancelamentos = (
        df_filtrado.groupby(['categoria'])
        .agg(
            total_estornado=('estorno_cancelamento', 'sum'),
            quantidade=('ordem_id', 'count')
        )
        .reset_index()
    )

    tipos_cancelamentos["texto_barra"] = tipos_cancelamentos.apply(
        lambda row: f"{formatar_reais(row['total_estornado'])} | {row['quantidade']} pedidos",
        axis=1
    )

    tipos_cancelamentos["cor_personalizada"] = tipos_cancelamentos["categoria"].map(
        lambda x: cores_padronizadas.get(x, "#AAAAAA")  # Cor padrão cinza para categorias não mapeadas
    )

    # 3. Cria o gráfico de barra
    if not tipos_cancelamentos.empty:
        fig_barra_cancelados = px.bar(
            tipos_cancelamentos,
            y='categoria',
            x='total_estornado',
            orientation="h",
            text='texto_barra',
            title='Valor e Quantidade de Cancelamentos por Produto',
            labels={
                "categoria": "Categoria do Produto",
                "total_estornado": "Valor Estornado"
            },
            range_x=[0, tipos_cancelamentos["total_estornado"].max() * 1.1]
        )

        # 4. Aumentar tamanho da fonte dos textos nas barras
        fig_barra_cancelados.update_traces(
            marker_color=tipos_cancelamentos["cor_personalizada"],
            textfont_size=14,  # aumenta o tamanho da fonte
            textposition="outside"  # coloca o texto fora da barra,
        )

        fig_barra_cancelados.update_layout(
            yaxis_title=None,
            xaxis_title="Valor Estornado (R$)",
            margin=dict(l=0, r=0, t=40, b=0)
        )
        st.plotly_chart(fig_barra_cancelados, use_container_width=True)
    else:
        st.info("Não há dados de cancelamento para exibir com os filtros atuais.")