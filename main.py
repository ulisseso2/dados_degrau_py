import streamlit as st
import os

db_host = os.getenv("DB_HOST")
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_name = os.getenv("DB_NAME")
db_port = os.getenv("DB_PORT")

st.set_page_config(page_title="Dashboard Degrau", layout="wide")

st.title("Bem-vindo ao Relatório Seducar📊")
st.markdown("""
Este painel contém os dashboards de análise de matrículas, vendas e outras métricas do da Degrau Cultural e Central de Concursos.

Utilize o menu lateral para navegar entre os dashboards disponíveis.
""")
