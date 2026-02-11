import sys
import os
import io
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime
from style.config_collor import CATEGORIA_PRODUTO
from utils.sql_loader import carregar_dados


def run_page():
    st.title("🎓 Dashboard de Matrículas por Unidade")
    TIMEZONE = 'America/Sao_Paulo'

    # ✅ Carrega os dados com cache (10 min por padrão, pode ajustar no sql_loader.py)
    df = carregar_dados("consultas/orders/orders.sql")
    dfo = carregar_dados("consultas/oportunidades/oportunidades.sql")

    # Filtro: empresa
    empresas = df["empresa"].dropna().unique().tolist()
    
    # Definir o índice padrão para 'Degrau'
    default_index = 0
    if "Degrau" in empresas:
        default_index = empresas.index("Degrau")
        
    empresa_selecionada = st.sidebar.radio("Selecione uma empresa:", empresas, index=default_index)
    df_filtrado_empresa = df[df["empresa"] == empresa_selecionada]

    df["data_pagamento"] = pd.to_datetime(df["data_pagamento"]).dt.tz_localize(TIMEZONE, ambiguous='infer')

    # Filtro: data (padrão: Hoje)
    hoje_aware = pd.Timestamp.now(tz=TIMEZONE).date() 
    periodo = st.sidebar.date_input("Data Pagamento", [hoje_aware, hoje_aware])

    # Filtro: status (padrão: "Pago")
    status_list = df_filtrado_empresa["status"].dropna().unique().tolist()

    # Verificar quais status estão disponíveis para a empresa selecionada
    default_status_name = []
    if any(status_id in df_filtrado_empresa['status_id'].values for status_id in [2, 3, 14, 10, 15]):
        default_status_name = df_filtrado_empresa[df_filtrado_empresa['status_id'].isin([2, 3, 14, 10, 15])]['status'].unique().tolist()
    elif status_list:  # Se não encontrar os status padrão mas tiver algum status disponível
        default_status_name = [status_list[0]]  # Usa o primeiro status disponível como default

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

    # Cria um DataFrame filtrado apenas com empresa e período de data para uso nos filtros seguintes
    df_filtrado_data = df[
        (df["empresa"] == empresa_selecionada) & 
        (df["data_pagamento"] >= data_inicio_aware) & 
        (df["data_pagamento"] < data_fim_aware) &
        (df["total_pedido"] != 0) &
        (~df["metodo_pagamento"].isin([5, 8, 13]))
    ]

    # Filtra também por status se já tiver sido selecionado
    if status_selecionado:
        df_filtrado_data = df_filtrado_data[df_filtrado_data["status"].isin(status_selecionado)]

    st.sidebar.subheader("Filtro de Categoria")
    # Busca as categorias disponíveis apenas para a empresa selecionada E no período selecionado
    categorias_disponiveis = df_filtrado_data['categoria'].str.split(', ').explode().str.strip().dropna().unique().tolist()
    
    # Lista de categorias que gostaríamos de ter como default
    categorias_default_desejadas = ["Curso Presencial", "Curso Live", "Passaporte", "Smart", "Curso Online"]
    
    # Filtrar apenas as categorias default que realmente existem nos dados filtrados
    categorias_default_reais = [cat for cat in categorias_default_desejadas if cat in categorias_disponiveis]
    
    # Se nenhuma das categorias default estiver disponível, usa todas as categorias disponíveis
    if not categorias_default_reais:
        categorias_default_reais = categorias_disponiveis
    
    categoria_selecionada = st.sidebar.multiselect(
        "Selecione a(s) categoria(s):",
        options=sorted(categorias_disponiveis),
        default=categorias_default_reais
    )

    # Atualiza o DataFrame filtrado com a seleção de categorias
    if categoria_selecionada:
        df_filtrado_data = df_filtrado_data[df_filtrado_data['categoria'].str.contains('|'.join(categoria_selecionada), na=False)]

    # O filtro de Unidades agora fica dentro de seu próprio expander
    with st.sidebar.expander("Filtrar por Unidade"):
        # Garantir que só mostra unidades disponíveis na empresa selecionada E no período/categoria selecionado
        unidades_list = sorted(df_filtrado_data["unidade"].dropna().unique().tolist())
        # Evitar lista vazia de unidades
        if unidades_list:
            unidade_selecionada = st.multiselect(
                "Selecione a(s) unidade(s):", 
                unidades_list, 
                default=unidades_list
            )
        else:
            st.warning("Nenhuma unidade disponível para os filtros selecionados.")
            unidade_selecionada = []

    # Atualiza o DataFrame filtrado com a seleção de unidades
    if unidade_selecionada:
        df_filtrado_data = df_filtrado_data[df_filtrado_data["unidade"].isin(unidade_selecionada)]

    # Filtro para Método de Pagamento
    st.sidebar.subheader("Filtro de Pagamento")
    metodos_pagamento_disponiveis = sorted(df_filtrado_data["metodo_pagamento"].dropna().unique().tolist())
    if metodos_pagamento_disponiveis:
        metodo_pagamento_selecionado = st.sidebar.multiselect(
            "Selecione o(s) método(s) de pagamento:",
            options=metodos_pagamento_disponiveis,
            default=metodos_pagamento_disponiveis
        )
    else:
        st.sidebar.warning("Nenhum método de pagamento disponível para os filtros selecionados.")
        metodo_pagamento_selecionado = []

    # Atualiza o DataFrame filtrado com a seleção de métodos de pagamento
    if metodo_pagamento_selecionado:
        df_filtrado_data = df_filtrado_data[df_filtrado_data["metodo_pagamento"].isin(metodo_pagamento_selecionado)]

    # Filtro para Vendedor
    st.sidebar.subheader("Filtro de Vendedor")
    vendedores_disponiveis = sorted(df_filtrado_data["vendedor"].dropna().unique().tolist())
    if vendedores_disponiveis:
        vendedor_selecionado = st.sidebar.multiselect(
            "Selecione o(s) vendedor(es):",
            options=vendedores_disponiveis,
            default=vendedores_disponiveis
        )
    else:
        st.sidebar.warning("Nenhum vendedor disponível para os filtros selecionados.")
        vendedor_selecionado = []

    # Aplica filtros finais
    filtros = (df["empresa"] == empresa_selecionada)

    # Adiciona filtro de unidade apenas se tiver unidades selecionadas
    if unidade_selecionada:
        filtros = filtros & (df["unidade"].isin(unidade_selecionada))
    
    # Adiciona filtro de método de pagamento
    if metodo_pagamento_selecionado:
        filtros = filtros & (df["metodo_pagamento"].isin(metodo_pagamento_selecionado))

    # Adiciona filtro de vendedor
    if vendedor_selecionado:
        filtros = filtros & (df["vendedor"].isin(vendedor_selecionado))

    # Adiciona outros filtros
    if categoria_selecionada:
        filtros = filtros & (df['categoria'].str.contains('|'.join(categoria_selecionada), na=False))
    
    filtros = filtros & (
        (df["data_pagamento"] >= data_inicio_aware) &
        (df["data_pagamento"] < data_fim_aware) &
        (df["status"].isin(status_selecionado)) &
        (df["total_pedido"] != 0) &
        (~df["metodo_pagamento"].isin([5, 8, 13]))
    )
    
    df_filtrado = df[filtros]

    # Função para formatar valores em reais
    def formatar_reais(valor):
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")