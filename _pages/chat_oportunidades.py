# _pages/chat_oportunidades.py
# Tabela de oportunidades com botão "Ver msg" que busca na API do Octadesk

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import pandas as pd
import requests
import re
import html as html_mod
from datetime import datetime, timedelta
import html as html_mod
from datetime import datetime, timedelta
from utils.sql_loader import carregar_dados
from utils.chat_ia_analyzer import ChatIAAnalyzer
from utils.chat_mysql_writer import salvar_avaliacao_chat

TIMEZONE = 'America/Sao_Paulo'

# Mapeamento de origens conhecidas (mesmo do octadesk.py)
_ORIGIN_MAP = {
    '+552139701015': 'Whats Degrau',
    '+551130178800': 'Whats Central',
    'Degrau Cultural • Concursos (@degraucultural)': 'Insta Degrau',
}


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


# ==============================================================================
# FUNÇÕES DE LIMPEZA DE HTML
# ==============================================================================

def _strip_html(text):
    """Converte HTML para texto plano legível."""
    if not isinstance(text, str) or not text.strip():
        return text

    # Se não contém tags HTML, retorna como está
    if '<' not in text:
        return text.strip()

    # Substitui <br>, <br/>, <br /> por quebra de linha
    text = re.sub(r'<br\s*/?\s*>', '\n', text, flags=re.IGNORECASE)
    # Substitui </p>, </div>, </li> por quebra de linha
    text = re.sub(r'</(?:p|div|li|tr|h[1-6])>', '\n', text, flags=re.IGNORECASE)
    # Substitui <li> por marcador
    text = re.sub(r'<li[^>]*>', '• ', text, flags=re.IGNORECASE)
    # Remove todas as tags restantes
    text = re.sub(r'<[^>]+>', '', text)
    # Decodifica entidades HTML (&amp; &lt; &gt; &nbsp; etc.)
    text = html_mod.unescape(text)
    # Colapsa múltiplas quebras de linha em no máximo 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Remove espaços extras em cada linha
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines)

    return text.strip()


# ==============================================================================
# FUNÇÕES DE API
# ==============================================================================

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


def _fetch_chat_details(token, base_url, chat_id):
    """Busca os detalhes/metadados de um chat na API do Octadesk."""
    headers = {"accept": "application/json", "X-API-KEY": token}
    try:
        resp = requests.get(f"{base_url}/chat/{chat_id}", headers=headers, timeout=20)
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# ==============================================================================
# FORMATAÇÃO DE MENSAGENS (lógica robusta inspirada no octadesk.py)
# ==============================================================================

# Candidatos de campo para cada informação, na ordem de prioridade
_SENDER_CANDIDATES = [
    'sentBy.name', 'sentBy.fullName', 'sentBy.displayName', 'sentBy.nickname',
    'sender.name', 'sender.fullName', 'sender.displayName', 'sender.nickname',
    'from.name', 'from.fullName', 'from.displayName',
    'author.name', 'author.fullName', 'author.displayName',
    'user.name', 'user.fullName', 'user.displayName',
    'agent.name', 'agent.fullName', 'agent.displayName',
    'owner.name', 'owner.fullName', 'owner.displayName',
    'bot.name', 'bot.fullName', 'bot.displayName',
    'contact.name', 'contact.fullName', 'contact.displayName',
    'customer.name', 'customer.fullName', 'customer.displayName',
    'client.name', 'client.fullName', 'client.displayName',
    'visitor.name', 'visitor.fullName', 'visitor.displayName',
    'person.name', 'person.fullName', 'person.displayName',
    'responsible.name', 'responsible.fullName', 'responsible.displayName',
    'assignee.name', 'assignee.fullName', 'assignee.displayName',
]

_TEXT_CANDIDATES = [
    'body', 'text', 'content', 'message',
    'payload.text', 'payload.content', 'payload.message',
    'payload.body', 'payload.html', 'html',
]

_ROLE_CANDIDATES = [
    'sentBy.type', 'sentBy.role',
    'sender.type', 'sender.role',
    'from.type', 'from.role',
    'author.type', 'author.role',
    'user.type', 'user.role',
    'type', 'messageType', 'direction', 'origin', 'source', 'side', 'flow',
    'eventType', 'event.type',
]

_SENDER_ID_CANDIDATES = [
    'sentBy.id',
    'sender.id', 'from.id', 'author.id', 'user.id',
    'agent.id', 'owner.id', 'contact.id', 'customer.id', 'client.id',
    'visitor.id', 'person.id', 'responsible.id', 'assignee.id',
    'sentById', 'senderId', 'fromId', 'authorId', 'userId',
    'agentId', 'ownerId', 'contactId', 'customerId', 'clientId',
    'visitorId', 'personId', 'responsibleId', 'assigneeId',
]


