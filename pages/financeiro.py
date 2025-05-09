import sys
import os
import io
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime
import numpy as np

from utils.sql_loader import carregar_dados  # agora usamos a função com cache

st.title("Dashboard Financeiro")

# ✅ Carrega os dados com cache (1h por padrão, pode ajustar no sql_loader.py)
df = carregar_dados("consultas/contas/contas_a_pagar.sql")

empresas = df["empresa"].dropna().unique().tolist()
empresa_selecionada = st.multiselect("Selecione as empresas:", empresas, default=["Degrau"])
df_filtrado_empresa = df[df["empresa"].isin(empresa_selecionada)]


# Configuração inicial

# Filtro: data (padrão: dia atual)
hoje = datetime.today().date()
periodo = st.date_input("Período de vendas:", [hoje, hoje])

df['data_pagamento_parcela'] = pd.to_datetime(df['data_pagamento_parcela'])
st.write(f"Tipo da coluna 'data_pagamento_parcela' após conversão: {df['data_pagamento_parcela'].dtype}") # Para verificar a conversão

with st.expander("Filtros Avançados: Unidades"):
    col1, col2 = st.columns(2)

    with col1:
        unidades_estrategicas = df_filtrado_empresa["unidade_estrategica"].dropna().unique().tolist()
        unidade_estrategica_selecionada = st.multiselect("Selecione a unidade:", unidades_estrategicas, default=unidades_estrategicas)
        df_filtrado_estrategica = df[df["unidade_estrategica"].isin(unidade_estrategica_selecionada)]
    
    with col2:
        unidades_negocio = df_filtrado_estrategica["unidade_negocio"].dropna().unique().tolist()
        unidade_negocio_selecionada = st.multiselect("Selecione a unidade de Negócio:", unidades_negocio, default=unidades_negocio)

with st.expander("Filtro Categorias / Custo / Planos"):
    col1, col2, col3 = st.columns(3)
    
    with col1:
        categorias_pedido_compra = df_filtrado_empresa["categoria_pedido_compra"].dropna().unique().tolist()
        categoria_pedido_compra_selecionada = st.multiselect("Selecione a categoria:", categorias_pedido_compra, default=categorias_pedido_compra)
    
    with col2:
        planos_contas = df_filtrado_empresa["plano_contas"].dropna().unique().tolist()
        plano_contas_selecionado = st.multiselect("Selecione o plano de contas:", planos_contas, default=planos_contas)
    
    with col3:
        # Obtém todas as contas bancárias únicas do DataFrame
        todas_contas = df['conta_bancaria'].dropna().unique().tolist()
        
        # Inicializa o session_state se não existir
        if "contas_bancarias_selecionadas" not in st.session_state:
            st.session_state.contas_bancarias_selecionadas = todas_contas.copy()
        
        # Checkbox mestre "Selecionar Todas"
        todas_selecionadas = st.checkbox(
            "Selecionar Todas", 
            value=len(st.session_state.contas_bancarias_selecionadas) == len(todas_contas)
        )
        
        # Lógica para selecionar/deselecionar todas
        if todas_selecionadas:
            st.session_state.contas_bancarias_selecionadas = todas_contas.copy()
        else:
            if len(st.session_state.contas_bancarias_selecionadas) == len(todas_contas):
                st.session_state.contas_bancarias_selecionadas = []
        
        # Checkboxes individuais para cada conta bancária
        st.write("Selecione as contas bancárias:")
        cols = st.columns(1)  # Cria 3 colunas para organizar os checkboxes
        
        for idx, conta in enumerate(todas_contas):
            with cols[idx % 1]:  # Distribui os checkboxes nas colunas
                checkbox = st.checkbox(
                    conta,
                    value=conta in st.session_state.contas_bancarias_selecionadas,
                    key=f"check_{conta}"
                )
                
                # Atualiza a lista de contas selecionadas
                if checkbox and conta not in st.session_state.contas_bancarias_selecionadas:
                    st.session_state.contas_bancarias_selecionadas.append(conta)
                elif not checkbox and conta in st.session_state.contas_bancarias_selecionadas:
                    st.session_state.contas_bancarias_selecionadas.remove(conta)
        
        contas_filtradas = st.session_state.contas_bancarias_selecionadas

# Aplicação do filtro no DataFrame (corrigido)
data_inicio = pd.to_datetime(periodo[0])
data_fim = pd.to_datetime(periodo[1]) + pd.Timedelta(days=1)


