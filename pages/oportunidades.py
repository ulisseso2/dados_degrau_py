import sys
import os
import io
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime
from utils.sql_loader import carregar_dados  # agora usamos a função com cache
import plotly.graph_objects as go

st.title("Dashboard Oportunidades")

# ✅ Carrega os dados com cache (1h por padrão, pode ajustar no sql_loader.py)
df = carregar_dados("consultas/oportunidades/oportunidades.sql")

# Pré-filtros
df["criacao"] = pd.to_datetime(df["criacao"])

# Filtro: empresa
empresas = df["empresa"].dropna().unique().tolist()
empresa_selecionada = st.multiselect("Selecione as empresas:", empresas, default=["Degrau"])
df_filtrado_empresa = df[df["empresa"].isin(empresa_selecionada)]

# Filtro: data (padrão: dia atual)
hoje = datetime.today().date()
periodo = st.date_input("Período de vendas:", [hoje, hoje])


# Filtros adicionais recolhidos
with st.expander("Filtros Avançados: Unidades, Etapas, Modalidade e H. Ligar"):
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        unidades = df_filtrado_empresa["unidade"].dropna().unique().tolist()
        unidade_selecionada = st.multiselect("Selecione a unidade:", unidades, default=unidades)

    with col2:
        etapas = df_filtrado_empresa["etapa"].dropna().unique().tolist()
        etapa_selecionada = st.multiselect("Selecione a etapa:", etapas, default=etapas)
    
    with col3:
        modalidades = df_filtrado_empresa["modalidade"].dropna().unique().tolist()
        modalidade_selecionada = st.multiselect("Selecione a modalidade:", modalidades, default=modalidades)

    with col4:
        hs_ligar = df_filtrado_empresa["h_ligar"].dropna().unique().tolist()
        h_ligar_selecionada = st.multiselect("Selecione a Hora", hs_ligar, default=hs_ligar)

# Aplica filtros finais
data_inicio = pd.to_datetime(periodo[0])
data_fim = pd.to_datetime(periodo[1]) + pd.Timedelta(days=1)

df_filtrado = df[
    (df["empresa"].isin(empresa_selecionada)) &
    ((df["unidade"].isin(unidade_selecionada)) | df["unidade"].isna()) &
    ((df["etapa"].isin(etapa_selecionada)) | df["etapa"].isna()) &
    ((df["modalidade"].isin(modalidade_selecionada)) | df["modalidade"].isna()) &
    ((df["h_ligar"].isin(h_ligar_selecionada)) | df["h_ligar"].isna()) &
    (df["criacao"] >= data_inicio) &
    (df["criacao"] < data_fim) 

]

st.metric("Total de Oportunidades", df_filtrado.shape[0])

df_diario = df_filtrado.groupby(df["criacao"].dt.date)["oportunidade"].count().reset_index()

# Renomeia coluna de data para 'Data' (opcional)
df_diario.columns = ["Data", "Total"]

oport_dia = px.bar(
    df_diario,
    x="Data",
    y="Total",
    title="Oportunidades por dia",
    labels={"quantidade": "Qtd. oportunidades", "unidade": "Unidade"},
    barmode="stack",
    text_auto=True,
)
st.plotly_chart(oport_dia, use_container_width=True)

#pizza unidades
# Agrupa por unidade e conta a quantidade de oportunidades
df_unidade = df_filtrado.groupby("unidade")["oportunidade"].count().reset_index()

# Cria o gráfico de pizza
fig = px.pie(
    df_unidade,
    names="unidade",
    values="oportunidade",
    title="Oportunidades por Unidade",
    labels={"unidade": "Unidade", "oportunidade": "Quantidade"},
    )
st.plotly_chart(fig, use_container_width=True)