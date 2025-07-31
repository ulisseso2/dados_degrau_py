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
        default=["Curso Presencial", "Curso Live", "Passaporte", "Smart"]
    )

    # O filtro de Unidades agora fica dentro de seu próprio expander
    with st.sidebar.expander("Filtrar por Unidade"):
        unidades_list = sorted(df_filtrado_empresa["unidade"].dropna().unique())
        unidade_selecionada = st.multiselect(
            "Selecione a(s) unidade(s):", 
            unidades_list, 
            default=unidades_list
        )

    # Aplica filtros finais
    df_filtrado = df[
        (df["empresa"].isin(empresa_selecionada)) &
        (df["unidade"].isin(unidade_selecionada)) &
        (df['categoria'].str.contains('|'.join(categoria_selecionada), na=False)) &
        (df["data_pagamento"] >= data_inicio_aware) &
        (df["data_pagamento"] < data_fim_aware) &
        (df["status"].isin(status_selecionado)) &
        (df["total_pedido"] != 0) &
        (~df["metodo_pagamento"].isin([5, 8]))
    ]

    df_cancelados = df_filtrado[df_filtrado["status_id"].isin([3, 15])].copy()
    # Função para formatar valores em reais
    def formatar_reais(valor):
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    # Tabela de resumo
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total de Pedidos", df_filtrado.shape[0])
    with col2:
        st.metric("Pedidos Cancelados", df_cancelados.shape[0])
    with col3:
        st.metric("Valor", formatar_reais(df_filtrado["total_pedido"].sum()))

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

    st.divider()
    st.subheader("Lista de Alunos Matriculados")

    # 1. Cria a tabela base com os dados que já passaram pelos filtros da sidebar
    tabela_base = df_filtrado[[
      "ordem_id", "curso_venda", "turma", "turno", "cpf","nome_cliente", "email_cliente", "celular_cliente","status", "unidade", "total_pedido", "data_pagamento","cep_cliente", "endereco_cliente", "bairro_cliente", "cidade_cliente", "vendedor"
    ]].copy() # Usamos .copy() para garantir que é um novo DataFrame

    # --- 2. CRIAÇÃO DOS FILTROS ESPECÍFICOS PARA A TABELA ---
    st.markdown("Filtre a lista de alunos abaixo:")
    col1, col2, col3 = st.columns([1, 1, 1]) # Duas colunas para os filtros

    with col1:
        # Filtro para Curso Venda
        cursos_venda_disponiveis = sorted(tabela_base['curso_venda'].dropna().unique().tolist())
        placeholder_curso_nulo = "Online/Passaporte/Smart" # Placeholder para cursos nulos

        opcoes_cv = cursos_venda_disponiveis
        if tabela_base['curso_venda'].isna().any():
            opcoes_cv = [placeholder_curso_nulo] + opcoes_cv

        curso_venda_selecionado = st.multiselect(
            "Filtrar por Curso Venda:",
            options=opcoes_cv,
            default=opcoes_cv,
            key="filtro_curso_venda_tabela"
        )

    with col2:
        # Filtro para Turno
        turnos_disponiveis = sorted(tabela_base['turno'].dropna().unique().tolist())
        placeholder_turno_nulo = "Sem Turno" # Placeholder para turnos nulos

        opcoes_turno = turnos_disponiveis
        if tabela_base['turno'].isna().any():
            opcoes_turno = [placeholder_turno_nulo] + opcoes_turno

        turno_selecionado = st.multiselect(
            "Filtrar por Turno:",
            options=opcoes_turno,
            default=opcoes_turno,
            key="filtro_turno_tabela"
        )
    
    with col3:
        #Filtro Vendedor
        vendedores_disponiveis = sorted(tabela_base['vendedor'].dropna().unique().tolist())
        vendedor_selecionado = st.multiselect(
            "Filtrar por Vendedor:",
            options=vendedores_disponiveis,
            default=vendedores_disponiveis
        )
    

        # Lógica para o filtro de Curso Venda
        cursos_reais_selecionados = [c for c in curso_venda_selecionado if c != placeholder_curso_nulo]
        mascara_curso = tabela_base['curso_venda'].isin(cursos_reais_selecionados)
        if placeholder_curso_nulo in curso_venda_selecionado:
            mascara_curso = mascara_curso | tabela_base['curso_venda'].isna()

        # Lógica para o filtro de Turno
        turnos_reais_selecionados = [t for t in turno_selecionado if t != placeholder_turno_nulo]
        mascara_turno = tabela_base['turno'].isin(turnos_reais_selecionados)
        if placeholder_turno_nulo in turno_selecionado:
            mascara_turno = mascara_turno | tabela_base['turno'].isna()


        mascara_vendedor = tabela_base['vendedor'].isin(vendedor_selecionado)

        # Combina as máscaras de filtro
        tabela_final = tabela_base[mascara_curso & mascara_turno & mascara_vendedor]

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
        st.info("Nenhum aluno encontrado para os filtros de Curso Venda e Turno selecionados.")
