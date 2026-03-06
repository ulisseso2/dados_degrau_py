# _pages/chat_oportunidades.py
# Tabela de oportunidades com botão "Ver msg" que busca na API do Octadesk

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from utils.sql_loader import carregar_dados

TIMEZONE = 'America/Sao_Paulo'


def _get_octadesk_config():
    """Recupera token e base_url do Octadesk."""
    try:
        token = st.secrets["octadesk_api"]["token"]
    except (st.errors.StreamlitAPIException, KeyError):
        token = os.getenv("OCTADESK_API_TOKEN")

    try:
        base_url = st.secrets["octadesk_api"].get("base_url") or st.secrets["octadesk_api"].get("octadesk_base_url")
    except (st.errors.StreamlitAPIException, KeyError):
        base_url = os.getenv("OCTADESK_BASE_URL") or os.getenv("OCTADESK_API_BASE_URL")

    return token, (base_url.rstrip("/") if base_url else base_url)


def _fetch_messages_api(token, base_url, chat_id):
    """Busca mensagens de um chat direto na API do Octadesk."""
    headers = {"accept": "application/json", "X-API-KEY": token}
    for endpoint in [f"{base_url}/chat/{chat_id}/messages", f"{base_url}/chat/{chat_id}/message"]:
        try:
            resp = requests.get(endpoint, headers=headers, timeout=20)
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for key in ["data", "items", "results", "content"]:
                    if key in data and isinstance(data[key], list):
                        return data[key]
            return []
        except Exception:
            continue
    return []


def _format_messages(messages_list):
    """Formata lista de mensagens em texto legível."""
    if not messages_list:
        return None
    lines = []
    for msg in messages_list:
        # Texto
        text = ""
        for key in ['body', 'text', 'content', 'message']:
            val = msg.get(key)
            if isinstance(val, str) and val.strip():
                text = val.strip()
                break
        if not text:
            continue

        # Remetente
        sender = ""
        sent_by = msg.get('sentBy')
        if isinstance(sent_by, dict):
            sender = sent_by.get('name') or sent_by.get('fullName') or sent_by.get('displayName') or ""
        if not sender:
            for key in ['sender', 'from', 'author']:
                val = msg.get(key)
                if isinstance(val, dict):
                    sender = val.get('name') or val.get('fullName') or ""
                elif isinstance(val, str) and val.strip():
                    sender = val
                if sender:
                    break
        if not sender:
            sender = "(?)"

        # Hora
        time_str = ""
        created = msg.get('createdAt') or msg.get('time') or ""
        if created:
            try:
                dt = pd.to_datetime(created, utc=True).tz_convert(TIMEZONE)
                time_str = dt.strftime('%d/%m %H:%M')
            except Exception:
                pass

        if time_str:
            lines.append(f"[{time_str}] **{sender}**: {text}")
        else:
            lines.append(f"**{sender}**: {text}")

    return "\n\n".join(lines) if lines else None


