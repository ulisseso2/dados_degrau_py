import mysql.connector
from dotenv import load_dotenv
import os

# Carrega variáveis do .env
load_dotenv()

def conectar_mysql():
    try:
        conexao = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            port=int(os.getenv("DB_PORT", 3306))
        )
        return conexao
    except mysql.connector.Error as e:
        print(f"Erro ao conectar: {e}")
        return None

