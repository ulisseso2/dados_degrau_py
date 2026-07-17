# -*- coding: utf-8 -*-
"""
transcricao_analyzer.py — v2 (régua canônica compartilhada)
===========================================================
Avaliador de transcrições de ligações de vendas.

MUDANÇAS v2 (jul/2026):
- Prompt: importado de utils.venda_consultiva_core (fonte única da régua,
  compartilhada com o WhatsApp). Listas fechadas mantidas; schema unificado.
- Contexto adicional: agora recebe tipo_ligacao (receptivo/ativo), empresa,
  etapa do CRM e qualificação prévia P1/P2 (princípio do juiz cego).
- Fornecedor: Claude (inalterado). Prompt caching mantido.
- API pública preservada: TranscricaoAnalyzer, analisar_transcricao,
  analisar_lote_paralelo, criar_batch, consultar_batch,
  coletar_resultados_batch.

ENV VARS:
  ANTHROPIC_API_KEY        — obrigatória
  CLAUDE_MODEL             — default claude-sonnet-4-6
  CLAUDE_TEMPERATURE       — default 0.2
  CLAUDE_MAX_TOKENS        — default 6000 (subiu de 4096: schema maior)
  CLAUDE_MAX_INPUT_CHARS   — default 25000
  CLAUDE_MAX_WORKERS       — default 2
  CLAUDE_THROTTLE_SECONDS  — default 4
"""

import os
import re
import json
import logging
import time as _time
import threading
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import anthropic
from dotenv import load_dotenv

from utils.venda_consultiva_core import (
    REGUA_VERSAO,
    build_user_prompt,
    system_prompt,
)

load_dotenv()
logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = system_prompt("ligacao")


# ══════════════════════════════════════════════════════════════════════════════
# HEURÍSTICAS DE TRIAGEM (0 tokens) — inalteradas
# ══════════════════════════════════════════════════════════════════════════════

def _heuristica_triagem(transcricao: str) -> Optional[Dict]:
    """Triagem por heurística — sem API call."""
    texto = " ".join(transcricao.lower().split())

    if len(texto) < 15:
        return {'tipo': 'dados_insuficientes', 'motivo': 'Transcrição muito curta', 'deve_avaliar': False}

    padroes_ura = [
        "caixa postal", "correio de voz", "grave seu recado", "grave a sua mensagem",
        "deixe a sua mensagem", "deixe sua mensagem", "não receber recados",
        "não está disponível", "após o sinal", "mensagem na caixa postal",
    ]
    tem_dialogo = ("vendedor:" in texto) and ("cliente:" in texto)

    if any(p in texto for p in padroes_ura) and not tem_dialogo:
        return {'tipo': 'ura', 'motivo': 'Caixa postal / URA sem diálogo humano', 'deve_avaliar': False}

    if not tem_dialogo and len(texto) < 255:
        return {'tipo': 'dados_insuficientes', 'motivo': 'Sem diálogo bilateral identificado', 'deve_avaliar': False}

    turnos_v = texto.count("vendedor:")
    turnos_c = texto.count("cliente:")
    total_turnos = turnos_v + turnos_c

    if turnos_v == 0 or turnos_c == 0:
        return {'tipo': 'dados_insuficientes', 'motivo': 'Apenas um lado da conversa', 'deve_avaliar': False}

    if total_turnos < 6:
        return {'tipo': 'dialogo_incompleto', 'motivo': 'Menos de 6 turnos', 'deve_avaliar': False}

    padroes_ocupado = [
        "estou ocupado", "não posso falar", "estou dirigindo", "dirigindo",
        "no trânsito", "ligue depois", "me liga depois", "retorno depois",
    ]
    if any(p in texto for p in padroes_ocupado) and total_turnos < 12:
        return {'tipo': 'dialogo_incompleto', 'motivo': 'Cliente ocupado, conversa interrompida', 'deve_avaliar': False}

    padroes_cancelamento = ["cancelamento", "cancelar", "reembolso", "estorno", "quero cancelar"]
    if any(p in texto for p in padroes_cancelamento):
        return {'tipo': 'cancelamento', 'motivo': 'Solicitação de cancelamento/reembolso', 'deve_avaliar': False}

    padroes_interno = ["ramal", "sala de reunião", "coordenação", "secretaria"]
    padroes_produto = ["curso", "matrícula", "turma", "aula", "presencial", "live", "ead", "pagamento"]
    if any(p in texto for p in padroes_interno) and not any(p in texto for p in padroes_produto):
        return {'tipo': 'ligacao_interna', 'motivo': 'Conversa interna entre colaboradores', 'deve_avaliar': False}

    return None  # Passar pra IA


