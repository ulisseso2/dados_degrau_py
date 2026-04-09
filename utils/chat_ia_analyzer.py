import os
import re
import json
import logging
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import anthropic
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTES DE BOTS
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

# ──────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT (fixo, cacheável pela API)
# ──────────────────────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """Você é um avaliador sênior de qualidade (QA) de vendas no WhatsApp e coach de performance comercial para um curso preparatório de concursos com +30 anos e +100 mil aprovações.

CONTEXTO DO NEGÓCIO — MODALIDADES DE ESTUDO (CRÍTICO, LEIA COM ATENÇÃO):

Existem 3 modalidades, com prioridades diferentes para o negócio:

1. PRESENCIAL (PRIORIDADE MÁXIMA) — Ticket ~R$2.000
   Aulas 100% presenciais na unidade física.

2. LIVE (PRIORIDADE ALTA) — Ticket ~R$1.000
   Aulas AO VIVO transmitidas online, com interação em tempo real. NÃO é EAD.
   Live é produto de alto valor. Fechar Live é um BOM resultado. NÃO penalize o vendedor por fechar Live.

3. EAD (SECUNDÁRIO) — Ticket ~R$300
   Aulas GRAVADAS, sem interação ao vivo. Também chamado de "curso online" ou "aula gravada".
   Produto de menor valor e menor prioridade.

REGRA DE IDENTIFICAÇÃO (NÃO CONFUNDA):
- "Live" / "aula ao vivo" / "ao vivo online" → modalidade LIVE (prioridade ALTA)
- "EAD" / "curso online" / "aula gravada" / "gravado" → modalidade EAD (secundário)
- Se o lead pedir "curso online" sem especificar, assuma EAD até que o contexto prove o contrário.

OUTROS PRODUTOS:
- Passaporte (~R$3.500+): acesso a TODAS as modalidades + "estudar até passar".
- Smart: acesso full digital (EAD + Live + banco de questões).

HIERARQUIA DE VALOR: Presencial > Passaporte > Live > Smart > EAD

PRÉ-PROCESSAMENTO: Mensagens de bots (Ariel, OctaBot, dicas) já foram REMOVIDAS. Você lê apenas interação humana. Não penalize falta de rapport inicial — o bot já fez triagem.

REGRAS:
- Não invente informações. Use "Não mencionado" quando ausente.
- Justifique notas com evidências do histórico (até 15 palavras, dados sensíveis como [DADO_SENSIVEL]).
- Destaque riscos de compliance como "Alerta" APENAS para: promessa de aprovação garantida, informação enganosa, pressão indevida, desrespeito ao cliente.
- Aceitar pagamento com cartão de terceiros NÃO é problema de compliance. É prática comum no B2C. NÃO gere alerta por isso.
- Responda APENAS em JSON válido, sem markdown.

Retorne sempre JSON válido."""

# ──────────────────────────────────────────────────────────────────────────────
# USER PROMPT TEMPLATE (compactado ~40% vs original, mesma qualidade)
# ──────────────────────────────────────────────────────────────────────────────
_USER_PROMPT_TEMPLATE = """TAREFA ÚNICA: Classifique E avalie esta conversa de WhatsApp em uma única análise.

ETAPA 0 — CLASSIFICAÇÃO:
Determine o tipo: "venda" (diálogo real sobre cursos/matrículas com resposta substantiva do lead), "suporte", "duvida_geral", "cancelamento", "sem_interacao" (lead não respondeu ou só monossilábico), "outros".
Se NÃO for "venda", retorne JSON mínimo (veja abaixo) e pare.

ETAPA 1 — IDENTIFICAR PARTICIPANTES + IQH:
Quem é vendedor, quem é lead. IQH (0-100): Rotulagem(0-25) + Ordem(0-15) + Legibilidade(0-20) + Cobertura(0-20) + Coerência(0-20).

ETAPA 2 — EXTRAÇÃO: concurso/área, prazo, nível, tempo estudo, dores, restrições, tomador decisão, produtos citados (qual modalidade: Presencial/Live/EAD/Passaporte/Smart, por quê, ancoragem, se respeitou prioridade Presencial>Live>EAD). ATENÇÃO: Live NÃO é EAD. Se o lead pediu Live e o vendedor fechou Live, marque "respeitou_prioridade" como "Sim".

