"""
Módulo para análise de transcrições de ligações de vendas
Usa Claude (Anthropic) com metodologia de Venda Consultiva Adaptada
"""

import os
import re
import json
import logging
import time as _time
import threading
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import anthropic
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT (fixo, cacheável pela API)
# ══════════════════════════════════════════════════════════════════════════════

_SYSTEM_PROMPT = """Você é avaliador sênior de qualidade (QA) de ligações de vendas e coach de performance comercial.

CONTEXTO DO NEGÓCIO:
Curso preparatório para concursos, +3 décadas, +100 mil aprovações.

MODALIDADES (CRÍTICO — NÃO CONFUNDA):
1. PRESENCIAL (PRIORIDADE MÁXIMA) — Ticket ~R$2.000. Aulas na unidade física.
2. LIVE (PRIORIDADE ALTA) — Ticket ~R$1.000. Aulas AO VIVO online, com interação em tempo real. NÃO é EAD. Fechar Live é BOM resultado.
3. EAD (SECUNDÁRIO) — Ticket ~R$300. Aulas GRAVADAS. "Curso online" / "aula gravada" = EAD.
Outros: Passaporte (~R$3.500+, todas modalidades), Smart (digital full).
HIERARQUIA: Presencial > Passaporte > Live > Smart > EAD

ENTRADA: Transcrição de ligação com rótulos "Vendedor:" e "Cliente:" (ou nomes).
Os rótulos PODEM estar invertidos por falha na transcrição. Identifique o vendedor pelo contexto (quem apresenta produto/benefícios/preço). NÃO penalize por trechos com rótulos trocados.

COMPLIANCE:
- Aceitar pagamento com cartão de terceiros NÃO é problema. Prática comum no B2C.
- Alerte APENAS para: promessa de aprovação garantida, informação enganosa, pressão indevida, desrespeito.

REGRAS:
- Justifique com EVIDÊNCIAS da transcrição (citações até 15 palavras).
- Não invente informações. Use "Não mencionado" quando ausente.
- Responda APENAS em JSON válido, sem markdown.

Retorne sempre JSON válido."""

# ══════════════════════════════════════════════════════════════════════════════
# USER PROMPT TEMPLATE
# ══════════════════════════════════════════════════════════════════════════════

