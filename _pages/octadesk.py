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

load_dotenv()
TIMEZONE = 'America/Sao_Paulo'

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

def _fetch_chats_from_api(api_token, base_url, max_pages=5, limit=100, stop_before_date=None):
    """Busca chats da API do Octadesk com paginação inteligente.
    
    A API retorna chats do mais recente ao mais antigo.
    Se stop_before_date for informado, para de paginar quando todos os
    chats de uma página forem anteriores a essa data (não precisa ir além).
    """
    url = f"{base_url}/chat"
    headers = {"accept": "application/json", "X-API-KEY": api_token}
    all_results = []
    page = 1
    reached_target = False

    while page <= max_pages:
        params = {"page": page, "limit": limit}
        try:
            response = requests.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            items = _normalize_list_response(data)
            if not items:
                break
            all_results.extend(items)

            # Paginação inteligente: se todos os itens da página são anteriores
            # à data alvo, não precisa buscar mais páginas
            if stop_before_date and items:
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


def _fetch_messages_from_api(api_token, base_url, chat_id):
    """Busca mensagens de um chat diretamente da API (sem cache)."""
    headers = {"accept": "application/json", "X-API-KEY": api_token}
    endpoints = [
        f"{base_url}/chat/{chat_id}/messages",
        f"{base_url}/chat/{chat_id}/message"
    ]
    for url in endpoints:
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 404:
                continue
            response.raise_for_status()
            data = response.json()
            return _normalize_list_response(data)
        except requests.exceptions.HTTPError as http_err:
            st.error(
                f"Erro na API do Octadesk ao buscar mensagens do chat {chat_id}: "
                f"{http_err.response.status_code} - {http_err.response.text}"
            )
            return []
        except Exception as e:
            st.error(f"Erro ao buscar mensagens do chat {chat_id}: {e}")
            return []
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


def sync_octadesk_history(api_token, base_url, max_pages=120, limit=100):
    """Sincroniza TODOS os chats e mensagens do Octadesk para o cache SQLite.
    
    Fase 1: Busca todas as páginas de chats da API e salva no cache.
    Fase 2: Para cada chat sem mensagens em cache, busca as mensagens.
    """
    url = f"{base_url}/chat"
    headers = {"accept": "application/json", "X-API-KEY": api_token}

    # ── FASE 1: Buscar todos os chats ──────────────────────────────
    st.info("📥 **Fase 1/2**: Buscando chats da API...")
    progress_bar = st.progress(0, text="Buscando chats...")
    total_chats_saved = 0
    page = 1

    while page <= max_pages:
        progress_bar.progress(
            page / max_pages,
            text=f"Fase 1/2 — Página {page}/{max_pages} — {total_chats_saved} chats salvos"
        )

        params = {"page": page, "limit": limit}
        try:
            response = requests.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            items = _normalize_list_response(data)

            if not items:
                break

            # Salvar TODOS os chats (não apenas fechados)
            saved = octadesk_db.save_chats(items)
            total_chats_saved += saved

            if len(items) < limit:
                break

            page += 1
            time.sleep(0.5)  # Rate limiting entre páginas

        except Exception as e:
            st.error(f"Erro na sincronização (página {page}): {e}")
            break

    progress_bar.progress(1.0, text=f"✅ Fase 1/2 concluída: {total_chats_saved} chats salvos")

    # ── FASE 2: Buscar mensagens dos chats sem cache ───────────────
    st.info("📨 **Fase 2/2**: Buscando mensagens dos chats...")
    chats_missing = octadesk_db.get_chats_without_messages()
    total_missing = len(chats_missing)
    total_messages_saved = 0

    if total_missing > 0:
        progress_msgs = st.progress(0, text=f"Buscando mensagens... 0/{total_missing}")
        for idx, chat_id in enumerate(chats_missing):
            progress_msgs.progress(
                (idx + 1) / total_missing,
                text=f"Fase 2/2 — Chat {idx+1}/{total_missing} — {total_messages_saved} msgs salvas"
            )
            try:
                msgs = _fetch_messages_from_api(api_token, base_url, chat_id)
                if msgs:
                    octadesk_db.save_messages(chat_id, msgs)
                    total_messages_saved += len(msgs)
                time.sleep(0.2)  # Rate limiting
            except Exception:
                continue
        progress_msgs.progress(1.0, text=f"✅ Fase 2/2 concluída: {total_messages_saved} mensagens salvas")
    else:
        st.success("✅ Todos os chats já possuem mensagens em cache!")

    octadesk_db.log_sync(
        sync_type='manual_completo',
        pages_fetched=page,
        chats_saved=total_chats_saved,
        messages_saved=total_messages_saved
    )

    st.success(
        f"✅ Sincronização concluída: **{total_chats_saved}** chats e "
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
    col_sync1, col_sync2 = st.sidebar.columns(2)
    with col_sync1:
        btn_sync = st.button("📥 Sincronizar Tudo", use_container_width=True,
                              help="Busca TODOS os chats e mensagens da API e salva no cache")
    with col_sync2:
        btn_clear = st.button("🗑️ Limpar Cache", use_container_width=True)

    if btn_sync:
        sync_octadesk_history(api_token, base_url, max_pages=120, limit=100)
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
            'botName',
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

        st.dataframe(df_detalhes, use_container_width=True, height=600)

        if st.button("Exibir mais 50"):
            st.session_state['octadesk_table_limit'] += 50
        
    else:
        st.info(
            f"Nenhum chat encontrado para **{data_inicio_padrao.strftime('%d/%m/%Y')}** "
            f"a **{data_fim.strftime('%d/%m/%Y')}**. "
            f"Verifique a data selecionada ou clique em **📥 Sincronizar** para importar dados."
        )