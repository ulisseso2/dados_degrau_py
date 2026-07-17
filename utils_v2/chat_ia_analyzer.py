# -*- coding: utf-8 -*-
"""
chat_ia_analyzer.py — v3 (unificação de fornecedor + régua canônica)
====================================================================
Avaliador de conversas de WhatsApp (Octadesk).

MUDANÇAS v3 (jul/2026):
- Fornecedor: OpenAI → CLAUDE (Anthropic). Mesmo juiz do canal telefone.
  Motivo: notas comparáveis entre canais + prompt caching + Batch Anthropic
  já integrada no pipeline de ligações e no gerador de treinamentos.
- Prompt: importado de utils.venda_consultiva_core (fonte única da régua).
  Listas fechadas de fortes/melhorias/erros agora também no WhatsApp.
- Contexto adicional: aceita qualificação prévia P1/P2 (princípio do juiz
  cego — ver docstring do core).
- API pública preservada: ChatIAAnalyzer, filtrar_mensagens_bot,
  verificar_avaliabilidade, avaliar_chat, avaliar_lote_paralelo,
  criar_batch, consultar_batch, coletar_resultados_batch.
  ATENÇÃO: consultar_batch agora retorna o formato Anthropic
  (processing_status 'ended', request_counts succeeded/errored/...).
  A página octadesk.py foi ajustada em conjunto.

ENV VARS (unificadas com o canal telefone):
  ANTHROPIC_API_KEY        — obrigatória
  CLAUDE_MODEL             — default claude-sonnet-4-6
  CLAUDE_TEMPERATURE       — default 0.2
  CLAUDE_MAX_TOKENS        — default 6000
  CLAUDE_MAX_INPUT_CHARS   — default 25000
  CHAT_CLAUDE_MAX_WORKERS  — default 2 (paralelismo tempo real)
  CLAUDE_THROTTLE_SECONDS  — default 4
"""

import json
import logging
import os
import re
import threading
import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

import anthropic
from dotenv import load_dotenv

from utils.venda_consultiva_core import (
    REGUA_VERSAO,
    build_user_prompt,
    system_prompt,
)

_ENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(_ENV_PATH)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTES DE BOTS (inalteradas — pré-processamento em Python, 0 tokens)
# ──────────────────────────────────────────────────────────────────────────────
NOMES_BOT = {
    'ariel', 'octabot', 'dicas', 'bot', 'null', 'none', '',
    'dicas octabot',
}

TEMPLATES_BOT = [
    '📢 Oi,', '📢 Olá,', '📢',
    'Perfeito!\nEstou te encaminhando',
    'Estou te encaminhando agora',
    'Aguarde um momento enquanto te transfiro',
    'Gostaria de prosseguir com o seu atendimento?',
    'Clique no botão abaixo', 'Clique no botão 👇',
    'Você já é nosso aluno?',
    'Qual  a modalidade de estudo está buscando?',
    'Qual o turno da sua preferência?',
    'Para te direcionar melhor',
]

_SYSTEM_PROMPT = system_prompt("whatsapp")


# ══════════════════════════════════════════════════════════════════════════════
# PRÉ-PROCESSAMENTO (sem mudanças funcionais vs v2)
# ══════════════════════════════════════════════════════════════════════════════

def _eh_nome_bot(nome: str) -> bool:
    nome_lower = nome.strip().lower()
    if nome_lower in NOMES_BOT:
        return True
    for bot in NOMES_BOT:
        if bot and bot in nome_lower:
            return True
    return False


def _eh_template_bot(texto: str) -> bool:
    texto_stripped = texto.strip()
    for template in TEMPLATES_BOT:
        if texto_stripped.startswith(template):
            return True
    return False


