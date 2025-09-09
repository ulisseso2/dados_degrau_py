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
    st.title("🎯 Dashboard de Vendedores")
    TIMEZONE = 'America/Sao_Paulo'

    # ✅ Carrega os dados com cache (10 min por padrão, pode ajustar no sql_loader.py)
    df = carregar_dados("consultas/orders/orders.sql")
    
    # Verificação de debug para garantir que os dados foram carregados corretamente
    if df.empty:
        st.error("Erro: Nenhum dado foi carregado. Verifique a conexão com o banco de dados.")
        st.stop()
    
    # Verificação se as colunas essenciais existem
    colunas_essenciais = ["empresa", "data_pagamento", "status", "vendedor"]
    colunas_faltando = [col for col in colunas_essenciais if col not in df.columns]
    
    if colunas_faltando:
        st.error(f"Erro: Colunas essenciais não encontradas: {colunas_faltando}")
        st.info("Colunas disponíveis:")
        st.write(list(df.columns))
        st.stop()

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

    # Filtro para Vendedor
    st.sidebar.subheader("Filtro de Vendedor")
    vendedores_disponiveis = sorted(df_filtrado_data["vendedor"].dropna().unique().tolist())
    
    # Remove "Indefinido" da lista de vendedores padrão se existir
    vendedores_default = [v for v in vendedores_disponiveis if v != "Indefinido"]
    
    if vendedores_disponiveis:
        vendedor_selecionado = st.sidebar.multiselect(
            "Selecione o(s) vendedor(es):",
            options=vendedores_disponiveis,
            default=vendedores_default
        )
    else:
        st.sidebar.warning("Nenhum vendedor disponível para os filtros selecionados.")
        vendedor_selecionado = []

    # Aplica filtros finais
    filtros = (df["empresa"] == empresa_selecionada)

    # Adiciona filtro de unidade apenas se tiver unidades selecionadas
    if unidade_selecionada:
        filtros = filtros & (df["unidade"].isin(unidade_selecionada))

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

    # Verifica se há dados para mostrar
    if df_filtrado.empty:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
        st.stop()

    # Tabela de resumo por vendedor
    tabela_vendedores = (
        df_filtrado.groupby("vendedor")
        .agg(
            quantidade=pd.NamedAgg(column="ordem_id", aggfunc="count"),
            total_vendido=pd.NamedAgg(column="total_pedido", aggfunc="sum")
        )
        .reset_index()
        .sort_values("total_vendido", ascending=False)
    )
    tabela_vendedores["ticket_medio"] = tabela_vendedores["total_vendido"] / tabela_vendedores["quantidade"]
    
    # Tabela de resumo geral
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total de Pedidos", df_filtrado.shape[0])
    with col2:
        st.metric("Total de Vendedores", len(tabela_vendedores))
    with col3:
        st.metric("Total Vendas", formatar_reais(df_filtrado["total_pedido"].sum()))
    with col4:
        ticket_medio_geral = df_filtrado["total_pedido"].sum() / df_filtrado.shape[0] if df_filtrado.shape[0] > 0 else 0
        st.metric("Ticket Médio Geral", formatar_reais(ticket_medio_geral))

    # ===========================================================================
    # GRÁFICO DE BARRAS: Vendedor por Total Pedido / Quantidade
    # ===========================================================================
    st.subheader("📊 Vendedores por Faturamento")
    
    # Prepara dados para o gráfico de barras
    vendedores_barras = tabela_vendedores.copy()
    vendedores_barras["valor_formatado"] = vendedores_barras["total_vendido"].apply(formatar_reais)
    vendedores_barras["texto_combinado"] = vendedores_barras.apply(
        lambda row: f"{row['valor_formatado']} / {int(row['quantidade'])}", axis=1
    )
    
    fig_barras = px.bar(
        vendedores_barras,
        y="vendedor",
        x="total_vendido",
        text="texto_combinado",
        title="Faturamento por Vendedor (Valor / Quantidade)",
        labels={"vendedor": "Vendedor", "total_vendido": "Valor Total (R$)"},
        color="total_vendido",
        color_continuous_scale="Viridis",
        orientation="h"
    )
    fig_barras.update_layout(
        yaxis={'categoryorder': 'total ascending'},
        yaxis_title="Vendedor",
        xaxis_title="Valor Total (R$)"
    )
    st.plotly_chart(fig_barras, use_container_width=True)

    # ===========================================================================
    # GRÁFICO DE PIZZA: Vendedor por Total Pedido
    # ===========================================================================
    st.subheader("🥧 Distribuição de Vendas por Vendedor")
    
    # Se houver muitos vendedores, mostra apenas os top 10 e agrupa o resto
    vendedores_pizza = tabela_vendedores.copy()
    if len(vendedores_pizza) > 10:
        top_10 = vendedores_pizza.head(10)
        outros_valor = vendedores_pizza.iloc[10:]["total_vendido"].sum()
        if outros_valor > 0:
            outros_row = pd.DataFrame({
                'vendedor': ['Outros'],
                'total_vendido': [outros_valor],
                'quantidade': [vendedores_pizza.iloc[10:]["quantidade"].sum()]
            })
            vendedores_pizza = pd.concat([top_10, outros_row], ignore_index=True)
        else:
            vendedores_pizza = top_10
    
    fig_pizza = px.pie(
        vendedores_pizza,
        values="total_vendido",
        names="vendedor",
        title="Distribuição do Faturamento por Vendedor",
        color_discrete_sequence=px.colors.qualitative.Set3
    )
    fig_pizza.update_traces(textposition='inside', textinfo='percent+label')
    st.plotly_chart(fig_pizza, use_container_width=True)

    # ===========================================================================
    # GRÁFICO DE COLUNAS: Vendedor por Quantidade com Detalhamento de Categoria
    # ===========================================================================
    st.subheader("📈 Vendedores por Quantidade (Detalhado por Categoria)")
    
    # Agrupa por vendedor e categoria
    vendedor_categoria = (
        df_filtrado.groupby(["vendedor", "categoria"])
        .size()
        .reset_index(name="quantidade")
    )
    
    fig_colunas = px.bar(
        vendedor_categoria,
        x="vendedor",
        y="quantidade",
        color="categoria",
        title="Quantidade de Vendas por Vendedor (Detalhado por Categoria)",
        labels={"vendedor": "Vendedor", "quantidade": "Quantidade de Vendas"},
        barmode="stack",
        text_auto=True
    )
    fig_colunas.update_layout(
        xaxis_tickangle=-45,
        xaxis_title="Vendedor",
        yaxis_title="Quantidade de Vendas"
    )
    st.plotly_chart(fig_colunas, use_container_width=True)

    # ===========================================================================
    # PLANILHA DETALHADA DOS VENDEDORES
    # ===========================================================================
    st.divider()
    st.subheader("📋 Lista Detalhada de Vendas")

    # Colunas selecionadas conforme solicitado
    colunas_planilha = ["ordem_id", "produto", "email_cliente", "metodo_pagamento", 
                       "status", "total_pedido", "data_pagamento", "categoria", "vendedor"]
    
    # Cria a tabela base para exportação
    tabela_detalhada = df_filtrado[colunas_planilha].copy()
    
    if not tabela_detalhada.empty:
        # Filtros específicos para a tabela
        col1_det, col2_det, col3_det = st.columns([1, 1, 1])
        
        with col1_det:
            vendedores_disponiveis = sorted(tabela_detalhada['vendedor'].dropna().unique().tolist())
            vendedor_selecionado = st.multiselect(
                "Filtrar por Vendedor:",
                options=vendedores_disponiveis,
                default=vendedores_disponiveis,
                key="filtro_vendedor_detalhado"
            )
        
        with col2_det:
            categorias_disponiveis_det = sorted(tabela_detalhada['categoria'].dropna().unique().tolist())
            categoria_selecionada_det = st.multiselect(
                "Filtrar por Categoria:",
                options=categorias_disponiveis_det,
                default=categorias_disponiveis_det,
                key="filtro_categoria_detalhado"
            )
            
        with col3_det:
            status_disponiveis = sorted(tabela_detalhada['status'].dropna().unique().tolist())
            status_selecionado = st.multiselect(
                "Filtrar por Status:",
                options=status_disponiveis,
                default=status_disponiveis,
                key="filtro_status_detalhado"
            )
        
        # Aplica os filtros da tabela
        tabela_final_detalhada = tabela_detalhada[
            (tabela_detalhada['vendedor'].isin(vendedor_selecionado)) &
            (tabela_detalhada['categoria'].isin(categoria_selecionada_det)) &
            (tabela_detalhada['status'].isin(status_selecionado))
        ]
        
        if not tabela_final_detalhada.empty:
            # Prepara tabela para exibição
            tabela_para_exibir = tabela_final_detalhada.copy()
            tabela_para_exibir["total_pedido"] = tabela_para_exibir["total_pedido"].apply(formatar_reais)
            tabela_para_exibir["data_pagamento"] = pd.to_datetime(tabela_para_exibir["data_pagamento"]).dt.strftime('%d/%m/%Y')
            
            st.dataframe(tabela_para_exibir, use_container_width=True, hide_index=True)
            
            # Prepara a versão para exportação
            tabela_para_exportar = tabela_final_detalhada.copy()
            if 'data_pagamento' in tabela_para_exportar.columns:
                tabela_para_exportar['data_pagamento'] = tabela_para_exportar['data_pagamento'].dt.tz_localize(None)
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                tabela_para_exportar.to_excel(writer, index=False, sheet_name='Vendas Detalhadas')
            buffer.seek(0)
            
            st.download_button(
                label="📥 Baixar Lista de Vendas",
                data=buffer,
                file_name="vendas_detalhadas.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("Nenhuma venda encontrada para os filtros selecionados.")
    else:
        st.info("Nenhum dado disponível para o período e filtros selecionados.")

    # ===========================================================================
    # TABELA RESUMO DE PERFORMANCE DOS VENDEDORES
    # ===========================================================================
    st.divider()
    st.subheader("🏆 Ranking de Performance dos Vendedores")
    
    # Formata a tabela de vendedores para exibição
    tabela_performance = tabela_vendedores.copy()
    tabela_performance["total_vendido_fmt"] = tabela_performance["total_vendido"].apply(formatar_reais)
    tabela_performance["ticket_medio_fmt"] = tabela_performance["ticket_medio"].apply(formatar_reais)
    
    # Reorganiza as colunas para melhor visualização
    tabela_performance = tabela_performance[["vendedor", "quantidade", "total_vendido_fmt", "ticket_medio_fmt"]]
    tabela_performance.columns = ["Vendedor", "Qtd. Vendas", "Total Vendido", "Ticket Médio"]
    
    st.dataframe(tabela_performance, use_container_width=True, hide_index=True)
