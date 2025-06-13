# conexao/mysql_connector.py - Versão Híbrida (st.secrets + .env)

import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from dotenv import load_dotenv
import os

# Carrega as variáveis do .env (só terá efeito no ambiente local)
load_dotenv()

def conectar_mysql():
    """
    Cria um engine de conexão híbrido, capturando o erro correto do Streamlit.
    """
    creds = {}
    try:
        # Tenta usar as credenciais do Streamlit Secrets (para produção)
        creds = st.secrets["database"]
    
    # AQUI ESTÁ A CORREÇÃO: Capturamos o erro específico do Streamlit
    except st.errors.StreamlitAPIException:
        # Se falhar (estamos localmente), usa as variáveis de ambiente do .env
        creds = {
            "user": os.getenv("DB_USER"),
            "password": os.getenv("DB_PASSWORD"),
            "host": os.getenv("DB_HOST"),
            "port": os.getenv("DB_PORT"),
            "db_name": os.getenv("DB_NAME")
        }

    # Verifica se as credenciais foram carregadas
    if not all(creds.values()):
        st.error("As credenciais do banco de dados não foram encontradas. Verifique seus Secrets ou o arquivo .env.")
        return None

    try:
        database_url = URL.create(
            drivername="mysql+mysqlconnector",
            username=creds["user"], password=creds["password"], host=creds["host"],
            port=creds["port"], database=creds["db_name"]
        )
        engine = create_engine(database_url)
        return engine
    except Exception as e:
        st.error(f"Erro ao criar o engine de conexão: {e}")
        return None