def filtrar_mensagens_bot(transcricao: str) -> Dict:
    """Separa mensagens humanas de bots. Retorna dict com transcrição limpa + stats."""
    if not transcricao or not transcricao.strip():
        return {
            'transcricao_limpa': '', 'transcricao_completa': '',
            'mensagens_humanas': [], 'mensagens_bot': [],
            'stats': {
                'total': 0, 'humanas': 0, 'bot': 0,
                'remetentes_humanos': set(), 'remetentes_bot': set(),
                'chars_humanos': 0, 'turnos_cliente': 0, 'turnos_agente': 0,
            }
        }

    linhas = transcricao.split('\n')
    humanas, bots = [], []
    remetentes_humanos, remetentes_bot = set(), set()

    pattern = re.compile(r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s*-\s*(.+?):\s*(.*)')
    pattern_sem_ts = re.compile(r'^(.+?):\s*(.*)')

    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue

        match = pattern.match(linha)
        if match:
            ts, rem, txt = match.group(1), match.group(2).strip(), match.group(3).strip()
        else:
            match2 = pattern_sem_ts.match(linha)
            if match2:
                ts, rem, txt = '', match2.group(1).strip(), match2.group(2).strip()
            else:
                humanas.append({'remetente': '(desconhecido)', 'texto': linha, 'timestamp': '', 'linha': linha})
                continue

        msg = {'remetente': rem, 'texto': txt, 'timestamp': ts, 'linha': linha}

        if _eh_nome_bot(rem) or _eh_template_bot(txt):
            bots.append(msg)
            remetentes_bot.add(rem)
        else:
            humanas.append(msg)
            remetentes_humanos.add(rem)

    return {
        'transcricao_limpa': '\n'.join(m['linha'] for m in humanas if m['linha']),
        'transcricao_completa': transcricao,
        'mensagens_humanas': humanas,
        'mensagens_bot': bots,
        'stats': {
            'total': len(humanas) + len(bots),
            'humanas': len(humanas), 'bot': len(bots),
            'remetentes_humanos': remetentes_humanos,
            'remetentes_bot': remetentes_bot,
            'chars_humanos': sum(len(m['texto']) for m in humanas),
            'turnos_cliente': 0, 'turnos_agente': 0,
        }
    }


def verificar_avaliabilidade(filtro: Dict, agent_name: str = '') -> Tuple[bool, str]:
    """Verifica se há interação humana bilateral suficiente."""
    stats = filtro['stats']

    if stats['humanas'] == 0:
        return False, 'Sem mensagens humanas (apenas bot)'

    remetentes = stats['remetentes_humanos']
    if len(remetentes) < 2:
        nomes = ', '.join(remetentes) if remetentes else 'nenhum'
        return False, f'Apenas 1 participante humano ({nomes}). Sem diálogo bilateral.'

    agent_lower = agent_name.strip().lower() if agent_name else ''
    turnos_agente, turnos_cliente = 0, 0

    for msg in filtro['mensagens_humanas']:
        rem_lower = msg['remetente'].strip().lower()
        if agent_lower and rem_lower == agent_lower:
            turnos_agente += 1
        elif rem_lower not in ('(desconhecido)', '(sem remetente)'):
            if not _eh_nome_bot(msg['remetente']):
                turnos_cliente += 1

    if not agent_lower and len(remetentes) >= 2:
        contagem = {}
        for msg in filtro['mensagens_humanas']:
            r = msg['remetente']
            contagem[r] = contagem.get(r, 0) + 1
        sorted_r = sorted(contagem.items(), key=lambda x: -x[1])
        turnos_agente = sorted_r[0][1]
        turnos_cliente = sum(c for _, c in sorted_r[1:])

    stats['turnos_agente'] = turnos_agente
    stats['turnos_cliente'] = turnos_cliente

    if turnos_cliente == 0:
        return False, 'Cliente não enviou mensagens para o agente humano'
    if turnos_agente == 0:
        return False, 'Agente humano não enviou mensagens'
    if turnos_cliente < 2 and turnos_agente < 2:
        return False, f'Interação muito curta (agente: {turnos_agente}, cliente: {turnos_cliente} msgs)'
    if stats['chars_humanos'] < 800:
        return False, f'Conteúdo humano insuficiente ({stats["chars_humanos"]} chars)'

    return True, f'Apto: {turnos_agente} agente + {turnos_cliente} cliente ({stats["chars_humanos"]} chars)'


# ══════════════════════════════════════════════════════════════════════════════
# CLASSE PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

class ChatIAAnalyzer:
    def __init__(self):
        load_dotenv(_ENV_PATH, override=True)
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.client: Optional[anthropic.Anthropic] = (
            anthropic.Anthropic(api_key=self.api_key) if self.api_key else None
        )
        self.model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
        self.temperature = float(os.getenv("CLAUDE_TEMPERATURE", "0.2"))
        self.max_tokens = int(os.getenv("CLAUDE_MAX_TOKENS", "6000"))
        self.max_input_chars = int(os.getenv("CLAUDE_MAX_INPUT_CHARS", "25000"))
        self.max_workers = int(os.getenv("CHAT_CLAUDE_MAX_WORKERS", "2"))
        self.throttle_seconds = float(os.getenv("CLAUDE_THROTTLE_SECONDS", "4"))
        self._throttle_lock = threading.Lock()
        self._last_request_time = 0.0

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _limpar_markdown(content: str) -> str:
        if not content:
            return content
        content = content.strip()
        match = re.match(r'^```(?:json)?\s*\n?(.*?)\n?```$', content, re.DOTALL)
        return match.group(1).strip() if match else content

    @staticmethod
    def _extrair_main_product(ai_eval: dict) -> Optional[str]:
        rec = ai_eval.get('recomendacao_final') or {}
        # Schema canônico usa 'produto_principal'; aceita legado 'produto_principal_indicado'
        for key in ('produto_principal', 'produto_principal_indicado'):
            produto = rec.get(key)
            if produto and isinstance(produto, str) and produto.lower() not in ('não mencionado', 'não identificado', 'null', 'none', ''):
                return produto
        for p in (ai_eval.get('extracao') or {}).get('produtos_citados') or []:
            if isinstance(p, dict):
                nome = p.get('produto')
                if nome and isinstance(nome, str) and nome.lower() not in ('não mencionado', 'null', 'none', ''):
                    return nome
        for key in ('produto_alternativo', 'produto_alternativo_indicado'):
            alt = rec.get(key)
            if alt and isinstance(alt, str) and alt.lower() not in ('não mencionado', 'null', 'none', ''):
                return alt
        return None

    @staticmethod
    def _extrair_lead_score(ai_eval: dict) -> Optional[int]:
        avl = ai_eval.get('avaliacao_lead') or {}
        score = avl.get('lead_score_0_100')
        if score is not None:
            try:
                return int(score)
            except (ValueError, TypeError):
                pass
        dims = avl.get('dimensoes') or {}
        if dims:
            total = sum(int(v) for v in dims.values() if v is not None and str(v).isdigit())
            if total > 0:
                return total
        return None

    @staticmethod
    def _extrair_vendor_score(ai_eval: dict) -> Optional[int]:
        avv = ai_eval.get('avaliacao_vendedor') or {}
        score = avv.get('nota_final_0_100')
        if score is not None:
            try:
                return int(score)
            except (ValueError, TypeError):
                pass
        cats = avv.get('notas_por_categoria') or {}
        if cats:
            total = sum(int(v) for v in cats.values() if v is not None and str(v).isdigit())
            if total > 0:
                return total
        return None

    def _build_prompt(self, chat_text: str, contexto_adicional: Optional[Dict] = None) -> str:
        ctx_json = ""
        if contexto_adicional:
            ctx_json = json.dumps(contexto_adicional, ensure_ascii=False)
        return build_user_prompt(
            canal="whatsapp",
            conteudo=chat_text[:self.max_input_chars],
            contexto_adicional_json=ctx_json,
        )

    # ── chamada unitária ao Claude (classificação + avaliação em 1 call) ─────

    def _call_claude(self, chat_text: str, contexto_adicional: Optional[Dict] = None) -> Dict:
        client = self.client
        if client is None:
            return {'erro': 'Anthropic não inicializado (ANTHROPIC_API_KEY ausente)'}

        prompt = self._build_prompt(chat_text, contexto_adicional)
        content = ""

        for tentativa in range(3):
            with self._throttle_lock:
                now = _time.time()
                elapsed = now - self._last_request_time
                if self.throttle_seconds > 0 and elapsed < self.throttle_seconds:
                    _time.sleep(self.throttle_seconds - elapsed)
                self._last_request_time = _time.time()

            try:
                response = client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=[{
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }],
                    messages=[{"role": "user", "content": prompt}],
                )

                usage = getattr(response, 'usage', None)
                logger.info(
                    "[Claude/chat] modelo=%s regua=%s | tokens in=%s out=%s | stop=%s",
                    self.model, REGUA_VERSAO,
                    getattr(usage, 'input_tokens', None),
                    getattr(usage, 'output_tokens', None),
                    response.stop_reason,
                )

                content = (response.content[0].text if response.content else "").strip()
                if not content:
                    if tentativa < 2:
                        continue
                    return {'erro': 'Resposta vazia após retentativas'}

                if response.stop_reason == 'max_tokens':
                    logger.warning("[Claude/chat] max_tokens atingido (tentativa %d)", tentativa + 1)
                    if tentativa < 2:
                        continue
                    return {'erro': 'Resposta truncada (max_tokens) após retentativas'}

                content = self._limpar_markdown(content)
                return json.loads(content)

            except json.JSONDecodeError as e:
                logger.warning(
                    "[Claude/chat] JSONDecodeError tentativa %d: %s | início: %r",
                    tentativa + 1, e, content[:200] if content else "(vazio)",
                )
                if tentativa < 2:
                    continue
                return {'erro': f'JSON inválido: {e}'}
            except anthropic.RateLimitError as e:
                wait = min(2 ** (tentativa + 2), 60)
                logger.warning("Rate limit (429) tentativa %d. Aguardando %ds...", tentativa + 1, wait)
                _time.sleep(wait)
                if tentativa == 2:
                    return {'erro': f'Rate limit excedido após 3 tentativas: {e}'}
            except (anthropic.APIConnectionError, anthropic.APIStatusError) as e:
                logger.error("Erro na avaliação (tentativa %d): %s", tentativa + 1, e)
                if tentativa < 2:
                    _time.sleep(min(2 ** (tentativa + 1), 10))
                    continue
                return {'erro': str(e)}
            except Exception as e:
                logger.error("Erro na avaliação (tentativa %d): %s", tentativa + 1, e)
                return {'erro': str(e)}

        return {'erro': 'Falha após retentativas'}

    # ── pipeline completo (1 chat) ───────────────────────────────────────────

    def avaliar_chat(self, chat_text: str, contexto_adicional: Optional[Dict] = None,
                     agent_name: str = '') -> Dict:
        """
        Pipeline completo:
          1. Filtra bot (Python, 0 API calls)
          2. Verifica avaliabilidade (Python, 0 API calls)
          3. Classifica + avalia com Claude (1 API call)
        """
        filtro = filtrar_mensagens_bot(chat_text)
        transcricao_limpa = filtro['transcricao_limpa']
        stats = filtro['stats']

        resultado = {
            'classificacao': None, 'motivo': '', 'deve_avaliar': False,
            'ai_evaluation': None, 'lead_score': None,
            'vendor_score': None, 'main_product': None, 'erro': None,
            'vendedor_disclaimer': None, 'lead_disclaimer': None,
            'filtro_stats': {
                'msgs_total': stats['total'], 'msgs_humanas': stats['humanas'],
                'msgs_bot': stats['bot'], 'chars_humanos': stats['chars_humanos'],
                'turnos_agente': stats.get('turnos_agente', 0),
                'turnos_cliente': stats.get('turnos_cliente', 0),
            }
        }

        # Camada 1+2: filtro + avaliabilidade
        avaliavel, motivo = verificar_avaliabilidade(filtro, agent_name)
        if not avaliavel:
            resultado['classificacao'] = 'inapto_regra'
            resultado['motivo'] = motivo
            return resultado

        # Camada 3: Claude faz classificação + avaliação (1 call)
        if not self.client:
            resultado['classificacao'] = 'outros'
            resultado['motivo'] = 'Anthropic não inicializado'
            return resultado

        ai_result = self._call_claude(transcricao_limpa, contexto_adicional)

        if 'erro' in ai_result and ai_result.get('erro'):
            resultado['erro'] = ai_result['erro']
            resultado['classificacao'] = 'falha_avaliacao'
            return resultado

        tipo = ai_result.get('tipo', 'outros')
        resultado['classificacao'] = tipo
        resultado['motivo'] = ai_result.get('motivo', '')
        resultado['deve_avaliar'] = (tipo == 'venda')

        if tipo == 'venda':
            resultado['ai_evaluation'] = ai_result
            resultado['lead_score'] = self._extrair_lead_score(ai_result)
            resultado['vendor_score'] = self._extrair_vendor_score(ai_result)
            resultado['main_product'] = self._extrair_main_product(ai_result)
            resultado['vendedor_disclaimer'] = ai_result.get('vendedor_disclaimer')
            resultado['lead_disclaimer'] = ai_result.get('lead_disclaimer')

        return resultado

    # ══════════════════════════════════════════════════════════════════════════
    # PROCESSAMENTO PARALELO (modo tempo-real, ThreadPoolExecutor)
    # ══════════════════════════════════════════════════════════════════════════

    def avaliar_lote_paralelo(
        self,
        chats: List[Dict],
        max_workers: Optional[int] = None,
        callback=None
    ) -> List[Dict]:
        """
        Avalia múltiplos chats em paralelo.
        chats: lista de dicts com chat_id, transcript, agent_name, contexto_adicional
        """
        workers = max_workers or self.max_workers
        resultados: List[Optional[Dict]] = [None] * len(chats)

        def _process(idx, chat_data):
            chat_id = chat_data.get('chat_id', f'chat_{idx}')
            try:
                result = self.avaliar_chat(
                    chat_text=chat_data.get('transcript', ''),
                    contexto_adicional=chat_data.get('contexto_adicional'),
                    agent_name=chat_data.get('agent_name', '')
                )
                result['chat_id'] = chat_id
                return idx, result
            except Exception as e:
                return idx, {
                    'chat_id': chat_id,
                    'classificacao': 'falha_avaliacao',
                    'motivo': str(e),
                    'erro': str(e),
                    'ai_evaluation': None, 'lead_score': None,
                    'vendor_score': None, 'main_product': None,
                    'deve_avaliar': False, 'filtro_stats': {}
                }

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_process, i, chat): i
                for i, chat in enumerate(chats)
            }
            completed = 0
            for future in as_completed(futures):
                idx, result = future.result()
                resultados[idx] = result
                completed += 1
                if callback:
                    try:
                        callback(completed, len(chats), result.get('chat_id', ''), result)
                    except Exception:
                        pass

        return [r for r in resultados if r is not None]

    # ══════════════════════════════════════════════════════════════════════════
    # BATCH API (Anthropic Message Batches — 50% de desconto)
    # ══════════════════════════════════════════════════════════════════════════

    def criar_batch(self, chats: List[Dict]) -> Optional[str]:
        """
        Envia chats para a Anthropic Batch API. Retorna batch_id (msgbatch_...).
        chats: mesma estrutura de avaliar_lote_paralelo. Inaptos são pulados.
        IMPORTANTE: preserve os metadados (oportunidade etc.) num manifest
        externo indexado por chat_id — a página octadesk.py faz isso.
        """
        client = self.client
        if client is None:
            logger.error("Anthropic não inicializado")
            return None

        requests = []
        for chat_data in chats:
            chat_id = str(chat_data.get('chat_id', '') or '')
            filtro = filtrar_mensagens_bot(chat_data.get('transcript', ''))
            avaliavel, _ = verificar_avaliabilidade(filtro, chat_data.get('agent_name', ''))
            if not avaliavel or not chat_id:
                continue

            prompt = self._build_prompt(
                filtro['transcricao_limpa'],
                chat_data.get('contexto_adicional')
            )
            requests.append({
                "custom_id": chat_id,
                "params": {
                    "model": self.model,
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                    "system": [{"type": "text", "text": _SYSTEM_PROMPT}],
                    "messages": [{"role": "user", "content": prompt}],
                }
            })

        if not requests:
            logger.info("Nenhum chat apto para batch")
            return None

        try:
            batch = client.messages.batches.create(requests=requests)
            logger.info("Batch criado: %s (%d requests)", batch.id, len(requests))
            return batch.id
        except Exception as e:
            logger.error("Erro ao criar batch: %s", e)
            return None

    def consultar_batch(self, batch_id: str) -> Dict:
        """Consulta status de um batch na Anthropic (formato Anthropic)."""
        if not self.client:
            return {'erro': 'Anthropic não inicializado'}
        try:
            batch = self.client.messages.batches.retrieve(batch_id)
            return {
                'id': batch.id,
                'processing_status': batch.processing_status,
                'request_counts': {
                    'succeeded': batch.request_counts.succeeded,
                    'errored': batch.request_counts.errored,
                    'canceled': batch.request_counts.canceled,
                    'expired': batch.request_counts.expired,
                    'processing': batch.request_counts.processing,
                },
                'ended_at': str(batch.ended_at) if batch.ended_at else None,
                'created_at': str(batch.created_at) if batch.created_at else None,
            }
        except Exception as e:
            return {'erro': str(e)}

    def coletar_resultados_batch(self, batch_id: str) -> List[Dict]:
        """Coleta resultados de batch finalizado. Formato igual a avaliar_chat()."""
        resultados = []
        try:
            client = self.client
            if client is None:
                logger.error("Anthropic não inicializado")
                return resultados

            for entry in client.messages.batches.results(batch_id):
                chat_id = entry.custom_id
                resultado = {
                    'chat_id': chat_id,
                    'classificacao': None, 'motivo': '', 'deve_avaliar': False,
                    'ai_evaluation': None, 'lead_score': None,
                    'vendor_score': None, 'main_product': None, 'erro': None,
                    'vendedor_disclaimer': None, 'lead_disclaimer': None,
                }

                if entry.result.type == 'succeeded':
                    content = (entry.result.message.content[0].text
                               if entry.result.message.content else "").strip()
                    content = self._limpar_markdown(content)
                    try:
                        ai_result = json.loads(content)
                        tipo = ai_result.get('tipo', 'outros')
                        resultado['classificacao'] = tipo
                        resultado['motivo'] = ai_result.get('motivo', '')
                        resultado['deve_avaliar'] = (tipo == 'venda')
                        if tipo == 'venda':
                            resultado['ai_evaluation'] = ai_result
                            resultado['lead_score'] = self._extrair_lead_score(ai_result)
                            resultado['vendor_score'] = self._extrair_vendor_score(ai_result)
                            resultado['main_product'] = self._extrair_main_product(ai_result)
                            resultado['vendedor_disclaimer'] = ai_result.get('vendedor_disclaimer')
                            resultado['lead_disclaimer'] = ai_result.get('lead_disclaimer')
                    except json.JSONDecodeError as e:
                        resultado['erro'] = f'JSON inválido: {e}'
                        resultado['classificacao'] = 'falha_avaliacao'
                else:
                    resultado['erro'] = f'Batch entry falhou: {entry.result.type}'
                    resultado['classificacao'] = 'falha_avaliacao'

                resultados.append(resultado)
        except Exception as e:
            logger.error("Erro ao coletar resultados do batch %s: %s", batch_id, e)

        return resultados
