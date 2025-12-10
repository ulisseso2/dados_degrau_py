import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder
from st_aggrid.shared import JsCode
from datetime import datetime
from utils.sql_loader import carregar_dados
import plotly.express as px
import io
from pandas import ExcelWriter

def run_page():

    st.title("💰 Análise Financeira")

    # --- 1. DEFINIÇÃO DO FUSO HORÁRIO ---
    TIMEZONE = 'America/Sao_Paulo'

    # --- Função Auxiliar ---
    def formatar_reais(valor):
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    # --- Carregamento e Preparação dos Dados ---
    df = carregar_dados("consultas/contas/contas_a_pagar.sql")

    # Converte para datetime, trata erros e ATRIBUI o fuso horário correto
    df['data_pagamento_parcela'] = pd.to_datetime(df['data_pagamento_parcela'], errors='coerce').dt.tz_localize(TIMEZONE, ambiguous='infer')
    df['data_vencimento_parcela'] = pd.to_datetime(df['data_vencimento_parcela'], errors='coerce').dt.tz_localize(TIMEZONE, ambiguous='infer') # 

    # --- Seção de Filtros na Barra Lateral ---
    st.sidebar.header("Filtros da Análise")

    # Filtro de Empresa
    empresas_list = df["empresa"].dropna().unique().tolist()
    empresa_selecionada = st.sidebar.radio("Selecione uma empresa:", empresas_list)

    df_para_opcoes = df[df["empresa"] == empresa_selecionada]

    # Pega a data de "hoje" já com o fuso horário correto
    hoje_aware = pd.Timestamp.now(tz=TIMEZONE).date()
    data_min_geral = df_para_opcoes['data_pagamento_parcela'].min().date() if not df_para_opcoes.empty else hoje_aware
    data_max_geral = df_para_opcoes['data_pagamento_parcela'].max().date() if not df_para_opcoes.empty else hoje_aware
    primeiro_dia_mes_atual = hoje_aware.replace(day=1)
    ultimo_dia_mes_atual_ts = (primeiro_dia_mes_atual + pd.DateOffset(months=1)) - pd.DateOffset(days=1)
    data_fim_padrao = min(ultimo_dia_mes_atual_ts.date(), data_max_geral)
    periodo = st.sidebar.date_input("Período de Pagamento:", value=[primeiro_dia_mes_atual, data_fim_padrao], min_value=data_min_geral, max_value=data_max_geral)

    # --- Abas para Filtros Detalhados ---
    tab_unidades, tab_contabil, tab_banco = st.sidebar.tabs(["🏢 Unidades", "🧾 Contábil", "🏦 Contas"])

    # DataFrames filtrados em cascata
    df_filtrado_ue = df_para_opcoes
    df_filtrado_un = df_para_opcoes
    df_filtrado_cc = df_para_opcoes
    df_filtrado_cat = df_para_opcoes

    with tab_unidades:
        st.markdown("#### Filtrar por Unidades")
        
        # Nível 1: Unidade Estratégica
        unidade_estrategica_list = df_para_opcoes["unidade_estrategica"].dropna().unique().tolist()
        unidade_estrategica_selecionada = st.multiselect("Unidade Estratégica:", unidade_estrategica_list, default=unidade_estrategica_list)
        
        # Filtra o DataFrame com base na seleção anterior para popular o próximo filtro
        df_filtrado_ue = df_para_opcoes[df_para_opcoes["unidade_estrategica"].isin(unidade_estrategica_selecionada)]
        
        # Nível 2: Unidade de Negócio (dependente da Unidade Estratégica)
        unidade_negocio_list = df_filtrado_ue["unidade_negocio"].dropna().unique().tolist()
        unidade_negocio_selecionada = st.multiselect("Unidade de Negócio:", unidade_negocio_list, default=unidade_negocio_list)

    with tab_contabil:
        st.markdown("#### Filtrar por Classificação")
        
        # Filtra o DataFrame com base na seleção da aba anterior
        df_filtrado_un = df_filtrado_ue[df_filtrado_ue["unidade_negocio"].isin(unidade_negocio_selecionada)]

        # Nível 3: Centro de Custo (dependente das Unidades)
        centro_custo_list = df_filtrado_un["centro_custo"].dropna().unique().tolist()
        centro_custo_selecionado = st.multiselect("Centro de Custo:", centro_custo_list, default=centro_custo_list)

        # Filtra o DataFrame com base na seleção anterior
        df_filtrado_cc = df_filtrado_un[df_filtrado_un["centro_custo"].isin(centro_custo_selecionado)]
        
        # Nível 4: Categoria (dependente do Centro de Custo)
        categoria_list = df_filtrado_cc["categoria_pedido_compra"].dropna().unique().tolist()
        categoria_selecionada = st.multiselect("Categoria do Pedido:", categoria_list, default=categoria_list)

    with tab_banco:
        st.markdown("#### Filtrar por Conta Bancária")
        
        # Filtra o DataFrame com base na seleção da aba anterior
        df_filtrado_cat = df_filtrado_cc[df_filtrado_cc["categoria_pedido_compra"].isin(categoria_selecionada)]
        
        # Nível 5: Conta Bancária (dependente de tudo acima)
        todas_contas = df_filtrado_cat['conta_bancaria'].dropna().unique().tolist()
        
        if st.checkbox("Selecionar/Limpar Todas as Contas", value=True, key="select_all_accounts"):
            contas_selecionadas = st.multiselect("Contas Bancárias:", todas_contas, default=todas_contas)
        else:
            contas_selecionadas = st.multiselect("Contas Bancárias:", todas_contas)

    # --- Aplicação Final dos Filtros ---
    try:
            data_inicio_aware = pd.Timestamp(periodo[0], tz=TIMEZONE)
            data_fim_aware = pd.Timestamp(periodo[1], tz=TIMEZONE) + pd.Timedelta(days=1)
    except IndexError:
            # Caso o usuário limpe o campo de data, evita o erro
            st.warning("Por favor, selecione um período de datas.")
            st.stop() # Interrompe a execução para evitar erros abaixo

    df_filtrado = df[
        (df["empresa"] == empresa_selecionada) &
        (df["data_pagamento_parcela"] >= data_inicio_aware) &
        (df["data_pagamento_parcela"] < data_fim_aware) &
        (df["unidade_estrategica"].isin(unidade_estrategica_selecionada)) &
        (df["unidade_negocio"].isin(unidade_negocio_selecionada)) &
        (df["centro_custo"].isin(centro_custo_selecionado)) &
        (df["categoria_pedido_compra"].isin(categoria_selecionada)) &
        (df["conta_bancaria"].isin(contas_selecionadas))
    ]

    # 2. Define um mapa de cores para dar sentido a cada status
    mapa_cores = {
        'Em Atraso': '#d62728',       # Vermelho
        'Pago Atrasado': '#ff7f0e',    # Laranja
        'A Vencer': '#1f77b4',        # Azul
        'Pago em dia': '#2ca02c'       # Verde
    }

    # --- PREPARAÇÃO DOS DADOS PARA A TABELA HIERÁRQUICA ---
    if not df_filtrado.empty:
            # Agrupa os dados conforme sua estrutura original
            tabela_agrupada = (
                df_filtrado.groupby(["centro_custo", "categoria_pedido_compra", "descricao_pedido_compra"])
                .agg(valor_total=("valor_corrigido", "sum"))
                .reset_index()
            )
            
            # Adiciona a coluna formatada
            tabela_agrupada["valor_total_formatado"] = tabela_agrupada["valor_total"].apply(formatar_reais)

            # --- CONFIGURAÇÃO DA AG-GRID ---
            gb = GridOptionsBuilder.from_dataframe(tabela_agrupada)
            
            # Configura as colunas para a hierarquia
            gb.configure_column(
                field="centro_custo",
                header_name="Centro de Custo",
                rowGroup=True,
                hide=True
            )
            
            gb.configure_column(
                field="categoria_pedido_compra",
                header_name="Categoria",
                rowGroup=True,
                hide=True
            )
            
            gb.configure_column(
                field="descricao_pedido_compra",
                header_name="Histórico"
            )
            
            gb.configure_column(
                field="valor_total",
                header_name="Valor",
                type=["numericColumn"],
                aggFunc="sum",
                valueFormatter=JsCode("""
                    function(params) {
                    if (params.value === undefined || params.value === null) return '';
                    return 'R$ ' + params.value.toLocaleString('pt-BR', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2
                    }).replace('.', '#').replace(',', '.').replace('#', ',');
                    
                }
                """)
            )
            
            # Configurações adicionais da grid
            grid_options = gb.build()
            grid_options["autoGroupColumnDef"] = {
                "headerName": "Grupo/Item",
                "minWidth": 350,
                "cellRenderer": "agGroupCellRenderer",
                "cellRendererParams": {
                    "suppressCount": False,
                }
            }
            grid_options["groupDisplayType"] = "groupRow" # Exibe os grupos como linhas
            grid_options["groupDefaultExpanded"] = 0 # Expande até o primeiro nível
            grid_options["groupIncludeFooter"] = True
            grid_options["groupIncludeTotalFooter"] = True
            
            # --- EXIBIÇÃO DA TABELA ---
            st.title("Análise de Despesas")
            
            # Exibe o total de despesas
            st.markdown(f"""
            **Período selecionado:** {periodo[0].strftime('%d/%m/%Y')} a {periodo[1].strftime('%d/%m/%Y')}  
            **Total de despesas:** {formatar_reais(tabela_agrupada['valor_total'].sum())}
            """)
            
            # Exibe a tabela AgGrid
            grid_response = AgGrid(
                tabela_agrupada,
                gridOptions=grid_options,
                height=600,
                width='100%',
                theme='streamlit',
                enable_enterprise_modules=True,
                update_mode='MODEL_CHANGED',
                allow_unsafe_jscode=True,
                fit_columns_on_grid_load=True
            )
    # --- EXPORTAÇÃO PARA EXCEL ---    
        # Cria uma cópia dos dados para exportação (sem formatação)
    tabela_export = tabela_agrupada.copy()
    tabela_export['valor_total'] = tabela_export['valor_total'].round(2)  # Garante 2 casas decimais
        
        # Cria buffer para o Excel
    buffer = io.BytesIO()
    with ExcelWriter(buffer, engine='xlsxwriter') as writer:
            # Exporta a tabela principal
            tabela_export.to_excel(
                writer, 
                index=False, 
                sheet_name='Despesas Detalhadas',
                columns=["centro_custo", "categoria_pedido_compra", "descricao_pedido_compra", "valor_total"]
            )
            
            # Adiciona uma aba com totais consolidados
            totais_cc = tabela_export.groupby("centro_custo")["valor_total"].sum().reset_index()
            totais_cc.to_excel(
                writer, 
                index=False, 
                sheet_name='Totais por Centro Custo'
            )
            
            # Adiciona uma aba com totais por categoria
            totais_cat = tabela_export.groupby(["centro_custo", "categoria_pedido_compra"])["valor_total"].sum().reset_index()
            totais_cat.to_excel(
                writer, 
                index=False, 
                sheet_name='Totais por Categoria'
            )
        
        # Prepara o botão de download
    buffer.seek(0)
    st.download_button(
            label="📥 Exportar para Excel",
            data=buffer,
            file_name=f"despesas_{periodo[0].strftime('%Y%m%d')}_{periodo[1].strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="Clique para baixar os dados em formato Excel com abas detalhadas"
        )

    st.divider()  # Linha de separação

    st.subheader("Distribuição por Situação das Parcelas")

    # 1. Prepara os dados: agrupa por situação e soma o valor
    df_situacao = df_filtrado.groupby('situacao')['valor_corrigido'].sum().reset_index()
    # 3. Cria o gráfico de pizza
    if not df_situacao.empty:
        fig_pizza_situacao = px.pie(
            df_situacao,
            names='situacao',
            values='valor_corrigido',
            title='Valor Total por Situação da Parcela',
            # Aplica nosso mapa de cores customizado
            color='situacao',
            color_discrete_map=mapa_cores
        )
        
        # Atualiza para mostrar o valor (R$) e o percentual
        fig_pizza_situacao.update_traces(
            textinfo='percent+value',
            texttemplate='%{percent:,.1%} <br>R$ %{value:,.2f}' # Formata o texto
        )
        
        st.plotly_chart(fig_pizza_situacao, use_container_width=True)
    else:
        st.info("Não há dados de situação para exibir com os filtros atuais.")

    st.divider()
    st.subheader("Análises Detalhadas por Categoria")

    if not df_filtrado.empty:
        # --- Gráfico 1: Despesas por Centro de Custo ---
        st.markdown("#### Total por Centro de Custo")
        df_cc = df_filtrado.groupby('centro_custo')['valor_corrigido'].sum().reset_index()
        # Remove valores zerados para um gráfico mais limpo
        df_cc = df_cc[df_cc['valor_corrigido'] > 0].sort_values('valor_corrigido', ascending=True)
        
        if not df_cc.empty:
            fig_cc = px.bar(
                df_cc,
                x='valor_corrigido',
                y='centro_custo',
                orientation='h',
                text=df_cc['valor_corrigido'].apply(formatar_reais),
                labels={'valor_corrigido': 'Valor Total (R$)', 'centro_custo': 'Centro de Custo'},
                title="Despesas Agrupadas por Centro de Custo"
            )
            fig_cc.update_traces(textposition='outside')
            st.plotly_chart(fig_cc, use_container_width=True)
        else:
            st.info("Não há dados de Centro de Custo para os filtros selecionados.")
        
        st.divider()

        # --- Gráfico 2: Despesas por Conta Bancária ---
        st.markdown("#### Total por Conta Bancária")
        df_cb = df_filtrado.groupby('conta_bancaria')['valor_corrigido'].sum().reset_index()
        df_cb = df_cb[df_cb['valor_corrigido'] > 0].sort_values('valor_corrigido', ascending=True)

        if not df_cb.empty:
            fig_cb = px.bar(
                df_cb,
                x='valor_corrigido',
                y='conta_bancaria',
                orientation='h',
                text=df_cb['valor_corrigido'].apply(formatar_reais),
                labels={'valor_corrigido': 'Valor Total (R$)', 'conta_bancaria': 'Conta Bancária'},
                title="Despesas Agrupadas por Conta Bancária"
            )
            fig_cb.update_traces(textposition='outside', marker_color='#ff7f0e')
            st.plotly_chart(fig_cb, use_container_width=True)
        else:
            st.info("Não há dados de Conta Bancária para os filtros selecionados.")
            
        st.divider()

        # --- Gráfico 3: Despesas por Unidade de Negócio ---
        st.markdown("#### Total por Unidade de Negócio")
        df_un = df_filtrado.groupby('unidade_negocio')['valor_corrigido'].sum().reset_index()
        df_un = df_un[df_un['valor_corrigido'] > 0].sort_values('valor_corrigido', ascending=True)

        if not df_un.empty:
            fig_un = px.bar(
                df_un,
                x='valor_corrigido',
                y='unidade_negocio',
                orientation='h',
                text=df_un['valor_corrigido'].apply(formatar_reais),
                labels={'valor_corrigido': 'Valor Total (R$)', 'unidade_negocio': 'Unidade de Negócio'},
                title="Despesas Agrupadas por Unidade de Negócio"
            )
            fig_un.update_traces(textposition='outside', marker_color='#2ca02c')
            st.plotly_chart(fig_un, use_container_width=True)
        else:
            st.info("Não há dados de Unidade de Negócio para os filtros selecionados.")
            
        st.divider()
            
        # --- Gráfico 4: Despesas por Unidade Estratégica ---
        st.markdown("#### Total por Unidade Estratégica")
        df_ue = df_filtrado.groupby('unidade_estrategica')['valor_corrigido'].sum().reset_index()
        df_ue = df_ue[df_ue['valor_corrigido'] > 0].sort_values('valor_corrigido', ascending=True)

        if not df_ue.empty:
            fig_ue = px.bar(
                df_ue,
                x='valor_corrigido',
                y='unidade_estrategica',
                orientation='h',
                text=df_ue['valor_corrigido'].apply(formatar_reais),
                labels={'valor_corrigido': 'Valor Total (R$)', 'unidade_estrategica': 'Unidade Estratégica'},
                title="Despesas Agrupadas por Unidade Estratégica"
            )
            fig_ue.update_traces(textposition='outside', marker_color='#d62728')
            st.plotly_chart(fig_ue, use_container_width=True)
        else:
            st.info("Não há dados de Unidade Estratégica para os filtros selecionados.")

    else:
        st.warning("Não há dados para os filtros selecionados para gerar os gráficos.")

    # ==============================================================================
    # CONTAS A PAGAR POR VENCIMENTO
    # Esta análise usa filtros independentes, respeitando apenas a seleção de EMPRESA.
    # ==============================================================================
    st.divider()
    st.header("🗓️ Análise de Contas a Pagar (por Vencimento)")

    # --- 1. FILTROS INDEPENDENTES PARA ESTA ANÁLISE ---
    # O DataFrame base é o 'df_filtrado_empresa', que já respeita o filtro da sidebar.
    base_df_apagar = df_para_opcoes.copy()

    df_apagar = base_df_apagar[base_df_apagar['situacao'].isin(['Em Atraso', 'A Vencer'])]

    # --- 1. FILTROS INDEPENDENTES DENTRO DE UM EXPANDER ---
    with st.expander("Aplicar Filtros para a Análise de Contas a Pagar (Os Filtros de Previsão de Vencimento são independentes da Análise Geral)", expanded=True):
        col_filtro1, col_filtro2, col_filtro3 = st.columns(3)

        # --- Filtro de Data de Vencimento com Mês Atual como Padrão ---
        with col_filtro1:
            hoje_aware = pd.Timestamp.now(tz=TIMEZONE).date()
            data_min_venc = df_apagar['data_vencimento_parcela'].min().date() if not df_apagar.empty else hoje_aware
            data_max_venc = df_apagar['data_vencimento_parcela'].max().date() if not df_apagar.empty else hoje_aware

            primeiro_dia_mes_atual = hoje_aware.replace(day=1)
            ultimo_dia_mes_atual_ts = (primeiro_dia_mes_atual + pd.DateOffset(months=1)) - pd.DateOffset(days=1)
            
            # Garante que data_inicio esteja dentro do range válido
            data_inicio_padrao = max(primeiro_dia_mes_atual, data_min_venc)
            # Garante que data_fim esteja dentro do range válido
            data_fim_padrao = min(ultimo_dia_mes_atual_ts.date(), data_max_venc)
            # Se data_inicio for maior que data_fim, ajusta para o mínimo
            if data_inicio_padrao > data_fim_padrao:
                data_inicio_padrao = data_min_venc
                data_fim_padrao = data_max_venc
            
            periodo_vencimento = st.date_input(
                "Período de Vencimento:",
                value=[data_inicio_padrao, data_fim_padrao],
                min_value=data_min_venc, max_value=data_max_venc,
                key="filtro_vencimento_apagar"
            )
        
        # --- NOVO FILTRO: Situação ---
        with col_filtro2:
            situacao_list = df_apagar['situacao'].dropna().unique().tolist()
            situacao_selecionada = st.multiselect(
                "Situação da Parcela:",
                options=sorted(situacao_list),
                default=situacao_list, # Padrão: todas as situações de não pagos
                key="filtro_situacao_apagar"
            )

        # --- NOVO FILTRO: Status da Parcela ---
        with col_filtro3:
            status_list = df_apagar['status_parcela'].dropna().unique().tolist()
            status_selecionado = st.multiselect(
                "Status da Parcela:",
                options=sorted(status_list),
                default=["A pagar", "Aprovado"], # Padrão: todos os status de parcelas
                key="filtro_status_apagar"
            )
            
        # Filtro de Centro de Custo (movido para dentro do expander)
        cc_list_apagar = base_df_apagar['centro_custo'].dropna().unique().tolist()
        cc_selecionado_apagar = st.multiselect(
            "Centro de Custo:",
            options=sorted(cc_list_apagar),
            default=cc_list_apagar,
            key="filtro_cc_apagar"
        )

        conta_lista = base_df_apagar['conta_bancaria'].dropna().unique().tolist()
        contas_selecionadas_apagar = st.multiselect(
            "Conta Bancária:",
            options=sorted(conta_lista),
            default=conta_lista,
            key="filtro_conta_apagar"
        )

    # --- Aplicação dos Filtros da Seção ---
    df_apagar_filtrado = pd.DataFrame() # Inicia um DF vazio
    if len(periodo_vencimento) == 2:
        inicio_venc_aware = pd.Timestamp(periodo_vencimento[0], tz=TIMEZONE)
        fim_venc_aware = pd.Timestamp(periodo_vencimento[1], tz=TIMEZONE) + pd.Timedelta(days=1)
        
        df_apagar_filtrado = df_apagar[
            (df_apagar['data_vencimento_parcela'] >= inicio_venc_aware) &
            (df_apagar['data_vencimento_parcela'] < fim_venc_aware) &
            (df_apagar['centro_custo'].isin(cc_selecionado_apagar)) &
            (df_apagar['situacao'].isin(situacao_selecionada)) &
            (df_apagar['status_parcela'].isin(status_selecionado)) &
            (df_apagar['conta_bancaria'].isin(contas_selecionadas_apagar))
        ]

    # --- EXIBIÇÃO DOS KPIs E TABELA ---
    if not df_apagar_filtrado.empty:
        valor_vencido = df_apagar_filtrado[df_apagar_filtrado['situacao'] == 'Em Atraso']['valor_corrigido'].sum()
        valor_a_vencer = df_apagar_filtrado[df_apagar_filtrado['situacao'] == 'A Vencer']['valor_corrigido'].sum()
        total_apagar = df_apagar_filtrado['valor_corrigido'].sum()

        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("Total a Pagar", formatar_reais(total_apagar))
        kpi2.metric("Valor Vencido (Em Atraso)", formatar_reais(valor_vencido))
        kpi3.metric("A Vencer no Período", formatar_reais(valor_a_vencer))

        st.divider()
        
        st.markdown("#### Detalhamento das Contas")
        tabela_apagar = df_apagar_filtrado[[
            'pedido_compra_id', 'parcelas_de', 'fornecedor', 'data_vencimento_parcela', 
            'situacao', 'status_parcela', 'descricao_pedido_compra', 
            'unidade_negocio', 'valor_corrigido'
        ]].sort_values(by='data_vencimento_parcela')  # Ordena por vencimento

        tabela_apagar.rename(columns={
            'pedido_compra_id': 'ID Pedido',
            'parcelas_de': 'Parcela',
            'data_vencimento_parcela': 'Vencimento',
            'status_parcela': 'Status',
            'descricao_pedido_compra': 'Histórico',
            'unidade_negocio': 'Unidade de Negócio',
            'valor_corrigido': 'Valor (R$)'
        }, inplace=True)

        st.dataframe(
            tabela_apagar,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Valor (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                "Vencimento": st.column_config.DateColumn(format="DD/MM/YYYY")
            }
        )
        
    else:
        st.info("Não há contas a pagar para os filtros selecionados.")
