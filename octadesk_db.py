# octadesk_db.py - Cache SQLite para chats e mensagens do Octadesk
# Armazena TODOS os chats e mensagens para preservar histórico
# (a API só retém ~30 dias de dados) e evitar chamadas repetidas.

import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# Path absoluto baseado na localização deste arquivo (raiz do projeto)
_PROJECT_ROOT = Path(__file__).resolve().parent
DB_DIR = str(_PROJECT_ROOT / "data_cache")
DB_FILE = str(_PROJECT_ROOT / "data_cache" / "octadesk_cache.db")
_PLACEHOLDER_LIKE_PATTERNS = ('%"type": "placeholder"%', '%"type":"placeholder"%')


def _placeholder_sql(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return f"({prefix}raw_json LIKE ? OR {prefix}raw_json LIKE ?)"


def _is_placeholder_message(msg) -> bool:
    if not isinstance(msg, dict):
        return False
    if str(msg.get('type') or '').lower() != 'placeholder':
        return False
    return not any(str(msg.get(field) or '').strip() for field in ('body', 'text', 'content', 'message'))


def _get_connection():
    """Retorna conexão ao banco SQLite com WAL mode para melhor concorrência."""
    Path(DB_DIR).mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Inicializa as tabelas do banco de cache."""
    with _get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS octadesk_chats (
                id TEXT PRIMARY KEY,
                status TEXT,
                created_at TEXT,
                phone TEXT,
                raw_json TEXT NOT NULL,
                cached_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS octadesk_messages (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                cached_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS octadesk_sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_type TEXT,
                pages_fetched INTEGER,
                chats_saved INTEGER,
                messages_saved INTEGER,
                oldest_chat_date TEXT,
                newest_chat_date TEXT,
                synced_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_chats_status ON octadesk_chats(status);
            CREATE INDEX IF NOT EXISTS idx_chats_created_at ON octadesk_chats(created_at);
            CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON octadesk_messages(chat_id);
        """)

        # Migração: adiciona coluna phone se tabela já existia sem ela
        try:
            conn.execute("ALTER TABLE octadesk_chats ADD COLUMN phone TEXT")
        except sqlite3.OperationalError:
            pass  # coluna já existe

        # Índice na coluna phone (criado após garantir que a coluna existe)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chats_phone ON octadesk_chats(phone)")


def _extract_phone_from_chat(chat):
    """Extrai telefone(s) do cliente a partir do dict do chat.
    
    Retorna string formatada ex: '+5521967261242' ou '+5521967261242 / +5588988407203'.
    """
    contact = chat.get('contact', {})
    if not isinstance(contact, dict):
        return ''
    phone_contacts = contact.get('phoneContacts', [])
    if not isinstance(phone_contacts, list) or not phone_contacts:
        return ''
    phones = []
    for pc in phone_contacts:
        if isinstance(pc, dict) and pc.get('number'):
            country = pc.get('countryCode', '')
            number = str(pc['number'])
            if country:
                phones.append(f'+{country}{number}')
            else:
                phones.append(number)
    return ' / '.join(phones) if phones else ''


def save_chats(chats_list):
    """Salva lista de chats (dicts raw da API) no banco. Retorna quantidade salva."""
    if not chats_list:
        return 0
    init_db()
    saved = 0
    with _get_connection() as conn:
        for chat in chats_list:
            chat_id = chat.get('id')
            if not chat_id:
                continue
            status = str(chat.get('status', '')).lower()
            created_at = chat.get('createdAt', '')
            phone = _extract_phone_from_chat(chat)
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO octadesk_chats (id, status, created_at, phone, raw_json, cached_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (chat_id, status, created_at, phone, json.dumps(chat, default=str), datetime.now().isoformat())
                )
                saved += 1
            except Exception:
                continue
        conn.commit()
    return saved


