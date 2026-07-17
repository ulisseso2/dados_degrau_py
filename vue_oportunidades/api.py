"""
Backend leve para o dashboard de Oportunidades em Vue.js.

Reaproveita EXATAMENTE a mesma query usada pela página Streamlit
(_pages/oportunidades.py -> consultas/oportunidades/oportunidades.sql),
mas em vez de renderizar com Streamlit, expõe os dados como JSON para o front Vue.

Diferença de arquitetura:
- Streamlit = backend + frontend no mesmo processo Python.
- Vue = só frontend. Por isso precisamos desta API para rodar o SQL e devolver JSON.

Rodar:
    pip install fastapi uvicorn sqlalchemy mysql-connector-python python-dotenv
    uvicorn vue_oportunidades.api:app --reload --port 8000
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

load_dotenv()

# Caminho do MESMO arquivo .sql usado pela página Streamlit
SQL_PATH = (
    Path(__file__).resolve().parent.parent
    / "consultas"
    / "oportunidades"
    / "oportunidades.sql"
)

app = FastAPI(title="Oportunidades API")

# Libera o front Vue (ajuste as origens em produção)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _engine():
    url = URL.create(
        drivername="mysql+mysqlconnector",
        username=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        database=os.getenv("DB_NAME"),
    )
    return create_engine(url, pool_pre_ping=True)


_cache = {"data": None, "ts": 0.0}
_TTL = 600  # 10 min, igual ao @st.cache_data da versão Streamlit


@app.get("/api/oportunidades")
def oportunidades():
    """Executa o SQL e devolve as linhas cruas em JSON.

    Toda a filtragem/agregação acontece no front (como o pandas fazia no Streamlit).
    Alternativa: mover filtros para query params e agregar em SQL para payloads menores.
    """
    import time

    now = time.time()
    if _cache["data"] is not None and now - _cache["ts"] < _TTL:
        return {"data": _cache["data"], "cached": True}

    query = SQL_PATH.read_text()
    with _engine().connect() as conn:
        result = conn.execute(text(query))
        cols = list(result.keys())
        rows = [dict(zip(cols, r)) for r in result.fetchall()]

    # Serializa datetime -> ISO
    for row in rows:
        if row.get("criacao") is not None:
            row["criacao"] = row["criacao"].isoformat()

    _cache["data"] = rows
    _cache["ts"] = now
    return {"data": rows, "cached": False}