def _deep_get(obj, dotted_key):
    """Acessa chaves aninhadas por notação de ponto: 'sentBy.name' → obj['sentBy']['name']."""
    parts = dotted_key.split('.')
    current = obj
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    if isinstance(current, str) and current.strip():
        return current.strip()
    return None


def _pick_first(msg, candidates):
    """Retorna o primeiro valor não-vazio dos candidatos."""
    for key in candidates:
        val = _deep_get(msg, key)
        if val:
            return val
        # Tenta também chave direta (campo flat de json_normalize)
        if key in msg:
            v = msg[key]
            if isinstance(v, str) and v.strip():
                return v.strip()
            if isinstance(v, dict):
                for k in ['name', 'fullName', 'displayName', 'nickname', 'email']:
                    if k in v and isinstance(v[k], str) and v[k].strip():
                        return v[k].strip()
    return None


def _resolve_sender(msg, chat_details):
    """Resolve o nome do remetente usando múltiplas estratégias."""
    # 1. Tenta campos de nome direto na mensagem
    sender = _pick_first(msg, _SENDER_CANDIDATES)
    if sender:
        return sender

    # 2. Tenta inferir pelo role/type + dados do chat
    role = (_pick_first(msg, _ROLE_CANDIDATES) or '').lower()

    agent_name = _deep_get(chat_details, 'agent.name') or _deep_get(chat_details, 'owner.name') or ''
    contact_name = _deep_get(chat_details, 'contact.name') or _deep_get(chat_details, 'customer.name') or ''
    bot_name = _deep_get(chat_details, 'bot.name') or _deep_get(chat_details, 'botName') or ''

    if role in ('agent', 'attendant', 'operator', 'owner', 'assignee', 'responsible', 'outbound', 'outgoing'):
        return agent_name or '🧑‍💼 Agente'
    if role in ('bot', 'automation', 'workflow', 'robot'):
        return bot_name or '🤖 Bot'
    if role in ('customer', 'client', 'contact', 'visitor', 'user', 'person', 'lead', 'inbound', 'incoming'):
        return contact_name or '👤 Cliente'

    # 3. Tenta mapear pelo sender ID
    sender_id = _pick_first(msg, _SENDER_ID_CANDIDATES)
    if sender_id and chat_details:
        # Verifica se o ID bate com agent ou contact
        agent_id = _deep_get(chat_details, 'agent.id') or _deep_get(chat_details, 'owner.id')
        contact_id = _deep_get(chat_details, 'contact.id') or _deep_get(chat_details, 'customer.id')
        if agent_id and str(sender_id) == str(agent_id):
            return agent_name or '🧑‍💼 Agente'
        if contact_id and str(sender_id) == str(contact_id):
            return contact_name or '👤 Cliente'

    return '(?)'


def _get_sender_role(msg, chat_details):
    """Determina o papel do remetente para estilização."""
    role = (_pick_first(msg, _ROLE_CANDIDATES) or '').lower()

    if role in ('agent', 'attendant', 'operator', 'owner', 'assignee', 'responsible', 'outbound', 'outgoing'):
        return 'agent'
    if role in ('bot', 'automation', 'workflow', 'robot'):
        return 'bot'
    if role in ('customer', 'client', 'contact', 'visitor', 'user', 'person', 'lead', 'inbound', 'incoming'):
        return 'customer'

    # Tenta pelo sender ID
    sender_id = _pick_first(msg, _SENDER_ID_CANDIDATES)
    if sender_id and chat_details:
        agent_id = _deep_get(chat_details, 'agent.id') or _deep_get(chat_details, 'owner.id')
        contact_id = _deep_get(chat_details, 'contact.id') or _deep_get(chat_details, 'customer.id')
        if agent_id and str(sender_id) == str(agent_id):
            return 'agent'
        if contact_id and str(sender_id) == str(contact_id):
            return 'customer'

    return 'unknown'


def _format_datetime(raw):
    """Formata datetime da API para exibição."""
    if not raw:
        return ''
    try:
        dt = pd.to_datetime(raw, utc=True).tz_convert(TIMEZONE)
        return dt.strftime('%d/%m/%Y %H:%M')
    except Exception:
        return str(raw)[:19] if raw else ''


def _extract_phone_from_contacts(phone_contacts):
    """Extrai telefone de contact.phoneContacts (mesmo padrão do octadesk.py)."""
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


