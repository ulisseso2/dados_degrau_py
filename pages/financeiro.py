import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder
from st_aggrid.shared import JsCode
from datetime import datetime
from utils.sql_loader import carregar_dados
import plotly.express as px
import io
from pandas import ExcelWriter

st.set_page_config(layout="wide")

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

# --- Seção de Filtros na Barra Lateral ---
st.sidebar.header("Filtros da Análise")

# Filtro de Empresa
empresas_list = df["empresa"].dropna().unique().tolist()
empresa_selecionada = st.sidebar.multiselect("Empresa:", empresas_list, default=empresas_list)

df_para_opcoes = df[df["empresa"].isin(empresa_selecionada)]

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
data_inicio_aware = pd.Timestamp(periodo[0], tz=TIMEZONE)
data_fim_aware = pd.Timestamp(periodo[1], tz=TIMEZONE) + pd.Timedelta(days=1)

df_filtrado = df[
    (df["empresa"].isin(empresa_selecionada)) &
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

st.divider() # Adiciona uma linha para separar as seções