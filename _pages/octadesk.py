# _pages/octadesk.py - Com cache SQLite para chats fechados

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import pandas as pd
import requests
from dotenv import load_dotenv
import time
from datetime import datetime
import plotly.express as px
import octadesk_db
from utils.chat_ia_analyzer import ChatIAAnalyzer
from utils.chat_mysql_writer import salvar_avaliacao_chat
from utils.sql_loader import carregar_dados

load_dotenv()
TIMEZONE = 'America/Sao_Paulo'

SQL_MATCH_OPORTUNIDADES = os.path.join(
    os.path.dirname(__file__), '..', 'consultas', 'chat_oportunidades',
    'buscar_oportunidades_match.sql'
)
SQL_AVALIACOES_EXISTENTES = os.path.join(
    os.path.dirname(__file__), '..', 'consultas', 'chat_oportunidades',
    'avaliacoes_existentes.sql'
)

# ==============================================================================
# 0. CONFIGURAÇÕES
# ==============================================================================

def get_octadesk_base_url():
    """Recupera a base URL do tenant Octadesk."""
    try:
        # Tenta primeiro base_url, depois octadesk_base_url
        base_url = st.secrets["octadesk_api"].get("base_url") or st.secrets["octadesk_api"].get("octadesk_base_url")
    except (st.errors.StreamlitAPIException, KeyError):
        base_url = os.getenv("OCTADESK_BASE_URL") or os.getenv("OCTADESK_API_BASE_URL")

    if not base_url:
        st.error("Base URL da API do Octadesk não encontrada.")
    return base_url.rstrip("/") if base_url else base_url

# ==============================================================================
# 1. FUNÇÕES AUXILIARES
# ==============================================================================

def get_octadesk_token():
    """Carrega o token da API do Octadesk de forma híbrida e segura."""
    try:
        token = st.secrets["octadesk_api"]["token"]
    except (st.errors.StreamlitAPIException, KeyError):
        token = os.getenv("OCTADESK_API_TOKEN")
    
    if not token:
        st.error("Token da API do Octadesk não encontrado.")
    return token

