"""
Cache SQLite local para respostas da API Bling.
Duas tabelas:
  - notas:    cache por ID individual (detalhes de NFe/NFS-e)
  - listagens: cache de listagens por período (resultados do endpoint /nfe?dataEmissao...)
"""

import json
import sqlite3
import time
from pathlib import Path

_DB_PATH       = Path(__file__).parent.parent / ".bling_cache.db"
_TTL_NOTAS     = 30 * 24 * 3600   # 30 dias  — dados de NF são estáticos
_TTL_LISTAGEM  =  2 * 3600         # 2 horas  — listagem pode ter notas novas no dia


def _conectar() -> sqlite3.Connection:
    con = sqlite3.connect(_DB_PATH, check_same_thread=False)
    con.execute("""
        CREATE TABLE IF NOT EXISTS notas (
            id       INTEGER NOT NULL,
            tipo     TEXT    NOT NULL,
            dados    TEXT    NOT NULL,
            salvo_em INTEGER NOT NULL,
            PRIMARY KEY (id, tipo)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS listagens (
            periodo_key TEXT    NOT NULL,
            tipo        TEXT    NOT NULL,
            dados       TEXT    NOT NULL,
            salvo_em    INTEGER NOT NULL,
            PRIMARY KEY (periodo_key, tipo)
        )
    """)
    return con


# ---------------------------------------------------------------------------
# Cache de notas individuais (por ID)
# ---------------------------------------------------------------------------

def buscar_cache(ids: list[int], tipo: str) -> dict[int, dict]:
    """Retorna entradas do cache para os IDs informados."""
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    with _conectar() as con:
        rows = con.execute(
            f"SELECT id, dados FROM notas WHERE tipo=? AND id IN ({placeholders})",
            [tipo, *ids],
        ).fetchall()
    return {row[0]: json.loads(row[1]) for row in rows}


def ids_sem_campo(ids: list[int], tipo: str, campo: str) -> list[int]:
    """Retorna IDs que estão no cache mas sem o campo informado (ex: 'valor')."""
    if not ids:
        return []
    cached = buscar_cache(ids, tipo)
    return [nid for nid in ids if not cached.get(nid, {}).get(campo)]


def salvar_cache(resultados: dict[int, dict], tipo: str):
    """Persiste resultados no cache, sobrescrevendo entradas existentes."""
    if not resultados:
        return
    agora = int(time.time())
    rows = [
        (nid, tipo, json.dumps({k: v for k, v in d.items() if k != "_debug"}), agora)
        for nid, d in resultados.items()
    ]
    with _conectar() as con:
        con.executemany(
            "INSERT OR REPLACE INTO notas (id, tipo, dados, salvo_em) VALUES (?, ?, ?, ?)",
            rows,
        )


def stats_cache(tipo: str) -> dict:
    with _conectar() as con:
        row = con.execute(
            "SELECT COUNT(*), MIN(salvo_em) FROM notas WHERE tipo=?", [tipo]
        ).fetchone()
    return {"total": row[0], "mais_antigo": row[1]}


# ---------------------------------------------------------------------------
# Cache de listagens por período
# ---------------------------------------------------------------------------

def buscar_listagem(periodo_key: str, tipo: str) -> list[dict] | None:
    """
    Retorna a listagem cached para o período, ou None se expirada/inexistente.
    periodo_key: ex. '2026-02-01_2026-02-28'
    """
    min_ts = int(time.time()) - _TTL_LISTAGEM
    with _conectar() as con:
        row = con.execute(
            "SELECT dados, salvo_em FROM listagens WHERE periodo_key=? AND tipo=?",
            [periodo_key, tipo],
        ).fetchone()
    if row is None:
        return None
    salvo_em = row[1]
    if salvo_em < min_ts:
        return None          # expirado
    return json.loads(row[0])


def salvar_listagem(periodo_key: str, tipo: str, dados: list[dict]):
    """Persiste uma listagem de período no cache."""
    with _conectar() as con:
        con.execute(
            "INSERT OR REPLACE INTO listagens (periodo_key, tipo, dados, salvo_em) "
            "VALUES (?, ?, ?, ?)",
            [periodo_key, tipo, json.dumps(dados), int(time.time())],
        )


def stats_listagem() -> list[dict]:
    """Retorna todas as entradas de listagem com idade."""
    with _conectar() as con:
        rows = con.execute(
            "SELECT periodo_key, tipo, salvo_em FROM listagens ORDER BY salvo_em DESC"
        ).fetchall()
    agora = int(time.time())
    return [
        {"periodo": r[0], "tipo": r[1],
         "idade_min": round((agora - r[2]) / 60)}
        for r in rows
    ]