_USER_PROMPT_TEMPLATE = """TAREFA ÚNICA: Classifique E avalie esta ligação de vendas em uma única análise.

ETAPA 0 — TRIAGEM:
Confirme se houve conversa de venda real e suficiente.
NÃO AVALIAR se: <6 turnos, só um lado fala, cliente ocupado/encerra rápido, apenas URA/caixa postal, conversa administrativa sem venda.
Tipos: "venda", "ura", "dialogo_incompleto", "dados_insuficientes", "ligacao_interna", "chamada_errada", "cancelamento", "suporte", "outros".
Se NÃO for "venda", retorne JSON mínimo e pare.

ETAPA 1 — IDENTIFICAR PARTICIPANTES:
Quem é vendedor, quem é lead. Se rótulos parecem invertidos, normalize mentalmente.

ETAPA 2 — EXTRAÇÃO: concurso/área, prazo, nível, dores, restrições, tomador decisão, produto discutido (Presencial/Live/EAD/Passaporte/Smart). Live NÃO é EAD.

ETAPA 3 — SCORE VENDEDOR (0-100):
Metodologia: Venda Consultiva Adaptada para Ligações Telefônicas B2C Educacional.

Categorias (somam 100):
- Rapport e conexão (0-10): Abertura natural? Confiança? Usou nome? Tom adaptado?
- Qualificação e leitura de contexto (0-15): Identificou concurso, modalidade, urgência? Se lead já trouxe infos, reconheceu — NÃO precisa interrogar. Ligação ativa = lead pode não saber por que ligaram; qualificação inicial é mais importante.
- Construção de valor e diferenciação (0-30): CATEGORIA MAIS IMPORTANTE. Apresentou diferenciais (tradição, aprovações, professores, método)? Ancorou valor ANTES do preço? Explicou por que vale o investimento? Se pulou pro preço sem construir valor = penalize pesado.
- Persuasão ética (0-10): Prova social, autoridade, urgência real, reciprocidade.
- Tratamento de objeções (0-10): Acolheu resistência? Contornou com empatia + evidência? Ofereceu alternativas?
- Condução ao fechamento (0-20): CTA claro? Próximo passo concreto (visita, matrícula, envio de proposta, follow-up com data)? Se ligação morreu sem compromisso = nota baixa.
- Clareza e compliance (0-5): Comunicação clara? Sem promessas irreais?

PONTOS FORTES — escolha 3, use EXATAMENTE um destes textos:

rapport:
  "Abertura empática e personalizada ao perfil do lead"
  "Estabeleceu conexão inicial amigável e interesse genuíno"
  "Criou conexão usando dado pessoal ou regional do lead"
  "Confirmou interesse do lead e deu sequência natural"
  "Escuta ativa com confirmações ao longo da ligação"

qualificacao:
  "Leu o contexto do lead sem interrogá-lo desnecessariamente"
  "Mapeou concurso-alvo e adequou toda a conversa ao perfil"
  "Identificou rotina e disponibilidade do lead"
  "Mapeou tentativas anteriores e dificuldades vivenciadas"
  "Qualificou rápido e direcionou pra modalidade certa"

valor:
  "Ancorou valor antes de apresentar o preço"
  "Produto indicado alinhado ao perfil e concurso do lead"
  "Benefícios conectados a necessidades explícitas do lead"
  "Apresentou tradição e histórico de aprovações como diferencial"
  "Diferenciou modalidades com benefícios concretos"
  "Destacou carga horária, material e estrutura como valor"

persuasao:
  "Autoridade e aprovações usadas com naturalidade"
  "Prova social com aprovações em concursos similares"
  "Urgência ética com base em prazo ou calendário real"
  "Escassez ética com vagas ou data de início da turma"

objecao:
  "Antecipou objeção antes que surgisse"
  "Tratou objeção com empatia e evidência concreta"
  "Contornou restrição financeira sem desqualificar o lead"

fechamento:
  "Próximo passo concreto proposto com data ou horário"
  "Resumiu necessidade + solução antes do fechamento"
  "Obteve compromisso de pagamento ou matrícula na ligação"
  "Encaminhou para visita à unidade ou aula experimental"
  "Enviou proposta ou link com prazo claro para decisão"

clareza:
  "Comunicação clara, objetiva e adaptada ao lead"
  "Informações precisas sem promessas inadequadas"

MELHORIAS — escolha 3, use EXATAMENTE um destes textos:

rapport:
  "Personalizar abertura ao perfil específico do lead"
  "Reduzir falas longas e ouvir mais o lead"

qualificacao:
  "Identificar concurso e perfil antes de apresentar produto"
  "Confirmar cronograma do concurso e alinhar expectativas"
  "Verificar pré-requisitos antes da proposta"
  "Mapear tentativas anteriores e dificuldades vivenciadas"

valor:
  "Ancorar valor do produto antes de apresentar o preço"
  "Conectar benefícios a necessidades explícitas do lead"
  "Reforçar diferenciais: tradição, professores, aprovações"
  "Apresentar diferencial da modalidade frente ao custo"

persuasao:
  "Criar urgência ética com base em prazo real"
  "Usar prova social em momento oportuno"
  "Mencionar aprovações em concursos similares ao do lead"

objecao:
  "Antecipar objeções previsíveis antes que surjam"
  "Aprofundar valor antes de ceder em desconto"

fechamento:
  "Definir próximo passo concreto antes de encerrar"
  "Resumir necessidade + solução antes do fechamento"
  "Obter mini-compromisso concreto antes de encerrar"

clareza:
  "Simplificar explicações e evitar jargões"
  "Confirmar valores corretos antes de processar pagamento"

ERRO MAIS CARO — use EXATAMENTE um destes textos:
  "Apresentou preço sem ancoragem de valor"
  "Não investigou contexto suficientemente antes da oferta"
  "Encerrou a ligação sem definir próximo passo concreto"
  "Perdeu momento de fechamento sem aproveitamento"
  "Deixou objeção principal sem tratamento"
  "Não contornou objeção de preço com evidências de valor"
  "Indicou produto fora do perfil e objetivo do lead"
  "Confundiu valores ou condições de modalidades"
  "Fez promessa inadequada ou com risco de compliance"
  "Nenhum erro crítico identificado"

ETAPA 4 — SCORE LEAD (0-100, A/B/C/D):
Fit Presencial/Live(0-30) + Intenção(0-30) + Orientação a valor(0-20) + Abertura(0-10) + Restrições invertido(0-10).
A(80-100), B(60-79), C(40-59), D(0-39).

ETAPA 5 — RECOMENDAÇÃO: produto principal, próximo passo.

ETAPA 6 — DISCLAIMERS (OBRIGATÓRIO):
vendedor_disclaimer (2-3 frases): POR QUE essa nota. Causa → efeito. Inclua a nota.
lead_disclaimer (2-3 frases): POR QUE essa classificação. Sinais concretos.

CONFIANÇA: base 0.90. Descontos: <10 turnos(-0.20), ruído(-0.15), atores ambíguos(-0.15), concurso NI(-0.10), unilateral(-0.10), produto NM(-0.10). Min 0.30, Max 0.90.

SE tipo != "venda", retorne APENAS:
{{"tipo":"<tipo>","motivo":"<frase curta>"}}

SE tipo == "venda":
{{
  "tipo": "venda",
  "motivo": "...",
  "avaliacao_vendedor": {{
    "nota_final_0_100": 0,
    "notas_por_categoria": {{
      "rapport_conexao_0_10": 0,
      "qualificacao_leitura_contexto_0_15": 0,
      "construcao_valor_diferenciacao_0_30": 0,
      "persuasao_etica_0_10": 0,
      "objecoes_0_10": 0,
      "conducao_fechamento_0_20": 0,
      "clareza_compliance_0_5": 0
    }},
    "pontos_fortes": [{{"categoria": "...", "ponto": "texto da lista", "evidencia": "até 15 palavras"}}],
    "melhorias": [{{"categoria": "...", "melhoria": "texto da lista", "evidencia": "até 15 palavras"}}],
    "erro_mais_caro": {{"categoria": "...", "descricao": "texto da lista", "evidencia": "até 15 palavras"}},
    "alertas": ["..."]
  }},
  "vendedor_disclaimer": "2-3 frases causa→efeito",
  "avaliacao_lead": {{
    "lead_score_0_100": 0,
    "classificacao": "A|B|C|D",
    "dimensoes": {{
      "fit_0_30": 0, "intencao_0_30": 0, "orientacao_valor_0_20": 0,
      "abertura_0_10": 0, "restricoes_invertido_0_10": 0
    }},
    "sinais_quente": [{{"sinal": "...", "evidencia": "..."}}],
    "sinais_frio": [{{"sinal": "...", "evidencia": "..."}}],
    "perguntas_que_faltaram": ["..."]
  }},
  "lead_disclaimer": "2-3 frases sinais concretos",
  "extracao": {{
    "concurso_area": "...",
    "dores_principais": ["..."],
    "restricoes": ["..."]
  }},
  "recomendacao_final": {{
    "produto_principal": "Presencial|Live|EAD|Passaporte|Smart|Não identificado",
    "proximo_passo": "...",
    "mensagem_pronta": "msg ≤240 chars para follow-up"
  }},
  "confianca_avaliacao": 0.0,
  "motivo_baixa_confianca": "preencher se < 0.70"
}}

TRANSCRIÇÃO DA LIGAÇÃO:
{transcricao}

{contexto_extra}"""


