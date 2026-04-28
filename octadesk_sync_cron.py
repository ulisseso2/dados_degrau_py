#!/usr/bin/env python3
"""
octadesk_sync_cron.py - Sincronização automática do Octadesk via cron/systemd

Busca TODOS os chats disponíveis na API do Octadesk e suas mensagens,
salvando no cache SQLite local. A API retém ~30 dias de dados, então
este script deve rodar periodicamente para não perder histórico.

CONFIGURAÇÃO:
  1. Copie .env.example ou configure as variáveis de ambiente:
     - OCTADESK_API_TOKEN (obrigatório)
     - OCTADESK_BASE_URL (obrigatório)

  2. Agende no cron (ex: a cada 6 horas):
     crontab -e
     0 */6 * * * cd /home/ulisses/dados_degrau_py && python3 octadesk_sync_cron.py >> data_cache/sync.log 2>&1

  Ou rode manualmente:
     python3 octadesk_sync_cron.py
     python3 octadesk_sync_cron.py --only-messages   # Só busca msgs de chats já cacheados
     python3 octadesk_sync_cron.py --max-pages 50     # Limita páginas de chats
     python3 octadesk_sync_cron.py --max-messages 500  # Limita qtd de chats para buscar msgs
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

# Garante que o diretório do projeto está no path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import octadesk_db
from utils.octadesk_mysql_writer import (log_sync_mysql, save_chats_mysql,
                                         save_messages_mysql)

# ==============================================================================
# CONFIGURAÇÃO DE LOGGING
# ==============================================================================
LOG_DIR = PROJECT_ROOT / "data_cache"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_DIR / "octadesk_sync.log"), encoding="utf-8"),
    ]
)
logger = logging.getLogger("octadesk_sync")


# ==============================================================================
# FUNÇÕES DE BUSCA NA API
# ==============================================================================

def _load_config():
    """Carrega token e base_url do .env ou .streamlit/secrets.toml."""
    load_dotenv()
    
    token = os.getenv("OCTADESK_API_TOKEN")
    base_url = os.getenv("OCTADESK_BASE_URL") or os.getenv("OCTADESK_API_BASE_URL")
    
    # Tenta ler de .streamlit/secrets.toml se não encontrou em .env
    if not token or not base_url:
        secrets_path = PROJECT_ROOT / ".streamlit" / "secrets.toml"
        if secrets_path.exists():
            try:
                import tomllib
            except ImportError:
                try:
                    import tomli as tomllib
                except ImportError:
                    tomllib = None
            
            if tomllib:
                try:
                    with open(secrets_path, "rb") as f:
                        secrets = tomllib.load(f)
                    octadesk_conf = secrets.get("octadesk_api", {})
                    token = token or octadesk_conf.get("token")
                    base_url = base_url or octadesk_conf.get("base_url") or octadesk_conf.get("octadesk_base_url")
                except Exception as e:
                    logger.warning(f"Erro ao ler secrets.toml: {e}")
    
    if not token:
        logger.error("OCTADESK_API_TOKEN não encontrado. Configure em .env ou .streamlit/secrets.toml")
        sys.exit(1)
    if not base_url:
        logger.error("OCTADESK_BASE_URL não encontrado. Configure em .env ou .streamlit/secrets.toml")
        sys.exit(1)
    
    return token, base_url.rstrip("/")


def _normalize_list_response(data):
    """Normaliza resposta da API para lista."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ["data", "items", "results", "content"]:
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


