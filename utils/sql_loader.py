from pathlib import Path
import pandas as pd
import streamlit as st
from conexao.mysql_connector import conectar_mysql

def carregar_sql(caminho_arquivo):
    caminho = Path(caminho_arquivo)
    if caminho.exists():
        return caminho.read_text()
    else:
        raise FileNotFoundError(f"Arquivo {caminho} não encontrado.")

@st.cache_data(ttl=600)
def carregar_dados(caminho_sql):
    """
    Carrega os dados do banco executando o SQL de um arquivo.
    O resultado é armazenado em cache por 5 minutos (300 segundos).
    """
    query = carregar_sql(caminho_sql)
    conexao = conectar_mysql()
    if conexao:
        df = pd.read_sql(query, conexao)
        conexao.close()
        return df
    else:
        st.error("Erro ao conectar ao banco de dados.")
        return pd.DataFrame()