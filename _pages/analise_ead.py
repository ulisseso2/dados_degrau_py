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
    st.title( "Análise produtos EAD")
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
    categorias_default_desejadas = ["Curso Online"]
    
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
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total de Pedidos EAD", df_filtrado.shape[0])
    with col2:
        st.metric("Valor EAD", formatar_reais(df_filtrado[df_filtrado["categoria"] == "Curso Online"]["total_pedido"].sum()) if not df_filtrado.empty else "R$ 0,00")

    # Verifica se há dados para mostrar
    if df_filtrado.empty:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
        st.stop()

    # ---------------------------------------------
    # Análise: clientes cuja 1ª compra paga foi Curso Online
    # ---------------------------------------------
    st.divider()
    st.subheader("Jornada pós-1ª compra Online — Análise aprofundada")

    # Opções de escopo: usar histórico completo (todas as datas) ou limitar ao período atual
    usar_historico_completo = st.sidebar.checkbox(
        "Usar histórico completo de compras para definir 1ª compra (não limitar ao período)",
        value=True,
        help="Se ativo, a 1ª compra será determinada no histórico completo do banco (todas as datas disponíveis)."
    )

    # Construir dataframe histórico usado para determinar a 1ª compra
    # Base mínima: mesma empresa, pedidos pagos (total != 0) e métodos excluídos
    status_filter = status_selecionado if status_selecionado else df['status'].dropna().unique().tolist()

    if usar_historico_completo:
        df_historico = df[(df['empresa'] == empresa_selecionada) &
                          (df['total_pedido'] != 0) &
                          (~df['metodo_pagamento'].isin([5, 8, 13])) &
                          (df['status'].isin(status_filter))].copy()
    else:
        # usar apenas o escopo já filtrado pelo usuário (data, empresa, status, etc.)
        df_historico = df_filtrado.copy()

    # Garantir que temos cliente_id e data_pagamento válidos
    df_historico = df_historico.dropna(subset=['cliente_id', 'data_pagamento'])

    if df_historico.empty:
        st.info("Sem histórico disponível para realizar a análise de jornada.")
    else:
        # 1) Encontrar a data da primeira compra paga por cliente
        first_dates = (
            df_historico.groupby('cliente_id', as_index=False)['data_pagamento']
            .min()
            .rename(columns={'data_pagamento': 'first_purchase_date'})
        )

        # 2) Juntar com o histórico para obter os detalhes da primeira compra
        first_purchases = pd.merge(
            first_dates,
            df_historico,
            left_on=['cliente_id', 'first_purchase_date'],
            right_on=['cliente_id', 'data_pagamento'],
            how='left',
            suffixes=('', '_y')
        )

        # Normaliza coluna categoria para comparação simples (pode ser string com múltiplas categorias)
        first_purchases['is_first_online'] = first_purchases['categoria'].str.contains('Curso Online', na=False)

        # 3) Selecionar clientes cuja primeira compra foi Curso Online
        clientes_online = first_purchases.loc[first_purchases['is_first_online'], ['cliente_id', 'first_purchase_date', 'categoria', 'produto', 'ordem_id', 'total_pedido']]

        st.markdown(f"Clientes com 1ª compra Online: **{clientes_online['cliente_id'].nunique()}** (amostra mostrada abaixo)")
        st.dataframe(clientes_online.head(50), use_container_width=True)

        if clientes_online.empty:
            st.info("Nenhum cliente com 1ª compra marcada como 'Curso Online' encontrado no escopo selecionado.")
        else:
            # 4) Para esses clientes, encontrar a próxima compra (primeira posterior à first_purchase_date)
            clientes_ids = clientes_online['cliente_id'].unique().tolist()

            # juntar first_dates para cada cliente e filtrar compras posteriores
            df_with_first = pd.merge(df_historico, first_dates, on='cliente_id', how='inner')
            posteriores = df_with_first[df_with_first['data_pagamento'] > df_with_first['first_purchase_date']].copy()

            # se não houver compras posteriores, avisar
            if posteriores.empty:
                st.info('Nenhum registro de compra posterior encontrado para esses clientes.')
            else:
                # encontrar a próxima compra por cliente (menor data_pagamento > first)
                next_dates = (
                    posteriores.groupby('cliente_id', as_index=False)['data_pagamento']
                    .min()
                    .rename(columns={'data_pagamento': 'next_purchase_date'})
                )

                next_purchases = pd.merge(
                    next_dates,
                    posteriores,
                    left_on=['cliente_id', 'next_purchase_date'],
                    right_on=['cliente_id', 'data_pagamento'],
                    how='left',
                    suffixes=('', '_y')
                )

                # Garantir que temos a coluna first_purchase_date (pode já existir via 'posteriores')
                if 'first_purchase_date' not in next_purchases.columns:
                    # tentar usar colunas com sufixos caso pandas as tenha criado
                    for col_try in ('first_purchase_date_x', 'first_purchase_date_y'):
                        if col_try in next_purchases.columns:
                            next_purchases['first_purchase_date'] = next_purchases[col_try]
                            break
                    else:
                        # se não existir, faz o merge com first_dates
                        next_purchases = pd.merge(next_purchases, first_dates, on='cliente_id', how='left')

                # Calcular diferença em dias entre primeira compra e próxima compra
                next_purchases['days_to_next'] = (next_purchases['next_purchase_date'] - next_purchases['first_purchase_date']).dt.days

                # Preparar tabela final com os campos relevantes
                # Temos os detalhes da 1ª compra em 'clientes_online' e da próxima compra em 'next_purchases'.
                # Normalizar e juntar ambos para evitar dependência de sufixos gerados pelo merge.
                first_details = clientes_online.rename(columns={
                    'categoria': 'first_categoria',
                    'produto': 'first_produto',
                    'ordem_id': 'first_ordem_id',
                    'total_pedido': 'first_total_pedido'
                })[['cliente_id', 'first_purchase_date', 'first_categoria', 'first_produto', 'first_ordem_id', 'first_total_pedido']]

                # Padronizar colunas da próxima compra
                next_details = next_purchases.copy()
                # garantir que as colunas esperadas existam e renomear
                rename_map = {}
                if 'data_pagamento' in next_details.columns:
                    rename_map['data_pagamento'] = 'next_data_pagamento'
                if 'categoria' in next_details.columns:
                    rename_map['categoria'] = 'next_categoria'
                if 'produto' in next_details.columns:
                    rename_map['produto'] = 'next_produto'
                if 'ordem_id' in next_details.columns:
                    rename_map['ordem_id'] = 'next_ordem_id'
                if 'total_pedido' in next_details.columns:
                    rename_map['total_pedido'] = 'next_total_pedido'
                if 'next_purchase_date' in next_details.columns:
                    rename_map['next_purchase_date'] = 'next_purchase_date'
                next_details = next_details.rename(columns=rename_map)

                # Selecionar apenas as colunas relevantes da próxima compra
                cols_next = ['cliente_id', 'next_purchase_date', 'next_data_pagamento', 'next_categoria', 'next_produto', 'next_ordem_id', 'next_total_pedido', 'days_to_next']
                cols_next = [c for c in cols_next if c in next_details.columns]
                next_details = next_details[cols_next]

                # Merge first + next
                resultado = pd.merge(first_details, next_details, on='cliente_id', how='left')

                # Mostrar amostra e permitir exportar
                st.subheader('Amostra: próxima compra após 1ª compra Online')
                st.dataframe(resultado.head(100), use_container_width=True)

                # Estatísticas resumidas
                st.subheader('Resumo das recompras (primeira posterior)')
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric('Clientes com recompra', resultado['cliente_id'].nunique())
                with col2:
                    st.metric('Média dias até recomprar', f"{resultado['days_to_next'].mean():.1f} dias")
                with col3:
                    st.metric('Gasto médio na próxima compra', formatar_reais(resultado['next_total_pedido'].mean()))

                # Gráfico: distribuição de dias até a próxima compra
                st.subheader('Distribuição: dias até próxima compra')
                fig_days = px.histogram(resultado, x='days_to_next', nbins=30, title='Dias entre 1ª compra (Online) e próxima compra')
                st.plotly_chart(fig_days, use_container_width=True)

                # Gráfico: categorias compradas na próxima compra
                st.subheader('Categorias compradas na próxima compra')
                # next_categoria pode ter múltiplas categorias concatenadas — explodir
                next_cat = resultado[['cliente_id', 'next_categoria', 'next_total_pedido']].copy()
                next_cat = next_cat.dropna(subset=['next_categoria'])
                next_cat = next_cat.assign(next_categoria=next_cat['next_categoria'].str.split(', ')).explode('next_categoria')
                cat_count = next_cat.groupby('next_categoria').agg({'cliente_id':'nunique','next_total_pedido':'sum'}).reset_index()
                cat_count = cat_count.sort_values('cliente_id', ascending=False)
                fig_cat = px.bar(cat_count, x='cliente_id', y='next_categoria', orientation='h', title='Número de clientes por categoria da próxima compra', labels={'cliente_id':'Clientes únicos','next_categoria':'Categoria'})
                st.plotly_chart(fig_cat, use_container_width=True)

                # Sugestões de análises adicionais
                st.markdown('''
                ### Sugestões de análises complementares
                - Analisar LTV (valor total gasto nos 90/180/365 dias após a 1ª compra Online).
                - Coortes por mês/semana de 1ª compra Online para ver retenção ao longo do tempo.
                - Agrupar por produto da 1ª compra (diferenciar passaporte, smart, curso) para ver diferenças de jornada.
                - Analisar tempo até segunda compra por canal/metodo_pagamento/unidade/vendedor.
                - Construir a métrica % de clientes que fazem qualquer nova compra dentro de 30/90/180 dias.
                ''')

                
                # -------------------------
                # Análises adicionais (LTV, % recompras, coortes)
                # -------------------------
                st.divider()
                st.subheader('Análises adicionais: LTV por janelas, % recompras e coortes')

                # Controles na sidebar para janelas LTV/retention e granularidade de coorte
                janelas_default = [30, 90, 180, 365]
                janelas_selecionadas = st.sidebar.multiselect('Selecione janelas (dias) para LTV/retention', options=janelas_default, default=[30,90,180])
                cohort_gran = st.sidebar.radio('Cohort por', ['Mês', 'Semana'], index=0)

                # Preparar df_clients com primeira compra para os clientes cuja 1ª foi online
                df_clients = first_dates.merge(clientes_online[['cliente_id']], on='cliente_id', how='inner')

                # Preparar histórico restrito a esses clientes
                df_clients_history = pd.merge(df_historico, df_clients[['cliente_id','first_purchase_date']], on='cliente_id', how='inner')

                # Calcular LTV médio por janela
                import numpy as np
                ltv_records = []
                total_clients = df_clients['cliente_id'].nunique()
                for days in sorted(set(janelas_selecionadas)):
                    window_end = df_clients_history['first_purchase_date'] + pd.to_timedelta(days, unit='d')
                    mask = (df_clients_history['data_pagamento'] > df_clients_history['first_purchase_date']) & (df_clients_history['data_pagamento'] <= window_end)
                    ltv = df_clients_history.loc[mask].groupby('cliente_id')['total_pedido'].sum().reindex(df_clients['cliente_id']).fillna(0)
                    ltv_mean = ltv.mean()
                    ltv_median = ltv.median()
                    ltv_records.append({'days': days, 'ltv_mean': ltv_mean, 'ltv_median': ltv_median})

                if ltv_records:
                    ltv_df = pd.DataFrame(ltv_records)
                    st.markdown('#### LTV médio por janela (após 1ª compra Online)')
                    fig_ltv = px.bar(ltv_df, x='days', y='ltv_mean', text='ltv_mean', labels={'days':'Dias','ltv_mean':'LTV Médio (R$)'}, title='LTV médio por janela (R$)')
                    st.plotly_chart(fig_ltv, use_container_width=True)

                # % recompras nas janelas selecionadas
                perc_records = []
                for days in sorted(set(janelas_selecionadas)):
                    window_end = df_clients_history['first_purchase_date'] + pd.to_timedelta(days, unit='d')
                    mask_any = (df_clients_history['data_pagamento'] > df_clients_history['first_purchase_date']) & (df_clients_history['data_pagamento'] <= window_end)
                    clientes_recompraram = df_clients_history.loc[mask_any].groupby('cliente_id').size().index.unique()
                    perc = len(clientes_recompraram) / total_clients * 100 if total_clients>0 else 0
                    perc_records.append({'days': days, 'perc_recompra': perc})

                if perc_records:
                    perc_df = pd.DataFrame(perc_records)
                    st.markdown('#### % de clientes que recompraram dentro da janela')
                    cols = st.columns(len(perc_df))
                    for i, row in perc_df.iterrows():
                        with cols[i]:
                            st.metric(f"{int(row['days'])} dias", f"{row['perc_recompra']:.1f}%")

                # Cohorts: construir matriz de retenção por cohort (mês ou semana)
                df_cohort = df_clients_history.copy()
                df_cohort['delta_days'] = (df_cohort['data_pagamento'] - df_cohort['first_purchase_date']).dt.days
                if cohort_gran == 'Mês':
                    df_cohort['cohort'] = df_cohort['first_purchase_date'].dt.to_period('M').astype(str)
                    df_cohort['period_number'] = (df_cohort['data_pagamento'].dt.year - df_cohort['first_purchase_date'].dt.year) * 12 + (df_cohort['data_pagamento'].dt.month - df_cohort['first_purchase_date'].dt.month)
                    max_periods = 12
                else:
                    df_cohort['cohort'] = df_cohort['first_purchase_date'].dt.to_period('W').astype(str)
                    df_cohort['period_number'] = (df_cohort['delta_days'] // 7).astype(int)
                    max_periods = 26

                # Considerar apenas period_number >= 0
                df_cohort = df_cohort[df_cohort['period_number'] >= 0]

                # Para retenção consideramos clientes únicos por cohort e period
                cohort_pivot = (
                    df_cohort.groupby(['cohort','period_number'])['cliente_id']
                    .nunique()
                    .reset_index(name='n_clients')
                )

                # total de clientes por cohort (period_number==0)
                cohort_sizes = cohort_pivot[cohort_pivot['period_number']==0][['cohort','n_clients']].set_index('cohort')['n_clients']

                # montar matriz de retenção
                pivot_ret = cohort_pivot.pivot(index='cohort', columns='period_number', values='n_clients').fillna(0)
                # normalizar por tamanho do cohort
                pivot_ret_norm = pivot_ret.div(cohort_sizes, axis=0).fillna(0)

                if not pivot_ret_norm.empty:
                    # limitar colunas para max_periods
                    cols_keep = [c for c in pivot_ret_norm.columns if c <= max_periods]
                    pivot_plot = pivot_ret_norm[cols_keep]
                    st.markdown('#### Matriz de retenção por cohort')
                    fig_cohort = px.imshow(pivot_plot.values, x=pivot_plot.columns.astype(str), y=pivot_plot.index, color_continuous_scale='Blues', aspect='auto', labels=dict(x='Período', y='Cohort', color='Retenção'))
                    fig_cohort.update_layout(height=400)
                    st.plotly_chart(fig_cohort, use_container_width=True)

                # Adicionar sheets adicionais no arquivo exportado
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    clientes_online.to_excel(writer, index=False, sheet_name='clientes_primeira_online')
                    resultado.to_excel(writer, index=False, sheet_name='proxima_compra')
                    # salvar ltv e cohorts se existirem
                    if 'ltv_df' in locals():
                        ltv_df.to_excel(writer, index=False, sheet_name='ltv_por_janela')
                    if 'pivot_ret_norm' in locals() and not pivot_ret_norm.empty:
                        pivot_ret_norm.to_excel(writer, sheet_name='cohort_retention')
                buffer.seek(0)
                st.download_button('📥 Baixar resultados (Excel)', data=buffer, file_name='analise_jornada_online.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')