def _map_origin(val):
    """Mapeia origens conhecidas para labels legíveis."""
    if not isinstance(val, str):
        return val
    return _ORIGIN_MAP.get(val, val)


def _render_chat_details(chat_details, row):
    """Renderiza os metadados/detalhes do chat em layout organizado."""
    if not chat_details:
        return

    st.markdown("#### 📊 Dados do Atendimento")

    # Status
    status = chat_details.get('status', '-')
    status_emoji = {'closed': '🔴', 'talking': '🟢', 'started': '🟡'}.get(
        str(status).lower(), '⚪'
    )

    # Campos
    channel = chat_details.get('channel', '-')
    group_name = _deep_get(chat_details, 'group.name') or '-'
    origin = _map_origin(chat_details.get('conversationOrigin', '-'))
    agent_name = _deep_get(chat_details, 'agent.name') or _deep_get(chat_details, 'owner.name') or '-'
    created = _format_datetime(chat_details.get('createdAt')) or '-'

    # Tags (array da conversa — cada tag é um dict com 'id' e 'name')
    tags = chat_details.get('tags', [])
    if isinstance(tags, list) and tags:
        tag_names = []
        for t in tags:
            if isinstance(t, dict):
                tag_names.append(t.get('name', str(t)))
            elif isinstance(t, str) and t.strip():
                tag_names.append(t.strip())
        tags_str = ', '.join(f"`{n}`" for n in tag_names) if tag_names else '-'
    elif isinstance(tags, str) and tags.strip():
        tags_str = ', '.join(f"`{t.strip()}`" for t in tags.split(',') if t.strip())
    else:
        tags_str = '-'

    col1, col2, col3 = st.columns(3)
    col1.write(f"**Status:** {status_emoji} {status}")
    col2.write(f"**Canal:** {channel}")
    col3.write(f"**Grupo:** {group_name}")

    col4, col5, col6 = st.columns(3)
    col4.write(f"**Origem:** {origin}")
    col5.write(f"**Agente:** {agent_name}")
    col6.write(f"**Criado em:** {created}")

    st.write(f"**🏷️ Tags:** {tags_str}")


def _render_messages(messages_list, chat_details):
    """Renderiza mensagens formatadas com texto limpo e atores identificados."""
    if not messages_list:
        return

    st.markdown("### 💬 Conversa")

    # Ordena por data
    sorted_msgs = sorted(
        messages_list,
        key=lambda m: m.get('createdAt') or m.get('time') or '',
    )

    for msg in sorted_msgs:
        # Texto
        text = _pick_first(msg, _TEXT_CANDIDATES)
        if not text:
            continue

        # Limpa HTML
        text = _strip_html(text)
        if not text:
            continue

        # Remetente
        sender = _resolve_sender(msg, chat_details)
        role = _get_sender_role(msg, chat_details)

        # Hora
        time_str = _format_datetime(msg.get('createdAt') or msg.get('time'))

        # Ícone baseado no papel
        role_icon = {
            'agent': '🧑‍💼',
            'bot': '🤖',
            'customer': '👤',
        }.get(role, '💬')

        # Renderiza com st.chat_message para melhor visual
        avatar = {'agent': '🧑‍💼', 'bot': '🤖', 'customer': '👤'}.get(role, '💬')
        with st.chat_message(name=sender, avatar=avatar):
            header = f"**{sender}**"
            if time_str:
                header += f"  ·  `{time_str}`"
            st.markdown(header)
            st.markdown(text)

def _build_chat_transcript(messages_list, chat_details):
    """Monta arquivo de transcrição única (texto) para a IA ler."""
    if not messages_list:
        return ""
    
    sorted_msgs = sorted(
        messages_list,
        key=lambda m: m.get('createdAt') or m.get('time') or '',
    )
    
    lines = []
    for msg in sorted_msgs:
        text = _pick_first(msg, _TEXT_CANDIDATES)
        if not text:
            continue
        text = _strip_html(text)
        if not text:
            continue
        sender = _resolve_sender(msg, chat_details)
        lines.append(f"{sender}: {text}")
        
    return "\n".join(lines)