def _detectar_troca_interlocutores(transcricao: str) -> Dict:
    """Detecta possível inversão de rótulos vendedor/cliente."""
    texto = transcricao.lower()
    if "vendedor:" not in texto or "cliente:" not in texto:
        return {"invertidos": False, "confianca": 0.0, "motivo": "Rótulos ausentes"}

    keywords = [
        "curso", "matrícula", "matricula", "mensalidade", "parcelamento",
        "turma", "aulas", "presencial", "live", "ead", "desconto", "pagamento",
        "boleto", "pix", "cartão",
    ]

    def _contar(prefixo):
        linhas = [l for l in texto.splitlines() if l.strip().startswith(prefixo)]
        return sum(" ".join(linhas).count(k) for k in keywords) if linhas else 0

    sv, sc = _contar("vendedor:"), _contar("cliente:")
    if sc >= sv + 3:
        return {"invertidos": True, "confianca": 0.7, "motivo": "Cliente tem mais termos de vendedor"}
    return {"invertidos": False, "confianca": 0.6 if sv > 0 else 0.3, "motivo": "Distribuição compatível"}


# ══════════════════════════════════════════════════════════════════════════════
# CLASSE PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

class TranscricaoAnalyzer:
    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.client = anthropic.Anthropic(api_key=self.api_key) if self.api_key else None
        self.model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
        self.temperature = float(os.getenv("CLAUDE_TEMPERATURE", "0.2"))
        self.max_tokens = int(os.getenv("CLAUDE_MAX_TOKENS", "6000"))
        self.max_input_chars = int(os.getenv("CLAUDE_MAX_INPUT_CHARS", "25000"))
        self.max_workers = int(os.getenv("CLAUDE_MAX_WORKERS", "2"))
        self.throttle_seconds = float(os.getenv("CLAUDE_THROTTLE_SECONDS", "4"))
        self._thread_local = threading.local()

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _limpar_markdown(content: str) -> str:
        if not content:
            return content
        content = content.strip()
        match = re.match(r'^```(?:json)?\s*\n?(.*?)\n?```$', content, re.DOTALL)
        return match.group(1).strip() if match else content

    def _build_prompt(self, transcricao: str, contexto_adicional: Optional[Dict] = None) -> str:
        ctx_json = ""
        if contexto_adicional:
            ctx_json = json.dumps(contexto_adicional, ensure_ascii=False)
        return build_user_prompt(
            canal="ligacao",
            conteudo=transcricao[:self.max_input_chars],
            contexto_adicional_json=ctx_json,
        )

    # ── chamada unitária ao Claude ────────────────────────────────────────────

    def _call_claude(self, transcricao: str, contexto_adicional: Optional[Dict] = None) -> Dict:
        prompt = self._build_prompt(transcricao, contexto_adicional)
        content = ""

        for tentativa in range(3):
            last = getattr(self._thread_local, 'last_request_time', 0.0)
            elapsed = _time.time() - last
            if elapsed < self.throttle_seconds:
                _time.sleep(self.throttle_seconds - elapsed)
            self._thread_local.last_request_time = _time.time()

            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=[{
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"}
                    }],
                    messages=[{"role": "user", "content": prompt}],
                )

                usage = getattr(response, 'usage', None)
                logger.info(
                    "[Claude/ligacao] modelo=%s regua=%s | tokens in=%s out=%s | stop=%s",
                    self.model, REGUA_VERSAO,
                    getattr(usage, 'input_tokens', None),
                    getattr(usage, 'output_tokens', None),
                    response.stop_reason,
                )

                content = (response.content[0].text if response.content else "").strip()
                if not content:
                    if tentativa < 2:
                        continue
                    return {'erro': 'Resposta vazia'}

                if response.stop_reason == 'max_tokens' and tentativa < 2:
                    continue

                content = self._limpar_markdown(content)
                return json.loads(content)

            except json.JSONDecodeError as e:
                if tentativa < 2:
                    continue
                return {'erro': f'JSON inválido: {e}'}
            except anthropic.RateLimitError as e:
                wait = min(2 ** (tentativa + 2), 60)
                logger.warning("Rate limit 429 (tentativa %d). Aguardando %ds...", tentativa + 1, wait)
                _time.sleep(wait)
                if tentativa == 2:
                    return {'erro': f'Rate limit excedido: {e}'}
            except Exception as e:
                logger.error("Erro (tentativa %d): %s", tentativa + 1, e)
                return {'erro': str(e)}

        return {'erro': 'Falha após retentativas'}

    # ── pipeline completo (1 ligação) ─────────────────────────────────────────

    def analisar_transcricao(self, transcricao: str, contexto_adicional: Optional[Dict] = None) -> Dict:
        """
        Pipeline completo:
          1. Heurística de triagem (0 API calls)
          2. Detecção de inversão de interlocutores (0 API calls)
          3. Classificação + avaliação com Claude (1 API call)
        contexto_adicional: dict montado por venda_consultiva_core
        .montar_contexto_qualificacao (tipo_ligacao, empresa, P1/P2, etapa).
        """
        resultado = {
            'classificacao_ligacao': None, 'motivo': '', 'deve_avaliar': False,
            'avaliacao_completa': None, 'nota_vendedor': 0,
            'lead_score': None, 'lead_classificacao': None,
            'concurso_area': None, 'produto_recomendado': None,
            'vendedor_disclaimer': None, 'lead_disclaimer': None,
            'confianca_avaliacao': None, 'erro': None,
        }

        if not transcricao or len(transcricao.strip()) < 10:
            resultado['classificacao_ligacao'] = 'dados_insuficientes'
            resultado['motivo'] = 'Transcrição vazia ou muito curta'
            return resultado

        # Camada 1: heurística
        heuristica = _heuristica_triagem(transcricao)
        if heuristica and not heuristica.get('deve_avaliar', False):
            resultado['classificacao_ligacao'] = heuristica['tipo']
            resultado['motivo'] = heuristica['motivo']
            return resultado

        # Camada 2: detecção de inversão
        info_interloc = _detectar_troca_interlocutores(transcricao)

        # Camada 3: Claude faz triagem + avaliação (1 call)
        if not self.client:
            resultado['classificacao_ligacao'] = 'erro'
            resultado['motivo'] = 'Anthropic não inicializado'
            return resultado

        ai_result = self._call_claude(transcricao, contexto_adicional)

        if 'erro' in ai_result and ai_result.get('erro'):
            resultado['erro'] = ai_result['erro']
            resultado['classificacao_ligacao'] = 'erro'
            return resultado

        tipo = ai_result.get('tipo', 'outros')
        resultado['classificacao_ligacao'] = tipo
        resultado['motivo'] = ai_result.get('motivo', '')
        resultado['deve_avaliar'] = (tipo == 'venda')

        if tipo == 'venda':
            resultado['avaliacao_completa'] = json.dumps(ai_result, ensure_ascii=False)
            resultado['nota_vendedor'] = ai_result.get('avaliacao_vendedor', {}).get('nota_final_0_100', 0)
            resultado['lead_score'] = ai_result.get('avaliacao_lead', {}).get('lead_score_0_100')
            resultado['lead_classificacao'] = ai_result.get('avaliacao_lead', {}).get('classificacao')
            resultado['concurso_area'] = ai_result.get('extracao', {}).get('concurso_area')
            resultado['vendedor_disclaimer'] = ai_result.get('vendedor_disclaimer')
            resultado['lead_disclaimer'] = ai_result.get('lead_disclaimer')
            resultado['confianca_avaliacao'] = ai_result.get('confianca_avaliacao')

            # Produto — schema canônico ('produto_principal' string) + legados
            rec = ai_result.get('recomendacao_final', {})
            if isinstance(rec, dict):
                produto = rec.get('produto_principal') or rec.get('produto_principal_indicado')
                if isinstance(produto, dict):
                    resultado['produto_recomendado'] = produto.get('produto', 'N/A')
                elif isinstance(produto, str):
                    resultado['produto_recomendado'] = produto
                else:
                    resultado['produto_recomendado'] = 'N/A'

        # Metadata de interlocutores
        resultado['interlocutores_invertidos'] = info_interloc.get('invertidos')

        return resultado

    # ── processamento paralelo ────────────────────────────────────────────────

    def analisar_lote_paralelo(
        self,
        transcricoes: List[Dict],
        max_workers: Optional[int] = None,
        callback=None
    ) -> List[Dict]:
        """
        Avalia múltiplas transcrições em paralelo.
        transcricoes: dicts com transcricao_id, transcricao, contexto_adicional.
        """
        workers = max_workers or self.max_workers
        resultados = [None] * len(transcricoes)

        def _process(idx, item):
            tid = item.get('transcricao_id', f'trans_{idx}')
            try:
                result = self.analisar_transcricao(
                    transcricao=item.get('transcricao', ''),
                    contexto_adicional=item.get('contexto_adicional')
                )
                result['transcricao_id'] = tid
                return idx, result
            except Exception as e:
                return idx, {
                    'transcricao_id': tid,
                    'classificacao_ligacao': 'erro',
                    'motivo': str(e), 'erro': str(e),
                    'nota_vendedor': 0, 'lead_score': None,
                    'avaliacao_completa': None,
                }

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_process, i, t): i
                for i, t in enumerate(transcricoes)
            }
            completed = 0
            for future in as_completed(futures):
                idx, result = future.result()
                resultados[idx] = result
                completed += 1
                if callback:
                    try:
                        callback(completed, len(transcricoes), result.get('transcricao_id', ''), result)
                    except Exception:
                        pass

        return resultados

    # ── batch API ─────────────────────────────────────────────────────────────

    def consultar_batch(self, batch_id: str) -> dict:
        """Consulta status de um batch na Anthropic."""
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

    def criar_batch(self, transcricoes: List[Dict]) -> Optional[str]:
        """Envia transcrições para Batch API (50% desconto). Retorna batch_id."""
        if not self.client:
            return None

        requests = []
        for item in transcricoes:
            tid = str(item.get('transcricao_id', ''))
            transcricao = item.get('transcricao', '')

            heuristica = _heuristica_triagem(transcricao)
            if heuristica and not heuristica.get('deve_avaliar', False):
                continue

            prompt = self._build_prompt(transcricao, item.get('contexto_adicional'))
            requests.append({
                "custom_id": tid,
                "params": {
                    "model": self.model,
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                    "system": [{"type": "text", "text": _SYSTEM_PROMPT}],
                    "messages": [{"role": "user", "content": prompt}],
                }
            })

        if not requests:
            return None

        try:
            batch = self.client.messages.batches.create(requests=requests)
            logger.info("Batch criado: %s (%d requests)", batch.id, len(requests))
            return batch.id
        except Exception as e:
            logger.error("Erro ao criar batch: %s", e)
            return None

    def coletar_resultados_batch(self, batch_id: str) -> List[Dict]:
        """Coleta resultados de batch finalizado."""
        resultados = []
        try:
            for entry in self.client.messages.batches.results(batch_id):
                resultado = {
                    'transcricao_id': entry.custom_id,
                    'classificacao_ligacao': None, 'motivo': '',
                    'nota_vendedor': 0, 'avaliacao_completa': None,
                    'lead_score': None, 'lead_classificacao': None,
                    'vendedor_disclaimer': None, 'lead_disclaimer': None,
                    'erro': None,
                }

                if entry.result.type == 'succeeded':
                    content = (entry.result.message.content[0].text
                               if entry.result.message.content else "").strip()
                    content = self._limpar_markdown(content)
                    try:
                        ai_result = json.loads(content)
                        tipo = ai_result.get('tipo', 'outros')
                        resultado['classificacao_ligacao'] = tipo
                        resultado['motivo'] = ai_result.get('motivo', '')

                        if tipo == 'venda':
                            resultado['avaliacao_completa'] = json.dumps(ai_result, ensure_ascii=False)
                            resultado['nota_vendedor'] = ai_result.get('avaliacao_vendedor', {}).get('nota_final_0_100', 0)
                            resultado['lead_score'] = ai_result.get('avaliacao_lead', {}).get('lead_score_0_100')
                            resultado['lead_classificacao'] = ai_result.get('avaliacao_lead', {}).get('classificacao')
                            resultado['vendedor_disclaimer'] = ai_result.get('vendedor_disclaimer')
                            resultado['lead_disclaimer'] = ai_result.get('lead_disclaimer')
                    except json.JSONDecodeError as e:
                        resultado['erro'] = f'JSON inválido: {e}'
                        resultado['classificacao_ligacao'] = 'erro'
                else:
                    resultado['erro'] = f'Batch entry failed: {entry.result.type}'
                    resultado['classificacao_ligacao'] = 'erro'

                resultados.append(resultado)
        except Exception as e:
            logger.error("Erro batch %s: %s", batch_id, e)

        return resultados