ETAPA 3 — SCORE VENDEDOR (0-100):
Metodologia: Venda Consultiva Adaptada para WhatsApp B2C Educacional.
NÃO use SPIN selling puro. O lead vem de tráfego pago com intenção declarada. O vendedor deve LER o contexto (não interrogar), ANCORAR VALOR (não pular pro preço), e CONDUZIR AO FECHAMENTO (não deixar a conversa morrer).

Categorias (somam 100):
- Rapport e conexão (0-10): Cumprimentou com naturalidade? Criou clima de confiança? Usou nome? Adaptou tom ao lead?
- Qualificação e leitura de contexto (0-15): Identificou concurso, modalidade, urgência, restrições? Se o lead já trouxe essas infos, reconheceu e usou — NÃO precisa perguntar de novo. Lead que chega decidido exige leitura, não interrogatório.
- Construção de valor e diferenciação (0-30): Esta é a categoria MAIS IMPORTANTE. O vendedor apresentou diferenciais do curso (tradição, aprovações, professores, método)? Fez ancoragem de valor ANTES de falar preço? Explicou por que vale o investimento? Conectou o produto à dor/objetivo do lead? Se pulou direto pro preço sem construir valor, penalize pesado aqui.
- Persuasão ética (0-10): Prova social, autoridade, urgência real (não fabricada), reciprocidade, compromisso progressivo.
- Tratamento de objeções (0-10): Quando houve resistência (preço, tempo, dúvida), o vendedor acolheu e contornou? Ofereceu alternativas (parcelamento, outra modalidade)?
- Condução ao fechamento (0-20): CTA claro e proporcional ao estágio? Propôs próximo passo concreto? Facilitou pagamento? Se fechou venda, conduziu matrícula? Se não fechou, agendou follow-up? Conversa morreu sem compromisso = nota baixa.
- Clareza e compliance (0-5): Mensagens claras no WhatsApp? Sem erros graves de português? Sem promessas irreais? Dados sensíveis protegidos?

Entregue também: 3 pontos fortes (com evidência), 3 melhorias (com mensagem de WhatsApp pronta ≤240 chars cada), erro mais caro (com evidência), alertas de compliance.

ETAPA 4 — SCORE LEAD (0-100, A/B/C/D):
Fit Presencial/Live(0-30) + Intenção/micro-momentos(0-30) + Orientação a valor(0-20) + Abertura para personalização(0-10) + Restrições(0-10 invertido).
Sinais quentes/frios + perguntas que o vendedor deveria ter feito (até 5, baseadas no contexto que faltou explorar).

ETAPA 5 — RECOMENDAÇÃO: próximo passo, produto principal, alternativo, justificativa, risco, msg pronta (≤240 chars).

ETAPA 6 — DISCLAIMERS (OBRIGATÓRIO):
Dois resumos executivos em linguagem direta, para um gestor comercial que não vai ler o chat:

vendedor_disclaimer (2-3 frases): POR QUE essa nota. Causa (o que fez/deixou de fazer com exemplo concreto) → efeito (impacto na nota). Inclua a nota. Ex: "Vendedor recebeu 68/100. Leu bem o contexto e conduziu o fechamento com agilidade, mas não ancorou valor — pulou da qualificação direto pro preço sem apresentar diferenciais. Perdeu 22 pontos em Construção de Valor."

lead_disclaimer (2-3 frases): POR QUE essa classificação. Sinais concretos. Ex: "Lead B (72/100). Interesse claro em Live pra concurso INSS, mas sem urgência definida e sensível a preço. Pediu boleto e comparou com concorrente — precisa de ancoragem de valor no follow-up."

SE tipo != "venda", retorne APENAS:
{{"tipo":"<tipo>","motivo":"<frase curta>"}}

