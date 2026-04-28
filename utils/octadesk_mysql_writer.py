# utils/octadesk_mysql_writer.py
# Escreve chats e mensagens do Octadesk no banco MySQL (seducar).
# Espelha a estrutura do cache SQLite local (octadesk_db.py).

import json
import logging
import os
from datetime import datetime
from typing import List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# CONEXÃO — suporta contexto com e sem Streamlit (cron/script)
# ──────────────────────────────────────────────────────────────────────────────

def _get_engine():
    """Retorna engine MySQL de escrita, compatível com Streamlit e cron."""
    # Tenta via conector padrão do projeto (usa st.secrets ou .env)
    try:
        from conexao.mysql_connector import conectar_mysql_writer
        engine = conectar_mysql_writer()
        if engine is not None:
            return engine
    except Exception:
        pass

    # Fallback direto via .env (para uso em cron sem Streamlit)
    from dotenv import load_dotenv
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL

    load_dotenv()
    creds = {
        "user":     os.getenv("DB_WRITE_USER"),
        "password": os.getenv("DB_WRITE_PASSWORD"),
        "host":     os.getenv("DB_WRITE_HOST"),
        "port":     os.getenv("DB_WRITE_PORT", "3306"),
        "db_name":  os.getenv("DB_WRITE_NAME"),
    }
    if not all(creds.values()):
        logger.error("Credenciais MySQL de escrita não encontradas (DB_WRITE_*).")
        return None

    try:
        url = URL.create(
            drivername="mysql+mysqlconnector",
            username=creds["user"],
            password=creds["password"],
            host=creds["host"],
            port=int(creds["port"]),
            database=creds["db_name"],
        )
        return create_engine(url, pool_recycle=3600)
    except Exception as e:
        logger.error("Erro ao criar engine MySQL: %s", e)
        return None


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _parse_dt(value: Optional[str]) -> Optional[str]:
    """Converte string ISO 8601 para formato MySQL DATETIME (sem tz)."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        # Tenta só os primeiros 19 chars (ex: "2024-01-15T10:30:00...")
        return value[:19] if len(value) >= 19 else None


def _extract_fields(chat: dict) -> dict:
    """Extrai campos estruturados do dict raw do chat."""
    contact = chat.get("contact") or {}
    agent   = chat.get("agent") or {}
    tags    = chat.get("tags") or []

    # Telefone(s)
    phone_contacts = contact.get("phoneContacts") or []
    phones = []
    for pc in phone_contacts:
        if isinstance(pc, dict) and pc.get("number"):
            country = pc.get("countryCode", "")
            number  = str(pc["number"])
            phones.append(f"+{country}{number}" if country else number)
    phone = " / ".join(phones) if phones else None

    # Bot name
    bot_interactions = chat.get("botInteractions") or []
    bot_name = None
    if bot_interactions and isinstance(bot_interactions[0], dict):
        bot_name = bot_interactions[0].get("name") or bot_interactions[0].get("botName")

    # Survey / NPS
    survey = chat.get("survey") or {}
    survey_response = None
    if isinstance(survey, dict) and survey:
        survey_response = json.dumps(survey, ensure_ascii=False)

    # Tags como JSON string
    tags_str = json.dumps(tags, ensure_ascii=False) if tags else None

    return {
        "status":           str(chat.get("status", "")).lower() or None,
        "created_at":       _parse_dt(chat.get("createdAt")),
        "updated_at_octa":  _parse_dt(chat.get("updatedAt")),
        "closed_at":        _parse_dt(chat.get("closedAt")),
        "phone":            phone,
        "contact_name":     contact.get("name"),
        "agent_name":       agent.get("name"),
        "channel":          chat.get("channel"),
        "tags":             tags_str,
        "group":            (chat.get("group") or {}).get("name") if isinstance(chat.get("group"), dict) else chat.get("group"),
        "origin":           chat.get("origin"),
        "bot_name":         bot_name,
        "survey_response":  survey_response,
    }


# ──────────────────────────────────────────────────────────────────────────────
# FUNÇÕES PÚBLICAS
# ──────────────────────────────────────────────────────────────────────────────

_INSERT_CHAT = text("""
    INSERT INTO seducar.octadesk_chats (
        id, status, created_at, updated_at_octa, closed_at,
        phone, contact_name, agent_name, channel, tags,
        `group`, origin, bot_name, survey_response,
        raw_json, cached_at, synced_at
    ) VALUES (
        :id, :status, :created_at, :updated_at_octa, :closed_at,
        :phone, :contact_name, :agent_name, :channel, :tags,
        :group, :origin, :bot_name, :survey_response,
        :raw_json, :cached_at, NOW()
    )
    ON DUPLICATE KEY UPDATE
        status           = VALUES(status),
        updated_at_octa  = VALUES(updated_at_octa),
        closed_at        = VALUES(closed_at),
        phone            = VALUES(phone),
        contact_name     = VALUES(contact_name),
        agent_name       = VALUES(agent_name),
        channel          = VALUES(channel),
        tags             = VALUES(tags),
        `group`          = VALUES(`group`),
        origin           = VALUES(origin),
        bot_name         = VALUES(bot_name),
        survey_response  = VALUES(survey_response),
        raw_json         = VALUES(raw_json),
        synced_at        = NOW()
