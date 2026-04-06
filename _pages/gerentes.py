import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import timedelta
from style.config_collor import CATEGORIA_PRODUTO
from utils.sql_loader import carregar_dados


def run_page():
    st.title("📊 Painel Gerencial Comercial")
    TIMEZONE = 'America/Sao_Paulo'

    dfo = carregar_dados("consultas/orders/orders.sql")
    dfi = carregar_dados("consultas/oportunidades/oportunidades.sql")

    if dfo.empty and dfi.empty:
        st.error("Não foi possível carregar os dados.")
        st.stop()

    if not dfo.empty:
        dfo["data_pagamento"] = pd.to_datetime(dfo["data_pagamento"]).dt.tz_localize(TIMEZONE, ambiguous='infer')
    if not dfi.empty:
        dfi["criacao"] = pd.to_datetime(dfi["criacao"]).dt.tz_localize(TIMEZONE, ambiguous=False, nonexistent='shift_forward')

    # ================================================================
    # FILTROS SIDEBAR
    # ================================================================
    st.sidebar.header("Filtros")

    # Empresa
    empresas = sorted(dfo["empresa"].dropna().unique().tolist()) if not dfo.empty else []
    default_index = empresas.index("Degrau") if "Degrau" in empresas else 0
    empresa_selecionada = st.sidebar.radio("Empresa:", empresas, index=default_index)

    # Período — padrão: últimos 7 dias incluindo hoje
    hoje = pd.Timestamp.now(tz=TIMEZONE).date()
    sete_dias_atras = hoje - timedelta(days=6)
    periodo = st.sidebar.date_input("Período:", [sete_dias_atras, hoje])

    try:
        data_inicio = pd.Timestamp(periodo[0], tz=TIMEZONE)
        data_fim = pd.Timestamp(periodo[1], tz=TIMEZONE) + pd.Timedelta(days=1)
    except IndexError:
        st.warning("👈 Selecione um período de datas na barra lateral.")
        st.stop()

    # Comparação independente
    dias_comp = st.sidebar.selectbox(
        "Comparar com período anterior de:", [7, 15, 30], index=0,
        format_func=lambda x: f"{x} dias"
    )
    delta_comp = timedelta(days=dias_comp)
    data_inicio_comp = data_inicio - delta_comp
    data_fim_comp = data_fim - delta_comp

    # Pré-filtro por empresa para popular filtros dependentes
    dfo_emp = dfo[dfo["empresa"] == empresa_selecionada].copy() if not dfo.empty else pd.DataFrame()

    # Status
    if not dfo_emp.empty:
        status_list = sorted(dfo_emp["status"].dropna().unique().tolist())
        status_default = dfo_emp[dfo_emp["status_id"].isin([2, 3, 14, 10, 15])]["status"].dropna().unique().tolist()
        if not status_default:
            status_default = status_list
    else:
        status_list, status_default = [], []

    status_selecionado = st.sidebar.multiselect("Status do pedido:", status_list, default=status_default)

    # Base filtrada para popular filtros dependentes (período atual)
    if not dfo_emp.empty:
        mask_base = (
            (dfo_emp["data_pagamento"] >= data_inicio) &
            (dfo_emp["data_pagamento"] < data_fim) &
            (dfo_emp["total_pedido"] != 0) &
            (~dfo_emp["metodo_pagamento"].isin([5, 8, 13]))
        )
        dfo_base = dfo_emp[mask_base].copy()
        if status_selecionado:
            dfo_base = dfo_base[dfo_base["status"].isin(status_selecionado)]
    else:
        dfo_base = pd.DataFrame()

    # Categoria
    if not dfo_base.empty:
        cats_disponiveis = sorted(
            dfo_base["categoria"].str.split(", ").explode().str.strip().dropna().unique().tolist()
        )
        cats_default_desejadas = ["Curso Presencial", "Curso Live", "Passaporte", "Smart", "Curso Online"]
        cats_default = [c for c in cats_default_desejadas if c in cats_disponiveis] or cats_disponiveis
    else:
        cats_disponiveis, cats_default = [], []

    categoria_selecionada = st.sidebar.multiselect("Categoria:", options=cats_disponiveis, default=cats_default)

    if categoria_selecionada and not dfo_base.empty:
        dfo_base = dfo_base[dfo_base["categoria"].str.contains("|".join(categoria_selecionada), na=False)]

    # Unidade
    with st.sidebar.expander("Filtrar por Unidade"):
        unidades_list = sorted(dfo_base["unidade"].dropna().unique().tolist()) if not dfo_base.empty else []
        if unidades_list:
            unidade_selecionada = st.multiselect("Unidade(s):", unidades_list, default=unidades_list)
        else:
            st.warning("Nenhuma unidade disponível.")
            unidade_selecionada = []

    if unidade_selecionada and not dfo_base.empty:
        dfo_base = dfo_base[dfo_base["unidade"].isin(unidade_selecionada)]

    # Dono — usa owner se existir, senão user (IFNULL(ow.full_name, v.full_name))
    # null = venda pelo site (sem user_id), incluído por padrão para não quebrar Time vs Site
    st.sidebar.subheader("Dono")
    if not dfo_base.empty:
        # Exibe null como 'Indefinido' no filtro
        dono_disponiveis = sorted(dfo_base["dono"].fillna("Indefinido").dropna().unique().tolist())
        dono_selecionado = st.sidebar.multiselect(
            "Dono(s):", dono_disponiveis, default=dono_disponiveis
        )
    else:
        dono_disponiveis, dono_selecionado = [], []

    # ================================================================
    # APLICAR FILTROS FINAIS
    # ================================================================
    def aplicar_filtros_orders(df_src, di, df_fim, com_dono=True):
        if df_src.empty:
            return pd.DataFrame()
        mask = (
            (df_src["empresa"] == empresa_selecionada) &
            (df_src["data_pagamento"] >= di) &
            (df_src["data_pagamento"] < df_fim) &
            (df_src["total_pedido"] != 0) &
            (~df_src["metodo_pagamento"].isin([5, 8, 13]))
        )
        if status_selecionado:
            mask &= df_src["status"].isin(status_selecionado)
        if categoria_selecionada:
            mask &= df_src["categoria"].str.contains("|".join(categoria_selecionada), na=False)
        if unidade_selecionada:
            mask &= df_src["unidade"].isin(unidade_selecionada)
        if com_dono and dono_selecionado:
            # Mapeia null para 'Indefinido' para comparar com a seleção do filtro
            dono_mask = df_src["dono"].fillna("Indefinido").isin(dono_selecionado)
            mask &= dono_mask
        result = df_src[mask].copy()
        # Canal de venda: dono null → Site (sem user_id nem owner_id → venda pelo site)
        result["canal_venda"] = result["dono"].apply(lambda v: "Site" if pd.isna(v) else "Time")
        result["data"] = result["data_pagamento"].dt.date
        return result

    df_orders = aplicar_filtros_orders(dfo, data_inicio, data_fim)
    df_orders_comp = aplicar_filtros_orders(dfo, data_inicio_comp, data_fim_comp)

    def aplicar_filtros_oport(df_src, di, df_fim):
        if df_src.empty:
            return pd.DataFrame()
        result = df_src[
            (df_src["empresa"] == empresa_selecionada) &
            (df_src["criacao"] >= di) &
            (df_src["criacao"] < df_fim)
        ].copy()
        if unidade_selecionada:
            result = result[result["unidade"].isin(unidade_selecionada) | result["unidade"].isna()]
        result["data"] = result["criacao"].dt.date
        return result

    dfi_oport = aplicar_filtros_oport(dfi, data_inicio, data_fim)
    dfi_oport_comp = aplicar_filtros_oport(dfi, data_inicio_comp, data_fim_comp)

    # ================================================================
    # HELPER
    # ================================================================
    def fmt_brl(v):
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    # ================================================================
    # KPIs — 2 linhas
    # ================================================================
    total_oport = len(dfi_oport)
    total_oport_comp = len(dfi_oport_comp)
    total_vendas = len(df_orders) if not df_orders.empty else 0
    total_vendas_comp = len(df_orders_comp) if not df_orders_comp.empty else 0
    total_valor = df_orders["total_pedido"].sum() if not df_orders.empty else 0
    total_valor_comp = df_orders_comp["total_pedido"].sum() if not df_orders_comp.empty else 0
    ticket_medio = total_valor / total_vendas if total_vendas > 0 else 0
    ticket_medio_comp = total_valor_comp / total_vendas_comp if total_vendas_comp > 0 else 0
    conversao = (total_vendas / total_oport * 100) if total_oport > 0 else 0
    conversao_comp = (total_vendas_comp / total_oport_comp * 100) if total_oport_comp > 0 else 0

    valor_site = df_orders[df_orders["canal_venda"] == "Site"]["total_pedido"].sum() if not df_orders.empty else 0
    valor_site_comp = df_orders_comp[df_orders_comp["canal_venda"] == "Site"]["total_pedido"].sum() if not df_orders_comp.empty else 0
    valor_time = df_orders[df_orders["canal_venda"] == "Time"]["total_pedido"].sum() if not df_orders.empty else 0
    valor_time_comp = df_orders_comp[df_orders_comp["canal_venda"] == "Time"]["total_pedido"].sum() if not df_orders_comp.empty else 0

    def delta_pct(atual, anterior):
        if anterior == 0:
            return None
        return f"{((atual - anterior) / anterior * 100):+.1f}%"

    # Linha 1
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Oportunidades", f"{total_oport:,}", delta_pct(total_oport, total_oport_comp))
    c2.metric("Vendas", f"{total_vendas:,}", delta_pct(total_vendas, total_vendas_comp))
    c3.metric("Faturamento Total", fmt_brl(total_valor), delta_pct(total_valor, total_valor_comp))
    c4.metric("Ticket Médio", fmt_brl(ticket_medio), delta_pct(ticket_medio, ticket_medio_comp))

    # Linha 2
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Conversão", f"{conversao:.1f}%", delta_pct(conversao, conversao_comp))
    c6.metric("Vendas Site", fmt_brl(valor_site), delta_pct(valor_site, valor_site_comp))
    c7.metric("Vendas Time", fmt_brl(valor_time), delta_pct(valor_time, valor_time_comp))
    qtd_donos = df_orders["dono"].nunique() if not df_orders.empty else 0
    c8.metric("Donos Ativos", f"{qtd_donos:,}")

    # ================================================================
    # TABELA + GRÁFICO DIA A DIA
    # ================================================================
    st.divider()
    st.subheader("📅 Evolução Diária")

    # ---- Período atual ----
    all_dates = pd.date_range(start=periodo[0], end=periodo[1], freq="D").date
    df_diario = pd.DataFrame({"data": all_dates})

    if not dfi_oport.empty:
        df_diario = df_diario.merge(
            dfi_oport.groupby("data").size().reset_index(name="oportunidades"),
            on="data", how="left"
        )
    else:
        df_diario["oportunidades"] = 0

    if not df_orders.empty:
        diario_vendas = df_orders.groupby("data").agg(
            vendas=("ordem_id", "count"),
            valor_total=("total_pedido", "sum")
        ).reset_index()
        diario_site = df_orders[df_orders["canal_venda"] == "Site"].groupby("data")["total_pedido"].sum().reset_index(name="valor_site")
        diario_time = df_orders[df_orders["canal_venda"] == "Time"].groupby("data")["total_pedido"].sum().reset_index(name="valor_time")
        df_diario = df_diario.merge(diario_vendas, on="data", how="left")
        df_diario = df_diario.merge(diario_site, on="data", how="left")
        df_diario = df_diario.merge(diario_time, on="data", how="left")
    else:
        df_diario["vendas"] = 0
        df_diario["valor_total"] = 0
        df_diario["valor_site"] = 0
        df_diario["valor_time"] = 0

    df_diario = df_diario.fillna(0)
    df_diario["ticket_medio"] = df_diario.apply(
        lambda r: r["valor_total"] / r["vendas"] if r["vendas"] > 0 else 0, axis=1
    )
    df_diario["conversao"] = df_diario.apply(
        lambda r: (r["vendas"] / r["oportunidades"] * 100) if r["oportunidades"] > 0 else 0, axis=1
    )

    # ---- Período comparativo ----
    comp_dates = pd.date_range(
        start=(periodo[0] - delta_comp), end=(periodo[1] - delta_comp), freq="D"
    ).date
    df_comp = pd.DataFrame({"data_comp": comp_dates})
    df_comp["dia_idx"] = range(1, len(df_comp) + 1)
    df_diario["dia_idx"] = range(1, len(df_diario) + 1)

    if not dfi_oport_comp.empty:
        comp_oport = dfi_oport_comp.groupby("data").size().reset_index(name="oport_comp")
        comp_oport = comp_oport.rename(columns={"data": "data_comp"})
        df_comp = df_comp.merge(comp_oport, on="data_comp", how="left")
    else:
        df_comp["oport_comp"] = 0

    if not df_orders_comp.empty:
        comp_vendas = df_orders_comp.groupby("data").agg(
            vendas_comp=("ordem_id", "count")
        ).reset_index().rename(columns={"data": "data_comp"})
        df_comp = df_comp.merge(comp_vendas, on="data_comp", how="left")
    else:
        df_comp["vendas_comp"] = 0

    df_comp = df_comp.fillna(0)

    # Merge por dia_idx para alinhar os períodos no gráfico
    df_plot = df_diario.merge(df_comp[["dia_idx", "oport_comp", "vendas_comp"]], on="dia_idx", how="left").fillna(0)

    # Gráfico de comparação
    fig_comp = go.Figure()
    x_labels = [str(d) for d in df_diario["data"]]

    fig_comp.add_trace(go.Bar(
        x=x_labels, y=df_plot["oportunidades"],
        name="Oportunidades (atual)", marker_color="#3357FF", opacity=0.85
    ))
    fig_comp.add_trace(go.Bar(
        x=x_labels, y=df_plot["vendas"],
        name="Vendas (atual)", marker_color="#2ECC71", opacity=0.85
    ))
    fig_comp.add_trace(go.Scatter(
        x=x_labels, y=df_plot["oport_comp"],
        name=f"Oportunidades (−{dias_comp}d)", mode="lines+markers",
        line=dict(color="#85C1E9", dash="dot"), marker=dict(size=6)
    ))
    fig_comp.add_trace(go.Scatter(
        x=x_labels, y=df_plot["vendas_comp"],
        name=f"Vendas (−{dias_comp}d)", mode="lines+markers",
        line=dict(color="#A9DFBF", dash="dot"), marker=dict(size=6)
    ))
    fig_comp.update_layout(
        barmode="group",
        title=f"Oportunidades e Vendas — Atual vs {dias_comp} dias anteriores",
        xaxis_title="Data",
        yaxis_title="Quantidade",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_comp, use_container_width=True)

    # Tabela diária com split Site / Time no valor
    df_diario_exib = df_diario[["data", "oportunidades", "vendas", "valor_site", "valor_time", "valor_total", "ticket_medio", "conversao"]].copy()
    df_diario_exib["oportunidades"] = df_diario_exib["oportunidades"].astype(int)
    df_diario_exib["vendas"] = df_diario_exib["vendas"].astype(int)
    df_diario_exib["valor_site"] = df_diario_exib["valor_site"].apply(fmt_brl)
    df_diario_exib["valor_time"] = df_diario_exib["valor_time"].apply(fmt_brl)
    df_diario_exib["valor_total"] = df_diario_exib["valor_total"].apply(fmt_brl)
    df_diario_exib["ticket_medio"] = df_diario_exib["ticket_medio"].apply(fmt_brl)
    df_diario_exib["conversao"] = df_diario_exib["conversao"].apply(lambda v: f"{v:.1f}%")
    df_diario_exib.columns = ["Data", "Oportunidades", "Vendas", "Valor Site", "Valor Time", "Total Vendido", "Ticket Médio", "Conversão"]
    st.dataframe(df_diario_exib, use_container_width=True, hide_index=True)

    # ================================================================
    # ANÁLISE POR CATEGORIA DE PRODUTO
    # ================================================================
    st.divider()
    st.subheader("📦 Por Categoria de Produto")

    if not df_orders.empty and "categoria" in df_orders.columns:
        df_cat = df_orders.copy()
        df_cat["categoria_item"] = df_cat["categoria"].str.split(", ")
        df_cat = df_cat.explode("categoria_item")
        df_cat["categoria_item"] = df_cat["categoria_item"].str.strip()
        if categoria_selecionada:
            df_cat = df_cat[df_cat["categoria_item"].isin(categoria_selecionada)]

        cat_resumo = df_cat.groupby("categoria_item").agg(
            vendas=("ordem_id", "count"),
            valor=("total_pedido", "sum")
        ).reset_index()
        cat_resumo["ticket_medio"] = cat_resumo["valor"] / cat_resumo["vendas"]

        canal_cat = df_cat.groupby(["categoria_item", "canal_venda"]).size().reset_index(name="qtd")
        canal_pivot = canal_cat.pivot_table(
            index="categoria_item", columns="canal_venda", values="qtd", fill_value=0
        ).reset_index()
        for col in ["Time", "Site"]:
            if col not in canal_pivot.columns:
                canal_pivot[col] = 0
        canal_pivot["total_canal"] = canal_pivot["Time"] + canal_pivot["Site"]
        canal_pivot["% Time"] = (canal_pivot["Time"] / canal_pivot["total_canal"] * 100).round(1)
        canal_pivot["% Site"] = (canal_pivot["Site"] / canal_pivot["total_canal"] * 100).round(1)

        cat_completo = cat_resumo.merge(
            canal_pivot[["categoria_item", "Time", "Site", "% Time", "% Site"]],
            on="categoria_item", how="left"
        ).sort_values("valor", ascending=False)

        cat_exib = cat_completo.copy()
        cat_exib["valor"] = cat_exib["valor"].apply(fmt_brl)
        cat_exib["ticket_medio"] = cat_exib["ticket_medio"].apply(fmt_brl)
        cat_exib["% Time"] = cat_exib["% Time"].apply(lambda v: f"{v:.1f}%")
        cat_exib["% Site"] = cat_exib["% Site"].apply(lambda v: f"{v:.1f}%")
        cat_exib.columns = ["Categoria", "Vendas", "Valor Vendido", "Ticket Médio", "Time", "Site", "% Time", "% Site"]

        col_a, col_b = st.columns([3, 2])
        with col_a:
            st.dataframe(cat_exib, use_container_width=True, hide_index=True)
        with col_b:
            fig_cat = px.bar(
                cat_completo.sort_values("valor", ascending=True),
                y="categoria_item", x="valor", orientation="h",
                title="Faturamento por Categoria",
                labels={"categoria_item": "Categoria", "valor": "Valor (R$)"},
                color="categoria_item", color_discrete_map=CATEGORIA_PRODUTO
            )
            fig_cat.update_layout(showlegend=False, yaxis_title="")
            st.plotly_chart(fig_cat, use_container_width=True)

        st.markdown("**Canal de Venda por Categoria**")
        fig_canal_cat = px.bar(
            canal_cat, x="categoria_item", y="qtd", color="canal_venda",
            barmode="stack",
            title="Vendas Time vs Site por Categoria",
            labels={"categoria_item": "Categoria", "qtd": "Quantidade", "canal_venda": "Canal"},
            color_discrete_map={"Time": "#3357FF", "Site": "#E74C3C"},
            text_auto=True
        )
        fig_canal_cat.update_layout(xaxis_title="Categoria", yaxis_title="Quantidade")
        st.plotly_chart(fig_canal_cat, use_container_width=True)
    else:
        st.info("Nenhum dado de vendas por categoria encontrado.")

    # ================================================================
    # OPORTUNIDADES POR MODALIDADE
    # ================================================================
    st.divider()
    st.subheader("🎯 Oportunidades por Modalidade")

    if not dfi_oport.empty and "modalidade" in dfi_oport.columns:
        modal_resumo = dfi_oport.groupby("modalidade").size().reset_index(name="oportunidades")
        modal_resumo = modal_resumo.sort_values("oportunidades", ascending=False)

        col_e, col_f = st.columns([2, 3])
        with col_e:
            st.dataframe(
                modal_resumo.rename(columns={"modalidade": "Modalidade", "oportunidades": "Oportunidades"}),
                use_container_width=True, hide_index=True
            )
        with col_f:
            fig_modal = px.pie(
                modal_resumo, values="oportunidades", names="modalidade",
                title="Distribuição por Modalidade",
                color_discrete_sequence=px.colors.qualitative.Set2
            )
            fig_modal.update_traces(textinfo="value+percent")
            st.plotly_chart(fig_modal, use_container_width=True)
    else:
        st.info("Nenhum dado de oportunidades disponível para o período selecionado.")

    # ================================================================
    # CANAL DE VENDA: TIME VS SITE
    # ================================================================
    st.divider()
    st.subheader("🏪 Canal de Venda: Time vs Site")

    if not df_orders.empty:
        canal_resumo = df_orders.groupby("canal_venda").agg(
            vendas=("ordem_id", "count"),
            valor=("total_pedido", "sum")
        ).reset_index()
        canal_resumo["ticket_medio"] = canal_resumo["valor"] / canal_resumo["vendas"]

        col_c, col_d = st.columns(2)
        with col_c:
            fig_canal_qtd = px.pie(
                canal_resumo, values="vendas", names="canal_venda",
                title="Distribuição por Quantidade",
                color_discrete_map={"Time": "#3357FF", "Site": "#E74C3C"}
            )
            fig_canal_qtd.update_traces(textinfo="value+percent")
            st.plotly_chart(fig_canal_qtd, use_container_width=True)
        with col_d:
            fig_canal_val = px.pie(
                canal_resumo, values="valor", names="canal_venda",
                title="Distribuição por Valor (R$)",
                color_discrete_map={"Time": "#3357FF", "Site": "#E74C3C"}
            )
            fig_canal_val.update_traces(textinfo="percent+label")
            st.plotly_chart(fig_canal_val, use_container_width=True)

        canal_exib = canal_resumo.copy()
        canal_exib["valor"] = canal_exib["valor"].apply(fmt_brl)
        canal_exib["ticket_medio"] = canal_exib["ticket_medio"].apply(fmt_brl)
        canal_exib.columns = ["Canal", "Vendas", "Valor Vendido", "Ticket Médio"]
        st.dataframe(canal_exib, use_container_width=True, hide_index=True)

    # ================================================================
    # RANKING DE DONOS
    # ================================================================
    st.divider()
    st.subheader("🏆 Ranking por Dono")

    if not df_orders.empty:
        # Usa dono (owner → user como fallback); null = Site, exibido como 'Indefinido'
        df_rank = df_orders.copy()
        df_rank["dono_label"] = df_rank["dono"].fillna("Indefinido")

        rank = df_rank.groupby("dono_label").agg(
            vendas=("ordem_id", "count"),
            valor=("total_pedido", "sum")
        ).reset_index()
        rank["ticket_medio"] = rank["valor"] / rank["vendas"]
        rank = rank.sort_values("valor", ascending=False)

        col_g, col_h = st.columns([2, 3])
        with col_g:
            rank_exib = rank.copy()
            rank_exib["valor"] = rank_exib["valor"].apply(fmt_brl)
            rank_exib["ticket_medio"] = rank_exib["ticket_medio"].apply(fmt_brl)
            rank_exib.columns = ["Dono", "Vendas", "Valor Vendido", "Ticket Médio"]
            st.dataframe(rank_exib, use_container_width=True, hide_index=True)
        with col_h:
            fig_rank = px.bar(
                rank.head(15).sort_values("valor", ascending=True),
                y="dono_label", x="valor", orientation="h",
                title="Top 15 Donos por Faturamento",
                labels={"dono_label": "Dono", "valor": "Valor (R$)"},
                color="valor", color_continuous_scale="Blues"
            )
            fig_rank.update_layout(showlegend=False, yaxis_title="", coloraxis_showscale=False)
            st.plotly_chart(fig_rank, use_container_width=True)
        # Gráfico: dono x quantidade de vendas por categoria (barras empilhadas)
        st.subheader("📊 Vendas por Dono e Categoria")

        df_dono_cat = df_rank.copy()
        df_dono_cat["categoria_item"] = df_dono_cat["categoria"].str.split(", ")
        df_dono_cat = df_dono_cat.explode("categoria_item")
        df_dono_cat["categoria_item"] = df_dono_cat["categoria_item"].str.strip()
        if categoria_selecionada:
            df_dono_cat = df_dono_cat[df_dono_cat["categoria_item"].isin(categoria_selecionada)]

        dono_cat_qtd = (
            df_dono_cat.groupby(["dono_label", "categoria_item"])
            .size()
            .reset_index(name="qtd")
        )

        # Tabela pivot: linhas = dono, colunas = categoria, células = quantidade
        # Ordenada pelo total de vendas (mesmo critério do ranking acima)
        ordem_donos = rank["dono_label"].tolist()

        pivot = dono_cat_qtd.pivot_table(
            index="dono_label", columns="categoria_item", values="qtd",
            aggfunc="sum", fill_value=0
        )
        pivot.index.name = None
        pivot.columns.name = None
        pivot = pivot.reindex(ordem_donos).dropna(how="all")
        pivot["Total"] = pivot.sum(axis=1)

        # Mapa de calor por coluna: normaliza 0–1 dentro de cada categoria
        def cor_coluna(s):
            """Verde proporcional ao valor dentro da coluna; 0 fica neutro."""
            vmax = s.max()
            if vmax == 0:
                return [""] * len(s)
            return [
                f"background-color: rgba(46, 204, 113, {v / vmax * 0.85:.2f}); color: {'#000' if v / vmax > 0.4 else '#555'};"
                if v > 0 else ""
                for v in s
            ]

        styled = pivot.style.apply(cor_coluna, axis=0)
        st.dataframe(styled, use_container_width=True)

    else:
        st.info("Nenhum dado de vendas para o período selecionado.")