def save_messages(chat_id, messages_list):
    """Salva mensagens de um chat no banco. Retorna quantidade salva."""
    if not messages_list:
        return 0
    valid_messages = [msg for msg in messages_list if not _is_placeholder_message(msg)]
    if not valid_messages:
        return 0
    init_db()
    saved = 0
    with _get_connection() as conn:
        for idx, msg in enumerate(valid_messages):
            msg_id = msg.get('id') or msg.get('_id') or f"{chat_id}_{idx}"
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO octadesk_messages (id, chat_id, raw_json, cached_at) "
                    "VALUES (?, ?, ?, ?)",
                    (msg_id, chat_id, json.dumps(msg, default=str), datetime.now().isoformat())
                )
                saved += 1
            except Exception:
                continue
        conn.commit()
    return saved


def get_cached_chats(start_date=None, end_date=None, status_filter=None):
    """Retorna chats do cache como lista de dicts, filtrados por data e/ou status.
    
    NOTA: As datas no banco estão em UTC (createdAt da API) mas o filtro do
    usuário é em horário local (America/Sao_Paulo, UTC-3). Expandimos o range
    em ±1 dia para não perder chats de madrugada/noite. O filtro preciso
    é feito depois no DataFrame com tz_convert.
    """
    init_db()
    with _get_connection() as conn:
        query = "SELECT raw_json FROM octadesk_chats WHERE 1=1"
        params = []

        if status_filter:
            query += " AND status = ?"
            params.append(status_filter.lower())

        if start_date:
            # -1 dia para cobrir chats UTC que são do dia anterior no fuso local
            adjusted_start = start_date - timedelta(days=1)
            query += " AND created_at >= ?"
            params.append(str(adjusted_start))

        if end_date:
            # +2 dias para cobrir chats UTC que são do dia seguinte no fuso local
            adjusted_end = end_date + timedelta(days=2)
            query += " AND created_at < ?"
            params.append(str(adjusted_end))

        query += " ORDER BY created_at DESC"

        cursor = conn.execute(query, params)
        results = []
        for row in cursor.fetchall():
            try:
                results.append(json.loads(row[0]))
            except (json.JSONDecodeError, TypeError):
                continue
        return results


def get_cached_messages(chat_id):
    """Retorna mensagens de um chat do cache como lista de dicts."""
    init_db()
    with _get_connection() as conn:
        cursor = conn.execute(
            f"SELECT raw_json FROM octadesk_messages WHERE chat_id = ? AND NOT {_placeholder_sql()} ORDER BY cached_at",
            (chat_id, *_PLACEHOLDER_LIKE_PATTERNS)
        )
        results = []
        for row in cursor.fetchall():
            try:
                results.append(json.loads(row[0]))
            except (json.JSONDecodeError, TypeError):
                continue
        return results


def get_cached_messages_batch(chat_ids):
    """Retorna mensagens de múltiplos chats em uma única query SQLite.
    Retorna dict: {chat_id: [lista de mensagens]}
    """
    if not chat_ids:
        return {}
    init_db()
    placeholders = ",".join("?" * len(chat_ids))
    with _get_connection() as conn:
        cursor = conn.execute(
            f"SELECT chat_id, raw_json FROM octadesk_messages WHERE chat_id IN ({placeholders}) AND NOT {_placeholder_sql()} ORDER BY chat_id, cached_at",
            [*chat_ids, *_PLACEHOLDER_LIKE_PATTERNS],
        )
        result = {}
        for chat_id, raw in cursor.fetchall():
            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            result.setdefault(chat_id, []).append(msg)
        return result


def has_cached_messages(chat_id):
    """Verifica se já existem mensagens em cache para um chat."""
    init_db()
    with _get_connection() as conn:
        cursor = conn.execute(
            f"SELECT COUNT(*) FROM octadesk_messages WHERE chat_id = ? AND NOT {_placeholder_sql()}",
            (chat_id, *_PLACEHOLDER_LIKE_PATTERNS)
        )
        return cursor.fetchone()[0] > 0


def get_chats_without_messages():
    """Retorna lista de IDs de chats que NÃO possuem mensagens em cache."""
    init_db()
    with _get_connection() as conn:
        cursor = conn.execute(
            "SELECT c.id FROM octadesk_chats c "
            f"LEFT JOIN octadesk_messages m ON c.id = m.chat_id AND NOT {_placeholder_sql('m')} "
            "WHERE m.id IS NULL "
            "ORDER BY c.created_at DESC",
            _PLACEHOLDER_LIKE_PATTERNS,
        )
        return [row[0] for row in cursor.fetchall()]


