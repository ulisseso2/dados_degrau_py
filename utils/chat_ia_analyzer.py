import os
import re
import json
import logging
from typing import Dict, Optional
import anthropic
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_CONTEXTO_NEGOCIO = """
CONTEXTO DO NEGÓCIO (use como verdade):
- Somos um curso preparatório para concursos com mais de 3 décadas de tradição e histórico de +100 mil aprovações.
- Prioridade de venda: cursos Presenciais e Live. (EAD é secundário/marginal.)
- Produtos e tickets médios:
  - Presencial: ~R$ 2.000
  - Live: ~R$ 2.000
  - EAD: ~R$ 300
  - Passaporte: projeto de estudo de longo prazo com acesso a TODAS as modalidades + "estudar até passar" SE cumprir orientações pedagógicas do curso.
  - Smart: acesso full às ferramentas digitais (EAD, Live e ferramenta/banco de questões).

CANAL (WhatsApp) – o que esperar da entrada:
- Pode conter: mensagens automáticas do WhatsApp/WhatsApp Business, anexos descritos (ex.: "[ÁUDIO]", "[IMAGEM]"), mensagens apagadas, trechos fora de ordem.
- Pode vir: (a) rotulado por nome, (b) rotulado como "Você:"/"Atendente:"/"Cliente:", (c) sem rótulos.

REGRAS IMPORTANTES (obrigatórias):
- NÃO invente informações. Quando algo não estiver no histórico, marque como "Não mencionado" ou "Incerto".
- SEMPRE justifique notas com EVIDÊNCIAS do histórico (citações de até 15 palavras).
- Proteção de dados: se houver telefone, CPF, e-mail, endereço, substitua por [DADO_SENSIVEL] nas evidências.
- Se detectar risco de compliance (promessa de aprovação garantida, informação enganosa, pressão indevida, desrespeito), destaque como "Alerta".
- Seja rigoroso, mas justo: conversa curta pode ser boa se tiver objetivo claro e avanço real.
- Saída: responda APENAS em JSON válido. Sem markdown. Sem comentários fora do JSON.
"""


