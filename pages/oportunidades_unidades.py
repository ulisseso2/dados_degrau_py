import sys
import os
import io
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime
from utils.sql_loader import carregar_dados  # agora usamos a função com cache

st.title("Dashboard Oportunidades")

# ✅ Carrega os dados com cache (1h por padrão, pode ajustar no sql_loader.py)
df = carregar_dados("consultas/oportunidades/oportunidades.sql")

# Pré-filtros
df["criacao"] = pd.to_datetime(df["criacao"])
df = df[~df["unidade"].isin(["EAD", "Meier", "Copacabana", "Caxias", "Bonsucesso"])]

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

# Tabela por unidade
tabela = (
    df_filtrado.groupby("unidade")
    .agg(
        quantidade=pd.NamedAgg(column="ordem_id", aggfunc="count"),
        total_vendido=pd.NamedAgg(column="total_pedido", aggfunc="sum")
    )
    .reset_index()
    .sort_values("total_vendido", ascending=False)
)
tabela["ticket_medio"] = tabela["total_vendido"] / tabela["quantidade"]
tabela["ticket_medio"] = tabela["ticket_medio"].apply(formatar_reais)
tabela["total_vendido"] = tabela["total_vendido"].apply(formatar_reais)

st.subheader("Vendas por Unidade")
st.dataframe(tabela, use_container_width=True)

# Gráficos
st.subheader("Gráfico de Pedidos por Unidade e Categoria")
grafico = (
    df_filtrado.groupby(["unidade", "categoria"])
    .size()
    .reset_index(name="quantidade")
)
fig = px.bar(
    grafico,
    x="unidade",
    y="quantidade",
    color="categoria",
    title="Pedidos por Unidade (Detalhado por Categoria)",
    labels={"quantidade": "Qtd. Pedidos", "unidade": "Unidade"},
    barmode="stack",
    text_auto=True,
)
st.plotly_chart(fig, use_container_width=True)

# Gráfico de pedidos por curso venda quantitativa
st.subheader("Pedidos por Curso Venda")
grafico2 = (
    df_filtrado.groupby(["curso_venda", "unidade"])
    .size()
    .reset_index(name="quantidade")
)
fig2 = px.bar(
    grafico2,
    x="quantidade",
    y="curso_venda",
    color="unidade",
    title="Pedidos por Curso (Detalhado por Unidade)",
    labels={"quantidade": "Qtd. Pedidos", "curso_venda": "Curso Venda"},
    orientation="h",
    barmode="stack",
    text_auto=True,
)
st.plotly_chart(fig2, use_container_width=True)

# Tabela de venda por curso venda
st.subheader("Faturamento por Curso Venda (Modalidades)")

# Agrupa total vendido por categoria
valor_pivot = df_filtrado.pivot_table(
    index="curso_venda",
    columns="categoria",
    values="total_pedido",
    aggfunc="sum",
    fill_value=0
)

# Agrupa quantidade por categoria
qtd_pivot = df_filtrado.pivot_table(
    index="curso_venda",
    columns="categoria",
    values="ordem_id",
    aggfunc="count",
    fill_value=0
)

# Formata valores em reais (depois de fazer a junção)
valor_formatado = valor_pivot.copy()
for col in valor_formatado.columns:
    valor_formatado[col] = valor_formatado[col].apply(formatar_reais)

# Renomeia colunas com sufixo
valor_formatado.columns = [f"{col} (Valor)" for col in valor_formatado.columns]
qtd_pivot.columns = [f"{col} (Qtd)" for col in qtd_pivot.columns]

# Junta horizontalmente (eixo=1)
tabela_completa = pd.concat([valor_formatado, qtd_pivot], axis=1).reset_index()

# Mostra a tabela final
st.subheader("Vendas por Curso e Categoria (Valor e Quantidade)")
st.dataframe(tabela_completa, use_container_width=True)


# Tabela detalhada de alunos
tabela2 = df_filtrado[[
    "nome_cliente", "email_cliente", "celular_cliente", "curso_venda", "unidade", "total_pedido"
]]
tabela_alunos = tabela2.copy()
tabela_alunos["total_pedido"] = tabela_alunos["total_pedido"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

st.subheader("Tabela de Alunos")
st.dataframe(tabela_alunos, use_container_width=True)

# Exportar como Excel
buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
    tabela2.to_excel(writer, index=False, sheet_name='Pedidos')

# Resetar o ponteiro do buffer para o início
buffer.seek(0)

st.download_button(
    label="📥 Baixar como Excel",
    data=buffer,
    file_name="pedidos_detalhados.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
