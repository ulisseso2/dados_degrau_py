# conexao/mysql_connector.py

# Importa as bibliotecas necessárias
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from dotenv import load_dotenv
import os

# Carrega variáveis do .env
load_dotenv()

def conectar_mysql():
    """
    Cria um 'engine' de conexão do SQLAlchemy para o MySQL.
    Esta é a forma recomendada para usar com o pandas.
    """
    try:
        # Cria a URL de conexão a partir das variáveis de ambiente
        database_url = URL.create(
            drivername="mysql+mysqlconnector",
            username=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
            database=os.getenv("DB_NAME")
        )
        
        # Cria o "engine" de conexão
        engine = create_engine(database_url)
        return engine

    except Exception as e:
        # Usamos print para debug no terminal do Streamlit
        print(f"Erro ao criar o engine de conexão com SQLAlchemy: {e}")
        return None