def run_page():
    st.title("📋 Oportunidades × Chat Octadesk")
    st.caption("Selecione uma oportunidade e clique em **Ver msg** para buscar a conversa na API do Octadesk")

    token, base_url = _get_octadesk_config()
    if not token or not base_url:
        st.error("Token ou Base URL do Octadesk não configurados.")
        st.stop()

    # ── Carregar oportunidades do banco ────────────────────────────
    with st.spinner("Carregando oportunidades com chat_id..."):
        df = carregar_dados("consultas/chat_oportunidades/chat_oportunidades.sql")

    if df is None or df.empty:
        st.warning("Nenhuma oportunidade com chat_id encontrada no banco.")
        st.stop()

    if 'criacao' in df.columns:
        df['criacao'] = pd.to_datetime(df['criacao'], errors='coerce')

    # ── Filtros na sidebar ─────────────────────────────────────────
    st.sidebar.header("Filtros")

    hoje = datetime.now().date()
    default_start = hoje - timedelta(days=7)
    date_range = st.sidebar.date_input(
        "Período de criação:",
        [default_start, hoje],
        key="chat_oport_date"
    )
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        dt_ini, dt_fim = date_range
    elif isinstance(date_range, (list, tuple)) and len(date_range) == 1:
        st.sidebar.info("📅 Selecione a data final...")
        st.stop()
    else:
        dt_ini = dt_fim = date_range

    df_f = df.copy()
    if 'criacao' in df_f.columns:
        df_f = df_f[
            (df_f['criacao'].dt.date >= dt_ini) &
            (df_f['criacao'].dt.date <= dt_fim)
        ]

    if 'empresa' in df_f.columns:
        opts = sorted(df_f['empresa'].dropna().unique().tolist())
        sel = st.sidebar.multiselect("Empresa", opts)
        if sel:
            df_f = df_f[df_f['empresa'].isin(sel)]

    if 'dono' in df_f.columns:
        opts = sorted(df_f['dono'].dropna().unique().tolist())
        sel = st.sidebar.multiselect("Responsável", opts)
        if sel:
            df_f = df_f[df_f['dono'].isin(sel)]

    if 'etapa' in df_f.columns:
        opts = sorted(df_f['etapa'].dropna().unique().tolist())
        sel = st.sidebar.multiselect("Etapa", opts)
        if sel:
            df_f = df_f[df_f['etapa'].isin(sel)]

    # ── KPIs ───────────────────────────────────────────────────────
    st.metric("Oportunidades com chat", len(df_f))

    if df_f.empty:
        st.info("Nenhuma oportunidade para os filtros selecionados.")
        st.stop()

    # ── Tabela de oportunidades ────────────────────────────────────
    st.divider()

    df_show = df_f.copy()
    if 'criacao' in df_show.columns:
        df_show['criacao_fmt'] = df_show['criacao'].dt.strftime('%d/%m/%Y %H:%M')

    cols_table = ['nome', 'criacao_fmt', 'telefone', 'chat_id', 'empresa', 'dono', 'etapa']
    cols_table = [c for c in cols_table if c in df_show.columns]

    rename = {
        'nome': 'Nome',
        'criacao_fmt': 'Data',
        'telefone': 'Telefone',
        'chat_id': 'Chat ID',
        'empresa': 'Empresa',
        'dono': 'Responsável',
        'etapa': 'Etapa',
    }

    df_table = df_show[cols_table].rename(columns=rename).reset_index(drop=True)
    st.dataframe(df_table, use_container_width=True, height=500)

    # ── Seletor + botão "Ver msg" ─────────────────────────────────
    st.divider()
    st.subheader("💬 Ver mensagens do chat")

    options = []
    for _, row in df_show.iterrows():
        nome = row.get('nome', '?') or '?'
        data = row.get('criacao_fmt', '') or ''
        cid = row.get('chat_id', '') or ''
        tel = row.get('telefone', '') or ''
        options.append(f"{nome}  |  {data}  |  {tel}  |  {cid}")

    selected = st.selectbox("Selecione a oportunidade:", options, index=0)

    if st.button("🔍 Ver msg", type="primary", use_container_width=True):
        idx = options.index(selected)
        row = df_show.iloc[idx]
        chat_id = str(row.get('chat_id', '')).strip()

        if not chat_id:
            st.warning("Esta oportunidade não tem chat_id.")
        else:
            with st.spinner(f"Buscando mensagens do chat `{chat_id}` na API do Octadesk..."):
                messages = _fetch_messages_api(token, base_url, chat_id)

            if messages:
                st.success(f"✅ {len(messages)} mensagens encontradas")

                col1, col2, col3 = st.columns(3)
                col1.write(f"**Nome:** {row.get('nome', '-')}")
                col2.write(f"**Telefone:** {row.get('telefone', '-')}")
                col3.write(f"**Responsável:** {row.get('dono', '-')}")

                formatted = _format_messages(messages)
                if formatted:
                    st.markdown("---")
                    st.markdown(formatted)
                else:
                    st.info("Mensagens encontradas mas sem conteúdo de texto.")
            else:
                st.warning(
                    f"Nenhuma mensagem encontrada para o chat `{chat_id}`.\n\n"
                    f"Pode ser que o chat já tenha expirado na API (retenção ~30 dias)."
                )