""")

_INSERT_MESSAGE = text("""
    INSERT INTO seducar.octadesk_messages (id, chat_id, raw_json, cached_at, synced_at)
    VALUES (:id, :chat_id, :raw_json, :cached_at, NOW())
    ON DUPLICATE KEY UPDATE
        raw_json  = VALUES(raw_json),
        synced_at = NOW()
""")

_INSERT_SYNC_LOG = text("""
    INSERT INTO seducar.octadesk_sync_log
        (sync_type, source, pages_fetched, chats_saved, messages_saved,
         oldest_chat_date, newest_chat_date, duration_seconds, error_message)
    VALUES
        (:sync_type, :source, :pages_fetched, :chats_saved, :messages_saved,
         :oldest_chat_date, :newest_chat_date, :duration_seconds, :error_message)
""")


def save_chats_mysql(chats_list: list, cached_at: Optional[str] = None) -> int:
    """
    Insere ou atualiza chats no MySQL.
    Retorna a quantidade de chats processados com sucesso.

    Args:
        chats_list: lista de dicts raw da API Octadesk.
        cached_at:  valor padrão para cached_at (ISO string). Se None, usa NOW().
    """
    if not chats_list:
        return 0

    engine = _get_engine()
    if engine is None:
        logger.error("save_chats_mysql: engine indisponível, abortando.")
        return 0

    saved = 0
    _cached_at = cached_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with engine.begin() as conn:
            for chat in chats_list:
                chat_id = chat.get("id")
                if not chat_id:
                    continue
                fields = _extract_fields(chat)
                try:
                    conn.execute(_INSERT_CHAT, {
                        "id":               chat_id,
                        "raw_json":         json.dumps(chat, ensure_ascii=False, default=str),
                        "cached_at":        _cached_at,
                        **fields,
                    })
                    saved += 1
                except Exception as e:
                    logger.warning("Erro ao salvar chat %s: %s", chat_id, e)
    except Exception as e:
        logger.error("Erro na transação save_chats_mysql: %s", e)

    logger.info("save_chats_mysql: %d/%d chats salvos no MySQL.", saved, len(chats_list))
    return saved


def save_messages_mysql(chat_id: str, messages_list: list, cached_at: Optional[str] = None) -> int:
    """
    Insere ou atualiza mensagens de um chat no MySQL.
    Retorna a quantidade de mensagens processadas com sucesso.
    """
    if not messages_list or not chat_id:
        return 0

    engine = _get_engine()
    if engine is None:
        logger.error("save_messages_mysql: engine indisponível, abortando.")
        return 0

    saved = 0
    _cached_at = cached_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with engine.begin() as conn:
            for idx, msg in enumerate(messages_list):
                msg_id = msg.get("id") or msg.get("_id") or f"{chat_id}_{idx}"
                try:
                    conn.execute(_INSERT_MESSAGE, {
                        "id":       msg_id,
                        "chat_id":  chat_id,
                        "raw_json": json.dumps(msg, ensure_ascii=False, default=str),
                        "cached_at": _cached_at,
                    })
                    saved += 1
                except Exception as e:
                    logger.warning("Erro ao salvar mensagem %s: %s", msg_id, e)
    except Exception as e:
        logger.error("Erro na transação save_messages_mysql (chat %s): %s", chat_id, e)

    return saved


def log_sync_mysql(
    sync_type: str = "cron",
    source: str = "sqlite",
    pages_fetched: int = 0,
    chats_saved: int = 0,
    messages_saved: int = 0,
    oldest_chat_date: Optional[str] = None,
    newest_chat_date: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    error_message: Optional[str] = None,
) -> bool:
    """Registra uma entrada de log de sincronização no MySQL."""
    engine = _get_engine()
    if engine is None:
        return False
    try:
        with engine.begin() as conn:
            conn.execute(_INSERT_SYNC_LOG, {
                "sync_type":        sync_type,
                "source":           source,
                "pages_fetched":    pages_fetched,
                "chats_saved":      chats_saved,
                "messages_saved":   messages_saved,
                "oldest_chat_date": oldest_chat_date,
                "newest_chat_date": newest_chat_date,
                "duration_seconds": round(duration_seconds, 2) if duration_seconds else None,
                "error_message":    error_message,
            })
        return True
    except Exception as e:
        logger.error("Erro ao registrar log de sync no MySQL: %s", e)
        return False
