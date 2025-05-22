import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder
from st_aggrid.shared import JsCode
from datetime import datetime

# Função para formatar valores monetários
def formatar_reais(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# Função principal
def main():
    # Carrega seus dados reais
    df = carregar_dados("consultas/contas/contas_a_pagar.sql")
    
    # Converte a coluna de data
    df['data_pagamento_parcela'] = pd.to_datetime(df['data_pagamento_parcela'])
    
    # --- SEÇÃO DE FILTROS --- (mantendo sua implementação original)
    st.sidebar.title("Filtros")
    
    # Filtros globais
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
        tabela_agrupada["valor_formatado"] = tabela_agrupada["valor_total"].apply(formatar_reais)
        
        # --- CONFIGURAÇÃO DA AG-GRID ---
        gb = GridOptionsBuilder()
        
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
            field="valor_formatado",
            header_name="Valor",
            type=["numericColumn"],
            aggFunc="sum"
        )
        
        # Configura o renderizador JavaScript para mostrar totais
        js_code = """
        function(params) { 
            if (params.node.group) {
                return params.node.key + ' - Total: ' + params.node.aggData.valor_formatado;
            }
            return params.value;
        }
        """
        
        # Configurações adicionais da grid
        grid_options = gb.build()
        grid_options["autoGroupColumnDef"] = {
            "minWidth": 300,
            "cellRendererParams": {
                "suppressCount": True,
                "innerRenderer": JsCode(js_code)
            }
        }
        grid_options["groupDefaultExpanded"] = 1  # Expande até o primeiro nível
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
        
        # --- TOTAIS CONSOLIDADOS ---
        st.subheader("Totais Consolidados")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Por Centro de Custo**")
            totais_cc = tabela_agrupada.groupby("centro_custo")["valor_total"].sum().reset_index()
            totais_cc["Total"] = totais_cc["valor_total"].apply(formatar_reais)
            st.dataframe(
                totais_cc[["centro_custo", "Total"]].sort_values("valor_total", ascending=False),
                hide_index=True,
                use_container_width=True
            )
        
        with col2:
            st.markdown("**Por Categoria**")
            totais_cat = tabela_agrupada.groupby(["centro_custo", "categoria_pedido_compra"])["valor_total"].sum().reset_index()
            totais_cat["Total"] = totais_cat["valor_total"].apply(formatar_reais)
            st.dataframe(
                totais_cat.sort_values("valor_total", ascending=False),
                hide_index=True,
                use_container_width=True
            )
        
        # --- GRÁFICO DE VISUALIZAÇÃO ---
        st.subheader("Distribuição das Despesas")
        
        try:
            import plotly.express as px
            
            # Gráfico de treemap
            fig = px.treemap(
                tabela_agrupada,
                path=['centro_custo', 'categoria_pedido_compra'],
                values='valor_total',
                color='centro_custo',
                title='Distribuição por Centro de Custo e Categoria'
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Gráfico de barras
            fig2 = px.bar(
                totais_cc.sort_values("valor_total", ascending=False),
                x='centro_custo',
                y='valor_total',
                title='Total por Centro de Custo',
                labels={'valor_total': 'Valor Total', 'centro_custo': 'Centro de Custo'}
            )
            st.plotly_chart(fig2, use_container_width=True)
            
        except ImportError:
            st.warning("Instale plotly (pip install plotly) para ver as visualizações gráficas.")
    
    else:
        st.warning("Nenhuma despesa encontrada com os filtros selecionados.")

# Substitua esta função pela sua implementação real de carregamento de dados
def carregar_dados(query_path):
    # Implemente aqui sua função que carrega os dados do SQL
    # Esta é apenas uma função placeholder
    return pd.DataFrame()

if __name__ == "__main__":
    main()