SE tipo == "venda", retorne o JSON completo:
{{
  "tipo": "venda",
  "motivo": "...",
  "canal": "whatsapp",
  "qualidade_entrada": {{
    "iqh_0_100": 0, "nivel": "Alta|Média|Baixa", "precisa_reparacao": false,
    "problemas_detectados": ["..."],
    "quem_e_vendedor": "...", "quem_e_lead": "...", "confianca_identificacao_papeis_0_1": 0.0
  }},
  "resumo_da_conversa": ["..."],
  "extracao": {{
    "concurso_area": "...", "prazo_prova": "...", "nivel_atual": "...", "tempo_estudo": "...",
    "dores_principais": ["..."], "restricoes": ["..."], "tomador_decisao": "...",
    "produtos_citados": [{{
      "produto": "Presencial|Live|EAD|Passaporte|Smart",
      "foi_indicado_por_que": "...", "ancoragem_de_valor": "...",
      "respeitou_prioridade_presencial_live": "...", "evidencias": ["..."]
    }}]
  }},
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
    "pontos_fortes": [{{"ponto": "...", "evidencia": "..."}}],
    "melhorias": [{{"melhoria": "...", "como_fazer": "...", "evidencia_do_gap": "..."}}],
    "erro_mais_caro": {{"descricao": "...", "evidencia": "..."}},
    "alertas": ["..."]
  }},
  "vendedor_disclaimer": "2-3 frases: causa→efeito da nota do vendedor",
  "avaliacao_lead": {{
    "lead_score_0_100": 0, "classificacao": "A|B|C|D",
    "dimensoes": {{
      "fit_0_30": 0, "intencao_micro_momentos_0_30": 0, "orientacao_valor_0_20": 0,
      "abertura_personalizacao_0_10": 0, "restricoes_barreiras_0_10_invertido": 0
    }},
    "sinais_quente": [{{"sinal": "...", "evidencia": "..."}}],
    "sinais_frio": [{{"sinal": "...", "evidencia": "..."}}],
    "perguntas_que_faltaram": ["..."]
  }},
  "lead_disclaimer": "2-3 frases: sinais concretos que justificam a classificação do lead",
  "recomendacao_final": {{
    "melhor_proximo_passo": "...", "produto_principal_indicado": "...",
    "produto_alternativo_indicado": "...", "justificativa": "...",
    "risco_desalinhamento": "...", "mensagem_pronta_para_enviar_agora": "..."
  }}
}}

CONVERSA:
{chat_text}

