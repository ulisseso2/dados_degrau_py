import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder
from st_aggrid.shared import JsCode
from datetime import datetime
from utils.sql_loader import carregar_dados
# Função para formatar valores monetários
def formatar_reais(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
df = carregar_dados("consultas/contas/contas_a_pagar.sql")
# Função principal

df['data_pagamento_parcela'] = pd.to_datetime(df['data_pagamento_parcela'])
    
    # --- SEÇÃO DE FILTROS --- (mantendo sua implementação original)
st.sidebar.title("Filtros")

empresas = df["empresa"].dropna().unique().tolist()
empresa_selecionada = st.sidebar.multiselect("Selecione as empresas:", empresas, default=["Degrau"])
df_filtrado_empresa = df[df["empresa"].isin(empresa_selecionada)]
    
    # Filtro de período
hoje = datetime.today().date()
periodo = st.sidebar.date_input("Período de pagamentos:", [hoje.replace(day=1), hoje])
data_inicio = pd.to_datetime(periodo[0])
data_fim = pd.to_datetime(periodo[1]) + pd.Timedelta(days=1)

      # Filtros avançados
with st.sidebar.expander("Filtros Avançados"):
        # Unidades
        unidades_estrategicas = df_filtrado_empresa["unidade_estrategica"].dropna().unique().tolist()
        unidade_estrategica_selecionada = st.multiselect(
            "Selecione a unidade:", 
            unidades_estrategicas, 
            default=unidades_estrategicas
        )
        
        unidades_negocio = df_filtrado_empresa["unidade_negocio"].dropna().unique().tolist()
        unidade_negocio_selecionada = st.multiselect(
            "Selecione a unidade de Negócio:", 
            unidades_negocio, 
            default=unidades_negocio
        )
        
        # Centros de custo e categorias
        centros_custos = df_filtrado_empresa["centro_custo"].dropna().unique().tolist()
        centro_custo_selecionado = st.multiselect(
            "Selecione o Centro de Custo:", 
            centros_custos, 
            default=centros_custos
        )
        
        categorias_pedido_compra = df_filtrado_empresa["categoria_pedido_compra"].dropna().unique().tolist()
        categoria_pedido_compra_selecionada = st.multiselect(
            "Selecione a categoria:", 
            categorias_pedido_compra, 
            default=categorias_pedido_compra
        )
        
        # Filtro de contas bancárias (versão corrigida)
        st.write("Filtro de Contas Bancárias:")
        todas_contas = df['conta_bancaria'].dropna().unique().tolist()
        
        if "contas_bancarias_selecionadas" not in st.session_state:
            st.session_state.contas_bancarias_selecionadas = todas_contas.copy()
        
        todas_selecionadas = st.checkbox(
            "Selecionar Todas", 
            value=len(st.session_state.contas_bancarias_selecionadas) == len(todas_contas),
            key="select_all_accounts"
        )
        
        if todas_selecionadas:
            st.session_state.contas_bancarias_selecionadas = todas_contas.copy()
        elif len(st.session_state.contas_bancarias_selecionadas) == len(todas_contas):
            st.session_state.contas_bancarias_selecionadas = []
        
        for conta in todas_contas:
            checkbox = st.checkbox(
                conta,
                value=conta in st.session_state.contas_bancarias_selecionadas,
                key=f"check_{conta}"
            )
            
            if checkbox and conta not in st.session_state.contas_bancarias_selecionadas:
                st.session_state.contas_bancarias_selecionadas.append(conta)
            elif not checkbox and conta in st.session_state.contas_bancarias_selecionadas:
                st.session_state.contas_bancarias_selecionadas.remove(conta)
    
    # Aplicar todos os filtros
df_filtrado = df[
        (df["empresa"].isin(empresa_selecionada)) &
        (df["unidade_estrategica"].isin(unidade_estrategica_selecionada)) &
        (df["unidade_negocio"].isin(unidade_negocio_selecionada)) &
        (df["centro_custo"].isin(centro_custo_selecionado)) &
        (df["categoria_pedido_compra"].isin(categoria_pedido_compra_selecionada)) &
        (df["conta_bancaria"].isin(st.session_state.contas_bancarias_selecionadas)) &
        (df["data_pagamento_parcela"] >= data_inicio) &
        (df["data_pagamento_parcela"] < data_fim)
    ]
    
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
        grid_options["groupDefaultExpanded"] = 0  # Expande até o primeiro nível
        grid_options["groupIncludeFooter"] = True
        grid_options["groupIncludeTotalFooter"] = True
        
        # --- EXIBIÇÃO DA TABELA ---
        st.title("Análise de Despesas")
        
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