def _normalize_list_response(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ["data", "items", "results", "content"]:
            if key in data and isinstance(data[key], list):
                return data[key]
    return []

def _api_request_with_retry(url, headers, params=None, max_retries=3):
    """Faz request GET com retry e backoff exponencial."""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as http_err:
            status = http_err.response.status_code if http_err.response else 0
            if status == 429 or status >= 500:
                wait = 2 ** (attempt + 1)
                time.sleep(wait)
                continue
            raise
        except requests.exceptions.ConnectionError:
            if attempt < max_retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            raise
    return None


def _fetch_chats_from_api(api_token, base_url, max_pages=5, limit=100,
                          start_date=None, end_date=None, stop_before_date=None,
                          updated_since=None):
    """Busca chats da API do Octadesk com filtros de data e paginação.

    Parâmetros:
      start_date/end_date: filtrar por createdAt (date objects)
      updated_since: filtrar por updatedAt >= (ISO string), para sync incremental
      stop_before_date: fallback — para de paginar quando chats são anteriores
    """
    url = f"{base_url}/chat"
    headers = {"accept": "application/json", "X-API-KEY": api_token}
    all_results = []
    page = 1
    reached_target = False

    while page <= max_pages:
        params = {"page": page, "limit": limit}

        # Filtros de data via deep-object query (API Octadesk)
        filter_idx = 0
        if start_date:
            params[f"filters[{filter_idx}][property]"] = "createdAt"
            params[f"filters[{filter_idx}][operator]"] = "ge"
            params[f"filters[{filter_idx}][value]"] = str(start_date)
            filter_idx += 1
        if end_date:
            from datetime import timedelta
            # +1 dia para incluir o dia inteiro (API compara com datetime UTC)
            end_plus = end_date + timedelta(days=1)
            params[f"filters[{filter_idx}][property]"] = "createdAt"
            params[f"filters[{filter_idx}][operator]"] = "le"
            params[f"filters[{filter_idx}][value]"] = str(end_plus)
            filter_idx += 1
        if updated_since:
            params[f"filters[{filter_idx}][property]"] = "updatedAt"
            params[f"filters[{filter_idx}][operator]"] = "ge"
            params[f"filters[{filter_idx}][value]"] = updated_since
            filter_idx += 1

        # Ordenação: mais recentes primeiro
        params["sort[property]"] = "createdAt"
        params["sort[direction]"] = "desc"

        try:
            response = _api_request_with_retry(url, headers, params)
            if response is None:
                st.error(f"Falha após retries na página {page}")
                break
            data = response.json()
            items = _normalize_list_response(data)
            if not items:
                break
            all_results.extend(items)

            # Paginação inteligente (fallback se sem filtro de data)
            if stop_before_date and not start_date and items:
                oldest_on_page = min(
                    (i.get('createdAt', '')[:10] for i in items if i.get('createdAt')),
                    default=''
                )
                if oldest_on_page and oldest_on_page < str(stop_before_date):
                    reached_target = True
                    break

            if len(items) < limit:
                break
            page += 1
            time.sleep(0.3)  # Rate limiting
        except requests.exceptions.HTTPError as http_err:
            st.error(f"Erro na API do Octadesk (página {page}): {http_err.response.status_code} - {http_err.response.text}")
            break
        except Exception as e:
            st.error(f"Erro ao buscar dados do Octadesk: {e}")
            break

    if page > max_pages and not reached_target:
        st.warning(
            f"⚠️ Limite de {max_pages} páginas atingido sem cobrir todo o período. "
            f"Use **Sincronizar** na sidebar para popular o cache local com dados históricos."
        )

    return all_results


def get_octadesk_chats(api_token, base_url, start_date, end_date, max_pages=5, limit=100, force_api=False):
    """Busca chats combinando cache SQLite (fechados) + API (recentes/abertos).
    
    Estratégia:
    - Datas recentes (últimos 2 dias): busca API + complementa com cache
    - Datas passadas: prioriza cache SQLite, busca API apenas se cache vazio
    """
    from datetime import date

    try:
        today = date.today()

        # Validação: data futura
        if start_date > today:
            st.warning(
                f"⚠️ A data selecionada ({start_date.strftime('%d/%m/%Y')}) é **no futuro**. "
                f"Hoje é {today.strftime('%d/%m/%Y')}. Selecione uma data até hoje."
            )
            return pd.DataFrame()

        days_ago_end = (today - end_date).days
        is_recent = days_ago_end <= 2  # Últimos 2 dias: sempre buscar API

        # 1. Buscar chats do cache SQLite para o período
        cached_chats = []
        if not force_api:
            cached_chats = octadesk_db.get_cached_chats(start_date=start_date, end_date=end_date)

        # 2. Decidir se precisa buscar da API
        need_api = force_api or is_recent or len(cached_chats) == 0
        api_chats = []

        if need_api:
            api_chats = _fetch_chats_from_api(
                api_token, base_url, max_pages, limit,
                start_date=start_date, end_date=end_date,
                stop_before_date=start_date
            )
            # Salvar TODOS os chats da API no cache automaticamente
            if api_chats:
                octadesk_db.save_chats(api_chats)

            # Se não é recente, recarregar o cache (agora com novos dados)
            if not is_recent and not force_api:
                cached_chats = octadesk_db.get_cached_chats(start_date=start_date, end_date=end_date)
        elif not is_recent and cached_chats:
            st.info(f"📦 Exibindo **{len(cached_chats)}** chats do cache local para este período.")

        # 3. Combinar API + cache (API tem prioridade para deduplicação)
        seen_ids = set()
        combined = []
        for chat in api_chats:
            chat_id = chat.get('id')
            if chat_id and chat_id not in seen_ids:
                seen_ids.add(chat_id)
                combined.append(chat)
        for chat in cached_chats:
            chat_id = chat.get('id')
            if chat_id and chat_id not in seen_ids:
                seen_ids.add(chat_id)
                combined.append(chat)

        if not combined:
            cache_stats = octadesk_db.get_cache_stats()
            cache_range = ""
            if cache_stats.get('oldest_chat') and cache_stats.get('newest_chat'):
                try:
                    o = pd.to_datetime(cache_stats['oldest_chat']).strftime('%d/%m/%Y')
                    n = pd.to_datetime(cache_stats['newest_chat']).strftime('%d/%m/%Y')
                    cache_range = f" O cache cobre de **{o}** a **{n}**."
                except Exception:
                    pass
            st.warning(
                f"Nenhum chat encontrado para **{start_date.strftime('%d/%m/%Y')}** "
                f"a **{end_date.strftime('%d/%m/%Y')}**.{cache_range} "
                f"Clique em **📥 Sincronizar** na sidebar para importar mais histórico."
            )
            return pd.DataFrame()

        # 4. Normalizar para DataFrame e filtrar por data (fuso correto)
        df = pd.json_normalize(combined)
        if 'createdAt' in df.columns:
            df['createdAt'] = pd.to_datetime(df['createdAt'], utc=True, errors='coerce')
            df['createdAt'] = df['createdAt'].dt.tz_convert(TIMEZONE)
            df = df[(df['createdAt'].dt.date >= start_date) & (df['createdAt'].dt.date <= end_date)]

        return df

    except Exception as e:
        st.error(f"Erro ao buscar chats: {e}")
        import traceback
        st.code(traceback.format_exc())
        return pd.DataFrame()


def _fetch_messages_from_api(api_token, base_url, chat_id, max_pages=10):
    """Busca TODAS as mensagens de um chat com paginação completa."""
    headers = {"accept": "application/json", "X-API-KEY": api_token}
    endpoints = [
        f"{base_url}/chat/{chat_id}/messages",
        f"{base_url}/chat/{chat_id}/message"
    ]
    for url in endpoints:
        all_messages = []
        page = 1
        try:
            while page <= max_pages:
                params = {
                    "page": page,
                    "limit": 100,
                    "property": "time",
                    "direction": "asc"
                }
                response = _api_request_with_retry(url, headers, params)
                if response is None:
                    break
                if response.status_code == 404:
                    break
                response.raise_for_status()
                data = response.json()
                items = _normalize_list_response(data)
                if not items:
                    break
                all_messages.extend(items)
                if len(items) < 100:
                    break
                page += 1
                time.sleep(0.2)
            if all_messages:
                return all_messages
            if page > 1:
                return all_messages
        except requests.exceptions.HTTPError as http_err:
            if http_err.response and http_err.response.status_code == 404:
                continue
            st.error(
                f"Erro na API do Octadesk ao buscar mensagens do chat {chat_id}: "
                f"{http_err.response.status_code} - {http_err.response.text}"
            )
            return all_messages if all_messages else []
        except Exception as e:
            st.error(f"Erro ao buscar mensagens do chat {chat_id}: {e}")
            return all_messages if all_messages else []
    return []


def get_octadesk_chat_messages(api_token, base_url, chat_id, chat_status=None):
    """Busca mensagens de um chat. Usa cache SQLite para TODOS os chats."""
    # 1. Verificar cache SQLite primeiro (qualquer status)
    cached = octadesk_db.get_cached_messages(chat_id)
    if cached:
        return cached

    # 2. Buscar da API
    messages = _fetch_messages_from_api(api_token, base_url, chat_id)

    # 3. Salvar no cache para próximas consultas (qualquer status)
    if messages:
        octadesk_db.save_messages(chat_id, messages)

    return messages


def sync_octadesk_history(api_token, base_url, max_pages=120, limit=100, mode='auto'):
    """Sincroniza chats e mensagens do Octadesk para o cache SQLite.

    Modos:
      'auto': Incremental se já sincronizou antes, completo se não.
      'completo': Busca todas as páginas do zero.
      'incremental': Busca apenas chats atualizados desde a última sync.

    Fase 1: Busca chats (com filtro incremental quando possível).
    Fase 2: Busca mensagens dos chats sem cache (priorizando os mais recentes).
    """
    cache_stats = octadesk_db.get_cache_stats()
    last_sync = cache_stats.get('last_sync')

    # Decidir modo efetivo
    if mode == 'auto':
        effective_mode = 'incremental' if last_sync else 'completo'
    else:
        effective_mode = mode

    updated_since = None
    if effective_mode == 'incremental' and last_sync:
        # Buscar chats atualizados desde a última sync (com margem de 1h)
        from datetime import timedelta as _td
        try:
            last_dt = pd.to_datetime(last_sync)
            updated_since = (last_dt - _td(hours=1)).strftime('%Y-%m-%dT%H:%M:%S')
        except Exception:
            effective_mode = 'completo'

    mode_label = "incremental" if effective_mode == 'incremental' else "completa"
    st.info(f"📥 **Fase 1/2**: Buscando chats da API (sync {mode_label})...")
    progress_bar = st.progress(0, text="Buscando chats...")
    total_chats_saved = 0
    page = 1

    # Sync incremental usa menos páginas (dados são recentes)
    effective_max_pages = min(30, max_pages) if effective_mode == 'incremental' else max_pages

    while page <= effective_max_pages:
        progress_bar.progress(
            page / effective_max_pages,
            text=f"Fase 1/2 — Página {page}/{effective_max_pages} — {total_chats_saved} chats salvos"
        )

        params = {"page": page, "limit": limit}
        params["sort[property]"] = "createdAt"
        params["sort[direction]"] = "desc"

        if updated_since:
            params["filters[0][property]"] = "updatedAt"
            params["filters[0][operator]"] = "ge"
            params["filters[0][value]"] = updated_since

        try:
            url = f"{base_url}/chat"
            headers = {"accept": "application/json", "X-API-KEY": api_token}
            response = _api_request_with_retry(url, headers, params)
            if response is None:
                st.error(f"Falha após retries na página {page}")
                break
            data = response.json()
            items = _normalize_list_response(data)

            if not items:
                break

            saved = octadesk_db.save_chats(items)
            total_chats_saved += saved

            if len(items) < limit:
                break

            page += 1
            time.sleep(0.3)

        except Exception as e:
            st.error(f"Erro na sincronização (página {page}): {e}")
            break

    progress_bar.progress(1.0, text=f"✅ Fase 1/2 concluída: {total_chats_saved} chats salvos")

    # ── FASE 2: Buscar mensagens (priorizando chats recentes) ──────
    st.info("📨 **Fase 2/2**: Buscando mensagens dos chats sem cache...")
    chats_missing = octadesk_db.get_chats_without_messages()
    total_missing = len(chats_missing)
    total_messages_saved = 0
    errors = 0

    if total_missing > 0:
        progress_msgs = st.progress(0, text=f"Buscando mensagens... 0/{total_missing}")
        for idx, chat_id in enumerate(chats_missing):
            progress_msgs.progress(
                (idx + 1) / total_missing,
                text=f"Fase 2/2 — Chat {idx+1}/{total_missing} — {total_messages_saved} msgs salvas ({errors} erros)"
            )
            try:
                msgs = _fetch_messages_from_api(api_token, base_url, chat_id)
                if msgs:
                    octadesk_db.save_messages(chat_id, msgs)
                    total_messages_saved += len(msgs)
                else:
                    # Salvar registro vazio para não tentar novamente
                    octadesk_db.save_messages(chat_id, [{"id": f"{chat_id}_empty", "body": "", "type": "placeholder"}])
            except Exception:
                errors += 1
                if errors > 50:
                    st.warning(f"⚠️ Muitos erros ({errors}), interrompendo busca de mensagens.")
                    break
                continue
        progress_msgs.progress(1.0, text=f"✅ Fase 2/2 concluída: {total_messages_saved} mensagens salvas")
    else:
        st.success("✅ Todos os chats já possuem mensagens em cache!")

    octadesk_db.log_sync(
        sync_type=f'manual_{effective_mode}',
        pages_fetched=page,
        chats_saved=total_chats_saved,
        messages_saved=total_messages_saved
    )

    st.success(
        f"✅ Sincronização {mode_label} concluída: **{total_chats_saved}** chats e "
        f"**{total_messages_saved}** mensagens salvas no cache."
    )
    return total_chats_saved, total_messages_saved

def get_octadesk_messages(api_token, base_url, chats_df, max_chats=20):
    if chats_df is None or chats_df.empty or 'id' not in chats_df.columns:
        return pd.DataFrame()

    messages = []
    chats_to_fetch = chats_df.head(max_chats)

    for _, row in chats_to_fetch.iterrows():
        chat_id = row.get('id')
        if not chat_id:
            continue
        chat_status = str(row.get('status', '')).lower() if 'status' in chats_to_fetch.columns else None
        chat_messages = get_octadesk_chat_messages(api_token, base_url, chat_id, chat_status=chat_status)
        for msg in chat_messages:
            msg["chatId"] = chat_id
            messages.append(msg)

    if not messages:
        return pd.DataFrame()

    df_messages = pd.json_normalize(messages)
    if 'createdAt' in df_messages.columns:
        df_messages['createdAt'] = pd.to_datetime(df_messages['createdAt'], utc=True, errors='coerce')
        df_messages['createdAt'] = df_messages['createdAt'].dt.tz_convert(TIMEZONE)

    return df_messages

def build_chat_transcripts(df_messages, df_chats=None):
    if df_messages is None or df_messages.empty or 'chatId' not in df_messages.columns:
        return pd.DataFrame()

    df = df_messages.copy()

    chat_name_map = {}
    id_name_map = {}
    if df_chats is not None and not df_chats.empty and 'id' in df_chats.columns:
        def _pick_chat_name(row, cols):
            for col in cols:
                val = row.get(col)
                if isinstance(val, str) and val.strip():
                    return val
            return ""

        for _, row in df_chats.iterrows():
            chat_id = row.get('id')
            if not chat_id:
                continue
            chat_name_map[chat_id] = {
                "agent": _pick_chat_name(row, [
                    'agent.name', 'owner.name', 'assignee.name', 'responsible.name', 'user.name'
                ]),
                "contact": _pick_chat_name(row, [
                    'contact.name', 'customer.name', 'client.name', 'visitor.name', 'person.name'
                ]),
                "bot": _pick_chat_name(row, ['bot.name'])
            }

            # Mapeia IDs -> nomes quando disponíveis no chat
            for col in df_chats.columns:
                if not col.endswith('.id'):
                    continue
                base = col[:-3]
                name_col = None
                for suffix in ['.name', '.fullName', '.displayName']:
                    if f"{base}{suffix}" in df_chats.columns:
                        name_col = f"{base}{suffix}"
                        break
                if name_col:
                    entity_id = row.get(col)
                    entity_name = row.get(name_col)
                    if entity_id and isinstance(entity_name, str) and entity_name.strip():
                        id_name_map[str(entity_id)] = entity_name

    # Normaliza campos para transcrição
    sender_candidates = [
        'sentBy.name', 'sentBy.fullName', 'sentBy.displayName', 'sentBy.nickname', 'sentBy',
        'sender.name', 'sender.fullName', 'sender.displayName', 'sender.nickname', 'sender',
        'from.name', 'from.fullName', 'from.displayName', 'from',
        'author.name', 'author.fullName', 'author.displayName', 'author',
        'user.name', 'user.fullName', 'user.displayName', 'user',
        'agent.name', 'agent.fullName', 'agent.displayName', 'agent',
        'owner.name', 'owner.fullName', 'owner.displayName', 'owner',
        'bot.name', 'bot.fullName', 'bot.displayName', 'bot',
        'contact.name', 'contact.fullName', 'contact.displayName', 'contact',
        'customer.name', 'customer.fullName', 'customer.displayName', 'customer',
        'client.name', 'client.fullName', 'client.displayName', 'client',
        'visitor.name', 'visitor.fullName', 'visitor.displayName', 'visitor',
        'person.name', 'person.fullName', 'person.displayName', 'person',
        'responsible.name', 'responsible.fullName', 'responsible.displayName', 'responsible',
        'assignee.name', 'assignee.fullName', 'assignee.displayName', 'assignee'
    ]

    text_candidates = [
        'body', 'text', 'content', 'message',
        'payload.text', 'payload.content', 'payload.message',
        'payload.body', 'payload.html', 'html'
    ]

    role_candidates = [
        'sentBy.type', 'sentBy.role',
        'sender.type', 'sender.role',
        'from.type', 'from.role',
        'author.type', 'author.role',
        'user.type', 'user.role',
        'type', 'messageType', 'direction', 'origin', 'source', 'side', 'flow',
        'eventType', 'event.type'
    ]

    sender_id_candidates = [
        'sentBy.id',
        'sender.id', 'from.id', 'author.id', 'user.id',
        'agent.id', 'owner.id', 'contact.id', 'customer.id', 'client.id',
        'visitor.id', 'person.id', 'responsible.id', 'assignee.id',
        'sentById', 'senderId', 'fromId', 'authorId', 'userId',
        'agentId', 'ownerId', 'contactId', 'customerId', 'clientId',
        'visitorId', 'personId', 'responsibleId', 'assigneeId'
    ]

    needed_cols = set(sender_candidates + text_candidates + role_candidates + sender_id_candidates)
    missing_cols = [c for c in needed_cols if c not in df.columns]
    if missing_cols:
        df = pd.concat(
            [df, pd.DataFrame({c: [None] * len(df) for c in missing_cols})],
            axis=1
        )

    if 'createdAt' in df.columns:
        df = df.sort_values('createdAt')
    elif 'time' in df.columns:
        df['__time_dt'] = pd.to_datetime(df['time'], utc=True, errors='coerce')
        df = df.sort_values('__time_dt')

    def _extract_value(val, keys=None):
        if isinstance(val, str) and val.strip():
            return val
        if isinstance(val, dict):
            keys = keys or []
            for k in keys:
                v = val.get(k)
                if isinstance(v, str) and v.strip():
                    return v
        return ""

    def _pick_first_non_empty(row, cols, dict_keys=None):
        for col in cols:
            val = row.get(col)
            extracted = _extract_value(val, dict_keys)
            if extracted:
                return extracted
        return ""

    df['__msg_text'] = df.apply(
        lambda r: _pick_first_non_empty(r, text_candidates, dict_keys=['text', 'content', 'message', 'body', 'html']),
        axis=1
    )
    df['__sender'] = df.apply(
        lambda r: _pick_first_non_empty(r, sender_candidates, dict_keys=['name', 'fullName', 'displayName', 'nickname', 'email']),
        axis=1
    )

    df['__sender_id'] = df.apply(
        lambda r: _pick_first_non_empty(r, sender_id_candidates, dict_keys=['id']),
        axis=1
    )

    df['__role'] = df.apply(
        lambda r: _pick_first_non_empty(r, role_candidates, dict_keys=['type', 'role', 'kind']).lower(),
        axis=1
    )

    def _role_to_sender(row):
        role = row.get('__role') or ""
        chat_id = row.get('chatId')
        chat_names = chat_name_map.get(chat_id, {})
        sender_id = row.get('__sender_id')

        if sender_id:
            mapped = id_name_map.get(str(sender_id))
            if mapped:
                return mapped

        if role in ['agent', 'attendant', 'operator', 'owner', 'assignee', 'responsible']:
            return chat_names.get('agent')
        if role in ['bot', 'automation', 'workflow', 'robot']:
            return chat_names.get('bot') or 'Bot'
        if role in ['customer', 'client', 'contact', 'visitor', 'user', 'person', 'lead']:
            return chat_names.get('contact')
        if role in ['outbound', 'outgoing']:
            return chat_names.get('agent') or chat_names.get('bot')
        if role in ['inbound', 'incoming']:
            return chat_names.get('contact')

        return ""

    df['__sender'] = df.apply(
        lambda r: r['__sender'] or _role_to_sender(r) or '(sem remetente)',
        axis=1
    )
    if 'createdAt' in df.columns:
        df['__time'] = df['createdAt'].dt.strftime('%Y-%m-%d %H:%M:%S')
    elif 'time' in df.columns:
        df['__time'] = pd.to_datetime(df['time'], utc=True, errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')
    else:
        df['__time'] = ""

    def _format_line(row):
        if row['__time']:
            return f"{row['__time']} - {row['__sender']}: {row['__msg_text']}"
        return f"{row['__sender']}: {row['__msg_text']}"

    df['__line'] = df.apply(_format_line, axis=1)

    transcripts = (
        df.groupby('chatId')['__line']
        .apply(lambda lines: "\n".join([l for l in lines if l and l.strip()]))
        .reset_index()
        .rename(columns={'__line': 'transcricao'})
    )

    return transcripts
# ==============================================================================
# 2. FUNÇÃO PRINCIPAL DA PÁGINA (run_page)
# ==============================================================================

def run_page():
    st.title("💬 Análise de Atendimento (Octadesk)")

    api_token = get_octadesk_token()
    base_url = get_octadesk_base_url()

    if not api_token or not base_url:
        st.stop()

    # --- FILTRO DE DATA (VISUAL) ---
    st.sidebar.header("Filtro de Período (Octadesk)")
    hoje = datetime.now().date()

    date_range = st.sidebar.date_input(
        "Selecione o Período de Análise:",
        [hoje, hoje],
        key="octadesk_date_range",
        disabled=False
    )
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        data_inicio_padrao, data_fim = date_range
    elif isinstance(date_range, (list, tuple)) and len(date_range) == 1:
        st.sidebar.info("📅 Selecione a data final do período...")
        st.stop()
    else:
        data_inicio_padrao = date_range
        data_fim = date_range

    # Auto-cálculo de paginação baseado no período selecionado
    # (API retorna ~300-400 chats/dia → ~3-4 páginas/dia de 100 itens)
    days_back = max(1, (hoje - data_inicio_padrao).days + 1)
    max_pages = max(10, min(200, days_back * 4))
    limit = 100

    # --- CACHE SQLITE ---
    st.sidebar.divider()
    st.sidebar.subheader("📦 Cache Local (SQLite)")
    cache_stats = octadesk_db.get_cache_stats()
    st.sidebar.caption(
        f"💾 **{cache_stats['total_chats']}** chats em cache | "
        f"**{cache_stats['total_messages']}** mensagens"
    )
    chats_sem_msgs = cache_stats.get('chats_without_messages', 0)
    if chats_sem_msgs > 0:
        st.sidebar.caption(f"⚠️ **{chats_sem_msgs}** chats ainda sem mensagens")
    if cache_stats['oldest_chat'] and cache_stats['newest_chat']:
        try:
            oldest = pd.to_datetime(cache_stats['oldest_chat']).strftime('%d/%m/%Y')
            newest = pd.to_datetime(cache_stats['newest_chat']).strftime('%d/%m/%Y')
            st.sidebar.caption(f"📅 Período coberto: {oldest} a {newest}")
        except Exception:
            pass
    if cache_stats['last_sync']:
        try:
            last_sync_dt = pd.to_datetime(cache_stats['last_sync']).strftime('%d/%m/%Y %H:%M')
            st.sidebar.caption(f"🔄 Última sync: {last_sync_dt}")
        except Exception:
            pass

    force_api = st.sidebar.checkbox(
        "🔄 Forçar busca pela API",
        value=False,
        help="Ignora o cache local e busca tudo direto da API"
    )
    col_sync1, col_sync2, col_sync3 = st.sidebar.columns(3)
    with col_sync1:
        btn_sync = st.button("📥 Sync Auto", use_container_width=True,
                              help="Incremental se já sincronizou, completa se não")
    with col_sync2:
        btn_sync_full = st.button("📥 Sync Completa", use_container_width=True,
                                   help="Busca TODOS os chats e mensagens da API")
    with col_sync3:
        btn_clear = st.button("🗑️ Limpar Cache", use_container_width=True)

    if btn_sync:
        sync_octadesk_history(api_token, base_url, max_pages=120, limit=100, mode='auto')
    if btn_sync_full:
        sync_octadesk_history(api_token, base_url, max_pages=120, limit=100, mode='completo')
    if btn_clear:
        octadesk_db.clear_cache()
        st.toast("Cache limpo com sucesso!")
        st.rerun()

    st.divider()

    # --- Diagnóstico do Cache (expandir para debug) ---
    with st.expander("🔍 Diagnóstico do Cache", expanded=False):
        diag_stats = octadesk_db.get_cache_stats()
        st.write(f"**DB Path:** `{octadesk_db.DB_FILE}`")
        st.write(f"**Chats em cache:** {diag_stats['total_chats']} (fechados: {diag_stats['closed_chats']})")
        st.write(f"**Mensagens em cache:** {diag_stats['total_messages']}")
        st.write(f"**Período:** {diag_stats['oldest_chat'] or 'N/A'} → {diag_stats['newest_chat'] or 'N/A'}")
        st.write(f"**Período selecionado:** {data_inicio_padrao} a {data_fim}")
        st.write(f"**Forçar API:** {force_api} | **Máx páginas:** {max_pages}")

    # --- Tabela de Validação ---
    df_chats = get_octadesk_chats(api_token, base_url, data_inicio_padrao, data_fim, max_pages=max_pages, limit=limit, force_api=force_api)

    if df_chats is not None and not df_chats.empty:
        # --- Filtros ---
        df_chats_filtered = df_chats.copy()

        if 'agent.name' in df_chats_filtered.columns:
            df_chats_filtered['agent.name'] = df_chats_filtered['agent.name'].fillna('Bot')

        if 'conversationOrigin' in df_chats_filtered.columns:
            def _map_origin(val):
                if not isinstance(val, str):
                    return val
                if val == '+552139701015':
                    return 'Whats Degrau'
                if val == '+551130178800':
                    return 'Whats Central'
                if val == 'Degrau Cultural • Concursos (@degraucultural)':
                    return 'Insta Degrau'
                return val

            df_chats_filtered['conversationOriginLabel'] = df_chats_filtered['conversationOrigin'].apply(_map_origin)

        # --- Marcar chats já avaliados via IA ---
        try:
            df_aval = carregar_dados(SQL_AVALIACOES_EXISTENTES)
            evaluated_ids = set(df_aval['chat_id'].dropna().astype(str).tolist()) if df_aval is not None and not df_aval.empty else set()
        except Exception:
            evaluated_ids = set()

        if 'id' in df_chats_filtered.columns:
            df_chats_filtered['Já Avaliado'] = df_chats_filtered['id'].astype(str).isin(evaluated_ids)
        else:
            df_chats_filtered['Já Avaliado'] = False

        # Status
        if 'status' in df_chats_filtered.columns:
            status_opts = sorted(df_chats_filtered['status'].dropna().unique().tolist())
            status_sel = st.sidebar.multiselect("Status", status_opts)
            if status_sel:
                df_chats_filtered = df_chats_filtered[df_chats_filtered['status'].isin(status_sel)]

        # Grupo
        if 'group.name' in df_chats_filtered.columns:
            group_opts = sorted(df_chats_filtered['group.name'].dropna().unique().tolist())
            group_sel = st.sidebar.multiselect("Grupo", group_opts)
            if group_sel:
                df_chats_filtered = df_chats_filtered[df_chats_filtered['group.name'].isin(group_sel)]

        # Agente
        if 'agent.name' in df_chats_filtered.columns:
            agent_opts = sorted(df_chats_filtered['agent.name'].dropna().unique().tolist())
            agent_sel = st.sidebar.multiselect("Agente", agent_opts)
            if agent_sel:
                df_chats_filtered = df_chats_filtered[df_chats_filtered['agent.name'].isin(agent_sel)]

        # Tags
        if 'tags' in df_chats_filtered.columns:
            tags_series = df_chats_filtered['tags'].dropna().apply(
                lambda v: v if isinstance(v, list) else [t.strip() for t in str(v).split(',') if t.strip()]
            )
            all_tags = sorted({t for tags in tags_series for t in tags})
            tags_sel = st.sidebar.multiselect("Tags", all_tags)
            if tags_sel:
                df_chats_filtered = df_chats_filtered[df_chats_filtered['tags'].apply(
                    lambda v: any(t in (v if isinstance(v, list) else [s.strip() for s in str(v).split(',')]) for t in tags_sel)
                )]

        # Canal
        if 'channel' in df_chats_filtered.columns:
            channel_opts = sorted(df_chats_filtered['channel'].dropna().unique().tolist())
            channel_sel = st.sidebar.multiselect("Canal", channel_opts)
            if channel_sel:
                df_chats_filtered = df_chats_filtered[df_chats_filtered['channel'].isin(channel_sel)]

        # Origem da conversa
        origin_col = 'conversationOriginLabel' if 'conversationOriginLabel' in df_chats_filtered.columns else 'conversationOrigin'
        if origin_col in df_chats_filtered.columns:
            origin_opts = sorted(df_chats_filtered[origin_col].dropna().unique().tolist())
            origin_sel = st.sidebar.multiselect("Origem da conversa", origin_opts)
            if origin_sel:
                df_chats_filtered = df_chats_filtered[df_chats_filtered[origin_col].isin(origin_sel)]

        # Avaliação IA
        ja_avaliado_sel = st.sidebar.selectbox(
            "Avaliação IA",
            ["Todos", "Já avaliados", "Não avaliados"],
            index=0
        )
        if ja_avaliado_sel == "Já avaliados":
            df_chats_filtered = df_chats_filtered[df_chats_filtered['Já Avaliado'] == True]
        elif ja_avaliado_sel == "Não avaliados":
            df_chats_filtered = df_chats_filtered[df_chats_filtered['Já Avaliado'] == False]

        cache_info = f" (💾 {cache_stats['total_chats']} em cache)" if cache_stats['total_chats'] > 0 else ""
        st.success(f"✅ {len(df_chats)} chats encontrados e analisados{cache_info}.")
        
        # --- Seção de KPIs de Status ---
        st.header("Status dos Atendimentos Recentes")
        status_series = df_chats_filtered['status'].astype(str).str.lower()

        em_atendimento = (status_series == 'talking').sum()
        com_bot = (status_series == 'started').sum()
        finalizadas = (status_series == 'closed').sum()

        col1, col2, col3 = st.columns(3)
        col1.metric("Em Atendimento", f"{em_atendimento}")
        col2.metric("Com o Bot", f"{com_bot}")
        col3.metric("Finalizadas", f"{finalizadas}")
        st.divider()

        # --- Seção de Gráficos de Distribuição ---
        st.header("Distribuição dos Atendimentos")
        col_graf1, col_graf2 = st.columns(2)

        with col_graf1:
            st.subheader("Volume por Grupo de Atendimento")
            # Verifica se a coluna existe antes de usar
            if 'group.name' in df_chats_filtered.columns:
                df_grupo = df_chats_filtered['group.name'].dropna().value_counts().reset_index()
                df_grupo.columns = ['Grupo', 'Quantidade']
                fig_grupo = px.bar(
                    df_grupo.sort_values('Quantidade'),
                    y='Grupo', x='Quantidade', orientation='h', text_auto=True
                )
                fig_grupo.update_layout(yaxis_title=None, xaxis_title="Nº de Chats", height=400)
                st.plotly_chart(fig_grupo, use_container_width=True)

        with col_graf2:
            st.subheader("Volume por Canal")
            if 'channel' in df_chats_filtered.columns:
                df_canal = df_chats_filtered['channel'].value_counts().reset_index()
                df_canal.columns = ['Canal', 'Quantidade']
                fig_canal = px.pie(df_canal, names='Canal', values='Quantidade', hole=0.4, title="Proporção de Canais")
                st.plotly_chart(fig_canal, use_container_width=True)

        st.subheader("Origem da Conversa")
        origin_col = 'conversationOriginLabel' if 'conversationOriginLabel' in df_chats_filtered.columns else 'conversationOrigin'
        if origin_col in df_chats_filtered.columns:
            df_origem = df_chats_filtered[origin_col].value_counts().reset_index()
            df_origem.columns = ['Origem', 'Quantidade']
            fig_origem = px.bar(
                df_origem.sort_values('Quantidade'),
                y='Origem', x='Quantidade', orientation='h', text_auto=True
            )
            fig_origem.update_layout(yaxis_title=None, xaxis_title="Nº de Chats", height=400)
            st.plotly_chart(fig_origem, use_container_width=True)

        st.divider()

        # --- Tabela de Detalhes no Final ---
        st.header("Detalhamento dos Últimos Chats")

        if 'octadesk_table_limit' not in st.session_state:
            st.session_state['octadesk_table_limit'] = 50

        df_detalhes = df_chats_filtered.copy()
        if 'createdAt' in df_detalhes.columns:
            df_detalhes = df_detalhes.sort_values('createdAt', ascending=False)

        df_detalhes = df_detalhes.head(st.session_state['octadesk_table_limit'])

        # Extrair telefone do cliente a partir de contact.phoneContacts
        if 'contact.phoneContacts' in df_detalhes.columns:
            def _extract_phone(phone_contacts):
                if not isinstance(phone_contacts, list) or not phone_contacts:
                    return ""
                phones = []
                for pc in phone_contacts:
                    if isinstance(pc, dict) and pc.get('number'):
                        country = pc.get('countryCode', '')
                        number = str(pc['number'])
                        if country:
                            phones.append(f"+{country}{number}")
                        else:
                            phones.append(number)
                return " / ".join(phones) if phones else ""

            df_detalhes.insert(
                df_detalhes.columns.get_loc('contact.phoneContacts'),
                'Telefone Cliente',
                df_detalhes['contact.phoneContacts'].apply(_extract_phone)
            )

        df_messages = get_octadesk_messages(api_token, base_url, df_detalhes, max_chats=len(df_detalhes))
        df_transcricoes = build_chat_transcripts(df_messages, df_detalhes)

        if df_transcricoes is not None and not df_transcricoes.empty:
            df_detalhes = df_detalhes.merge(
                df_transcricoes,
                how='left',
                left_on='id',
                right_on='chatId'
            ).drop(columns=['chatId'], errors='ignore')

        cols_remover = [
            'assignedToGroupDate',
            'contact.id',
            'contact.phoneContacts',
            'contact.customFields',
            'contact.organization.name',
            'group.id',
            'survey.response',
            'survey.comment',
            'botAssignedDate',
            'assignedToAgentDate',
            'agent.id',
            'agent.email',
            'agent.phoneContacts',
            'agent.customFilds',
            'agent.organization.name'
        ]
        df_detalhes = df_detalhes.drop(columns=[c for c in cols_remover if c in df_detalhes.columns])

        # --- MATCHING COM OPORTUNIDADES ---
        def _normalizar_telefone_octa(tel_raw):
            """Remove +55 do DDI e retorna lista de números locais para match."""
            if not tel_raw or not isinstance(tel_raw, str):
                return []
            numeros = []
            for parte in tel_raw.split('/'):
                n = ''.join(filter(str.isdigit, parte.strip()))
                if n.startswith('55') and len(n) > 11:
                    n = n[2:]  # Remove DDI 55
                if n:
                    numeros.append(n)
            return numeros

        try:
            df_opor = carregar_dados(SQL_MATCH_OPORTUNIDADES)
            if df_opor is not None and not df_opor.empty:
                # Pré-processa telefones do CRM para lookup rápido
                crm_phone_map = {}
                for _, r in df_opor.iterrows():
                    tel = ''.join(filter(str.isdigit, str(r.get('telefone', '') or '')))
                    if tel:
                        crm_phone_map.setdefault(tel, []).append(r['oportunidade_id'])

                oportunidade_ids = []
                for _, row in df_detalhes.iterrows():
                    octa_number = str(row.get('number', '') or '')
                    octa_email = str(row.get('contact.email', '') or '').lower().strip()
                    octa_tel_raw = str(row.get('Telefone Cliente', '') or '')

                    # 1. Tentar por chat_id (number do Octadesk)
                    if octa_number:
                        match = df_opor[df_opor['chat_id'].astype(str) == octa_number]
                        if not match.empty:
                            oportunidade_ids.append(match.iloc[0]['oportunidade_id'])
                            continue

                    # 2. Tentar por email (ignorar @octachat.com)
                    if octa_email and '@octachat.com' not in octa_email:
                        match = df_opor[df_opor['email'] == octa_email]
                        if not match.empty:
                            com_chat = match[match['chat_id'].notna() & (match['chat_id'] != '')]
                            oportunidade_ids.append(
                                com_chat.iloc[0]['oportunidade_id'] if not com_chat.empty
                                else match.iloc[0]['oportunidade_id']
                            )
                            continue

                    # 3. Tentar por telefone (remove +55 do DDI do Octadesk)
                    fones_locais = _normalizar_telefone_octa(octa_tel_raw)
                    matched_by_phone = None
                    for fone in fones_locais:
                        if fone in crm_phone_map:
                            matched_by_phone = crm_phone_map[fone][0]
                            break
                    if matched_by_phone is not None:
                        oportunidade_ids.append(matched_by_phone)
                        continue

                    oportunidade_ids.append(None)

                df_detalhes['oportunidade_id'] = oportunidade_ids
            else:
                df_detalhes['oportunidade_id'] = None
        except Exception as e:
            st.warning(f"⚠️ Não foi possível buscar oportunidades: {e}")
            df_detalhes['oportunidade_id'] = None

        # --- LÓGICA DE AVALIAÇÃO (FASE 5) ---
        def _check_avaliavel(row):
            # 1) Agent.name é Bot / Ariel / Octabot
            agent = str(row.get('agent.name', '')).lower().strip()
            if agent in ['bot', 'ariel', 'octabot', 'none']:
                return False, "Atendido apenas por robô"
                
            # 2) Whats sem Human Response
            origem = str(row.get('conversationOriginLabel', '')).strip()
            if origem in ['Whats Degrau', 'Whats Central']:
                human_resp = row.get('bot.firstHumanResponseAt')
                if human_resp is None or (isinstance(human_resp, (list, tuple)) and len(human_resp) == 0):
                    return False, "Whats sem resposta humana"
                try:
                    if pd.isna(human_resp):
                        return False, "Whats sem resposta humana"
                except Exception:
                    pass
                if str(human_resp).strip() == '':
                    return False, "Whats sem resposta humana"
                    
            # 3) Transcrição muito curta
            transcricao = str(row.get('transcricao', '')).strip()
            if len(transcricao) < 1200:
                return False, f"Muito curta ({len(transcricao)} chars)"
                
            return True, "Apto para IA"

        df_detalhes['Avaliável'], df_detalhes['Motivo Inapto'] = zip(*df_detalhes.apply(_check_avaliavel, axis=1))

        # Reordenar colunas para trazer 'Avaliável' para frente
        cols_ordered = ['number', 'oportunidade_id', 'Já Avaliado', 'Avaliável', 'Motivo Inapto', 'createdAt', 'status', 'group.name', 'agent.name', 'conversationOriginLabel', 'Telefone Cliente', 'transcricao']
        cols_ordered_final = [c for c in cols_ordered if c in df_detalhes.columns] + [c for c in df_detalhes.columns if c not in cols_ordered]
        df_detalhes = df_detalhes[cols_ordered_final]
        
        # Interface de Seleção
        st.write("### 🤖 Avaliação em Lote via IA")
        st.info("Selecione abaixo os chats que deseja enviar para análise de qualidade. Chats sinalizados como inaptos serão ignorados ou reprovados automaticamente.")

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            filtro_aptidao = st.selectbox("Filtrar por Aptidão na Tabela", ["Todos", "Somente Aptos", "Somente Inaptos"], index=0)
        with col_f2:
            filtro_avaliacao = st.selectbox("Filtrar por Avaliação na Tabela", ["Todos", "Somente Não Avaliados", "Somente Já Avaliados"], index=0)

        df_show = df_detalhes.copy()
        
        if filtro_aptidao == "Somente Aptos":
            df_show = df_show[df_show['Avaliável'] == True]
        elif filtro_aptidao == "Somente Inaptos":
            df_show = df_show[df_show['Avaliável'] == False]
            
        if filtro_avaliacao == "Somente Não Avaliados":
            df_show = df_show[df_show['Já Avaliado'] == False]
        elif filtro_avaliacao == "Somente Já Avaliados":
            df_show = df_show[df_show['Já Avaliado'] == True]

        df_show.insert(0, "Selecionar", False)
        
        edited_df = st.data_editor(
            df_show, 
            hide_index=True,
            use_container_width=True, 
            height=500,
            column_config={
                "Selecionar": st.column_config.CheckboxColumn("Avaliar?", default=False),
                "Já Avaliado": st.column_config.CheckboxColumn("Avaliado?", disabled=True),
                "Avaliável": st.column_config.CheckboxColumn("Apto?", disabled=True),
            }
        )

        col_btn1, col_btn2 = st.columns([3, 7])
        with col_btn1:
            if st.button("Exibir mais 50", use_container_width=True):
                st.session_state['octadesk_table_limit'] += 50
                st.rerun()

        with col_btn2:
            if st.button("🧠 Enviar Selecionados para IA", type="primary", use_container_width=True):
                selected_rows = edited_df[edited_df["Selecionar"]]
                
                if selected_rows.empty:
                    st.warning("Selecione pelo menos um chat para avaliar!")
                else:
                    analyzer = ChatIAAnalyzer()
                    progress_bar = st.progress(0, text="Iniciando avaliação em lote...")
                    
                    total = len(selected_rows)
                    sucesso = 0
                    
                    for i, (idx_row, row) in enumerate(selected_rows.iterrows()):
                        # Usa o id (UUID) do Octadesk como chat_id
                        chat_id = str(row.get('id', '') or row.get('number', '')).strip()
                        if not chat_id:
                            progress_bar.progress((i + 1) / total, text=f"Chat inválido: pulando... ({i+1}/{total})")
                            continue
                            
                        progress_bar.progress(i / total, text=f"Analisando chat {chat_id} ({i+1}/{total})...")
                        
                        transcript = row.get('transcricao', '')
                        apto = row.get('Avaliável', False)
                        
                        agent_name = str(row.get('agent.name', ''))
                        
                        # Extrair Metadados Limpos do row DataFrame para o Banco
                        def _get_clean(c):
                            val = row.get(c)
                            if val is None:
                                return None
                            if isinstance(val, (list, tuple)):
                                return str(val) if len(val) > 0 else None
                            import pandas as pd
                            if pd.isna(val) is True:
                                return None
                            try:
                                if pd.isna(val): return None
                            except ValueError:
                                pass # Catch 'truth value of an array is ambiguous' if passed a numpy array
                            return str(val)
                            
                        # Avaliação ou Aborto Limpo
                        if not apto:
                            # Chat inapto: grava sem chamar IA (economiza tokens)
                            eval_result = {
                                "classificacao": "inapto_ia",
                                "motivo": str(row.get('Motivo Inapto', 'Regra não atendida')),
                                "lead_score": 0,
                                "vendor_score": 0,
                                "main_product": None,
                                "ai_evaluation": None,
                                "erro": None
                            }
                        else:
                            # 2. Avalia com IA de fato
                            contexto_extra = {
                                "origem": _get_clean('conversationOriginLabel'),
                                "canal": _get_clean('channel'),
                            }
                            eval_result = analyzer.avaliar_chat(transcript, contexto_extra)

                        if eval_result.get('erro'):
                            st.warning(f"⚠️ Erro parcial ao avaliar {chat_id}: {eval_result['erro']}")
                            # Salva mesmo com erro parcial — ai_evaluation pode ter dados úteis

                        # Tags como string limpa (comma-separated)
                        tags_raw = row.get('tags')
                        if isinstance(tags_raw, list):
                            tags_str = ', '.join(
                                t.get('name', str(t)) if isinstance(t, dict) else str(t)
                                for t in tags_raw if t
                            ) or None
                        else:
                            tags_str = _get_clean('tags')
                        telefone_str = _get_clean('Telefone Cliente')

                        # Usar oportunidade_id do matching (pode ser None)
                        matched_op_id = row.get('oportunidade_id')
                        try:
                            if pd.notna(matched_op_id):
                                matched_op_id = int(matched_op_id)
                            else:
                                matched_op_id = None
                        except (ValueError, TypeError):
                            matched_op_id = None

                        saved, msg = salvar_avaliacao_chat(
                            opportunity_id=matched_op_id,
                            chat_id=chat_id,
                            classification=eval_result.get('classificacao', 'outros'),
                            classification_reason=eval_result.get('motivo'),
                            ai_evaluation=eval_result.get('ai_evaluation'),  # dict ou None
                            transcript=transcript,
                            lead_score=eval_result.get('lead_score'),
                            vendor_score=eval_result.get('vendor_score'),
                            main_product=eval_result.get('main_product'),
                            octa_agent=_get_clean('agent.name'),
                            octa_channel=_get_clean('channel'),
                            octa_status=_get_clean('status'),
                            octa_tags=tags_str,
                            octa_group=_get_clean('group.name'),
                            octa_origin=_get_clean('conversationOriginLabel'),
                            octa_contact_name=_get_clean('contact.name'),
                            octa_contact_phone=telefone_str,
                            octa_bot_name=_get_clean('botName'),
                            octa_created_at=_get_clean('createdAt'),
                            octa_survey_response=_get_clean('conversationOriginLabel')
                        )

                        if saved:
                            sucesso += 1
                        else:
                            st.error(f"❌ Falha banco {chat_id}: {msg}")

                        progress_bar.progress((i + 1) / total, text=f"Progresso: {i+1}/{total} concluídos")
                        time.sleep(1) # limit rate
                        
                    st.success(f"🎉 Processamento finalizado! {sucesso} análises de chat cadastradas com sucesso.")
        
    else:
        st.info(
            f"Nenhum chat encontrado para **{data_inicio_padrao.strftime('%d/%m/%Y')}** "
            f"a **{data_fim.strftime('%d/%m/%Y')}**. "
            f"Verifique a data selecionada ou clique em **📥 Sincronizar** para importar dados."
        )