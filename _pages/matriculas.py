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

    # Tabela por unidade pivotada Passaporte e Outros
    valor_pivot_tabela = df_filtrado.pivot_table(
        index="unidade",
        columns=df_filtrado["categoria"].apply(lambda x: "Passaporte" if x == "Passaporte" else "Outros"),
        values="total_pedido",
        aggfunc="sum",
        fill_value=0
    )

    qtd_pivot_tabela = df_filtrado.pivot_table(
        index="unidade",
        columns=df_filtrado["categoria"].apply(lambda x: "Passaporte" if x == "Passaporte" else "Outros"),
        values="ordem_id",
        aggfunc="count",
        fill_value=0
    )

    

    if not valor_pivot_tabela.empty and not qtd_pivot_tabela.empty:
        # Formata valores em reais (depois de fazer a junção)
        valor_formatado_tabela = valor_pivot_tabela.copy()
        for col in valor_formatado_tabela.columns:
            valor_formatado_tabela[col] = valor_formatado_tabela[col].apply(formatar_reais)

        valor_formatado_tabela.columns = [f"{col} (Valor)" for col in valor_formatado_tabela.columns]
        qtd_pivot_tabela.columns = [f"{col} (Qtd)" for col in qtd_pivot_tabela.columns]

        # Junta horizontalmente
        tabela_unidade = pd.concat([valor_formatado_tabela, qtd_pivot_tabela], axis=1)

        # Adiciona total geral de valor (convertendo novamente para float)
        valor_total_unidade = valor_pivot_tabela.sum(axis=1)

        # Formata o valor total por último
        tabela_unidade["Valor total"] = valor_total_unidade.apply(formatar_reais)
        
        # Adiciona total geral de quantidade
        qtd_total_unidade = qtd_pivot_tabela.sum(axis=1)
        tabela_unidade["Qtd total"] = qtd_total_unidade

        # Calcula ticket médio ANTES de formatar os valores
        ticket_medio_unidade = valor_total_unidade / qtd_total_unidade
        tabela_unidade["Ticket Médio"] = ticket_medio_unidade.apply(formatar_reais)

        # Reset index para mostrar unidade como coluna
        tabela_unidade = tabela_unidade.reset_index()

        st.subheader("Vendas por Unidade (Passaporte vs Outros)")
        st.dataframe(tabela_unidade, use_container_width=True)
    else:
        st.info("Nenhum dado de vendas por unidade e categoria encontrado.")

    # --- Tabela de Vendas por Equipe (Unidade vs Central de Vendas) ---
    # Mapeamento: unidade → owner_ids pertencentes à equipe da unidade
    EQUIPES_UNIDADE = {
        "Campo Grande": [166, 52],
        "Madureira": [163, 161, 162],
        "Niterói": [164, 157, 156],
        "Centro": [158, 159, 160],
    }

    unidades_fisicas = list(EQUIPES_UNIDADE.keys())
    df_equipes = df_filtrado[df_filtrado["unidade"].isin(unidades_fisicas)].copy()

    if not df_equipes.empty and "owner_id" in df_equipes.columns:
        df_equipes["owner_id"] = pd.to_numeric(df_equipes["owner_id"], errors="coerce")

        # Função auxiliar: retorna (valor_soma, quantidade)
        def soma_e_qtd(df_subset, filtro_categoria):
            df_cat = df_subset[df_subset["categoria"].str.contains(filtro_categoria, na=False)]
            return df_cat["total_pedido"].sum(), df_cat.shape[0]

        resultados_val = []
        resultados_qtd = []
        for unidade in unidades_fisicas:
            df_uni = df_equipes[df_equipes["unidade"] == unidade]
            ids_equipe = EQUIPES_UNIDADE[unidade]

            # Separa vendas por equipe da unidade vs central de vendas
            df_eq_uni = df_uni[df_uni["owner_id"].isin(ids_equipe)]
            df_central = df_uni[~df_uni["owner_id"].isin(ids_equipe)]

            row_v, row_q = {"Unidade": unidade}, {"Unidade": unidade}

            # Equipe Unidade: Presencial, Passaporte, Smart
            row_v["Eq. Unidade - Presencial"], row_q["Eq. Unidade - Presencial"] = soma_e_qtd(df_eq_uni, "Curso Presencial")
            row_v["Eq. Unidade - Passaporte"], row_q["Eq. Unidade - Passaporte"] = soma_e_qtd(df_eq_uni, "Passaporte")
            row_v["Eq. Unidade - Smart"], row_q["Eq. Unidade - Smart"] = soma_e_qtd(df_eq_uni, "Smart")
            row_v["Total Eq. Unidade"] = row_v["Eq. Unidade - Presencial"] + row_v["Eq. Unidade - Passaporte"] + row_v["Eq. Unidade - Smart"]
            row_q["Total Eq. Unidade"] = row_q["Eq. Unidade - Presencial"] + row_q["Eq. Unidade - Passaporte"] + row_q["Eq. Unidade - Smart"]

            # Central de Vendas: Presencial, Passaporte
            row_v["Central Vendas - Presencial"], row_q["Central Vendas - Presencial"] = soma_e_qtd(df_central, "Curso Presencial")
            row_v["Central Vendas - Passaporte"], row_q["Central Vendas - Passaporte"] = soma_e_qtd(df_central, "Passaporte")
            row_v["Total Central Vendas"] = row_v["Central Vendas - Presencial"] + row_v["Central Vendas - Passaporte"]
            row_q["Total Central Vendas"] = row_q["Central Vendas - Presencial"] + row_q["Central Vendas - Passaporte"]

            row_v["Total Geral"] = row_v["Total Eq. Unidade"] + row_v["Total Central Vendas"]
            row_q["Total Geral"] = row_q["Total Eq. Unidade"] + row_q["Total Central Vendas"]

            resultados_val.append(row_v)
            resultados_qtd.append(row_q)

        df_val = pd.DataFrame(resultados_val)
        df_qtd = pd.DataFrame(resultados_qtd)

        # Adiciona linha de total
        colunas_valor = [col for col in df_val.columns if col != "Unidade"]
        total_val = {"Unidade": "TOTAL"}
        total_qtd = {"Unidade": "TOTAL"}
        for col in colunas_valor:
            total_val[col] = df_val[col].sum()
            total_qtd[col] = df_qtd[col].sum()
        df_val = pd.concat([df_val, pd.DataFrame([total_val])], ignore_index=True)
        df_qtd = pd.concat([df_qtd, pd.DataFrame([total_qtd])], ignore_index=True)

        # Formata: R$ X.XXX,XX (N)
        tabela_equipes = df_val[["Unidade"]].copy()
        for col in colunas_valor:
            tabela_equipes[col] = df_val[col].apply(formatar_reais) + " (" + df_qtd[col].astype(int).astype(str) + ")"

        st.subheader("Vendas por Equipe (Unidade vs Central de Vendas)")

        # Renderiza como HTML para suportar negrito e cores no dark mode
        colunas_totais_eq = ["Total Eq. Unidade", "Total Central Vendas", "Total Geral"]

        def gerar_html_equipes(df, colunas_totais, col_index="Unidade"):
            html = '<table style="width:100%; border-collapse:collapse; font-size:14px;">'
            # Cabeçalho
            html += '<tr>'
            for col in df.columns:
                style = 'padding:8px; border:1px solid #555; background-color:#2c3e50; color:#fff; text-align:center;'
                if col in colunas_totais:
                    style += ' font-weight:900;'
                html += f'<th style="{style}">{col}</th>'
            html += '</tr>'
            # Linhas
            for _, row in df.iterrows():
                is_total = row[col_index] == "TOTAL"
                html += '<tr>'
                for col in df.columns:
                    is_total_col = col in colunas_totais
                    if is_total:
                        style = 'padding:8px; border:1px solid #555; background-color:#80B2F8; color:#1a1a1a; font-weight:900; text-align:center;'
                    elif is_total_col:
                        style = 'padding:8px; border:1px solid #555; background-color:#BBD1F8; color:#1a1a1a; font-weight:900; text-align:center;'
                    else:
                        style = 'padding:8px; border:1px solid #555; text-align:center;'
                    html += f'<td style="{style}">{row[col]}</td>'
                html += '</tr>'
            html += '</table>'
            return html

        st.markdown(gerar_html_equipes(tabela_equipes, colunas_totais_eq, "Unidade"), unsafe_allow_html=True)

        # --- Tabela de Vendas Online e Live por Equipe ---
        # Todos os owner_ids das equipes de unidade (flat list)
        todos_ids_unidade = [uid for ids in EQUIPES_UNIDADE.values() for uid in ids]

        categorias_extras = {
            "Curso Online": "Curso Online",
            "Curso Live": "Curso Live",
        }

        # Usa df_filtrado completo (não apenas unidades físicas) pois Online/Live podem estar em qualquer unidade
        df_online_live = df_filtrado.copy()
        if "owner_id" in df_online_live.columns:
            df_online_live["owner_id"] = pd.to_numeric(df_online_live["owner_id"], errors="coerce")

        resultados_ol_val = []
        resultados_ol_qtd = []
        for cat_label, cat_filtro in categorias_extras.items():
            df_cat = df_online_live[df_online_live["categoria"].str.contains(cat_filtro, na=False)]
            row_v = {"Categoria": cat_label}
            row_q = {"Categoria": cat_label}

            # Colunas por unidade (vendas dos owners da equipe)
            for unidade, ids_equipe in EQUIPES_UNIDADE.items():
                df_eq = df_cat[df_cat["owner_id"].isin(ids_equipe)]
                row_v[unidade] = df_eq["total_pedido"].sum()
                row_q[unidade] = df_eq.shape[0]

            # Central de Vendas (demais owners com owner_id preenchido - exclui vendas do site sem owner)
            df_central_ol = df_cat[
                (~df_cat["owner_id"].isin(todos_ids_unidade)) & 
                (df_cat["owner_id"].notna())
            ]
            row_v["Central de Vendas"] = df_central_ol["total_pedido"].sum()
            row_q["Central de Vendas"] = df_central_ol.shape[0]

            # Total da linha
            cols_num = list(EQUIPES_UNIDADE.keys()) + ["Central de Vendas"]
            row_v["Total"] = sum(row_v[c] for c in cols_num)
            row_q["Total"] = sum(row_q[c] for c in cols_num)

            resultados_ol_val.append(row_v)
            resultados_ol_qtd.append(row_q)

        df_ol_val = pd.DataFrame(resultados_ol_val)
        df_ol_qtd = pd.DataFrame(resultados_ol_qtd)

        # Linha de total
        colunas_ol = [col for col in df_ol_val.columns if col != "Categoria"]
        total_ol_val = {"Categoria": "TOTAL"}
        total_ol_qtd = {"Categoria": "TOTAL"}
        for col in colunas_ol:
            total_ol_val[col] = df_ol_val[col].sum()
            total_ol_qtd[col] = df_ol_qtd[col].sum()
        df_ol_val = pd.concat([df_ol_val, pd.DataFrame([total_ol_val])], ignore_index=True)
        df_ol_qtd = pd.concat([df_ol_qtd, pd.DataFrame([total_ol_qtd])], ignore_index=True)

        # Formata: R$ X.XXX,XX (N)
        tabela_ol = df_ol_val[["Categoria"]].copy()
        for col in colunas_ol:
            tabela_ol[col] = df_ol_val[col].apply(formatar_reais) + " (" + df_ol_qtd[col].astype(int).astype(str) + ")"

        st.subheader("Vendas Online e Live por Equipe")

        # Renderiza como HTML para suportar negrito e cores no dark mode
        colunas_totais_ol = ["Total"]

        def gerar_html_ol(df, colunas_totais, col_index="Categoria"):
            html = '<table style="width:100%; border-collapse:collapse; font-size:14px;">'
            # Cabeçalho
            html += '<tr>'
            for col in df.columns:
                style = 'padding:8px; border:1px solid #555; background-color:#2c3e50; color:#fff; text-align:center;'
                if col in colunas_totais:
                    style += ' font-weight:900;'
                html += f'<th style="{style}">{col}</th>'
            html += '</tr>'
            # Linhas
            for _, row in df.iterrows():
                is_total = row[col_index] == "TOTAL"
                html += '<tr>'
                for col in df.columns:
                    is_total_col = col in colunas_totais
                    if is_total:
                        style = 'padding:8px; border:1px solid #555; background-color:#80B2F8; color:#1a1a1a; font-weight:900; text-align:center;'
                    elif is_total_col:
                        style = 'padding:8px; border:1px solid #555; background-color:#BBD1F8; color:#1a1a1a; font-weight:900; text-align:center;'
                    else:
                        style = 'padding:8px; border:1px solid #555; text-align:center;'
                    html += f'<td style="{style}">{row[col]}</td>'
                html += '</tr>'
            html += '</table>'
            return html

        st.markdown(gerar_html_ol(tabela_ol, colunas_totais_ol, "Categoria"), unsafe_allow_html=True)

        # --- Tabela Resumo: Categorias por Equipe ---
        categorias_produto = ["Curso Presencial", "Passaporte", "Smart", "Curso Live", "Curso Online"]
        equipes_nomes = list(EQUIPES_UNIDADE.keys()) + ["Central de Vendas"]

        df_resumo = df_filtrado.copy()
        if "owner_id" in df_resumo.columns:
            df_resumo["owner_id"] = pd.to_numeric(df_resumo["owner_id"], errors="coerce")

        resumo_val = []
        resumo_qtd = []

        for equipe in equipes_nomes:
            if equipe == "Central de Vendas":
                df_eq = df_resumo[
                    (~df_resumo["owner_id"].isin(todos_ids_unidade)) &
                    (df_resumo["owner_id"].notna())
                ]
            else:
                df_eq = df_resumo[df_resumo["owner_id"].isin(EQUIPES_UNIDADE[equipe])]

            row_v = {"Equipe": equipe}
            row_q = {"Equipe": equipe}

            for cat in categorias_produto:
                df_cat = df_eq[df_eq["categoria"].str.contains(cat, na=False)]
                row_v[cat] = df_cat["total_pedido"].sum()
                row_q[cat] = df_cat.shape[0]

            row_v["Total"] = sum(row_v[c] for c in categorias_produto)
            row_q["Total"] = sum(row_q[c] for c in categorias_produto)

            resumo_val.append(row_v)
            resumo_qtd.append(row_q)

        df_res_val = pd.DataFrame(resumo_val)
        df_res_qtd = pd.DataFrame(resumo_qtd)

        # Linha TOTAL
        colunas_res = [col for col in df_res_val.columns if col != "Equipe"]
        total_res_val = {"Equipe": "TOTAL"}
        total_res_qtd = {"Equipe": "TOTAL"}
        for col in colunas_res:
            total_res_val[col] = df_res_val[col].sum()
            total_res_qtd[col] = df_res_qtd[col].sum()
        df_res_val = pd.concat([df_res_val, pd.DataFrame([total_res_val])], ignore_index=True)
        df_res_qtd = pd.concat([df_res_qtd, pd.DataFrame([total_res_qtd])], ignore_index=True)

        # Formata: R$ X.XXX,XX (N)
        tabela_resumo = df_res_val[["Equipe"]].copy()
        for col in colunas_res:
            tabela_resumo[col] = df_res_val[col].apply(formatar_reais) + " (" + df_res_qtd[col].astype(int).astype(str) + ")"

        st.subheader("Vendas por Categoria e Equipe")

        colunas_totais_res = ["Total"]

        def gerar_html_resumo(df, colunas_totais, col_index="Equipe"):
            html = '<table style="width:100%; border-collapse:collapse; font-size:14px;">'
            html += '<tr>'
            for col in df.columns:
                style = 'padding:8px; border:1px solid #555; background-color:#2c3e50; color:#fff; text-align:center;'
                if col in colunas_totais:
                    style += ' font-weight:900;'
                html += f'<th style="{style}">{col}</th>'
            html += '</tr>'
            for _, row in df.iterrows():
                is_total = row[col_index] == "TOTAL"
                html += '<tr>'
                for col in df.columns:
                    is_total_col = col in colunas_totais
                    if is_total:
                        style = 'padding:8px; border:1px solid #555; background-color:#80B2F8; color:#1a1a1a; font-weight:900; text-align:center;'
                    elif is_total_col:
                        style = 'padding:8px; border:1px solid #555; background-color:#BBD1F8; color:#1a1a1a; font-weight:900; text-align:center;'
                    else:
                        style = 'padding:8px; border:1px solid #555; text-align:center;'
                    html += f'<td style="{style}">{row[col]}</td>'
                html += '</tr>'
            html += '</table>'
            return html

        st.markdown(gerar_html_resumo(tabela_resumo, colunas_totais_res, "Equipe"), unsafe_allow_html=True)

    else:
        st.info("Nenhum dado encontrado para as unidades físicas ou coluna owner_id não disponível.")

    # Tabela por unidade
    # tabela = (
    #     df_filtrado.groupby(["unidade", "categoria"])
    #     .agg(
    #         quantidade=pd.NamedAgg(column="ordem_id", aggfunc="count"),
    #         total_vendido=pd.NamedAgg(column="total_pedido", aggfunc="sum")
    #     )
    #     .reset_index()
    #     .sort_values("total_vendido", ascending=False)
    # )
    # tabela["ticket_medio"] = tabela["total_vendido"] / tabela["quantidade"]
    # tabela["ticket_medio"] = tabela["ticket_medio"].apply(formatar_reais)
    # tabela["total_vendido"] = tabela["total_vendido"].apply(formatar_reais)

    # st.subheader("Vendas por Unidade")
    # st.dataframe(tabela, use_container_width=True)

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
            grafico2['ticket'] = grafico2['total_pedido'] / grafico2['ordem_id']
            grafico2['ticket_medio'] = grafico2['ticket'].apply(formatar_reais)

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
                color_discrete_map=CATEGORIA_PRODUTO,  # Cores distintas para as categorias
                hover_data={
                    'total_pedido': ':,.2f',
                    'quantidade': True,
                    'ticket_medio': True
                }
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
                          "endereco_cliente", "bairro_cliente", "cidade_cliente", "vendedor", "idade_momento_compra"]
    
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
        
        # Métricas resumidas
        st.markdown("### Resumo das Matrículas")
        metricas_matriculas = st.columns(6)
        with metricas_matriculas[0]:
            st.metric("Total de Matrículas", tabela_final.shape[0])
        with metricas_matriculas[1]:
            valor_total_matriculas = tabela_final['total_pedido'].sum()
            st.metric("Faturamento Total", formatar_reais(valor_total_matriculas))
        with metricas_matriculas[2]:
            ticket_medio_matriculas = valor_total_matriculas / tabela_final.shape[0] if tabela_final.shape[0] > 0 else 0
            st.metric("Ticket Médio", formatar_reais(ticket_medio_matriculas))
        with metricas_matriculas[3]:
            cursos_distintos = len(tabela_final['curso_venda'].dropna().unique())
            st.metric("Cursos Distintos", cursos_distintos)
        with metricas_matriculas[4]:
            # Calcula idade média tratando S/DN
            idades_validas_mat = tabela_final[tabela_final['idade_momento_compra'] != 'S/DN']['idade_momento_compra']
            if len(idades_validas_mat) > 0:
                idade_media_mat = pd.to_numeric(idades_validas_mat, errors='coerce').mean()
                st.metric("Idade Média", f"{idade_media_mat:.1f} anos")
            else:
                st.metric("Idade Média", "S/DN")
        with metricas_matriculas[5]:
            # Conta quantos têm idade S/DN
            sem_idade_mat = len(tabela_final[tabela_final['idade_momento_compra'] == 'S/DN'])
            st.metric("Sem Idade (S/DN)", sem_idade_mat)
        
        st.divider()
        
        # Tabela de distribuição por curso e idade
        st.markdown("### Distribuição por Curso e Idade no Momento da Compra")
        
        # Agrupa os dados por curso_venda e idade
        tabela_curso_idade = tabela_final.groupby(['curso_venda', 'idade_momento_compra']).agg(
            quantidade_vendida=pd.NamedAgg(column='ordem_id', aggfunc='count')
        ).reset_index()
        
        # Remove registros S/DN e converte idade para numérico
        tabela_curso_idade = tabela_curso_idade[tabela_curso_idade['idade_momento_compra'] != 'S/DN'].copy()
        tabela_curso_idade['idade_momento_compra'] = pd.to_numeric(tabela_curso_idade['idade_momento_compra'], errors='coerce')
        tabela_curso_idade = tabela_curso_idade.dropna()
        
        # Converte idade para inteiro para melhor visualização
        tabela_curso_idade['idade_momento_compra'] = tabela_curso_idade['idade_momento_compra'].astype(int)
        
        # Ordena por quantidade vendida (decrescente) e depois por curso
        tabela_curso_idade = tabela_curso_idade.sort_values(['quantidade_vendida', 'curso_venda'], ascending=[False, True])
        
        # Renomeia colunas para exibição
        tabela_curso_idade.columns = ['Curso', 'Idade', 'Quantidade Vendida']
        
        if not tabela_curso_idade.empty:
            st.dataframe(tabela_curso_idade, use_container_width=True, hide_index=True)
        else:
            st.info("Não há dados de idade suficientes para gerar a tabela.")
        
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

    colunas_selecionadas_online = ["ordem_id", "produto", "cpf", "nome_cliente", "email_cliente", "celular_cliente", "metodo_pagamento", "status", "unidade", "total_pedido", "data_pagamento", "cep_cliente", "endereco_cliente", "bairro_cliente", "cidade_cliente", "vendedor", "uuid", "idade_momento_compra"
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
        produtos_reais = [p for p in produto_selecionado if p != placeholder_produto_nulo]
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
            metricas_online = st.columns(6)
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
            with metricas_online[4]:
                # Calcula idade média tratando S/DN
                idades_validas = tabela_final_online[tabela_final_online['idade_momento_compra'] != 'S/DN']['idade_momento_compra']
                if len(idades_validas) > 0:
                    idade_media = pd.to_numeric(idades_validas, errors='coerce').mean()
                    st.metric("Idade Média", f"{idade_media:.1f} anos")
                else:
                    st.metric("Idade Média", "S/DN")
            with metricas_online[5]:
                # Conta quantos têm idade S/DN
                sem_idade_online = len(tabela_final_online[tabela_final_online['idade_momento_compra'] == 'S/DN'])
                st.metric("Sem Idade (S/DN)", sem_idade_online)

            st.divider()
            
            # Tabela de distribuição por idade
            st.markdown("### Distribuição por Idade no Momento da Compra")
            
            # Agrupa os dados por idade
            tabela_idade = tabela_final_online.groupby('idade_momento_compra').agg(
                quantidade_vendida=pd.NamedAgg(column='ordem_id', aggfunc='count')
            ).reset_index()
            
            # Remove registros S/DN e converte idade para numérico
            tabela_idade = tabela_idade[tabela_idade['idade_momento_compra'] != 'S/DN'].copy()
            tabela_idade['idade_momento_compra'] = pd.to_numeric(tabela_idade['idade_momento_compra'], errors='coerce')
            tabela_idade = tabela_idade.dropna()
            
            # Converte idade para inteiro para melhor visualização
            tabela_idade['idade_momento_compra'] = tabela_idade['idade_momento_compra'].astype(int)
            
            # Ordena por quantidade vendida (decrescente)
            tabela_idade = tabela_idade.sort_values('quantidade_vendida', ascending=False)
            
            # Renomeia colunas para exibição
            tabela_idade.columns = ['Idade', 'Quantidade Vendida']
            
            if not tabela_idade.empty:
                st.dataframe(tabela_idade, use_container_width=True, hide_index=True)
            else:
                st.info("Não há dados de idade suficientes para gerar a tabela.")
                
        else:
            st.info("Nenhum aluno de curso online encontrado para os filtros de produtos selecionados.")
    else:
        st.info("Não há dados de produtos online para o período selecionado.")

    st.divider()
    st.subheader("Transações Relacionadas aos Pedidos")
    
    df2 = carregar_dados("consultas/orders/orders_trasactions.sql")
    
    if not df2.empty:
        # Converte para timezone aware
        df2['data_transacao'] = pd.to_datetime(df2['data_transacao']).dt.tz_localize(TIMEZONE, ambiguous='infer')
        
        # Filtros específicos para transações
        st.markdown("Filtre as transações abaixo:")
        col1_trans, col2_trans = st.columns([1, 1])
        
        with col1_trans:
            # Filtro de data em range (mês anterior como padrão)
            hoje = pd.Timestamp.now(tz=TIMEZONE).date()
            primeiro_dia_mes_anterior = (hoje.replace(day=1) - pd.Timedelta(days=1)).replace(day=1)
            ultimo_dia_mes_anterior = hoje.replace(day=1) - pd.Timedelta(days=1)
            
            periodo_trans = st.date_input(
                "Período da Transação:",
                value=[primeiro_dia_mes_anterior, ultimo_dia_mes_anterior],
                key="periodo_transacao"
            )
        
        with col2_trans:
            # Filtro de empresa
            empresas_trans = sorted(df2['empresa'].dropna().unique().tolist())
            empresa_selecionada_trans = st.multiselect(
                "Filtrar por Empresa:",
                options=empresas_trans,
                default=empresas_trans,
                key="filtro_empresa_transacao"
            )
        
        # Valida o período selecionado
        if len(periodo_trans) == 2:
            data_inicio_trans_aware = pd.Timestamp(periodo_trans[0], tz=TIMEZONE)
            data_fim_trans_aware = pd.Timestamp(periodo_trans[1], tz=TIMEZONE) + pd.Timedelta(days=1)
            
            tabela_transacoes = df2[
                (df2["data_transacao"] >= data_inicio_trans_aware) &
                (df2["data_transacao"] < data_fim_trans_aware) &
                (df2["empresa"].isin(empresa_selecionada_trans)) &
                (df2["valor"] > 0) &
                (df2["categoria_id"].isin([2, 6, 8]))  # Filtra apenas as categorias de interesse
            ].copy()
        else:
            st.warning("Selecione um período válido (data inicial e final).")
            tabela_transacoes = pd.DataFrame()
        
        if not tabela_transacoes.empty:
            # Formata dados para exibição
            tabela_para_exibir_trans = tabela_transacoes.copy()
            tabela_para_exibir_trans["valor"] = tabela_para_exibir_trans["valor"].apply(formatar_reais)
            tabela_para_exibir_trans["data_transacao"] = pd.to_datetime(tabela_para_exibir_trans["data_transacao"]).dt.strftime('%d/%m/%Y %H:%M:%S')
            
            st.dataframe(tabela_para_exibir_trans, use_container_width=True, hide_index=True)
            
            # Métricas resumidas
            metricas_trans = st.columns(3)
            with metricas_trans[0]:
                st.metric("Total de Transações", len(tabela_transacoes))
            with metricas_trans[1]:
                valor_total_trans = tabela_transacoes['valor'].sum()
                st.metric("Valor Total", formatar_reais(valor_total_trans))
            with metricas_trans[2]:
                pedidos_unicos = tabela_transacoes['pedido'].nunique()
                st.metric("Pedidos Únicos", pedidos_unicos)
            
            # Exportar tabela de transações excel
            tabela_para_exportar_trans = tabela_transacoes.copy()
            if 'data_transacao' in tabela_para_exportar_trans.columns:
                tabela_para_exportar_trans['data_transacao'] = tabela_para_exportar_trans['data_transacao'].dt.tz_localize(None)
            
            buffer_transacoes = io.BytesIO()
            with pd.ExcelWriter(buffer_transacoes, engine='xlsxwriter') as writer:
                tabela_para_exportar_trans.to_excel(writer, index=False, sheet_name='Transacoes')
            buffer_transacoes.seek(0)
            
            st.download_button(
                label="📥 Exportar Transações Filtradas",
                data=buffer_transacoes,
                file_name="transacoes_pedidos.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_transacoes"
            )
        else:
            st.info("Não há transações para os filtros selecionados.")
    else:
        st.info("Não há transações disponíveis no banco de dados.")