# ==============================================================================
# PÁGINA PRINCIPAL
# ==============================================================================

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

    # Fallback caso a query principal falhe (ex: tabela chat_ai_evaluations não existe ainda)
    if df is None or df.empty:
        df = carregar_dados("consultas/chat_oportunidades/chat_oportunidades_fallback.sql")
        if df is not None and not df.empty:
            st.warning("⚠️ **Aviso:** A tabela `chat_ai_evaluations` ainda não foi criada pela infraestrutura. As consultas estão operando em modo de fallback: exibir mensagens continua funcionando, mas a análise via IA retornará erro ao salvar.")

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

    # Insere a coluna Selecionar como False (booleano)
    df_show.insert(0, 'Selecionar', False)

    cols_table = ['Selecionar', 'analisado', 'classificacao_ia', 'score_ia', 'nome', 'criacao_fmt', 'telefone', 'email', 'chat_id', 'empresa', 'dono', 'etapa', 'area', 'origem']
    cols_table = [c for c in cols_table if c in df_show.columns]

    rename = {
        'Selecionar': 'Selecionar',
        'analisado': 'Avaliado (IA)',
        'classificacao_ia': 'Classificação',
        'score_ia': 'Score IA',
        'nome': 'Nome',
        'criacao_fmt': 'Data',
        'telefone': 'Telefone',
        'email': 'E-mail',
        'chat_id': 'Chat ID',
        'empresa': 'Empresa',
        'dono': 'Responsável',
        'etapa': 'Etapa',
        'area': 'Área',
        'origem': 'Origem',
    }

    df_table = df_show[cols_table].rename(columns=rename).reset_index(drop=True)
    
    # st.data_editor para permitir seleção
    edited_df = st.data_editor(
        df_table,
        use_container_width=True,
        height=500,
        hide_index=True,
        column_config={
            "Selecionar": st.column_config.CheckboxColumn(
                "Selecionar",
                help="Selecione os chats que deseja analisar em lote",
                default=False,
            )
        },
        disabled=[c for c in rename.values() if c != 'Selecionar'] # bloqueia as outras colunas
    )

    selected_rows = edited_df[edited_df['Selecionar'] == True]

    # --- NOVO: Botão de Avaliação em Lote ---
    st.divider()
    st.subheader("🤖 Avaliar Chats Selecionados")
    
    if not selected_rows.empty:
        st.info(f"{len(selected_rows)} conversa(s) selecionada(s) para análise.")
        
        if st.button("Iniciar Avaliação via IA", type="primary", use_container_width=True):
            analyzer = ChatIAAnalyzer()
            
            progress_bar = st.progress(0, text="Iniciando avaliação em lote...")
            total = len(selected_rows)
            sucesso = 0
            
            original_indices = selected_rows.index.tolist()
            
            for i, idx in enumerate(original_indices):
                row = df_show.iloc[idx]
                chat_id = str(row.get('chat_id', '')).strip()
                oportunidade_id = row.get('oportunidade_id') # Do banco original
                
                if not chat_id or not oportunidade_id:
                    progress_bar.progress((i + 1) / total, text=f"Chat inválido: pulando... ({i+1}/{total})")
                    continue
                
                progress_bar.progress(i / total, text=f"Analisando chat {chat_id} ({i+1}/{total})...")
                
                # 1. Busca API
                chat_details = _fetch_chat_details(token, base_url, chat_id)
                messages = _fetch_messages_api(token, base_url, chat_id)
                transcript = _build_chat_transcript(messages, chat_details)
                
                agent_name = _deep_get(chat_details, 'agent.name') or _deep_get(chat_details, 'owner.name') if chat_details else None

                # Se não tem agent humano (foi respondido só por bot) não precisamos torrar token da IA
                if not agent_name:
                    eval_result = {
                        "classificacao": "sem_interacao_humana",
                        "motivo": "Chat atendido exclusivamente por Bot/Nenhum agente humano alocado.",
                        "lead_score": 0,
                        "vendor_score": 0,
                        "main_product": None,
                        "ai_evaluation": None,
                        "erro": None
                    }
                else:
                    # 2. Avalia com IA
                    contexto_extra = {
                        "origem": row.get('origem', ''),
                        "etapa": row.get('etapa', ''),
                        "canal": chat_details.get('channel', 'Whatsapp') if chat_details else 'Whatsapp'
                    }
                    eval_result = analyzer.avaliar_chat(transcript, contexto_extra)
                    
                    if eval_result.get('erro'):
                        st.warning(f"⚠️ Erro parcial ao avaliar {chat_id}: {eval_result['erro']}")
                        # Salva mesmo com erro parcial — ai_evaluation pode ter dados úteis
                
                # Extrair tags em formato string separada por vírgulas
                tags_array = chat_details.get('tags', []) if chat_details else []
                tags_str = None
                if isinstance(tags_array, list) and tags_array:
                    tag_names = [t.get('name', str(t)) if isinstance(t, dict) else str(t) for t in tags_array]
                    tags_str = ','.join([n.strip() for n in tag_names if n.strip()])
                elif isinstance(tags_array, str) and tags_array.strip():
                    tags_str = tags_array.strip()

                agent_name = _deep_get(chat_details, 'agent.name') or _deep_get(chat_details, 'owner.name') if chat_details else None
                
                # Novos campos
                octa_group = _deep_get(chat_details, 'group.name') if chat_details else None
                octa_origin = chat_details.get('conversationOrigin', '') if chat_details else None
                octa_contact_name = _deep_get(chat_details, 'contact.name') or _deep_get(chat_details, 'customer.name') if chat_details else None
                
                phone_list = _deep_get(chat_details, 'contact.phoneContacts') if chat_details else []
                octa_contact_phone = _extract_phone_from_contacts(phone_list) if phone_list else None
                
                octa_bot_name = _deep_get(chat_details, 'botName') or _deep_get(chat_details, 'bot.name') if chat_details else None

                # 3. Salva no Banco
                salvou, msg_erro = salvar_avaliacao_chat(
                    opportunity_id=int(oportunidade_id),
                    chat_id=chat_id,
                    classification=eval_result.get('classificacao', 'outros'),
                    classification_reason=eval_result.get('motivo', ''),
                    ai_evaluation=eval_result.get('ai_evaluation'),  # dict ou None
                    transcript=transcript,
                    lead_score=eval_result.get('lead_score'),
                    vendor_score=eval_result.get('vendor_score'),
                    main_product=eval_result.get('main_product'),
                    octa_agent=agent_name,
                    octa_channel=str(chat_details.get('channel', '')) if chat_details else None,
                    octa_status=str(chat_details.get('status', '')) if chat_details else None,
                    octa_tags=tags_str,
                    octa_group=octa_group,
                    octa_origin=octa_origin,
                    octa_contact_name=octa_contact_name,
                    octa_contact_phone=octa_contact_phone,
                    octa_bot_name=octa_bot_name,
                    octa_created_at=str(chat_details.get('createdAt', '')) if chat_details else None,
                    octa_closed_at=str(chat_details.get('closedAt', '')) if chat_details else None,
                    octa_survey_response=str(_deep_get(chat_details, 'survey.response')) if chat_details and _deep_get(chat_details, 'survey.response') else None
                )
                
                if salvou:
                    sucesso += 1
                else:
                    st.error(f"Erro ao salvar no BD {chat_id}: {msg_erro}")
                
                progress_bar.progress((i + 1) / total, text=f"Concluído {chat_id} ({i+1}/{total})")
            
            st.success(f"Lote concluído! {sucesso} de {total} conversas analisadas e salvas com sucesso.")
            if st.button("Atualizar Tabela", key="refresh_tbl"):
                st.rerun()
    else:
        st.write("Marque as caixas na coluna **Selecionar** da tabela acima para avaliar.")

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
            # Busca dados do chat e mensagens em paralelo
            with st.spinner(f"Buscando dados do chat `{chat_id}` na API do Octadesk..."):
                chat_details = _fetch_chat_details(token, base_url, chat_id)
                messages = _fetch_messages_api(token, base_url, chat_id)

            if messages or chat_details:
                st.success(f"✅ {len(messages)} mensagens encontradas")

                # Dados do oportunidade (do banco)
                st.markdown("### 📋 Dados da Oportunidade")
                info_cols = st.columns(4)
                info_cols[0].write(f"**Nome:** {row.get('nome', '-')}")
                info_cols[1].write(f"**Telefone:** {row.get('telefone', '-')}")
                info_cols[2].write(f"**E-mail:** {row.get('email', '-')}")
                info_cols[3].write(f"**Responsável:** {row.get('dono', '-')}")

                info_cols2 = st.columns(4)
                info_cols2[0].write(f"**Empresa:** {row.get('empresa', '-')}")
                info_cols2[1].write(f"**Etapa:** {row.get('etapa', '-')}")
                info_cols2[2].write(f"**Área:** {row.get('area', '-')}")
                info_cols2[3].write(f"**Origem:** {row.get('origem', '-')}")

                st.divider()

                # Dados do chat (da API Octadesk)
                if chat_details:
                    _render_chat_details(chat_details, row)
                    st.divider()

                # Mensagens formatadas
                if messages:
                    _render_messages(messages, chat_details)
                else:
                    st.info("Chat encontrado mas sem mensagens de texto.")
            else:
                st.warning(
                    f"Nenhuma mensagem encontrada para o chat `{chat_id}`.\n\n"
                    f"Pode ser que o chat já tenha expirado na API (retenção ~30 dias)."
                )