class ChatIAAnalyzer:
    def __init__(self):
        """Inicializa cliente Anthropic (Claude)"""
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.client = anthropic.Anthropic(api_key=self.api_key) if self.api_key else None
        self.model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")
        self.model_classificacao = os.getenv("CLAUDE_MODEL_CLASSIFICACAO", "claude-haiku-4-5")
        self.temperature = float(os.getenv("CLAUDE_TEMPERATURE", "0.2"))
        self.max_tokens = int(os.getenv("CLAUDE_MAX_TOKENS", "8000"))
        self.max_tokens_classificacao = int(os.getenv("CLAUDE_MAX_TOKENS_CLASSIFICACAO", "2000"))
        self.max_input_chars = int(os.getenv("CLAUDE_MAX_INPUT_CHARS", "25000"))
        self.max_input_chars_classificacao = int(os.getenv("CLAUDE_MAX_INPUT_CHARS_CLASSIFICACAO", "4000"))

    def _criar_prompt_classificacao(self, chat_text: str) -> str:
        return f"""
Você é um triador de conversas de vendas educacionais por WhatsApp.

CATEGORIAS POSSÍVEIS (use exatamente um destes valores):
- "suporte": cliente quer resolver problema técnico, 2ª via de boleto, reset de senha, problema com plataforma.
- "duvida_geral": dúvida sobre endereço, telefone de unidade, calendário.
- "cancelamento": lead quer cancelar matrícula ou pedir reembolso.
- "venda": lead RESPONDEU e há diálogo real sobre cursos, concursos, bolsas, matrículas ou o vendedor oferece produtos E o lead interage.
- "sem_interacao": chat iniciado mas cliente NÃO RESPONDEU nada substantivo, ou SOMENTE robô/vendedor enviou mensagens sem resposta do lead.
- "outros": outra situação não enquadrada acima.

REGRA CRÍTICA: Se o lead/cliente NUNCA respondeu (só o vendedor ou bot enviaram mensagens), classifique como "sem_interacao" mesmo que o vendedor esteja oferecendo produtos.

RETORNE APENAS JSON VÁLIDO no formato:
{{
    "tipo": "...",
    "motivo": "uma frase curta explicando a classificação",
    "deve_avaliar": true
}}

Regra: "deve_avaliar" é true SOMENTE se "tipo" for "venda". Para todos os outros casos, false.

CONVERSA:
{chat_text[:self.max_input_chars_classificacao]}
"""

    def _criar_prompt_avaliacao(self, chat_text: str, contexto_adicional: Optional[Dict] = None) -> str:
        contexto_json = json.dumps(contexto_adicional, ensure_ascii=False) if contexto_adicional else "{}"
        return f"""
Você é um avaliador sênior de qualidade (QA) de VENDAS NO WHATSAPP e um coach de performance comercial.

{_CONTEXTO_NEGOCIO}

OBJETIVOS (DOIS):
1) Avaliar a qualidade da atuação do vendedor (SPIN, construção de valor, compromisso, persuasão ética, condução no WhatsApp).
2) Avaliar a qualidade do lead (fit + intenção + maturidade de decisão) com base APENAS no que aparece no histórico.

ETAPA 0 — IDENTIFICAR PARTICIPANTES + IQH (Índice de Qualidade do Histórico):
A) Identifique quem é VENDEDOR e quem é LEAD. Se houver mais de um atendente, trate como VENDEDOR (time). Se não der certeza, infira e declare baixa confiança.
B) Calcule IQH_0_100 somando: Rotulagem (0-25) + Ordem/tempo (0-15) + Legibilidade/ruído (0-20) + Cobertura (0-20) + Coerência (0-20).
   - 85-100 = Alta | 70-84 = Média | 0-69 = Baixa (marque precisa_reparacao: true, mas avalie mesmo assim).

O QUE VOCÊ DEVE IDENTIFICAR (extração objetiva):
A) Contexto do lead: Concurso/área-alvo, prazo/prova, nível atual, rotina/tempo, dores principais, restrições, tomador de decisão.
B) Produto(s) e oferta(s) discutidos (Presencial, Live, EAD, Passaporte, Smart):
   - Por que foi indicado | ancoragem de valor | se respeitou prioridade Presencial/Live.
C) SPIN na prática: Situação, Problema, Implicação, Necessidade de Solução (necessidades implícitas → explícitas?).
D) Persuasão ÉTICA: Autoridade, Prova social, Escassez/urgência (sem terrorismo), Reciprocidade, Compromisso/consistência, Afeição, Unidade.
E) Fechamento: houve resumo (dor+objetivo+solução)? Próximo passo específico? Compromisso proporcional ao estágio? Follow-up claro?

AVALIAÇÃO 1 — SCORE DO VENDEDOR (0 a 100):
Categorias: Abertura/rapport (0-10), Investigação SPIN (0-30), Valor/capacidade (0-20), Persuasão ética (0-10), Objeções (0-10), Compromisso/próximos passos (0-15), Clareza/compliance/WhatsApp (0-5).
Também entregue: 3 pontos fortes (com evidência), 3 melhorias (com mensagem de WhatsApp pronta ≤240 chars), erro mais caro (com evidência), alertas de compliance.

AVALIAÇÃO 2 — QUALIDADE DO LEAD (0 a 100):
Score + classificação: A (80-100) = alta qualidade, B (60-79) = bom, C (40-59) = morno, D (0-39) = fraco.
Dimensões (some 100): Fit Presencial/Live (0-30), Intenção/micro-momentos (0-30), Orientação a valor (0-20), Abertura para personalização (0-10), Restrições críticas (0-10, invertido: barreira forte = nota baixa).
Também: até 5 sinais quentes, até 5 sinais frios, perguntas SPIN que faltaram (até 7).

RECOMENDAÇÃO FINAL: melhor próximo passo, produto principal, produto alternativo, justificativa, risco de desalinhamento, mensagem pronta (≤240 chars).

Retorne EXATAMENTE o seguinte JSON preenchendo com "Não mencionado" quando necessário:
{{
  "canal": "whatsapp",
  "qualidade_entrada": {{
    "iqh_0_100": 0,
    "nivel": "Alta|Média|Baixa",
    "precisa_reparacao": false,
    "problemas_detectados": ["..."],
    "quem_e_vendedor": "...",
    "quem_e_lead": "...",
    "confianca_identificacao_papeis_0_1": 0.0
  }},
  "resumo_da_conversa": ["..."],
  "extracao": {{
    "concurso_area": "...",
    "prazo_prova": "...",
    "nivel_atual": "...",
    "tempo_estudo": "...",
    "dores_principais": ["..."],
    "restricoes": ["..."],
    "tomador_decisao": "...",
    "produtos_citados": [
      {{
        "produto": "Presencial|Live|EAD|Passaporte|Smart",
        "foi_indicado_por_que": "...",
        "ancoragem_de_valor": "...",
        "respeitou_prioridade_presencial_live": "...",
        "evidencias": ["..."]
      }}
    ]
  }},
  "avaliacao_vendedor": {{
    "nota_final_0_100": 0,
    "notas_por_categoria": {{
      "abertura_rapport_0_10": 0,
      "investigacao_spin_0_30": 0,
      "valor_capacidade_0_20": 0,
      "persuasao_etica_0_10": 0,
      "objecoes_0_10": 0,
      "compromisso_prox_passos_0_15": 0,
      "clareza_compliance_whatsapp_0_5": 0
    }},
    "pontos_fortes": [{{"ponto": "...", "evidencia": "..."}}],
    "melhorias": [{{"melhoria": "...", "como_fazer": "...", "evidencia_do_gap": "..."}}],
    "erro_mais_caro": {{"descricao": "...", "evidencia": "..."}},
    "alertas": ["..."]
  }},
  "avaliacao_lead": {{
    "lead_score_0_100": 0,
    "classificacao": "A|B|C|D",
    "dimensoes": {{
      "fit_0_30": 0,
      "intencao_micro_momentos_0_30": 0,
      "orientacao_valor_0_20": 0,
      "abertura_personalizacao_0_10": 0,
      "restricoes_barreiras_0_10_invertido": 0
    }},
    "sinais_quente": [{{"sinal": "...", "evidencia": "..."}}],
    "sinais_frio": [{{"sinal": "...", "evidencia": "..."}}],
    "perguntas_faltantes_spin": ["..."]
  }},
  "recomendacao_final": {{
    "melhor_proximo_passo": "...",
    "produto_principal_indicado": "...",
    "produto_alternativo_indicado": "...",
    "justificativa": "...",
    "risco_desalinhamento": "...",
    "mensagem_pronta_para_enviar_agora": "..."
  }}
}}

CONVERSA:
{chat_text[:self.max_input_chars]}

DADOS ADICIONAIS:
{contexto_json}
"""

    @staticmethod
    def _limpar_markdown(content: str) -> str:
        """Remove wrappers de markdown (```json ... ```) de forma segura."""
        if not content:
            return content
        content = content.strip()
        # Remove bloco ```json ... ``` ou ``` ... ```
        match = re.match(r'^```(?:json)?\s*\n?(.*?)\n?```$', content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return content

    @staticmethod
    def _extrair_main_product(ai_eval: dict) -> Optional[str]:
        """Extrai produto principal com múltiplos fallbacks."""
        # 1. Tenta recomendacao_final
        rec = ai_eval.get('recomendacao_final') or {}
        produto = rec.get('produto_principal_indicado')
        if produto and isinstance(produto, str) and produto.lower() not in ('não mencionado', 'null', 'none', ''):
            return produto

        # 2. Tenta primeiro produto de extracao.produtos_citados
        extracao = ai_eval.get('extracao') or {}
        produtos = extracao.get('produtos_citados') or []
        if produtos and isinstance(produtos, list):
            for p in produtos:
                if isinstance(p, dict):
                    nome = p.get('produto')
                    if nome and isinstance(nome, str) and nome.lower() not in ('não mencionado', 'null', 'none', ''):
                        return nome

        # 3. Tenta produto alternativo
        alt = rec.get('produto_alternativo_indicado')
        if alt and isinstance(alt, str) and alt.lower() not in ('não mencionado', 'null', 'none', ''):
            return alt

        return None

    @staticmethod
    def _extrair_lead_score(ai_eval: dict) -> Optional[int]:
        """Extrai lead_score com fallback para soma de dimensões."""
        avl = ai_eval.get('avaliacao_lead') or {}
        score = avl.get('lead_score_0_100')
        if score is not None:
            try:
                return int(score)
            except (ValueError, TypeError):
                pass

        # Fallback: soma das dimensões
        dims = avl.get('dimensoes') or {}
        if dims:
            total = 0
            for v in dims.values():
                try:
                    total += int(v)
                except (ValueError, TypeError):
                    pass
            if total > 0:
                return total
        return None

    @staticmethod
    def _extrair_vendor_score(ai_eval: dict) -> Optional[int]:
        """Extrai vendor_score com fallback para soma de categorias."""
        avv = ai_eval.get('avaliacao_vendedor') or {}
        score = avv.get('nota_final_0_100')
        if score is not None:
            try:
                return int(score)
            except (ValueError, TypeError):
                pass

        # Fallback: soma das notas por categoria
        cats = avv.get('notas_por_categoria') or {}
        if cats:
            total = 0
            for v in cats.values():
                try:
                    total += int(v)
                except (ValueError, TypeError):
                    pass
            if total > 0:
                return total
        return None

    def classificar_chat(self, chat_text: str) -> Dict:
        if not chat_text or len(chat_text.strip()) < 10:
            return {'tipo': 'sem_interacao', 'motivo': 'Chat vazio ou muito curto', 'deve_avaliar': False}
        if not self.client:
            return {'tipo': 'outros', 'motivo': 'Anthropic não inicializado (verifique ANTHROPIC_API_KEY)', 'deve_avaliar': False}

        prompt = self._criar_prompt_classificacao(chat_text)
        for tentativa in range(2):
            try:
                response = self.client.messages.create(
                    model=self.model_classificacao,
                    max_tokens=self.max_tokens_classificacao,
                    temperature=self.temperature,
                    system="Retorne sempre JSON válido.",
                    messages=[{"role": "user", "content": prompt}],
                )
                stop_reason = response.stop_reason
                content = (response.content[0].text if response.content else "").strip()
                if not content:
                    logger.warning("Classificação vazia (model=%s, stop_reason=%s, tentativa=%d)",
                                   self.model_classificacao, stop_reason, tentativa + 1)
                    if tentativa == 0:
                        continue
                    return {'tipo': 'outros', 'motivo': f'Classificação retornou resposta vazia (stop_reason={stop_reason})', 'deve_avaliar': False}
                content = self._limpar_markdown(content)
                return json.loads(content)
            except json.JSONDecodeError:
                if tentativa == 0:
                    continue
                return {'tipo': 'outros', 'motivo': 'Classificação retornou JSON inválido', 'deve_avaliar': False}
            except Exception as e:
                logger.warning("Falha na classificação (tentativa %d): %s", tentativa + 1, e)
                return {'tipo': 'outros', 'motivo': f'Falha na classificação: {e}', 'deve_avaliar': False}
        return {'tipo': 'outros', 'motivo': 'Classificação falhou após retentativas', 'deve_avaliar': False}

    def avaliar_chat(self, chat_text: str, contexto_adicional: Optional[Dict] = None) -> Dict:
        classificacao = self.classificar_chat(chat_text)

        # Chaves padronizadas: 'classificacao' e 'motivo' (usados em octadesk.py e chat_oportunidades.py)
        resultado = {
            'classificacao': classificacao.get('tipo', 'outros'),
            'motivo': classificacao.get('motivo', ''),
            'deve_avaliar': classificacao.get('deve_avaliar', False),
            'ai_evaluation': None,
            'lead_score': None,
            'vendor_score': None,
            'main_product': None,
            'erro': None
        }

        if not resultado['deve_avaliar']:
            return resultado

        prompt = self._criar_prompt_avaliacao(chat_text, contexto_adicional)

        # Retry: até 2 tentativas (mesma lógica da classificação)
        for tentativa in range(2):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system="Retorne sempre JSON válido.",
                    messages=[{"role": "user", "content": prompt}],
                )

                # Verificar se a resposta foi truncada
                stop_reason = response.stop_reason
                content = (response.content[0].text if response.content else "").strip()

                if not content:
                    logger.warning("Avaliação retornou conteúdo vazio (tentativa %d)", tentativa + 1)
                    if tentativa == 0:
                        continue
                    resultado['erro'] = 'Avaliação retornou resposta vazia após retentativas'
                    resultado['classificacao'] = 'falha_avaliacao'
                    return resultado

                if stop_reason == 'max_tokens':
                    logger.warning("Resposta truncada por max_tokens (tentativa %d, stop_reason=max_tokens)", tentativa + 1)
                    if tentativa == 0:
                        continue
                    # Na 2ª tentativa, tenta parsear mesmo truncado

                content = self._limpar_markdown(content)
                ai_eval = json.loads(content)

                resultado['ai_evaluation'] = ai_eval
                resultado['lead_score'] = self._extrair_lead_score(ai_eval)
                resultado['vendor_score'] = self._extrair_vendor_score(ai_eval)
                resultado['main_product'] = self._extrair_main_product(ai_eval)

                if stop_reason == 'max_tokens':
                    logger.warning("JSON parseado com sucesso apesar de truncamento. Seções podem estar faltando.")

                return resultado

            except json.JSONDecodeError as e:
                logger.warning("JSON inválido na avaliação (tentativa %d): %s", tentativa + 1, e)
                if tentativa == 0:
                    continue
                resultado['erro'] = f'Avaliação retornou JSON inválido: {e}'
                resultado['classificacao'] = 'falha_avaliacao'
            except Exception as e:
                logger.error("Erro na avaliação (tentativa %d): %s", tentativa + 1, e)
                resultado['erro'] = str(e)
                resultado['classificacao'] = 'falha_avaliacao'
                return resultado  # Erro de API/rede não adianta retry

        return resultado