df_filtrado = df[
    (df["empresa"].isin(empresa_selecionada)) &
    (df["unidade_estrategica"].isin(unidade_estrategica_selecionada)) &
    (df["unidade_negocio"].isin(unidade_negocio_selecionada)) &
    (df["categoria_pedido_compra"].isin(categoria_pedido_compra_selecionada)) &
    (df["plano_contas"].isin(plano_contas_selecionado)) &
    (df["conta_bancaria"].isin(contas_filtradas)) & # Corrigido: removido o df[] extra
    (df["data_pagamento_parcela"] >= data_inicio) &
    (df["data_pagamento_parcela"] < data_fim)
]

st.metric("valor_corrigido", f"R$ {df_filtrado['valor_corrigido'].sum():,.2f}")

# 2. Cria a estrutura hierárquica
niveis = ['centro_custo', 'categoria_pedido_compra', 'descricao_pedido_compra']
metrica = 'valor_corrigido'

def format_currency(value):
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# 4. Tabela Dinâmica com Hierarquia
st.title("📊 Tabela Dinâmica Financeira")

# CSS para estilo de tabela
st.markdown("""
<style>
    .dataframe {
        width: 100%;
    }
    .dataframe th {
        background-color: #f0f2f6 !important;
        font-weight: bold !important;
    }
    .dataframe tr:nth-child(even) {
        background-color: #f9f9f9;
    }
    .dataframe tr:hover {
        background-color: #f0f0f0;
    }
    .expand-button {
        background: none;
        border: none;
        color: #1f78b4;
        cursor: pointer;
        padding: 0;
        font: inherit;
    }
</style>
""", unsafe_allow_html=True)

# Função principal para renderizar a tabela
def render_pivot_table(data):
    # Agrupa por todos os níveis
    grouped = data.groupby(niveis)[metrica].sum().unstack(level=[1,2], fill_value=0)
    
    # Cria a tabela expandível
    for centro in grouped.index:
        # Total do centro de custo
        total_centro = grouped.loc[centro].sum().sum()
        
        # Linha do centro de custo
        cols = st.columns([3, 2, 3, 2])
        cols[0].markdown(f"**{centro}**")
        cols[3].markdown(f"**{format_currency(total_centro)}**")
        
        # Verifica se está expandido
        expanded_centro = st.session_state.get(f"exp_centro_{centro}", False)
        
        # Botão de expansão
        if cols[0].button("▶", key=f"btn_centro_{centro}", help="Expandir categorias"):
            st.session_state[f"exp_centro_{centro}"] = not expanded_centro
        
        if expanded_centro:
            # Dados para este centro
            df_centro = data[data['centro_custo'] == centro]
            
            # Agrupa por categoria
            categorias = df_centro.groupby('categoria_pedido_compra')[metrica].sum()
            
            for categoria, total_categoria in categorias.items():
                # Linha da categoria
                cols = st.columns([3, 2, 3, 2])
                cols[1].markdown(f"↳ {categoria}")
                cols[3].markdown(format_currency(total_categoria))
                
                # Verifica se está expandido
                expanded_cat = st.session_state.get(f"exp_cat_{categoria}", False)
                
                # Botão de expansão
                if cols[1].button("▶", key=f"btn_cat_{categoria}", help="Expandir itens"):
                    st.session_state[f"exp_cat_{categoria}"] = not expanded_cat
                
                if expanded_cat:
                    # Itens detalhados
                    df_items = df_centro[df_centro['categoria_pedido_compra'] == categoria]
                    
                    # Mostra como tabela
                    st.table(
                        df_items[['descricao_pedido_compra', metrica]]
                        .assign(**{metrica: df_items[metrica].apply(format_currency)})
                        .rename(columns={
                            'descricao_pedido_compra': 'Descrição',
                            metrica: 'Valor Corrigido'
                        })
                        .set_index('Descrição')
                    )

# Renderiza a tabela
render_pivot_table(df_filtrado)

# 5. Resumo dos filtros
st.sidebar.markdown("---")
st.sidebar.markdown("**Filtros Ativos:**")
st.sidebar.write(f"Empresas: {', '.join(empresa_selecionada) or 'Todas'}")
st.sidebar.write(f"Período: {periodo[0].strftime('%d/%m/%Y')} a {periodo[1].strftime('%d/%m/%Y')}")