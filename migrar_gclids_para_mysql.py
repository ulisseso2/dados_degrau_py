#!/usr/bin/env python3
"""
migrar_gclids_para_mysql.py — Migração única: SQLite locais → MySQL (seducar)

Lê os DOIS caches de GCLID (gclid_cache.db = Degrau, gclid_cache_central.db =
Central) e grava tudo na tabela MySQL `gclid_campaigns` (coluna `empresa` no
lugar de dois arquivos). Idempotente: INSERT ... ON DUPLICATE KEY UPDATE, e um
'Não encontrado' nunca sobrescreve uma campanha válida já gravada.

Pré-requisito: infra criar a tabela `gclid_campaigns` (ver api-analises/INFRA.md).

USO:
    python3 migrar_gclids_para_mysql.py --dry-run   # só conta
    python3 migrar_gclids_para_mysql.py             # migra os dois arquivos
    python3 migrar_gclids_para_mysql.py --empresa Degrau
"""
import argparse
import sqlite3
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv()

BANCOS = {
    "Degrau": PROJECT_ROOT / "gclid_cache.db",
    "Central": PROJECT_ROOT / "gclid_cache_central.db",
}
BATCH = 2000


def _engine():
    import os

    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL

    creds = {
        "user": os.getenv("DB_WRITE_USER"),
        "password": os.getenv("DB_WRITE_PASSWORD"),
        "host": os.getenv("DB_WRITE_HOST"),
        "port": os.getenv("DB_WRITE_PORT", "3306"),
        "db": os.getenv("DB_WRITE_NAME"),
    }
    if not all(creds.values()):
        print("❌ Credenciais DB_WRITE_* ausentes no .env")
        sys.exit(1)
    url = URL.create(
        "mysql+mysqlconnector",
        username=creds["user"], password=creds["password"],
        host=creds["host"], port=int(creds["port"]), database=creds["db"],
    )
    return create_engine(url, pool_recycle=3600)


UPSERT = """
INSERT INTO gclid_campaigns (gclid, empresa, campaign_name, last_updated)
VALUES (:gclid, :empresa, :campaign, COALESCE(:last_updated, NOW()))
ON DUPLICATE KEY UPDATE
    campaign_name = IF(VALUES(campaign_name) = 'Não encontrado' AND campaign_name != 'Não encontrado',
        campaign_name, VALUES(campaign_name)),
    last_updated = VALUES(last_updated)
"""


def migrar(empresa: str, db_file: Path, engine, dry_run: bool) -> int:
    from sqlalchemy import text

    if not db_file.exists():
        print(f"⚠️  {empresa}: arquivo não encontrado ({db_file}), pulando")
        return 0

    conn = sqlite3.connect(str(db_file))
    total = conn.execute("SELECT COUNT(*) FROM gclid_cache").fetchone()[0]
    print(f"{empresa}: {total} gclids no SQLite ({db_file.name})")
    if dry_run:
        return total

    cursor = conn.execute("SELECT gclid, campaign_name, last_updated FROM gclid_cache")
    migrados = 0
    lote = []
    with engine.connect() as mysql:
        for gclid, campaign, last_updated in cursor:
            if not gclid:
                continue
            lote.append({
                "gclid": gclid, "empresa": empresa,
                "campaign": campaign or "Não encontrado",
                "last_updated": (last_updated or None) and str(last_updated)[:19].replace("T", " "),
            })
            if len(lote) >= BATCH:
                mysql.execute(text(UPSERT), lote)
                mysql.commit()
                migrados += len(lote)
                print(f"  {empresa}: {migrados}/{total}")
                lote = []
                time.sleep(0.05)
        if lote:
            mysql.execute(text(UPSERT), lote)
            mysql.commit()
            migrados += len(lote)
    print(f"✅ {empresa}: {migrados}/{total} migrados")
    return migrados


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--empresa", choices=list(BANCOS), help="Migra só uma empresa")
    args = parser.parse_args()

    engine = None if args.dry_run else _engine()
    alvos = {args.empresa: BANCOS[args.empresa]} if args.empresa else BANCOS

    inicio = time.time()
    total = sum(migrar(emp, db, engine, args.dry_run) for emp, db in alvos.items())
    print(f"{'[DRY-RUN] ' if args.dry_run else ''}Total: {total} gclids em {time.time() - inicio:.1f}s")


if __name__ == "__main__":
    main()