def count_chats_without_messages():
    """Retorna contagem de chats sem mensagens em cache."""
    init_db()
    with _get_connection() as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM octadesk_chats c "
            f"LEFT JOIN octadesk_messages m ON c.id = m.chat_id AND NOT {_placeholder_sql('m')} "
            "WHERE m.id IS NULL",
            _PLACEHOLDER_LIKE_PATTERNS,
        )
        return cursor.fetchone()[0]


def purge_placeholder_messages():
    """Remove mensagens placeholder antigas que contaminam o cache local."""
    init_db()
    with _get_connection() as conn:
        cursor = conn.execute(
            f"DELETE FROM octadesk_messages WHERE {_placeholder_sql()}",
            _PLACEHOLDER_LIKE_PATTERNS,
        )
        conn.commit()
        return max(cursor.rowcount or 0, 0)


def log_sync(sync_type, pages_fetched, chats_saved, messages_saved=0, oldest_date=None, newest_date=None):
    """Registra uma sincronização no log."""
    init_db()
    with _get_connection() as conn:
        conn.execute(
            "INSERT INTO octadesk_sync_log "
            "(sync_type, pages_fetched, chats_saved, messages_saved, oldest_chat_date, newest_chat_date, synced_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sync_type, pages_fetched, chats_saved, messages_saved,
             str(oldest_date) if oldest_date else None,
             str(newest_date) if newest_date else None,
             datetime.now().isoformat())
        )
        conn.commit()


def get_cache_stats():
    """Retorna estatísticas do cache."""
    init_db()
    stats = {}
    with _get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM octadesk_chats")
        stats['total_chats'] = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM octadesk_chats WHERE status = 'closed'")
        stats['closed_chats'] = cursor.fetchone()[0]

        cursor = conn.execute(
            f"SELECT COUNT(*) FROM octadesk_messages WHERE NOT {_placeholder_sql()}",
            _PLACEHOLDER_LIKE_PATTERNS,
        )
        stats['total_messages'] = cursor.fetchone()[0]

        cursor = conn.execute(
            "SELECT COUNT(*) FROM octadesk_chats c "
            f"LEFT JOIN octadesk_messages m ON c.id = m.chat_id AND NOT {_placeholder_sql('m')} "
            "WHERE m.id IS NULL",
            _PLACEHOLDER_LIKE_PATTERNS,
        )
        stats['chats_without_messages'] = cursor.fetchone()[0]

        cursor = conn.execute("SELECT MIN(created_at), MAX(created_at) FROM octadesk_chats")
        row = cursor.fetchone()
        stats['oldest_chat'] = row[0] if row and row[0] else None
        stats['newest_chat'] = row[1] if row and row[1] else None

        cursor = conn.execute(
            "SELECT synced_at FROM octadesk_sync_log ORDER BY synced_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
        stats['last_sync'] = row[0] if row else None

    return stats


def clear_cache():
    """Limpa todo o cache (chats, mensagens e log de sincronização)."""
    init_db()
    with _get_connection() as conn:
        conn.executescript("""
            DELETE FROM octadesk_messages;
            DELETE FROM octadesk_chats;
            DELETE FROM octadesk_sync_log;
        """)


def backfill_phones():
    """Preenche a coluna phone para chats já em cache que não têm telefone extraído.
    
    Lê o raw_json, extrai o telefone e atualiza a coluna phone.
    Retorna quantidade de chats atualizados.
    """
    init_db()
    updated = 0
    with _get_connection() as conn:
        cursor = conn.execute(
            "SELECT id, raw_json FROM octadesk_chats WHERE phone IS NULL OR phone = ''"
        )
        rows = cursor.fetchall()
        for chat_id, raw_json in rows:
            try:
                chat = json.loads(raw_json)
                phone = _extract_phone_from_chat(chat)
                if phone:
                    conn.execute(
                        "UPDATE octadesk_chats SET phone = ? WHERE id = ?",
                        (phone, chat_id)
                    )
                    updated += 1
            except (json.JSONDecodeError, TypeError):
                continue
        conn.commit()
    return updated
