"""Funções de carregamento de transcrições, compartilhadas entre páginas."""

import pandas as pd
import streamlit as st
from pathlib import Path
from conexao.mysql_connector import conectar_mysql


@st.cache_data(ttl=21600, show_spinner=False)
def carregar_detalhe_transcricao(transcricao_id: int) -> dict:
    """Carrega transcrição, agente, duração e tipo de uma única linha."""
    engine = conectar_mysql()
    if not engine:
        return {}
    sql = Path("consultas/transcricoes/transcricao_detalhe.sql").read_text()
    sql = sql.replace("{ids}", str(int(transcricao_id)))
    try:
        df = pd.read_sql(sql, engine)
        if df.empty:
            return {}
        row = df.iloc[0]
        return {
            "transcricao": row.get("transcricao", ""),
            "agente": row.get("agente") or "Não identificado",
            "duracao": row.get("duracao"),
            "telefone": row.get("telefone"),
            "tipo": row.get("tipo") or "N/Informado",
            "insight_ia": row.get("insight_ia"),
        }
    except Exception as e:
        return {"erro": str(e)}
