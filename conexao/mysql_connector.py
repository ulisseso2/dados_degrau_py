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
    
    except (st.errors.StreamlitAPIException, KeyError):
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


def conectar_mysql_secundario():
    """
    Cria um engine de conexão para o banco secundário.
    Usa a mesma estratégia híbrida (st.secrets + .env).
    """
    creds = {}
    try:
        # Tenta usar as credenciais do Streamlit Secrets (para produção)
        creds = st.secrets["database_secundario"]
    
    except (st.errors.StreamlitAPIException, KeyError):
        # Se falhar (estamos localmente), usa as variáveis de ambiente do .env
        creds = {
            "user": os.getenv("DB_SECUNDARIO_USER"),
            "password": os.getenv("DB_SECUNDARIO_PASSWORD"),
            "host": os.getenv("DB_SECUNDARIO_HOST"),
            "port": os.getenv("DB_SECUNDARIO_PORT"),
            "db_name": os.getenv("DB_SECUNDARIO_NAME")
        }

    # Verifica se as credenciais foram carregadas
    if not all(creds.values()):
        st.error("As credenciais do banco secundário não foram encontradas. Verifique seus Secrets ou o arquivo .env.")
        return None

    try:
        database_url = URL.create(
            drivername="mysql+mysqlconnector",
            username=creds["user"], 
            password=creds["password"], 
            host=creds["host"],
            port=creds["port"], 
            database=creds["db_name"]
        )
        engine = create_engine(database_url)
        return engine
    except Exception as e:
        st.error(f"Erro ao criar o engine de conexão secundária: {e}")
        return None


def conectar_mysql_writer():
    """
    Cria um engine de conexão com permissões de escrita.
    Usa secrets (database_writer) ou variáveis do .env (DB_WRITE_*).
    """
    creds = {}
    try:
        creds = st.secrets["database_writer"]
    except (st.errors.StreamlitAPIException, KeyError):
        creds = {
            "user": os.getenv("DB_WRITE_USER"),
            "password": os.getenv("DB_WRITE_PASSWORD"),
            "host": os.getenv("DB_WRITE_HOST"),
            "port": os.getenv("DB_WRITE_PORT"),
            "db_name": os.getenv("DB_WRITE_NAME")
        }

    if not all(creds.values()):
        st.error("As credenciais de escrita não foram encontradas. Verifique seus Secrets ou o arquivo .env.")
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
        st.error(f"Erro ao criar o engine de conexão de escrita: {e}")
        return None