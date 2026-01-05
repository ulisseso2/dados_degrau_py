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
    df2 = carregar_dados("consultas/contas/movimento_caixa.sql")
    df3 = carregar_dados("consultas/contas/contas_bancarias.sql")


    # Converte para datetime, trata erros e ATRIBUI o fuso horário correto
    df['data_pagamento_parcela'] = pd.to_datetime(df['data_pagamento_parcela'], errors='coerce').dt.tz_localize(TIMEZONE, ambiguous='infer')
    df['data_vencimento_parcela'] = pd.to_datetime(df['data_vencimento_parcela'], errors='coerce').dt.tz_localize(TIMEZONE, ambiguous='infer') # 

    # --- Seção de Filtros na Barra Lateral ---
    st.sidebar.header("Filtros da Análise")

    # Filtro de Empresa
    empresas_list = df["empresa"].dropna().unique().tolist()
    empresa_selecionada = "Central"
    df_para_opcoes = df[df["empresa"] == empresa_selecionada]

    # Pega a data de "hoje" já com o fuso horário correto
    hoje_aware = pd.Timestamp.now(tz=TIMEZONE).date()
    
    if df_para_opcoes.empty:
        # Se não houver dados, usa um intervalo padrão
        data_min_geral = hoje_aware
        data_max_geral = hoje_aware
        data_inicio_padrao = hoje_aware
        data_fim_padrao = hoje_aware
    else:
        data_min_geral = df_para_opcoes['data_pagamento_parcela'].min().date()
        data_max_geral = df_para_opcoes['data_pagamento_parcela'].max().date()
        
        # Calcula primeiro e último dia do mês atual
        primeiro_dia_mes_atual = hoje_aware.replace(day=1)
        ultimo_dia_mes_atual_ts = (primeiro_dia_mes_atual + pd.DateOffset(months=1)) - pd.DateOffset(days=1)
        ultimo_dia_mes_atual = ultimo_dia_mes_atual_ts.date()
        
        # Verifica se há dados no mês atual
        if data_max_geral >= primeiro_dia_mes_atual:
            # Se há dados no mês atual, usa o mês atual como padrão
            data_inicio_padrao = max(primeiro_dia_mes_atual, data_min_geral)
            data_fim_padrao = min(ultimo_dia_mes_atual, data_max_geral)
        else:
            # Se não há dados no mês atual, usa o último mês com dados
            # Encontra o primeiro e último dia do mês da data_max_geral
            primeiro_dia_ultimo_mes = data_max_geral.replace(day=1)
            ultimo_dia_ultimo_mes_ts = (primeiro_dia_ultimo_mes + pd.DateOffset(months=1)) - pd.DateOffset(days=1)
            ultimo_dia_ultimo_mes = ultimo_dia_ultimo_mes_ts.date()
            
            data_inicio_padrao = max(primeiro_dia_ultimo_mes, data_min_geral)
            data_fim_padrao = min(ultimo_dia_ultimo_mes, data_max_geral)
        
        # Validação final: garante que início não seja posterior ao fim
        if data_inicio_padrao > data_fim_padrao:
            data_inicio_padrao = data_fim_padrao
    
    periodo = st.sidebar.date_input("Período de Pagamento:", value=[data_inicio_padrao, data_fim_padrao], min_value=data_min_geral, max_value=data_max_geral)

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
            # Valida se o período tem exatamente 2 datas
            if len(periodo) != 2:
                st.warning("Por favor, selecione um período com data de início e fim.")
                st.stop()
            
            # Valida se as datas são válidas
            if periodo[0] > periodo[1]:
                st.error("A data de início deve ser anterior à data de fim.")
                st.stop()
            
            data_inicio_aware = pd.Timestamp(periodo[0], tz=TIMEZONE)
            data_fim_aware = pd.Timestamp(periodo[1], tz=TIMEZONE) + pd.Timedelta(days=1)
    except (IndexError, TypeError, ValueError) as e:
            # Caso o usuário limpe o campo de data, evita o erro
            st.warning("Por favor, selecione um período de datas válido.")
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
                .agg(valor_total=("valor_corrigido", "sum"),
                     data_pagamento_parcela=("data_pagamento_parcela", "max"))
                .reset_index()
            )

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
                header_name="Histórico",
                minWidth=200
            )
            
            gb.configure_column(
                field="data_pagamento_parcela",
                header_name="Data de Pagamento",
                type=["dateColumnFilter", "customDateTimeFormat"],
                custom_format_string='dd/MM/yyyy',
                minWidth=150
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
                "headerName": "Centro de Custo / Categoria",
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
            
            # Remove timezone e converte para apenas data (sem hora)
            if 'data_pagamento_parcela' in tabela_export.columns:
                tabela_export['data_pagamento_parcela'] = tabela_export['data_pagamento_parcela'].dt.tz_localize(None).dt.date
                
            # Cria buffer para o Excel
            buffer = io.BytesIO()
            with ExcelWriter(buffer, engine='xlsxwriter') as writer:
                # Exporta a tabela principal
                tabela_export.to_excel(
                    writer, 
                    index=False, 
                    sheet_name='Despesas Detalhadas',
                    columns=["centro_custo", "categoria_pedido_compra", "descricao_pedido_compra", "valor_total", "data_pagamento_parcela"]
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
    else:
        st.info("Nenhum dado encontrado para os filtros selecionados.")

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

    df_apagar = base_df_apagar[base_df_apagar['situacao'].isin(['Em Atraso', 'A Vencer', 'Pago Atrasado', 'Pago em dia'])]

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
                min_value=data_min_venc,
                max_value=data_max_venc,
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
            # Garante que apenas valores existentes sejam usados como padrão
            default_status = [s for s in ["A pagar", "Aprovado"] if s in status_list]
            if not default_status:  # Se nenhum dos valores padrão existe, usa todos
                default_status = status_list
            status_selecionado = st.multiselect(
                "Status da Parcela:",
                options=sorted(status_list),
                default=default_status,
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
        total_pago = df_apagar_filtrado[df_apagar_filtrado['situacao'].isin(['Pago Atrasado', 'Pago em dia'])]['valor_corrigido'].sum()

        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("Total a Pagar", formatar_reais(total_apagar))
        kpi2.metric("Valor Vencido (Em Atraso)", formatar_reais(valor_vencido))
        kpi3.metric("A Vencer no Período", formatar_reais(valor_a_vencer))
        kpi4.metric("Pago no Período", formatar_reais(total_pago))

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
        
        # --- EXPORTAÇÃO PARA EXCEL ---
        st.divider()
        
        # Preparar dados para exportação
        tabela_apagar_export = df_apagar_filtrado[[
            'pedido_compra_id', 'parcelas_de', 'fornecedor', 'data_vencimento_parcela', 
            'situacao', 'status_parcela', 'descricao_pedido_compra', 
            'centro_custo', 'unidade_negocio', 'valor_corrigido'
        ]].copy()
        
        # Remover timezone e converter para data
        tabela_apagar_export['data_vencimento_parcela'] = tabela_apagar_export['data_vencimento_parcela'].dt.tz_localize(None).dt.date
        
        # Renomear colunas para exportação
        tabela_apagar_export.rename(columns={
            'pedido_compra_id': 'ID Pedido',
            'parcelas_de': 'Parcela',
            'data_vencimento_parcela': 'Vencimento',
            'status_parcela': 'Status',
            'situacao': 'Situação',
            'descricao_pedido_compra': 'Histórico',
            'centro_custo': 'Centro de Custo',
            'unidade_negocio': 'Unidade de Negócio',
            'valor_corrigido': 'Valor (R$)'
        }, inplace=True)
        
        # Ordenar por vencimento
        tabela_apagar_export = tabela_apagar_export.sort_values(by='Vencimento')
        
        # Criar buffer para o Excel
        buffer_apagar = io.BytesIO()
        with ExcelWriter(buffer_apagar, engine='xlsxwriter') as writer:
            # Exportar tabela principal
            tabela_apagar_export.to_excel(writer, index=False, sheet_name='Contas a Pagar')
            
            # Adicionar aba com resumo por situação
            resumo_situacao = df_apagar_filtrado.groupby('situacao')['valor_corrigido'].sum().reset_index()
            resumo_situacao.rename(columns={'situacao': 'Situação', 'valor_corrigido': 'Valor Total (R$)'}, inplace=True)
            resumo_situacao.to_excel(writer, index=False, sheet_name='Resumo por Situação')
            
            # Adicionar aba com resumo por fornecedor
            resumo_fornecedor = df_apagar_filtrado.groupby('fornecedor')['valor_corrigido'].sum().reset_index()
            resumo_fornecedor = resumo_fornecedor.sort_values('valor_corrigido', ascending=False)
            resumo_fornecedor.rename(columns={'fornecedor': 'Fornecedor', 'valor_corrigido': 'Valor Total (R$)'}, inplace=True)
            resumo_fornecedor.to_excel(writer, index=False, sheet_name='Resumo por Fornecedor')
        
        buffer_apagar.seek(0)
        st.download_button(
            label="📥 Exportar Contas a Pagar para Excel",
            data=buffer_apagar,
            file_name=f"contas_apagar_{periodo_vencimento[0].strftime('%Y%m%d')}_{periodo_vencimento[1].strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="Clique para baixar os dados em formato Excel com abas detalhadas"
        )
        
    else:
        st.info("Não há contas a pagar para os filtros selecionados.")


    # ==============================================================================
    # ANÁLISE DE MOVIMENTO DE CAIXA (df2)
    # Esta análise usa filtros independentes, respeitando apenas a seleção de EMPRESA.
    # ==============================================================================
    st.divider()
    st.header("💳 Análise de Movimento de Caixa")
    st.markdown("*Esta seção possui filtros independentes da análise principal, exceto o filtro de empresa.*")
    
    # --- SALDOS ATUAIS DAS CONTAS BANCÁRIAS (SEM FILTROS) ---
    st.subheader("💰 Saldos Atuais das Contas Bancárias")
    
    # Filtrar apenas pela empresa selecionada
    df_saldos = df3[df3['empresa'] == empresa_selecionada].copy()
    
    if not df_saldos.empty:
        # Formatar valores para exibição
        df_saldos_display = df_saldos[['conta_bancaria', 'saldo_atual']].copy()
        df_saldos_display['saldo_atual'] = df_saldos_display['saldo_atual'].apply(formatar_reais)
        df_saldos_display.rename(columns={
            'conta_bancaria': 'Conta Bancária',
            'saldo_atual': 'Saldo Atual'
        }, inplace=True)
        
        # Exibir tabela
        st.dataframe(df_saldos_display, use_container_width=True, hide_index=True)
        
        # Mostrar total geral
        total_saldos = df_saldos['saldo_atual'].sum()
        st.markdown(f"**Saldo Total:** {formatar_reais(total_saldos)}")
    else:
        st.info("Não há informações de saldo para a empresa selecionada.")
    
    st.divider()
    
    # Preparar dados base - apenas filtrado por empresa
    df2['data'] = pd.to_datetime(df2['data'], errors='coerce')
    df2['valor'] = pd.to_numeric(df2['valor'], errors='coerce')
    
    df_movimento_base = df2[df2["empresa"] == empresa_selecionada].copy()
    
    # --- FILTROS INDEPENDENTES ---
    st.subheader("Filtros")
    col_mov1, col_mov2, col_mov3 = st.columns(3)
    
    with col_mov1:
        # Filtro de Conta Bancária
        contas_movimento = df_movimento_base['conta_bancaria'].dropna().unique().tolist()
        contas_movimento_selecionadas = st.multiselect(
            "Conta Bancária:",
            options=sorted(contas_movimento),
            default=sorted(contas_movimento),
            key="filtro_conta_movimento"
        )
    
    with col_mov2:
        # Filtro de Data - INDEPENDENTE
        # Calcula hoje de forma independente
        hoje_movimento = pd.Timestamp.now(tz=TIMEZONE).date()
        
        # Obtém o range de datas disponível nos dados de movimento
        data_min_mov = df_movimento_base['data'].min().date() if not df_movimento_base['data'].isna().all() else hoje_movimento
        data_max_mov = df_movimento_base['data'].max().date() if not df_movimento_base['data'].isna().all() else hoje_movimento
        
        # Calcula o padrão (mês atual), mas garante que esteja dentro do range disponível
        primeiro_dia_mes = hoje_movimento.replace(day=1)
        ultimo_dia_mes = (primeiro_dia_mes + pd.DateOffset(months=1)) - pd.DateOffset(days=1)
        
        # Ajusta o início para estar dentro do range disponível
        data_inicio_mov_padrao = max(primeiro_dia_mes, data_min_mov)
        # Ajusta o fim para estar dentro do range disponível
        data_fim_mov_padrao = min(ultimo_dia_mes.date(), data_max_mov)
        
        # Se o início calculado for maior que o fim, usa o range completo disponível
        if data_inicio_mov_padrao > data_fim_mov_padrao:
            data_inicio_mov_padrao = data_min_mov
            data_fim_mov_padrao = data_max_mov
        
        periodo_movimento = st.date_input(
            "Período:",
            value=[data_inicio_mov_padrao, data_fim_mov_padrao],
            min_value=data_min_mov,
            max_value=data_max_mov,
            key="filtro_data_movimento"
        )
    
    with col_mov3:
        # Filtro de Tipo
        tipos_movimento = df_movimento_base['tipo'].dropna().unique().tolist()
        tipos_movimento_selecionados = st.multiselect(
            "Tipo de Movimento:",
            options=sorted(tipos_movimento),
            default=sorted(tipos_movimento),
            key="filtro_tipo_movimento"
        )
    
    # Aplicar filtros
    df_movimento_filtrado = pd.DataFrame()
    # Proteger o campo de data - verificar se foi selecionado um período válido
    if len(periodo_movimento) == 2 and periodo_movimento[0] is not None and periodo_movimento[1] is not None:
        data_inicio_mov = pd.Timestamp(periodo_movimento[0])
        data_fim_mov = pd.Timestamp(periodo_movimento[1]) + pd.Timedelta(days=1)
        
        df_movimento_filtrado = df_movimento_base[
            (df_movimento_base['data'] >= data_inicio_mov) &
            (df_movimento_base['data'] < data_fim_mov) &
            (df_movimento_base['conta_bancaria'].isin(contas_movimento_selecionadas)) &
            (df_movimento_base['tipo'].isin(tipos_movimento_selecionados))
        ]
    else:
        st.warning("⚠️ Por favor, selecione um período válido (data inicial e data final).")
    
    # --- EXIBIÇÃO DOS DADOS ---
    if not df_movimento_filtrado.empty:
        # --- KPIs NO TOPO COM TRANSFERÊNCIAS SEPARADAS ---
        st.subheader("Resumo do Período")
        
        # Calcular saldo anterior (movimentações antes do período selecionado)
        data_inicio_mov = pd.Timestamp(periodo_movimento[0])
        
        # Filtrar movimentações anteriores ao período para calcular saldo anterior
        df_anterior = df_movimento_base[
            (df_movimento_base['data'] < data_inicio_mov) &
            (df_movimento_base['conta_bancaria'].isin(contas_movimento_selecionadas))
        ]
        saldo_anterior = df_anterior['valor'].sum()
        
        # Calcular métricas do período separando transferências
        df_entradas = df_movimento_filtrado[(df_movimento_filtrado['valor'] > 0) & (df_movimento_filtrado['tipo'] != 'Transferência')]
        df_saidas = df_movimento_filtrado[(df_movimento_filtrado['valor'] < 0) & (df_movimento_filtrado['tipo'] != 'Transferência')]
        df_transferencias_entrada = df_movimento_filtrado[(df_movimento_filtrado['valor'] > 0) & (df_movimento_filtrado['tipo'] == 'Transferência')]
        df_transferencias_saida = df_movimento_filtrado[(df_movimento_filtrado['valor'] < 0) & (df_movimento_filtrado['tipo'] == 'Transferência')]
        
        total_entradas = df_entradas['valor'].sum()
        total_saidas = abs(df_saidas['valor'].sum())
        total_transf_entrada = df_transferencias_entrada['valor'].sum()
        total_transf_saida = abs(df_transferencias_saida['valor'].sum())
        saldo_periodo = (total_entradas + total_transf_entrada) - (total_saidas + total_transf_saida)
        
        # Calcular saldo atual (saldo anterior + movimentações do período)
        saldo_atual = saldo_anterior + saldo_periodo
        
        # Exibir KPIs de saldo em destaque
        col_saldo1, col_saldo2, col_saldo3 = st.columns(3)
        col_saldo1.metric("💰 Saldo Anterior", formatar_reais(saldo_anterior))
        col_saldo2.metric("📊 Movimentação do Período", formatar_reais(saldo_periodo), 
                         delta=formatar_reais(saldo_periodo) if saldo_periodo != 0 else None)
        col_saldo3.metric("💵 Saldo Atual", formatar_reais(saldo_atual),
                         delta=formatar_reais(saldo_periodo) if saldo_periodo != 0 else None)
        
        st.divider()
        
        # Exibir detalhes das movimentações
        col_kpi1, col_kpi2 = st.columns(2)
        col_kpi1.metric("Apenas Entradas", formatar_reais(total_entradas))
        col_kpi2.metric("Apenas Saídas", formatar_reais(total_saidas))
        col_kpi3, col_kpi4 = st.columns(2)
        col_kpi3.metric("Transferências entradas", formatar_reais(total_transf_entrada))
        col_kpi4.metric("Transferências saídas", formatar_reais(total_transf_saida))
        
        st.divider()
        
        # --- EXTRATO DETALHADO (como extrato bancário) ---
        st.subheader("Extrato Detalhado de Movimentações")
        
        # Preparar dados para o extrato
        df_extrato = df_movimento_filtrado.copy()
        df_extrato = df_extrato.sort_values('data')
        
        # Criar colunas de entrada e saída
        df_extrato['Entrada'] = df_extrato['valor'].apply(lambda x: x if x > 0 else None)
        df_extrato['Saída'] = df_extrato['valor'].apply(lambda x: abs(x) if x < 0 else None)
        
        # Calcular saldo após cada transação
        df_extrato['Saldo'] = saldo_anterior + df_extrato['valor'].cumsum()
        
        # Selecionar e renomear colunas para exibição
        extrato_display = df_extrato[['data', 'tipo', 'descricao', 'fornecedor', 'conta_bancaria', 'Entrada', 'Saída', 'Saldo']].copy()
        
        # Calcular totais ANTES de formatar (valores numéricos)
        total_entradas_extrato = extrato_display['Entrada'].sum()
        total_saidas_extrato = extrato_display['Saída'].sum()
        saldo_final_extrato = extrato_display['Saldo'].iloc[-1] if len(extrato_display) > 0 else saldo_anterior
        
        # Formatar data
        extrato_display['data'] = extrato_display['data'].dt.strftime('%d/%m/%Y')
        
        # Formatar valores monetários
        extrato_display['Entrada'] = extrato_display['Entrada'].apply(lambda x: formatar_reais(x) if pd.notna(x) else '-')
        extrato_display['Saída'] = extrato_display['Saída'].apply(lambda x: formatar_reais(x) if pd.notna(x) else '-')
        extrato_display['Saldo'] = extrato_display['Saldo'].apply(lambda x: formatar_reais(x) if pd.notna(x) else '-')
        
        # Renomear colunas
        extrato_display.rename(columns={
            'data': 'Data',
            'tipo': 'Tipo',
            'descricao': 'Descrição',
            'fornecedor': 'Fornecedor',
            'conta_bancaria': 'Conta Bancária'
        }, inplace=True)
        
        # Exibir tabela com linha de totais
        # Adicionar linha de totais (usando os totais calculados anteriormente)
        linha_total = pd.DataFrame([{
            'Data': 'TOTAL',
            'Tipo': '',
            'Descrição': '',
            'Fornecedor': '',
            'Conta Bancária': '',
            'Entrada': formatar_reais(total_entradas_extrato),
            'Saída': formatar_reais(total_saidas_extrato),
            'Saldo': formatar_reais(saldo_final_extrato)
        }])
        
        extrato_com_total = pd.concat([extrato_display, linha_total], ignore_index=True)
        st.dataframe(extrato_com_total, use_container_width=True, hide_index=True)
        
        # Exportar extrato
        st.divider()
        
        # Calcular métricas para o PDF
        df_entradas_pdf = df_movimento_filtrado[(df_movimento_filtrado['valor'] > 0) & (df_movimento_filtrado['tipo'] != 'Transferência')]
        df_saidas_pdf = df_movimento_filtrado[(df_movimento_filtrado['valor'] < 0) & (df_movimento_filtrado['tipo'] != 'Transferência')]
        df_transferencias_entrada_pdf = df_movimento_filtrado[(df_movimento_filtrado['valor'] > 0) & (df_movimento_filtrado['tipo'] == 'Transferência')]
        df_transferencias_saida_pdf = df_movimento_filtrado[(df_movimento_filtrado['valor'] < 0) & (df_movimento_filtrado['tipo'] == 'Transferência')]
        
        total_entradas_pdf = df_entradas_pdf['valor'].sum()
        total_saidas_pdf = abs(df_saidas_pdf['valor'].sum())
        total_transf_entrada_pdf = df_transferencias_entrada_pdf['valor'].sum()
        total_transf_saida_pdf = abs(df_transferencias_saida_pdf['valor'].sum())
        saldo_periodo_pdf = total_entradas_pdf - total_saidas_pdf
        
        col_export1, col_export2 = st.columns(2)
        
        with col_export1:
            # Exportar Excel
            buffer_movimento = io.BytesIO()
            with ExcelWriter(buffer_movimento, engine='xlsxwriter') as writer:
                # Exportar extrato detalhado
                df_extrato_export = df_movimento_filtrado[['data', 'tipo', 'descricao', 'fornecedor', 'conta_bancaria', 'valor']].copy()
                df_extrato_export['data'] = df_extrato_export['data'].dt.date
                df_extrato_export = df_extrato_export.sort_values('data')
                
                # Criar colunas de entrada e saída para o Excel
                df_extrato_export['Entrada'] = df_extrato_export['valor'].apply(lambda x: x if x > 0 else None)
                df_extrato_export['Saída'] = df_extrato_export['valor'].apply(lambda x: abs(x) if x < 0 else None)
                
                # Calcular saldo após cada transação
                df_extrato_export['Saldo'] = saldo_anterior + df_extrato_export['valor'].cumsum()
                
                df_extrato_export = df_extrato_export.drop('valor', axis=1)
                
                df_extrato_export.to_excel(writer, index=False, sheet_name='Extrato Detalhado')
            
            buffer_movimento.seek(0)
            st.download_button(
                label="📥 Exportar Excel",
                data=buffer_movimento,
                file_name=f"extrato_movimento_{periodo_movimento[0].strftime('%Y%m%d')}_{periodo_movimento[1].strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_movimento_excel"
            )
        
        with col_export2:
            # Exportar PDF
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import cm
            from reportlab.lib.enums import TA_CENTER, TA_LEFT
            from datetime import datetime
            
            buffer_pdf = io.BytesIO()
            
            # Criar documento PDF em retrato
            doc = SimpleDocTemplate(buffer_pdf, pagesize=A4, topMargin=1*cm, bottomMargin=1*cm, leftMargin=1*cm, rightMargin=1*cm)
            elements = []
            styles = getSampleStyleSheet()
            
            # Estilo para cabeçalho
            style_header = ParagraphStyle(
                'CustomHeader',
                parent=styles['Heading1'],
                fontSize=14,
                textColor=colors.HexColor('#1f77b4'),
                alignment=TA_CENTER,
                spaceAfter=12
            )
            
            style_info = ParagraphStyle(
                'CustomInfo',
                parent=styles['Normal'],
                fontSize=9,
                alignment=TA_LEFT,
                spaceAfter=6
            )
            
            # Cabeçalho do PDF
            elements.append(Paragraph("EXTRATO DE MOVIMENTAÇÕES BANCÁRIAS", style_header))
            elements.append(Spacer(1, 0.3*cm))
            
            # Informações do filtro e empresa
            periodo_str = f"{periodo_movimento[0].strftime('%d/%m/%Y')} a {periodo_movimento[1].strftime('%d/%m/%Y')}"
            contas_str = ", ".join(contas_movimento_selecionadas) if len(contas_movimento_selecionadas) <= 3 else f"{len(contas_movimento_selecionadas)} contas selecionadas"
            tipos_str = ", ".join(tipos_movimento_selecionados) if len(tipos_movimento_selecionados) <= 3 else f"{len(tipos_movimento_selecionados)} tipos selecionados"
            data_geracao = datetime.now().strftime('%d/%m/%Y às %H:%M')
            
            elements.append(Paragraph(f"<b>Empresa:</b> {empresa_selecionada}", style_info))
            elements.append(Paragraph(f"<b>Período:</b> {periodo_str}", style_info))
            elements.append(Paragraph(f"<b>Conta(s):</b> {contas_str}", style_info))
            elements.append(Paragraph(f"<b>Tipo(s):</b> {tipos_str}", style_info))
            elements.append(Paragraph(f"<b>Gerado em:</b> {data_geracao}", style_info))
            elements.append(Spacer(1, 0.3*cm))
            
            # Resumo dos movimentos
            elements.append(Paragraph("<b>RESUMO DOS MOVIMENTOS</b>", style_info))
            resumo_data = [
                ['Saldo Anterior', 'Entradas', 'Saídas', 'Transf. Entrada', 'Transf. Saída', 'Saldo Final'],
                [formatar_reais(saldo_anterior), formatar_reais(total_entradas_pdf), formatar_reais(total_saidas_pdf), 
                 formatar_reais(total_transf_entrada_pdf), formatar_reais(total_transf_saida_pdf), 
                 formatar_reais(saldo_atual)]
            ]
            
            resumo_table = Table(resumo_data, colWidths=[3*cm, 3*cm, 3*cm, 3*cm, 3*cm, 3*cm])
            resumo_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
            ]))
            elements.append(resumo_table)
            elements.append(Spacer(1, 0.4*cm))
            
            # Tabela de movimentações
            elements.append(Paragraph("<b>MOVIMENTAÇÕES DETALHADAS</b>", style_info))
            elements.append(Spacer(1, 0.2*cm))
            
            # Estilo para células da tabela
            style_cell = ParagraphStyle(
                'CellStyle',
                parent=styles['Normal'],
                fontSize=6,
                leading=7,
                wordWrap='CJK'
            )
            
            # Preparar dados da tabela
            table_data = [['Data', 'Tipo', 'Descrição', 'Fornecedor', 'Entrada', 'Saída', 'Saldo']]
            
            for _, row in extrato_com_total.iterrows():
                # Pular a linha de total pois será adicionada separadamente
                if row['Data'] == 'TOTAL':
                    continue
                
                # Converter descrição em Paragraph para quebra automática
                descricao_text = row['Descrição'] if pd.notna(row['Descrição']) and row['Descrição'] != '' else ''
                descricao_para = Paragraph(descricao_text, style_cell)
                
                # Converter fornecedor em Paragraph para quebra automática
                fornecedor_text = row['Fornecedor'] if pd.notna(row['Fornecedor']) and row['Fornecedor'] != '' else ''
                fornecedor_para = Paragraph(fornecedor_text, style_cell)
                    
                table_data.append([
                    row['Data'],
                    row['Tipo'][:10] if pd.notna(row['Tipo']) and row['Tipo'] != '' else '',
                    descricao_para,  # Usando Paragraph para quebra automática
                    fornecedor_para,  # Usando Paragraph para quebra automática
                    row['Entrada'] if row['Entrada'] != '-' else '-',
                    row['Saída'] if row['Saída'] != '-' else '-',
                    row['Saldo'] if row['Saldo'] != '-' else '-'
                ])
            
            # Adicionar linha de totais (já formatados na tabela)
            linha_total_pdf = extrato_com_total[extrato_com_total['Data'] == 'TOTAL'].iloc[0]
            table_data.append(['TOTAL', '', '', '', linha_total_pdf['Entrada'], linha_total_pdf['Saída'], linha_total_pdf['Saldo']])
            
            # Criar tabela com larguras ajustadas para retrato (descrição maior)
            col_widths = [1.6*cm, 1.5*cm, 5.5*cm, 2.5*cm, 2*cm, 2*cm, 2.4*cm]
            table = Table(table_data, colWidths=col_widths)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (4, 0), (6, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 7),
                ('FONTSIZE', (0, 1), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('TOPPADDING', (0, 0), (-1, 0), 6),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.lightgrey]),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#ffeb99')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('WORDWRAP', (2, 1), (2, -1), True),  # Quebra de linha na coluna Descrição
                ('WORDWRAP', (3, 1), (3, -1), True),  # Quebra de linha na coluna Fornecedor
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),  # Alinhamento vertical no topo
            ]))
            elements.append(table)
            
            # Gerar PDF
            doc.build(elements)
            buffer_pdf.seek(0)
            
            st.download_button(
                label="📄 Exportar PDF",
                data=buffer_pdf,
                file_name=f"extrato_movimento_{periodo_movimento[0].strftime('%Y%m%d')}_{periodo_movimento[1].strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                key="download_movimento_pdf"
            )
        
    else:
        st.info("Não há dados de movimento para os filtros selecionados.")

    # --- GRÁFICO DE PIZZA: Tipo x Valor ---
    # Só mostrar gráficos se houver dados filtrados
    if not df_movimento_filtrado.empty:
        st.subheader("Distribuição por Tipo de Movimento")
        
        # Preparar dados para o gráfico de pizza (valores absolutos)
        df_pizza = df_movimento_filtrado.copy()
        df_pizza['valor_abs'] = df_pizza['valor'].abs()
        df_tipo_valor = df_pizza.groupby('tipo')['valor_abs'].sum().reset_index()
        
        if not df_tipo_valor.empty:
            fig_pizza_tipo = px.pie(
                df_tipo_valor,
                names='tipo',
                values='valor_abs',
                title='Distribuição de Valores por Tipo de Movimento',
                hole=0.3  # Gráfico de rosca
            )
            fig_pizza_tipo.update_traces(
                textinfo='percent+value',
                texttemplate='%{percent:.1%}<br>R$ %{value:,.2f}'
            )
            st.plotly_chart(fig_pizza_tipo, use_container_width=True)
        else:
            st.info("Não há dados para exibir o gráfico de pizza.")
        
        st.divider()
        
        # --- GRÁFICO DE BARRAS EMPILHADAS: Contas x Tipo x Valor ---
        st.subheader("Movimentação por Conta Bancária e Tipo")
        
        # Preparar dados para o gráfico de barras
        df_barras = df_movimento_filtrado.copy()
        df_barras['valor_abs'] = df_barras['valor'].abs()
        df_conta_tipo = df_barras.groupby(['conta_bancaria', 'tipo'])['valor_abs'].sum().reset_index()
        
        if not df_conta_tipo.empty:
            fig_barras = px.bar(
                df_conta_tipo,
                x='conta_bancaria',
                y='valor_abs',
                color='tipo',
                title='Movimentação por Conta Bancária (Empilhado por Tipo)',
                labels={'valor_abs': 'Valor (R$)', 'conta_bancaria': 'Conta Bancária', 'tipo': 'Tipo'},
                barmode='stack',
                text_auto='.2s'
            )
            fig_barras.update_layout(
                xaxis_title="Conta Bancária",
                yaxis_title="Valor (R$)",
                legend_title="Tipo de Movimento"
            )
            st.plotly_chart(fig_barras, use_container_width=True)
        else:
            st.info("Não há dados para exibir o gráfico de barras.")
        
        st.divider()

