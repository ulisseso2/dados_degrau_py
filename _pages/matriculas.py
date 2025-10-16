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

    # Tabela de resumo
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total de Pedidos", df_filtrado.shape[0])
    with col2:
        st.metric("Valor Presencial/Live/EAD", formatar_reais(df_filtrado[df_filtrado["categoria"] != "Passaporte"]["total_pedido"].sum()) if not df_filtrado.empty else "R$ 0,00")
    with col3:
        st.metric("Vendas Passaporte", formatar_reais(df_filtrado[df_filtrado["categoria"] == "Passaporte"]["total_pedido"].sum()) if not df_filtrado.empty else "R$ 0,00")
    with col4:
        st.metric("Total Vendas", formatar_reais(df_filtrado["total_pedido"].sum()) if not df_filtrado.empty else "R$ 0,00")

    # Verifica se há dados para mostrar
    if df_filtrado.empty:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
        st.stop()

    # Tabela por unidade
    tabela = (
        df_filtrado.groupby("unidade")
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
        color_discrete_map=CATEGORIA_PRODUTO,

    )
    fig.update_traces(textfont_size=12, textangle=0, textposition="outside", cliponaxis=False)

    st.plotly_chart(fig, use_container_width=True)

    # Gráfico de pedidos por curso venda quantitativa
    st.subheader("Pedidos por Curso Venda")
    
    # Verifica se há dados antes de criar o gráfico
    if df_filtrado.empty:
        st.info("Nenhum dado de curso venda encontrado para os filtros selecionados.")
    else:
        # Agrupa por curso_venda e categoria para manter a informação de categoria
        grafico2 = (
            df_filtrado.groupby(["curso_venda", "categoria"])
            .agg({'total_pedido': 'sum',
                  'ordem_id': 'count'})
            .reset_index()
        )

        # Verifica se o agrupamento retornou dados
        if not grafico2.empty:
            grafico2['valor_numerico'] = grafico2['total_pedido']
            grafico2['quantidade'] = grafico2['ordem_id']
            grafico2["total_formatado"] = grafico2["valor_numerico"].apply(formatar_reais)

            grafico2['valor_combinado'] = grafico2.apply(
                lambda row: f"{row['total_formatado']} / {int(row['quantidade'])}", axis=1)

            max_value = float(grafico2["valor_numerico"].max())

            fig2 = px.bar(
                grafico2,
                x="total_pedido",
                y="curso_venda",
                text="valor_combinado",
                title="Pedidos por Curso Venda (Valor e Quantidade por Categoria)",
                labels={"total_pedido": "Valor Total (R$)", "curso_venda": "Curso Venda", "categoria": "Categoria"},
                orientation="h",
                barmode="stack",  # Mudado para stack para melhor visualização das categorias
                color="categoria",
                range_x=[0, max_value * 1.1],
                color_discrete_map=CATEGORIA_PRODUTO  # Cores distintas para as categorias
            )
            # Ordena o eixo y com base no total de vendas
            fig2.update_layout(
                yaxis={'categoryorder':'total ascending'},
                legend=dict(
                    orientation="v",
                    yanchor="bottom",
                    y=0,
                    xanchor="right",
                    x=1
                )
            )
            fig2.update_traces(textfont_size=12, textangle=0, textposition="inside", cliponaxis=False)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Nenhum curso venda encontrado para os filtros selecionados.")

    # Tabela de venda por curso venda
    if not df_filtrado.empty:
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

        # Verifica se os pivots retornaram dados
        if not valor_pivot.empty and not qtd_pivot.empty:
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
        else:
            st.info("Nenhum dado de vendas por curso e categoria encontrado.")
    else:
        st.info("Nenhum dado de vendas encontrado para criar a tabela por curso e categoria.")

    st.divider()
    st.subheader("Lista de Alunos Matriculados (Exceto Curso Online)")

    # 1. Cria a tabela base com os dados que já passaram pelos filtros da sidebar
    colunas_selecionadas = ["ordem_id", "curso_venda", "turma", "turno", "cpf", "nome_cliente", 
                          "email_cliente", "celular_cliente", "metodo_pagamento", "status", 
                          "unidade", "total_pedido", "data_pagamento", "cep_cliente", 
                          "endereco_cliente", "bairro_cliente", "cidade_cliente", "vendedor"]
    
    # Filtra primeiro e depois seleciona as colunas
    tabela_base_sem_online = df_filtrado[df_filtrado["categoria"] != "Curso Online"].copy()
    
    # Inicializa tabela_final como DataFrame vazio para evitar erro
    tabela_final = pd.DataFrame()
    
    if not tabela_base_sem_online.empty:
        tabela_base_sem_online = tabela_base_sem_online[colunas_selecionadas]

    # --- 2. CRIAÇÃO DOS FILTROS ESPECÍFICOS PARA A TABELA ---
    if not tabela_base_sem_online.empty:
        st.markdown("Filtre a lista de alunos abaixo:")
        col1, col2, col3 = st.columns([1, 1, 1]) # Três colunas para os filtros

        with col1:
            # Filtro para Curso Venda
            cursos_venda_disponiveis = sorted(tabela_base_sem_online['curso_venda'].dropna().unique().tolist())
            placeholder_curso_nulo = "Online/Passaporte/Smart" # Placeholder para cursos nulos

            opcoes_cv = cursos_venda_disponiveis
            if tabela_base_sem_online['curso_venda'].isna().any():
                opcoes_cv = [placeholder_curso_nulo] + opcoes_cv

            curso_venda_selecionado = st.multiselect(
                "Filtrar por Curso Venda:",
                options=opcoes_cv,
                default=opcoes_cv,
                key="filtro_curso_venda_tabela"
            )

        with col2:
            # Filtro para Turno
            turnos_disponiveis = sorted(tabela_base_sem_online['turno'].dropna().unique().tolist())
            placeholder_turno_nulo = "Sem Turno" # Placeholder para turnos nulos

            opcoes_turno = turnos_disponiveis
            if tabela_base_sem_online['turno'].isna().any():
                opcoes_turno = [placeholder_turno_nulo] + opcoes_turno

            turno_selecionado = st.multiselect(
                "Filtrar por Turno:",
                options=opcoes_turno,
                default=opcoes_turno,
                key="filtro_turno_tabela"
            )
        
        with col3:
            #Filtro Vendedor
            vendedores_disponiveis_tabela = sorted(tabela_base_sem_online['vendedor'].dropna().unique().tolist())
            vendedor_selecionado_tabela = st.multiselect(
                "Filtrar por Vendedor:",
                options=vendedores_disponiveis_tabela,
                default=vendedores_disponiveis_tabela,
                key="filtro_vendedor_tabela"
            )
        
        # Lógica para o filtro de Curso Venda
        cursos_reais_selecionados = [c for c in curso_venda_selecionado if c != placeholder_curso_nulo]
        mascara_curso = tabela_base_sem_online['curso_venda'].isin(cursos_reais_selecionados)
        if placeholder_curso_nulo in curso_venda_selecionado:
            mascara_curso = mascara_curso | tabela_base_sem_online['curso_venda'].isna()

        # Lógica para o filtro de Turno
        turnos_reais_selecionados = [t for t in turno_selecionado if t != placeholder_turno_nulo]
        mascara_turno = tabela_base_sem_online['turno'].isin(turnos_reais_selecionados)
        if placeholder_turno_nulo in turno_selecionado:
            mascara_turno = mascara_turno | tabela_base_sem_online['turno'].isna()

        mascara_vendedor = tabela_base_sem_online['vendedor'].isin(vendedor_selecionado_tabela)

        # Combina as máscaras de filtro
        tabela_final = tabela_base_sem_online[mascara_curso & mascara_turno & mascara_vendedor]
    else:
        st.info("Nenhum dado de curso presencial/live encontrado para o período e filtros selecionados.")

    # --- 4. EXIBIÇÃO E EXPORTAÇÃO DA TABELA JÁ FILTRADA ---
    if not tabela_final.empty:
        tabela_para_exibir = tabela_final.copy()
        tabela_para_exibir["total_pedido"] = tabela_para_exibir["total_pedido"].apply(formatar_reais)
        tabela_para_exibir["data_pagamento"] = pd.to_datetime(tabela_para_exibir["data_pagamento"]).dt.strftime('%d/%m/%Y')
        
        st.dataframe(tabela_para_exibir, use_container_width=True, hide_index=True)

        # Prepara a versão para exportação (com dados numéricos e sem timezone)
        tabela_para_exportar = tabela_final.copy()
        if 'data_pagamento' in tabela_para_exportar.columns:
            tabela_para_exportar['data_pagamento'] = tabela_para_exportar['data_pagamento'].dt.tz_localize(None)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            tabela_para_exportar.to_excel(writer, index=False, sheet_name='Matriculas Detalhadas')
        buffer.seek(0)

        st.download_button(
            label="📥 Baixar Lista Filtrada",
            data=buffer,
            file_name="matriculas_detalhadas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        if tabela_base_sem_online.empty:
            st.info("Nenhum aluno de curso presencial/live encontrado para os filtros selecionados.")
        else:
            st.info("Nenhum aluno encontrado para os filtros de Curso Venda, Turno e Vendedor selecionados.")
        
    # =====================================================================
    # Tabela específica para Cursos Online
    # =====================================================================
    st.divider()
    st.subheader("Lista de Alunos de Cursos Online (Detalhamento por Produto)")

    colunas_selecionadas_online = ["ordem_id", "produto", "cpf", "nome_cliente", "email_cliente", "celular_cliente", "metodo_pagamento", "status", "unidade", "total_pedido", "data_pagamento", "cep_cliente", "endereco_cliente", "bairro_cliente", "cidade_cliente", "vendedor"
    ]
    
    # Cria a tabela base para cursos online
    tabela_base_online = df_filtrado[df_filtrado["categoria"] == "Curso Online"].copy()
    if not tabela_base_online.empty:
        tabela_base_online = tabela_base_online[colunas_selecionadas_online]
        
        st.markdown("Filtre a lista de alunos de cursos online abaixo:")
        col1_online, col2_online, col3_online = st.columns([1, 1, 1])
        
        with col1_online:
            # Filtro para Produto
            produtos_online = sorted(tabela_base_online['produto'].dropna().unique().tolist())
            placeholder_produto_nulo = "Sem Produto" 
            
            opcoes_produto = produtos_online
            if tabela_base_online['produto'].isna().any():
                opcoes_produto = [placeholder_produto_nulo] + opcoes_produto
                
            produto_selecionado = st.multiselect(
                "Filtrar por Produto:",
                options=opcoes_produto,
                default=opcoes_produto,
                key="filtro_curso_produto"
            )
        
        with col2_online:
            # Filtro para Status
            status_online = sorted(tabela_base_online['status'].dropna().unique().tolist())
            status_selecionado_online = st.multiselect(
                "Filtrar por Status:",
                options=status_online,
                default=status_online,
                key="filtro_status_online"
            )
            
        with col3_online:
            # Filtro Vendedor
            vendedores_online = sorted(tabela_base_online['vendedor'].dropna().unique().tolist())
            vendedor_selecionado_online = st.multiselect(
                "Filtrar por Vendedor:",
                options=vendedores_online,
                default=vendedores_online,
                key="filtro_vendedor_online"
            )
            
        # Lógica para o filtro de Produto
        produtos_reais = [p for p in produtos_online if p != placeholder_produto_nulo]
        mascara_produto = tabela_base_online['produto'].isin(produtos_reais)
        if placeholder_produto_nulo in produto_selecionado:
            mascara_produto = mascara_produto | tabela_base_online['produto'].isna()
            
        # Lógica para o filtro de Status Online
        mascara_status_online = tabela_base_online['status'].isin(status_selecionado_online)
        
        # Lógica para o filtro de Vendedor Online
        mascara_vendedor_online = tabela_base_online['vendedor'].isin(vendedor_selecionado_online)
        
        # Combina as máscaras de filtro
        tabela_final_online = tabela_base_online[mascara_produto & mascara_status_online & mascara_vendedor_online]
        
        # Exibição e exportação da tabela de cursos online filtrada
        if not tabela_final_online.empty:
            tabela_para_exibir_online = tabela_final_online.copy()
            tabela_para_exibir_online["total_pedido"] = tabela_para_exibir_online["total_pedido"].apply(formatar_reais)
            tabela_para_exibir_online["data_pagamento"] = pd.to_datetime(tabela_para_exibir_online["data_pagamento"]).dt.strftime('%d/%m/%Y')
            
            st.dataframe(tabela_para_exibir_online, use_container_width=True, hide_index=True)
            
            # Prepara a versão para exportação
            tabela_para_exportar_online = tabela_final_online.copy()
            if 'data_pagamento' in tabela_para_exportar_online.columns:
                tabela_para_exportar_online['data_pagamento'] = tabela_para_exportar_online['data_pagamento'].dt.tz_localize(None)
                
            buffer_online = io.BytesIO()
            with pd.ExcelWriter(buffer_online, engine='xlsxwriter') as writer:
                tabela_para_exportar_online.to_excel(writer, index=False, sheet_name='Produtos Online Detalhados')
            buffer_online.seek(0)
            
            st.download_button(
                label="📥 Baixar Lista de Produtos Online",
                data=buffer_online,
                file_name="produtos_online_detalhados.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_online"
            )
            
            # =====================================================================
            # Análises Gráficas para Cursos Online
            # =====================================================================
            st.subheader("Análises dos Cursos Online")
            
            # 1. Gráfico de barras dos produtos por total financeiro
            st.markdown("### Produtos Online por Valor Total e Quantidade")
            
            # Agrupa os dados por produto e soma os valores
            produtos_valores = tabela_final_online.groupby('produto').agg({
                'total_pedido': 'sum',
                'ordem_id': 'count'  # Conta a quantidade de pedidos por produto
            }).reset_index()
            produtos_valores = produtos_valores.sort_values('total_pedido', ascending=False)

            # Renomeia a coluna para ficar mais clara
            produtos_valores['quantidade_vendida'] = produtos_valores['ordem_id']

            # Adiciona formatação em reais para exibição no gráfico
            produtos_valores['valor_formatado'] = produtos_valores['total_pedido'].apply(formatar_reais)
            
            # Cria texto combinado com valor e quantidade
            produtos_valores['texto_combinado'] = produtos_valores.apply(
                lambda row: f"{row['valor_formatado']} / {int(row['quantidade_vendida'])}", axis=1
            )
            
            # Cria o gráfico de barras horizontal com escala logarítmica
            fig_produtos = px.bar(
                produtos_valores,
                y='produto',
                x='total_pedido',
                text='texto_combinado',
                title="Faturamento por Produto Online (Valor / Quantidade)",
                labels={'produto': 'Produto', 'total_pedido': 'Valor Total (R$)', 'quantidade_vendida': 'Quantidade Vendida'},
                orientation='h',
                color='total_pedido', 
                color_continuous_scale='Viridis',
                log_x=True  # Adiciona escala logarítmica no eixo X
            )
            fig_produtos.update_layout(
                yaxis={'categoryorder': 'total ascending'},
                xaxis_title="Valor Total (R$) - Escala Logarítmica"
            )
            st.plotly_chart(fig_produtos, use_container_width=True)
            
            st.divider()
            
            # Layout de duas colunas para os gráficos restantes


            st.markdown("### Distribuição por Cidades")
                
            # Agrupa os dados por cidade
            cidades = tabela_final_online.groupby('cidade_cliente').agg(
                contagem=pd.NamedAgg(column='ordem_id', aggfunc='count')
            ).reset_index()
                
            # Ordena e pega as top 20 cidades se houver mais que isso
            cidades = cidades.sort_values('contagem', ascending=False)
            if len(cidades) > 20:
                cidades_resto = pd.DataFrame({
                    'cidade_cliente': ['Outras Cidades'],
                    'contagem': [cidades.iloc[20:]['contagem'].sum()]
                })
                cidades = pd.concat([cidades.iloc[:20], cidades_resto])
                
            # Cria o gráfico de barras com escala logarítmica
            fig_cidades = px.bar(
                cidades,
                x='contagem',
                y='cidade_cliente',
                orientation='h',
                title="Top 20 Cidades (Escala Logarítmica)",
                labels={'contagem': 'Quantidade de Alunos (Escala Log)', 'cidade_cliente': 'Cidade'},
                color='contagem',
                color_continuous_scale='Blues',
                log_x=True  # Adiciona escala logarítmica no eixo X
            )
            fig_cidades.update_layout(
                yaxis={'categoryorder': 'total ascending'},
                xaxis_title="Quantidade de Alunos (Escala Logarítmica)"
            )
            st.plotly_chart(fig_cidades, use_container_width=True)
            
            # Adiciona um indicador resumido
            st.markdown("### Resumo dos Cursos Online")
            metricas_online = st.columns(4)
            with metricas_online[0]:
                st.metric("Total de Matrículas", tabela_final_online.shape[0])
            with metricas_online[1]:
                valor_total_online = tabela_final_online['total_pedido'].sum()
                st.metric("Faturamento Total", formatar_reais(valor_total_online))
            with metricas_online[2]:
                ticket_medio_online = valor_total_online / tabela_final_online.shape[0] if tabela_final_online.shape[0] > 0 else 0
                st.metric("Ticket Médio", formatar_reais(ticket_medio_online))
            with metricas_online[3]:
                produtos_distintos = len(tabela_final_online['produto'].unique())
                st.metric("Produtos Distintos", produtos_distintos)
                
        else:
            st.info("Nenhum aluno de curso online encontrado para os filtros de produtos selecionados.")
    else:
        st.info("Não há dados de produtos online para o período selecionado.")
