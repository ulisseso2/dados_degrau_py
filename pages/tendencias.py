import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils.sql_loader import carregar_dados
from datetime import datetime

st.set_page_config(layout="wide")
st.title("📈 Análise de Tendências de Oportunidades")

# --- Carregamento e Filtros ---
df_completo = carregar_dados("consultas/oportunidades/oportunidades.sql")
df_completo["criacao"] = pd.to_datetime(df_completo["criacao"])

# 1. CORREÇÃO: Limita a busca para dados a partir de Jan/2024
data_minima = datetime(2024, 1, 1).date()
df_completo = df_completo[df_completo['criacao'].dt.date >= data_minima]

# Filtro de período na barra lateral
st.sidebar.header("Filtros de Tendência")
periodo = st.sidebar.date_input(
    "Selecione o Período de Análise:",
    [df_completo['criacao'].min().date(), df_completo['criacao'].max().date()],
    min_value=data_minima, # Define a data mínima selecionável
    key="filtro_data_tendencia"
)

data_inicio = pd.to_datetime(periodo[0])
data_fim = pd.to_datetime(periodo[1])
df_filtrado = df_completo[(df_completo['criacao'] >= data_inicio) & (df_completo['criacao'] <= data_fim)]

# --- INÍCIO DA ANÁLISE MENSAL CORRIGIDA ---
st.header("Análise Mensal de Oportunidades")
st.markdown("Comparativo do desempenho mensal e a tendência ao longo do tempo.")

# --- Lógica de cálculo Like-for-Like ---
hoje = pd.Timestamp.now()
dia_corrente = hoje.day

# Períodos do Mês Atual (Mês-a-Data)
mes_atual_inicio = hoje.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
df_mes_atual_mtd = df_filtrado[(df_filtrado['criacao'] >= mes_atual_inicio) & (df_filtrado['criacao'] <= hoje)]
total_mes_atual_mtd = df_mes_atual_mtd.shape[0]

# Períodos do Mês Anterior
mes_anterior_fim_total = mes_atual_inicio - pd.Timedelta(seconds=1)
mes_anterior_inicio = mes_anterior_fim_total.replace(day=1)
# Período "Like-for-Like" do mês anterior
mes_anterior_fim_like = (mes_anterior_inicio + pd.DateOffset(days=dia_corrente - 1)).replace(hour=23, minute=59, second=59)

df_mes_anterior_total = df_filtrado[(df_filtrado['criacao'] >= mes_anterior_inicio) & (df_filtrado['criacao'] <= mes_anterior_fim_total)]
df_mes_anterior_like = df_mes_anterior_total[df_mes_anterior_total['criacao'] <= mes_anterior_fim_like]

total_mes_anterior_completo = df_mes_anterior_total.shape[0]
total_mes_anterior_like = df_mes_anterior_like.shape[0]

# Cálculo da tendência "Like-for-Like"
delta_like_for_like = 0
if total_mes_anterior_like > 0:
    delta_like_for_like = ((total_mes_atual_mtd - total_mes_anterior_like) / total_mes_anterior_like) * 100

# --- Apresentação das Métricas ---
st.subheader(f"Comparativo Mês a Data: Primeiros {dia_corrente} dias")
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        label=f"Mês Atual (Até Dia {dia_corrente})",
        value=f"{total_mes_atual_mtd}",
        delta=f"{delta_like_for_like:.1f}%",
        help=f"Comparado com os primeiros {dia_corrente} dias do mês anterior."
    )

with col2:
    st.metric(
        label=f"Mês Anterior (Primeiros {dia_corrente} dias)",
        value=f"{total_mes_anterior_like}"
    )

with col3:
    st.metric(
        label=f"Total do Mês Anterior Completo",
        value=f"{total_mes_anterior_completo}",
        help="Valor total do mês anterior para referência."
    )

st.divider()

# --- Gráfico de Barras Mensal (continua igual) ---
st.subheader("Evolução Mensal de Oportunidades")
df_mensal = df_filtrado.groupby(df_filtrado['criacao'].dt.to_period('M')).agg(
    Quantidade=('oportunidade', 'count')
).reset_index()
df_mensal['Mes'] = df_mensal['criacao'].dt.strftime('%Y-%m')

if not df_mensal.empty:
    fig_mensal = go.Figure(go.Bar(
        x=df_mensal['Mes'], y=df_mensal['Quantidade'], text=df_mensal['Quantidade'],
        textposition='outside', marker_color='#1f77b4'
    ))
    fig_mensal.update_layout(
        title_text='Total de Oportunidades por Mês', xaxis_title='Mês',
        yaxis_title='Quantidade', xaxis_type='category'
    )
    st.plotly_chart(fig_mensal, use_container_width=True)
else:
    st.warning("Não há dados mensais para exibir no período selecionado.")