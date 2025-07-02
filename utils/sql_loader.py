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
    
# Carrega os dados do banco executando o SQL de um arquivo.
# Usa um engine do SQLAlchemy para a conexão, como recomendado pelo pandas.
# O cache é configurado para expirar a cada 10 minutos (600 segundos).
@st.cache_data(ttl=600)
def carregar_dados(caminho_sql):
    """
    Carrega os dados do banco executando o SQL de um arquivo.
    Usa um engine do SQLAlchemy para a conexão, como recomendado pelo pandas.
    """
    query = carregar_sql(caminho_sql)
    engine = conectar_mysql()
    if engine:
        try:
            # pd.read_sql lida com o engine, abrindo e fechando a conexão
            df = pd.read_sql(query, engine)
            return df
        except Exception as e:
            st.error(f"Erro ao executar a consulta: {e}")
            return pd.DataFrame()
    else:
        st.error("Erro ao conectar ao banco de dados.")
        return pd.DataFrame()
