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

    # UNIDADE FILTRADA
    unidade_filtrada = "Niterói"

    # Definição fixa da empresa como "Degrau" (sem opção de escolha)
    empresa_selecionada = "Degrau"
    df_filtrado_empresa = df[df["empresa"] == empresa_selecionada]

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


    # IDs da equipe local
    IDS_EQUIPE_LOCAL = [164, 157, 156]  # Niterói

    # DataFrame amplo: mesmas condições de filtro MAS sem restringir por unidade/categoria
    df_amplo = df[
        (df["empresa"] == empresa_selecionada) &
        (df["data_pagamento"] >= data_inicio_aware) &
        (df["data_pagamento"] < data_fim_aware) &
        (df["status"].isin(status_selecionado)) &
        (df["total_pedido"] != 0)
    ].copy()
    if "owner_id" in df_amplo.columns:
        df_amplo["owner_id"] = pd.to_numeric(df_amplo["owner_id"], errors="coerce")

    # Equipe Unidade: todas vendas dos owners da equipe (qualquer categoria/unidade)
    df_equipe_local = df_amplo[df_amplo["owner_id"].isin(IDS_EQUIPE_LOCAL)].copy()
    df_equipe_local["equipe"] = "Equipe Unidade"

    # Central de Vendas: vendas na unidade física por outros owners
    _df_unidade = df_amplo[df_amplo["unidade"] == unidade_filtrada]
    df_equipe_central = _df_unidade[
        (~_df_unidade["owner_id"].isin(IDS_EQUIPE_LOCAL)) &
        (_df_unidade["owner_id"].notna())
    ].copy()
    df_equipe_central["equipe"] = "Central de Vendas"

    # DataFrame completo: todas vendas atribuídas a esta unidade
    df_completo = pd.concat([df_equipe_local, df_equipe_central], ignore_index=True)

    # Aplica filtro de categoria do sidebar
    if categoria_selecionada:
        df_filtrado = df_completo[
            df_completo['categoria'].str.contains('|'.join(categoria_selecionada), na=False)
        ]
    else:
        df_filtrado = df_completo.copy()

    # Função para formatar valores em reais
    def formatar_reais(valor):
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


    # Métricas apenas da Equipe da Unidade
    df_metrica = df_filtrado[df_filtrado["equipe"] == "Equipe Unidade"] if "equipe" in df_filtrado.columns else df_filtrado
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total de Pedidos (Equipe)", df_metrica.shape[0])
    with col2:
        st.metric("Faturado no Período (Equipe)", formatar_reais(df_metrica["total_pedido"].sum()))
    with col3:
        ticket_medio = df_metrica["total_pedido"].mean() if not df_metrica.empty else 0
        st.metric("Ticket Médio (Equipe)", formatar_reais(ticket_medio))

    # --- Tabela de Vendas por Equipe (Equipe Unidade vs Central de Vendas) ---
    def gerar_html_tabela(df_html, colunas_totais, col_index):
        html = '<table style="width:100%; border-collapse:collapse; font-size:14px;">'
        html += '<tr>'
        for col in df_html.columns:
            style = 'padding:8px; border:1px solid #555; background-color:#2c3e50; color:#fff; text-align:center;'
            if col in colunas_totais: style += ' font-weight:900;'
            html += f'<th style="{style}">{col}</th>'
        html += '</tr>'
        for _, row in df_html.iterrows():
            is_total = row[col_index] == "TOTAL"
            html += '<tr>'
            for col in df_html.columns:
                if is_total:
                    style = 'padding:8px; border:1px solid #555; background-color:#80B2F8; color:#1a1a1a; font-weight:900; text-align:center;'
                elif col in colunas_totais:
                    style = 'padding:8px; border:1px solid #555; background-color:#BBD1F8; color:#1a1a1a; font-weight:900; text-align:center;'
                else:
                    style = 'padding:8px; border:1px solid #555; text-align:center;'
                html += f'<td style="{style}">{row[col]}</td>'
            html += '</tr>'
        html += '</table>'
        return html

    if not df_amplo.empty and "owner_id" in df_amplo.columns:
        def soma_e_qtd(df_subset, filtro_categoria):
            df_cat = df_subset[df_subset["categoria"].str.contains(filtro_categoria, na=False)]
            return df_cat["total_pedido"].sum(), df_cat.shape[0]

        df_local = df_amplo[df_amplo["owner_id"].isin(IDS_EQUIPE_LOCAL)]
        df_unidade_fisica = df_amplo[df_amplo["unidade"] == unidade_filtrada]
        df_central = df_unidade_fisica[(~df_unidade_fisica["owner_id"].isin(IDS_EQUIPE_LOCAL)) & (df_unidade_fisica["owner_id"].notna())]

        categorias_tab = ["Curso Presencial", "Passaporte", "Smart", "Curso Live", "Curso Online"]
        categorias_central = ["Curso Presencial", "Passaporte"]

        rows_val, rows_qtd = [], []
        row_v, row_q = {"Origem": "Equipe Unidade"}, {"Origem": "Equipe Unidade"}
        for cat in categorias_tab:
            row_v[cat], row_q[cat] = soma_e_qtd(df_local, cat)
        row_v["Total"] = sum(row_v[c] for c in categorias_tab)
        row_q["Total"] = sum(row_q[c] for c in categorias_tab)
        rows_val.append(row_v); rows_qtd.append(row_q)

        row_v2, row_q2 = {"Origem": "Central de Vendas"}, {"Origem": "Central de Vendas"}
        for cat in categorias_tab:
            if cat in categorias_central:
                row_v2[cat], row_q2[cat] = soma_e_qtd(df_central, cat)
            else:
                row_v2[cat], row_q2[cat] = 0, 0
        row_v2["Total"] = sum(row_v2[c] for c in categorias_tab)
        row_q2["Total"] = sum(row_q2[c] for c in categorias_tab)
        rows_val.append(row_v2); rows_qtd.append(row_q2)

        df_tv = pd.DataFrame(rows_val)
        df_tq = pd.DataFrame(rows_qtd)

        colunas_t = [c for c in df_tv.columns if c != "Origem"]
        tot_v = {"Origem": "TOTAL"}
        tot_q = {"Origem": "TOTAL"}
        for c in colunas_t:
            tot_v[c] = df_tv[c].sum()
            tot_q[c] = df_tq[c].sum()
        df_tv = pd.concat([df_tv, pd.DataFrame([tot_v])], ignore_index=True)
        df_tq = pd.concat([df_tq, pd.DataFrame([tot_q])], ignore_index=True)

        tabela_eq = df_tv[["Origem"]].copy()
        for c in colunas_t:
            tabela_eq[c] = df_tv[c].apply(formatar_reais) + " (" + df_tq[c].astype(int).astype(str) + ")"

        st.subheader("Vendas por Equipe (Unidade vs Central de Vendas)")
        st.markdown(gerar_html_tabela(tabela_eq, ["Total"], "Origem"), unsafe_allow_html=True)

    # Gráfico de Pedidos por Categoria (Equipe vs Central - Empilhado)
    st.subheader("Pedidos por Categoria (Equipe vs Central)")
    grafico = (
        df_filtrado.groupby(["categoria", "equipe"])
        .size()
        .reset_index(name="quantidade")
    )
    fig = px.bar(
        grafico,
        x="categoria",
        y="quantidade",
        color="equipe",
        title="Pedidos por Categoria (Equipe Unidade vs Central de Vendas)",
        labels={"quantidade": "Qtd. Pedidos", "categoria": "Categoria"},
        barmode="stack",
        text_auto=True,
        color_discrete_map={"Equipe Unidade": "#2E86C1", "Central de Vendas": "#E67E22"},
    )
    st.plotly_chart(fig, use_container_width=True)

    # Gráfico de Faturamento por Curso Venda (Equipe vs Central - Empilhado)
    st.subheader("Faturamento por Curso Venda (Equipe vs Central)")
    grafico2 = (
        df_filtrado.groupby(["curso_venda", "equipe"])
        .agg(total_pedido=("total_pedido", "sum"))
        .reset_index()
    )
    grafico2["total_formatado"] = grafico2["total_pedido"].apply(formatar_reais)
    max_value = float(grafico2.groupby("curso_venda")["total_pedido"].sum().max()) if not grafico2.empty else 0

    fig2 = px.bar(
        grafico2,
        x="total_pedido",
        y="curso_venda",
        color="equipe",
        title="Faturamento por Curso (Equipe Unidade vs Central de Vendas)",
        labels={"total_pedido": "Faturamento", "curso_venda": "Curso Venda"},
        orientation="h",
        barmode="stack",
        text="total_formatado",
        color_discrete_map={"Equipe Unidade": "#2E86C1", "Central de Vendas": "#E67E22"},
        range_x=[0, max_value * 1.2] if max_value > 0 else None,
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
    colunas_alunos = ["nome_cliente", "email_cliente", "celular_cliente", "status", "curso_venda", "unidade", "equipe", "total_pedido", "data_pagamento"]
    colunas_alunos = [c for c in colunas_alunos if c in df_filtrado.columns]
    tabela_base = df_filtrado[colunas_alunos]

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