# ══════════════════════════════════════════════════════════════════════════════
# HEURÍSTICAS DE TRIAGEM (0 tokens)
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
        self.max_tokens = int(os.getenv("CLAUDE_MAX_TOKENS", "4096"))
        self.max_input_chars = int(os.getenv("CLAUDE_MAX_INPUT_CHARS", "25000"))
        self.max_workers = int(os.getenv("CLAUDE_MAX_WORKERS", "1"))
        self.throttle_seconds = float(os.getenv("CLAUDE_THROTTLE_SECONDS", "8"))
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

    def _build_prompt(self, transcricao: str, contexto_adicional: Optional[Dict] = None) -> str:
        ctx = ""
        if contexto_adicional:
            ctx = f"DADOS ADICIONAIS:\n{json.dumps(contexto_adicional, ensure_ascii=False)}"
        return _USER_PROMPT_TEMPLATE.format(
            transcricao=transcricao[:self.max_input_chars],
            contexto_extra=ctx
        )

    # ── chamada unitária ao Claude ────────────────────────────────────────────

    def _call_claude(self, transcricao: str, contexto_adicional: Optional[Dict] = None) -> Dict:
        prompt = self._build_prompt(transcricao, contexto_adicional)

        for tentativa in range(3):
            with self._throttle_lock:
                now = _time.time()
                elapsed = now - self._last_request_time
                if elapsed < self.throttle_seconds:
                    _time.sleep(self.throttle_seconds - elapsed)
                self._last_request_time = _time.time()

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

            # Produto — novo formato
            rec = ai_result.get('recomendacao_final', {})
            if isinstance(rec, dict):
                produto = rec.get('produto_principal')
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

        Args:
            transcricoes: lista de dicts com:
                - transcricao_id: int/str
                - transcricao: str
                - contexto_adicional: dict (opcional)
            max_workers: threads (default: self.max_workers)
            callback: função(completed, total, id, resultado)
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
