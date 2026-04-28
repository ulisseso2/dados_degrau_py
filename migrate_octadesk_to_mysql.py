#!/usr/bin/env python3
"""
migrate_octadesk_to_mysql.py — Migração única: SQLite local → MySQL (seducar)

Lê TODOS os dados do cache SQLite (octadesk_cache.db) e os escreve nas tabelas
MySQL correspondentes. Seguro de re-executar: usa INSERT ... ON DUPLICATE KEY UPDATE.

USO:
    python3 migrate_octadesk_to_mysql.py
    python3 migrate_octadesk_to_mysql.py --batch-size 500
    python3 migrate_octadesk_to_mysql.py --only-chats
    python3 migrate_octadesk_to_mysql.py --only-messages
    python3 migrate_octadesk_to_mysql.py --dry-run     # Só conta, não escreve
"""

import argparse
import json
import logging
import sqlite3
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv()

# Logging para console e arquivo
LOG_DIR = PROJECT_ROOT / "data_cache"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_DIR / "migrate_octadesk_mysql.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger("migrate_octadesk")

SQLITE_DB = PROJECT_ROOT / "data_cache" / "octadesk_cache.db"


# ==============================================================================
# LEITURA DO SQLITE
# ==============================================================================

def _sqlite_conn():
    if not SQLITE_DB.exists():
        logger.error("Arquivo SQLite não encontrado: %s", SQLITE_DB)
        sys.exit(1)
    conn = sqlite3.connect(str(SQLITE_DB))
    conn.row_factory = sqlite3.Row
    return conn


def count_sqlite() -> dict:
    with _sqlite_conn() as conn:
        chats = conn.execute("SELECT COUNT(*) FROM octadesk_chats").fetchone()[0]
        messages = conn.execute("SELECT COUNT(*) FROM octadesk_messages").fetchone()[0]
    return {"chats": chats, "messages": messages}


def iter_chats(batch_size: int):
    """Gera batches de chats do SQLite."""
    with _sqlite_conn() as conn:
        cursor = conn.execute(
            "SELECT id, raw_json, cached_at FROM octadesk_chats ORDER BY created_at ASC"
        )
        batch = []
        for row in cursor:
            try:
                chat = json.loads(row["raw_json"])
                chat["_cached_at"] = row["cached_at"]  # injeta para preservar timestamp original
            except (json.JSONDecodeError, TypeError):
                continue
            batch.append(chat)
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch


def iter_messages(batch_size: int):
    """Gera batches de (chat_id, [mensagens]) do SQLite, agrupados por chat."""
    with _sqlite_conn() as conn:
        # Busca todos os chat_ids com mensagens
        chat_ids = [
            r[0] for r in conn.execute(
                "SELECT DISTINCT chat_id FROM octadesk_messages ORDER BY chat_id"
            ).fetchall()
        ]

    for i in range(0, len(chat_ids), batch_size):
        chunk = chat_ids[i : i + batch_size]
        with _sqlite_conn() as conn:
            placeholders = ",".join("?" * len(chunk))
            rows = conn.execute(
                f"SELECT chat_id, id, raw_json, cached_at FROM octadesk_messages "
                f"WHERE chat_id IN ({placeholders}) ORDER BY chat_id",
                chunk,
            ).fetchall()

        # Agrupa por chat_id
        by_chat: dict = {}
        for row in rows:
            cid = row["chat_id"]
            if cid not in by_chat:
                by_chat[cid] = {"msgs": [], "cached_at": row["cached_at"]}
            try:
                msg = json.loads(row["raw_json"])
                # Garante que o id da linha sqlite está no dict (pode ser gerado)
                if not msg.get("id") and not msg.get("_id"):
                    msg["id"] = row["id"]
                by_chat[cid]["msgs"].append(msg)
            except (json.JSONDecodeError, TypeError):
                continue

        yield by_chat


# ==============================================================================
# MIGRAÇÃO
# ==============================================================================

def migrate_chats(batch_size: int, dry_run: bool) -> int:
    from utils.octadesk_mysql_writer import save_chats_mysql

    counts = count_sqlite()
    total = counts["chats"]
    logger.info("Chats no SQLite: %d", total)

    if dry_run:
        logger.info("[DRY-RUN] Nenhum dado será escrito.")
        return total

    migrated = 0
    batch_num = 0

    for batch in iter_chats(batch_size):
        batch_num += 1
        # cached_at vem injetado no dict; extrai para passar ao writer
        cached_at = batch[0].get("_cached_at")
        # Remove campo auxiliar antes de salvar o raw_json
        for c in batch:
            c.pop("_cached_at", None)

        saved = save_chats_mysql(batch, cached_at=cached_at)
        migrated += saved

        pct = (migrated / total * 100) if total else 0
        logger.info(
            "Batch %d: %d chats salvos | Total: %d/%d (%.1f%%)",
            batch_num, saved, migrated, total, pct,
        )
        time.sleep(0.1)  # pausa mínima para não sobrecarregar o banco

    logger.info("Migração de chats concluída: %d/%d", migrated, total)
    return migrated


def migrate_messages(batch_size: int, dry_run: bool) -> int:
    from utils.octadesk_mysql_writer import save_messages_mysql

    counts = count_sqlite()
    total = counts["messages"]
    logger.info("Mensagens no SQLite: %d (em múltiplos chats)", total)

    if dry_run:
        logger.info("[DRY-RUN] Nenhum dado será escrito.")
        return total

    migrated = 0
    batch_num = 0

    for by_chat in iter_messages(batch_size):
        batch_num += 1
        batch_msgs = 0
        for chat_id, data in by_chat.items():
            saved = save_messages_mysql(chat_id, data["msgs"], cached_at=data["cached_at"])
            batch_msgs += saved
            migrated += saved
        logger.info("Batch %d: %d mensagens salvas | Total acumulado: %d", batch_num, batch_msgs, migrated)
        time.sleep(0.1)

    logger.info("Migração de mensagens concluída: %d", migrated)
    return migrated


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Migração Octadesk: SQLite → MySQL")
    parser.add_argument("--batch-size",    type=int,  default=200,  help="Registros por batch (default: 200)")
    parser.add_argument("--only-chats",    action="store_true",     help="Migra apenas chats")
    parser.add_argument("--only-messages", action="store_true",     help="Migra apenas mensagens")
    parser.add_argument("--dry-run",       action="store_true",     help="Só conta registros, não escreve nada")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("MIGRAÇÃO OCTADESK SQLite → MySQL")
    if args.dry_run:
        logger.info("MODO: DRY-RUN (apenas leitura)")
    logger.info("=" * 60)

    counts = count_sqlite()
    logger.info("SQLite: %d chats | %d mensagens", counts["chats"], counts["messages"])

    start = time.time()
    chats_done = 0
    msgs_done = 0

    if not args.only_messages:
        chats_done = migrate_chats(args.batch_size, args.dry_run)

    if not args.only_chats:
        msgs_done = migrate_messages(args.batch_size, args.dry_run)

    elapsed = time.time() - start

    if not args.dry_run:
        from utils.octadesk_mysql_writer import log_sync_mysql
        log_sync_mysql(
            sync_type="migration",
            source="sqlite",
            chats_saved=chats_done,
            messages_saved=msgs_done,
            duration_seconds=elapsed,
        )

    logger.info("-" * 60)
    logger.info("RESUMO:")
    logger.info("  Chats migrados:      %d", chats_done)
    logger.info("  Mensagens migradas:  %d", msgs_done)
    logger.info("  Tempo total:         %.1fs (%.1f min)", elapsed, elapsed / 60)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