{contexto_extra}"""


# ══════════════════════════════════════════════════════════════════════════════
# FUNÇÕES DE PRÉ-PROCESSAMENTO (sem mudanças funcionais vs versão anterior)
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
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.client = anthropic.Anthropic(api_key=self.api_key) if self.api_key else None
        self.model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
        self.temperature = float(os.getenv("CLAUDE_TEMPERATURE", "0.2"))
        self.max_tokens = int(os.getenv("CLAUDE_MAX_TOKENS", "4096"))
        self.max_input_chars = int(os.getenv("CLAUDE_MAX_INPUT_CHARS", "25000"))
        # Workers: default 1 para tiers baixos (8k tokens/min).
        # Suba para 3-5 se seu tier permitir (40k+ tokens/min).
        self.max_workers = int(os.getenv("CLAUDE_MAX_WORKERS", "1"))
        # Segundos entre requests (respeitando rate limit)
        self.throttle_seconds = float(os.getenv("CLAUDE_THROTTLE_SECONDS", "8"))
        import threading
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
        produto = rec.get('produto_principal_indicado')
        if produto and isinstance(produto, str) and produto.lower() not in ('não mencionado', 'null', 'none', ''):
            return produto
        for p in (ai_eval.get('extracao') or {}).get('produtos_citados') or []:
            if isinstance(p, dict):
                nome = p.get('produto')
                if nome and isinstance(nome, str) and nome.lower() not in ('não mencionado', 'null', 'none', ''):
                    return nome
        alt = rec.get('produto_alternativo_indicado')
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
        """Monta o user prompt com transcrição e contexto."""
        ctx = ""
        if contexto_adicional:
            ctx = f"DADOS ADICIONAIS:\n{json.dumps(contexto_adicional, ensure_ascii=False)}"
        return _USER_PROMPT_TEMPLATE.format(
            chat_text=chat_text[:self.max_input_chars],
            contexto_extra=ctx
        )

    # ── chamada unitária ao Sonnet (classificação + avaliação em 1 call) ─────

    def _call_sonnet(self, chat_text: str, contexto_adicional: Optional[Dict] = None) -> Dict:
        """Faz UMA chamada ao Sonnet que classifica E avalia. Inclui throttle e retry para 429."""
        import time as _time

        prompt = self._build_prompt(chat_text, contexto_adicional)

        for tentativa in range(3):  # 3 tentativas (extra pra 429)
            # Throttle: espera tempo mínimo entre requests
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

                stop_reason = response.stop_reason
                content = (response.content[0].text if response.content else "").strip()

                if not content:
                    if tentativa < 2:
                        continue
                    return {'erro': 'Resposta vazia após retentativas'}

                if stop_reason == 'max_tokens' and tentativa < 2:
                    continue

                content = self._limpar_markdown(content)
                return json.loads(content)

            except json.JSONDecodeError as e:
                if tentativa < 2:
                    continue
                return {'erro': f'JSON inválido: {e}'}
            except anthropic.RateLimitError as e:
                # 429: esperar e tentar de novo
                wait = min(2 ** (tentativa + 2), 60)  # 4s, 8s, 16s...
                logger.warning("Rate limit (429) na tentativa %d. Aguardando %ds...", tentativa + 1, wait)
                _time.sleep(wait)
                if tentativa == 2:
                    return {'erro': f'Rate limit excedido após 3 tentativas: {e}'}
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
          3. Classifica + avalia com Sonnet (1 API call)
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

        # Camada 3: Sonnet faz classificação + avaliação (1 call)
        if not self.client:
            resultado['classificacao'] = 'outros'
            resultado['motivo'] = 'Anthropic não inicializado'
            return resultado

        ai_result = self._call_sonnet(transcricao_limpa, contexto_adicional)

        if 'erro' in ai_result and ai_result.get('erro'):
            resultado['erro'] = ai_result['erro']
            resultado['classificacao'] = 'falha_avaliacao'
            return resultado

        # Extrair classificação do resultado unificado
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

        Args:
            chats: lista de dicts, cada um com:
                - chat_id: str
                - transcript: str (transcrição completa)
                - agent_name: str (opcional)
                - contexto_adicional: dict (opcional)
            max_workers: número de threads (default: self.max_workers)
            callback: função(i, total, chat_id, resultado) chamada após cada chat

        Returns:
            lista de dicts com resultado + chat_id
        """
        workers = max_workers or self.max_workers
        resultados = [None] * len(chats)

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

        return resultados

    # ══════════════════════════════════════════════════════════════════════════
    # BATCH API (modo assíncrono, 50% desconto, até 10k chats)
    # ══════════════════════════════════════════════════════════════════════════

    def criar_batch(self, chats: List[Dict]) -> Optional[str]:
        """
        Envia chats para a Message Batches API da Anthropic.
        Retorna batch_id para consulta posterior.

        Args:
            chats: lista de dicts com chat_id, transcript, agent_name, contexto_adicional
                   (mesma estrutura de avaliar_lote_paralelo)

        Returns:
            batch_id (str) ou None se falhar
        """
        if not self.client:
            logger.error("Anthropic não inicializado")
            return None

        requests = []
        for chat_data in chats:
            chat_id = chat_data.get('chat_id', '')

            # Pré-processar (filtrar bot + verificar avaliabilidade)
            filtro = filtrar_mensagens_bot(chat_data.get('transcript', ''))
            avaliavel, motivo = verificar_avaliabilidade(
                filtro, chat_data.get('agent_name', '')
            )
            if not avaliavel:
                # Não inclui no batch — será tratado localmente
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
            batch = self.client.messages.batches.create(requests=requests)
            logger.info("Batch criado: %s (%d requests)", batch.id, len(requests))
            return batch.id
        except Exception as e:
            logger.error("Erro ao criar batch: %s", e)
            return None

    def consultar_batch(self, batch_id: str) -> Dict:
        """
        Consulta status de um batch.
        Returns: dict com processing_status, request_counts, etc.
        """
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
        """
        Coleta resultados de um batch finalizado.
        Retorna lista de dicts no mesmo formato de avaliar_chat().
        """
        resultados = []
        try:
            for entry in self.client.messages.batches.results(batch_id):
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
                    resultado['erro'] = f'Batch entry failed: {entry.result.type}'
                    resultado['classificacao'] = 'falha_avaliacao'

                resultados.append(resultado)
        except Exception as e:
            logger.error("Erro ao coletar resultados do batch %s: %s", batch_id, e)

        return resultados
