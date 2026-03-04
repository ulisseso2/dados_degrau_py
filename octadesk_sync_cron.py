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

import os
import sys
import json
import time
import logging
import argparse
import requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Garante que o diretório do projeto está no path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import octadesk_db

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


def fetch_all_chats(token, base_url, max_pages=120, limit=100):
    """Busca TODOS os chats disponíveis na API e salva no cache."""
    url = f"{base_url}/chat"
    headers = {"accept": "application/json", "X-API-KEY": token}
    
    total_saved = 0
    page = 1
    
    logger.info(f"Iniciando busca de chats (máx {max_pages} páginas)...")
    
    while page <= max_pages:
        params = {"page": page, "limit": limit}
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            items = _normalize_list_response(data)
            
            if not items:
                logger.info(f"Página {page}: vazia — fim dos dados")
                break
            
            saved = octadesk_db.save_chats(items)
            total_saved += saved
            
            if page % 10 == 0:
                logger.info(f"Página {page}/{max_pages} — {total_saved} chats salvos até agora")
            
            if len(items) < limit:
                logger.info(f"Página {page}: {len(items)} itens (< {limit}) — última página")
                break
            
            page += 1
            time.sleep(0.5)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro na página {page}: {e}")
            time.sleep(2)
            # Tenta mais uma vez
            try:
                response = requests.get(url, params=params, headers=headers, timeout=30)
                response.raise_for_status()
                data = response.json()
                items = _normalize_list_response(data)
                if items:
                    saved = octadesk_db.save_chats(items)
                    total_saved += saved
                page += 1
                time.sleep(0.5)
            except Exception:
                logger.error(f"Falha definitiva na página {page}. Parando busca de chats.")
                break
    
    logger.info(f"Fase 1 concluída: {total_saved} chats salvos em {page} páginas")
    return total_saved, page


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
        
        endpoints = [
            f"{base_url}/chat/{chat_id}/messages",
            f"{base_url}/chat/{chat_id}/message",
        ]
        
        msgs = []
        for url in endpoints:
            try:
                response = requests.get(url, headers=headers, timeout=30)
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                data = response.json()
                msgs = _normalize_list_response(data)
                break
            except requests.exceptions.RequestException:
                continue
            except Exception:
                continue
        
        if msgs:
            saved = octadesk_db.save_messages(chat_id, msgs)
            total_msgs_saved += saved
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
    
    token, base_url = _load_config()
    
    # Stats antes
    stats_before = octadesk_db.get_cache_stats()
    logger.info(f"Cache atual: {stats_before['total_chats']} chats, {stats_before['total_messages']} msgs")
    
    start_time = time.time()
    total_chats = 0
    pages_fetched = 0
    total_msgs = 0
    
    # Fase 1: Chats
    if not args.only_messages:
        total_chats, pages_fetched = fetch_all_chats(token, base_url, max_pages=args.max_pages)
    
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
