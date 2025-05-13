import sys
import os
import io
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime
import json
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode, JsCode
import numpy as np

from utils.sql_loader import carregar_dados  # Função com cache

st.title("Dashboard Financeiro")

# Carrega os dados com cache
df = carregar_dados("consultas/contas/contas_a_pagar.sql")

# Filtros globais
empresas = df["empresa"].dropna().unique().tolist()
empresa_selecionada = st.multiselect("Selecione as empresas:", empresas, default=["Degrau"])
df_filtrado_empresa = df[df["empresa"].isin(empresa_selecionada)]

# Filtro de período
hoje = datetime.today().date()
periodo = st.date_input("Período de vendas:", [hoje, hoje])

# Converter coluna de data
df['data_pagamento_parcela'] = pd.to_datetime(df['data_pagamento_parcela'])

# Filtros avançados: Unidades
with st.expander("Filtros Avançados: Unidades"):
    col1, col2 = st.columns(2)

    with col1:
        unidades_estrategicas = df_filtrado_empresa["unidade_estrategica"].dropna().unique().tolist()
        unidade_estrategica_selecionada = st.multiselect("Selecione a unidade:", unidades_estrategicas, default=unidades_estrategicas)
        df_filtrado_estrategica = df[df["unidade_estrategica"].isin(unidade_estrategica_selecionada)]
    
    with col2:
        unidades_negocio = df_filtrado_estrategica["unidade_negocio"].dropna().unique().tolist()
        unidade_negocio_selecionada = st.multiselect("Selecione a unidade de Negócio:", unidades_negocio, default=unidades_negocio)

# Filtros de categorias, custo e planos
with st.expander("Filtro Categorias / Custo / Planos"):
    col1, col2 = st.columns(2)

    with col1:
        centros_custos = df_filtrado_empresa["centro_custo"].dropna().unique().tolist()
        centro_custo_selecionado = st.multiselect("Selecione o Centro de Custo:", centros_custos, default=centros_custos)
        df_filtrado_centro_custo = df[df["centro_custo"].isin(centro_custo_selecionado)]

    
    with col2:
        categorias_pedido_compra = df_filtrado_centro_custo["categoria_pedido_compra"].dropna().unique().tolist()
        categoria_pedido_compra_selecionada = st.multiselect("Selecione a categoria:", categorias_pedido_compra, default=categorias_pedido_compra)
    

with st.expander("Filtro de Contas"):
    col1, col2 = st.columns(2)

    with col1:
        planos_contas = df_filtrado_empresa["plano_contas"].dropna().unique().tolist()
        plano_contas_selecionado = st.multiselect("Selecione o plano de contas:", planos_contas, default=planos_contas)

    with col2:
        todas_contas = df['conta_bancaria'].dropna().unique().tolist()
        
        if "contas_bancarias_selecionadas" not in st.session_state:
            st.session_state.contas_bancarias_selecionadas = todas_contas.copy()
        
        todas_selecionadas = st.checkbox(
            "Sele calibre Todas", 
            value=len(st.session_state.contas_bancarias_selecionadas) == len(todas_contas)
        )
        
        if todas_selecionadas:
            st.session_state.contas_bancarias_selecionadas = todas_contas.copy()
        else:
            if len(st.session_state.contas_bancarias_selecionadas) == len(todas_contas):
                st.session_state.contas_bancarias_selecionadas = []
        
        st.write("Selecione as contas bancárias:")
        cols = st.columns(1)
        
        for idx, conta in enumerate(todas_contas):
            with cols[idx % 1]:
                checkbox = st.checkbox(
                    conta,
                    value=conta in st.session_state.contas_bancarias_selecionadas,
                    key=f"check_{conta}"
                )

                if checkbox and conta not in st.session_state.contas_bancarias_selecionadas:
                    st.session_state.contas_bancarias_selecionadas.append(conta)
                elif not checkbox and conta in st.session_state.contas_bancarias_selecionadas:
                    st.session_state.contas_bancarias_selecionadas.remove(conta)
        
        contas_filtradas = st.session_state.contas_bancarias_selecionadas