def _api_request_with_retry(url, headers, params=None, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as exc:
            status_code = exc.response.status_code if exc.response else None
            if status_code in {429, 500, 502, 503, 504} and attempt < max_retries - 1:
                wait_seconds = 2 ** (attempt + 1)
                logger.warning("Erro HTTP %s em %s. Nova tentativa em %ss.", status_code, url, wait_seconds)
                time.sleep(wait_seconds)
                continue
            raise
        except requests.exceptions.ConnectionError:
            if attempt < max_retries - 1:
                wait_seconds = 2 ** (attempt + 1)
                logger.warning("Falha de conexão em %s. Nova tentativa em %ss.", url, wait_seconds)
                time.sleep(wait_seconds)
                continue
            raise
    return None


def _build_updated_since(last_sync):
    if not last_sync:
        return None
    try:
        last_sync_dt = datetime.fromisoformat(str(last_sync).replace('Z', '+00:00'))
        return (last_sync_dt - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S')
    except Exception:
        return None


def fetch_all_chats(token, base_url, max_pages=120, limit=100, updated_since=None):
    """Busca chats na API usando paginação e filtro incremental por updatedAt."""
    url = f"{base_url}/chat"
    headers = {"accept": "application/json", "X-API-KEY": token}
    
    total_saved = 0
    page = 1
    pages_processed = 0
    
    if updated_since:
        logger.info("Iniciando busca incremental de chats (updatedAt >= %s, máx %d páginas)...", updated_since, max_pages)
    else:
        logger.info("Iniciando busca completa de chats (máx %d páginas)...", max_pages)
    
    while page <= max_pages:
        params = {
            "page": page,
            "limit": limit,
            "sort[property]": "createdAt",
            "sort[direction]": "desc",
        }
        if updated_since:
            params["filters[0][property]"] = "updatedAt"
            params["filters[0][operator]"] = "ge"
            params["filters[0][value]"] = updated_since

        try:
            response = _api_request_with_retry(url, headers, params)
            if response is None:
                logger.error("Falha após retentativas na página %d", page)
                break
            data = response.json()
            items = _normalize_list_response(data)
            pages_processed += 1
            
            if not items:
                logger.info(f"Página {page}: vazia — fim dos dados")
                break
            
            saved = octadesk_db.save_chats(items)
            total_saved += saved
            mysql_saved = save_chats_mysql(items)
            logger.info(
                "Página %d: %d chats → SQLite(%d) MySQL(%d)",
                page, len(items), saved, mysql_saved,
            )
            
            if len(items) < limit:
                logger.info(f"Página {page}: {len(items)} itens (< {limit}) — última página")
                break
            
            page += 1
            time.sleep(0.5)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro na página {page}: {e}")
            logger.error(f"Falha definitiva na página {page}. Parando busca de chats.")
            break
    
    logger.info(f"Fase 1 concluída: {total_saved} chats salvos em {pages_processed} páginas")
    return total_saved, pages_processed


def _fetch_messages_paginated(headers, base_url, chat_id, max_pages=20, limit=100):
    endpoints = [
        f"{base_url}/chat/{chat_id}/messages",
        f"{base_url}/chat/{chat_id}/message",
    ]

    for url in endpoints:
        all_messages = []
        page = 1
        try:
            while page <= max_pages:
                response = _api_request_with_retry(
                    url,
                    headers,
                    {"page": page, "limit": limit},
                )
                if response is None:
                    break
                if response.status_code == 404:
                    break
                data = response.json()
                items = _normalize_list_response(data)

                if not items:
                    break

                all_messages.extend(items)
                if len(items) < limit:
                    break

                page += 1
                time.sleep(0.2)
        except requests.exceptions.HTTPError as exc:
            if exc.response and exc.response.status_code == 404:
                continue
            logger.warning("Erro ao paginar mensagens do chat %s em %s: %s", chat_id, url, exc)
            continue
        except requests.exceptions.RequestException as exc:
            logger.warning("Erro de rede ao buscar mensagens do chat %s em %s: %s", chat_id, url, exc)
            continue

        if all_messages:
            return all_messages

    return []


def fetch_missing_messages(token, base_url, max_messages=None):
    """Busca mensagens para chats que ainda não têm mensagens em cache."""
    headers = {"accept": "application/json", "X-API-KEY": token}
    
    chats_missing = octadesk_db.get_chats_without_messages()
    total_missing = len(chats_missing)
    
    if total_missing == 0:
        logger.info("Todos os chats já possuem mensagens em cache!")
        return 0
    
    if max_messages:
        chats_missing = chats_missing[:max_messages]
    
    logger.info(f"Buscando mensagens para {len(chats_missing)} chats (de {total_missing} sem cache)...")
    
    total_msgs_saved = 0
    errors = 0
    
    for idx, chat_id in enumerate(chats_missing):
        if (idx + 1) % 50 == 0:
            logger.info(f"Progresso: {idx+1}/{len(chats_missing)} — {total_msgs_saved} msgs salvas — {errors} erros")

        msgs = _fetch_messages_paginated(headers, base_url, chat_id)
        
        if msgs:
            saved = octadesk_db.save_messages(chat_id, msgs)
            total_msgs_saved += saved
            save_messages_mysql(chat_id, msgs)
        else:
            errors += 1
            # Salva registro vazio para marcar que já tentou (evita re-tentativa infinita)
            # Não fazemos isso — deixamos tentar novamente no próximo ciclo
        
        time.sleep(0.2)
    
    logger.info(f"Fase 2 concluída: {total_msgs_saved} mensagens salvas ({errors} chats sem resposta)")
    return total_msgs_saved


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Sincronização automática do Octadesk")
    parser.add_argument("--max-pages", type=int, default=120,
                        help="Máximo de páginas de chats a buscar (default: 120)")
    parser.add_argument("--max-messages", type=int, default=None,
                        help="Máximo de chats para buscar mensagens (default: todos)")
    parser.add_argument("--only-messages", action="store_true",
                        help="Pula busca de chats, só busca mensagens de chats já cacheados")
    parser.add_argument("--only-chats", action="store_true",
                        help="Só busca chats, pula busca de mensagens")
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("OCTADESK SYNC — Início")
    logger.info("=" * 60)

    purged = octadesk_db.purge_placeholder_messages()
    if purged:
        logger.info("Placeholders inválidos removidos do cache: %d", purged)
    
    token, base_url = _load_config()
    
    # Stats antes
    stats_before = octadesk_db.get_cache_stats()
    logger.info(f"Cache atual: {stats_before['total_chats']} chats, {stats_before['total_messages']} msgs")
    updated_since = _build_updated_since(stats_before.get('last_sync')) if not args.only_messages else None
    if updated_since:
        logger.info("Modo incremental ativo. Filtro de chats por updatedAt >= %s", updated_since)
    
    start_time = time.time()
    total_chats = 0
    pages_fetched = 0
    total_msgs = 0
    
    # Fase 1: Chats
    if not args.only_messages:
        total_chats, pages_fetched = fetch_all_chats(
            token,
            base_url,
            max_pages=args.max_pages,
            updated_since=updated_since,
        )
    
    # Fase 2: Mensagens
    if not args.only_chats:
        total_msgs = fetch_missing_messages(token, base_url, max_messages=args.max_messages)
    
    elapsed = time.time() - start_time
    
    # Log da sincronização
    octadesk_db.log_sync(
        sync_type='cron',
        pages_fetched=pages_fetched,
        chats_saved=total_chats,
        messages_saved=total_msgs
    )
    log_sync_mysql(
        sync_type='cron',
        source='api',
        pages_fetched=pages_fetched,
        chats_saved=total_chats,
        messages_saved=total_msgs,
        duration_seconds=elapsed,
    )
    
    # Stats depois
    stats_after = octadesk_db.get_cache_stats()
    
    logger.info("-" * 60)
    logger.info(f"RESUMO:")
    logger.info(f"  Chats salvos nesta sync: {total_chats}")
    logger.info(f"  Mensagens salvas nesta sync: {total_msgs}")
    logger.info(f"  Total no cache: {stats_after['total_chats']} chats, {stats_after['total_messages']} msgs")
    logger.info(f"  Chats sem mensagens: {stats_after.get('chats_without_messages', '?')}")
    logger.info(f"  Tempo total: {elapsed:.1f}s ({elapsed/60:.1f} min)")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