# Aplicação dos filtros
data_inicio = pd.to_datetime(periodo[0])
data_fim = pd.to_datetime(periodo[1]) + pd.Timedelta(days=1)
def formatar_reais(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

df_filtrado = df[
    (df["empresa"].isin(empresa_selecionada)) &
    (df["unidade_estrategica"].isin(unidade_estrategica_selecionada)) &
    (df["unidade_negocio"].isin(unidade_negocio_selecionada)) &
    (df["categoria_pedido_compra"].isin(categoria_pedido_compra_selecionada)) &
    (df["plano_contas"].isin(plano_contas_selecionado)) &
    (df["conta_bancaria"].isin(contas_filtradas)) &
    (df["data_pagamento_parcela"] >= data_inicio) &
    (df["data_pagamento_parcela"] < data_fim)
]

st.metric("Total Gasto no Período", formatar_reais(df_filtrado['valor_corrigido'].sum()))

df_pagos = df_filtrado.copy()
df_pagos = df_pagos[df_pagos["status_id"] == 4]

# Tabela por Centro de Custo
tabela = (
    df_pagos.groupby("centro_custo")
    .agg(
        valor_corrigido=pd.NamedAgg(column="valor_corrigido", aggfunc="sum")
    )
    .reset_index()
    .sort_values("valor_corrigido", ascending=False)
)

tabela["valor_corrigido_formatado"] = tabela["valor_corrigido"].apply(formatar_reais)

st.dataframe(
    tabela[["centro_custo", "valor_corrigido_formatado"]].rename(
        columns={
            "centro_custo": "Centro de Custo",
            "valor_corrigido_formatado": "Total Pago"
        }
    ),
    use_container_width=True
)

# Tabela por Categoria
tabela2 = (
    df_pagos.groupby("categoria_pedido_compra")
    .agg(
        valor_corrigido=pd.NamedAgg(column="valor_corrigido", aggfunc="sum")
    )
    .reset_index()
    .sort_values("valor_corrigido", ascending=False)
)

tabela2["valor_corrigido_formatado"] = tabela2["valor_corrigido"].apply(formatar_reais)

st.dataframe(
    tabela2[["categoria_pedido_compra", "valor_corrigido_formatado"]].rename(
        columns={
            "categoria_pedido_compra": "Categoria",
            "valor_corrigido_formatado": "Total Pago"
        }
    ),
    use_container_width=True
)

# Tabela por Histórico
tabela3 = (
    df_pagos.groupby("descricao_pedido_compra")
    .agg(
        valor_corrigido=pd.NamedAgg(column="valor_corrigido", aggfunc="sum")
    )
    .reset_index()
    .sort_values("valor_corrigido", ascending=False)
)

tabela3["valor_corrigido_formatado"] = tabela3["valor_corrigido"].apply(formatar_reais)

st.dataframe(
    tabela3[["descricao_pedido_compra", "valor_corrigido_formatado"]].rename(
        columns={
            "descricao_pedido_compra": "Histórico",
            "valor_corrigido_formatado": "Total Pago"
        }
    ),
    use_container_width=True
)

tabela4 = (
    df_pagos.groupby(["centro_custo", "categoria_pedido_compra", "descricao_pedido_compra"])
    .agg(
        valor_corrigido=pd.NamedAgg(column="valor_corrigido", aggfunc="sum")
    )
    .reset_index()
    .sort_values("centro_custo", ascending=False)
)

tabela4["valor_corrigido_formatado"] = tabela4["valor_corrigido"].apply(formatar_reais)

st.dataframe(
    tabela4[["centro_custo", "categoria_pedido_compra", "descricao_pedido_compra", "valor_corrigido_formatado"]].rename(
        columns={
            "centro_custo": "Centro de Custo",
            "categoria_pedido_compra": "Categoria",
            "descricao_pedido_compra": "Histórico",
            "valor_corrigido_formatado": "Total Pago"
        }
    ),
    use_container_width=True
)


# Cria a tabela hierárquica (similar à tabela4)
df_hierarquico = (
    df_pagos.groupby(["centro_custo", "categoria_pedido_compra", "descricao_pedido_compra"])
    .agg(valor_corrigido=("valor_corrigido", "sum"))
    .reset_index()
    .sort_values(["centro_custo", "categoria_pedido_compra", "valor_corrigido"], ascending=[True, True, False])
)

# Formata os valores
df_hierarquico["valor_formatado"] = df_hierarquico["valor_corrigido"].apply(formatar_reais)

# Configuração da tabela interativa
gb = GridOptionsBuilder.from_dataframe(
    df_hierarquico[["centro_custo", "categoria_pedido_compra", "descricao_pedido_compra", "valor_formatado"]]
)

# Define a hierarquia
gb.configure_column("centro_custo", hide=False, rowGroup=True)
gb.configure_column("categoria_pedido_compra", hide=False, rowGroup=True)
gb.configure_column("descricao_pedido_compra", hide=False)
gb.configure_column("valor_formatado", headerName="Valor Pago")

# Configura o agrupamento
gb.configure_grid_options(
    groupDefaultExpanded=1,  # Expande apenas o primeiro nível inicialmente
    autoGroupColumnDef= {
        "headerName": "Centro de Custo",
        "field": "centro_custo",
        "cellRenderer": "agGroupCellRenderer",
        "cellRendererParams": {
            "suppressCount": True,
            "checkbox": False,
        },
    },
    groupDisplayType="groupRows",
)

# Adiciona estilo condicional
cellstyle_jscode = JsCode("""
function(params) {
    if (params.node.group) {
        return { 'font-weight': 'bold', 'background-color': '#f0f2f6' };
    }
}
""")

gb.configure_grid_options(getRowStyle=cellstyle_jscode)

# Cria a tabela
st.subheader("Tabela Hierárquica de Gastos")
grid_options = gb.build()

AgGrid(
    df_hierarquico,
    gridOptions=grid_options,
    height=600,
    width="100%",
    theme="streamlit",
    allow_unsafe_jscode=True,
    enable_enterprise_modules=True,
    update_mode="MODEL_CHANGED",
    fit_columns_on_grid_load=True,
)