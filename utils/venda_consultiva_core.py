# -*- coding: utf-8 -*-
"""
venda_consultiva_core.py — FONTE ÚNICA DA VERDADE da avaliação comercial via IA.
================================================================================

Este módulo é o contrato canônico compartilhado pelos DOIS canais (WhatsApp e
Ligação Telefônica). Tudo que define a régua de avaliação vive AQUI e somente
aqui: categorias e pesos, listas fechadas de pontos fortes/melhorias/erros,
system prompts, templates de user prompt, schema JSON de saída e o protocolo
de qualificação prévia (P1/P2) com o princípio do JUIZ CEGO.

Regra de ouro do projeto:
    Mudou a régua? Muda AQUI. Os analyzers apenas consomem este módulo.
    Assim os dois canais nunca mais divergem ("enviesam pra lados diferentes").

Versão da régua: VCA-2026.07  (Venda Consultiva Adaptada, revisão jul/2026)

PRINCÍPIO DO JUIZ CEGO (decisão de desenho — NÃO ALTERAR sem revisão):
    Os dados de qualificação prévia do bot (P1 urgência + P2 investimento)
    são injetados no prompt EXCLUSIVAMENTE para contextualizar a avaliação
    do VENDEDOR (ele reconheceu e tratou a temperatura declarada do lead?).
    O SCORE DO LEAD gerado pela IA permanece CEGO a esses dados — é calculado
    apenas pelo comportamento observado na conversa. A comparação entre
    "declarado no bot" × "inferido pela IA" é feita FORA do prompt, nos
    dashboards. Se a IA visse o P1/P2 ao pontuar o lead, ancoraria no
    declarado e a validação cruzada da régua perderia a independência.
"""

from typing import Dict, List, Optional

# ══════════════════════════════════════════════════════════════════════════════
# VERSÃO DA RÉGUA (gravada em toda avaliação para permitir cortes de era)
# ══════════════════════════════════════════════════════════════════════════════

REGUA_VERSAO = "VCA-2026.07"

# ══════════════════════════════════════════════════════════════════════════════
# 1. CATEGORIAS DO VENDEDOR — pesos canônicos (somam 100)
#    Formato: chave_json: (label_exibicao, peso_maximo)
# ══════════════════════════════════════════════════════════════════════════════

_CATS_VENDEDOR: Dict[str, tuple] = {
    "rapport_conexao_0_10":                ("Rapport e Conexão", 10),
    "qualificacao_leitura_contexto_0_15":  ("Qualificação / Leitura de Contexto", 15),
    "construcao_valor_diferenciacao_0_30": ("Construção de Valor", 30),
    "persuasao_etica_0_10":                ("Persuasão Ética", 10),
    "objecoes_0_10":                       ("Tratamento de Objeções", 10),
    "conducao_fechamento_0_20":            ("Condução ao Fechamento", 20),
    "clareza_compliance_0_5":              ("Clareza e Compliance", 5),
}

# Chaves antigas (era SPIN) → novas. Usado pelos dashboards p/ retrocompat.
_CATS_LEGACY: Dict[str, str] = {
    "abertura_rapport_0_10":       "rapport_conexao_0_10",
    "spin_0_30":                   "qualificacao_leitura_contexto_0_15",
    "investigacao_spin_0_30":      "qualificacao_leitura_contexto_0_15",
    "valor_capacidade_0_20":       "construcao_valor_diferenciacao_0_30",
    "valor_produto_0_20":          "construcao_valor_diferenciacao_0_30",
    "gatilhos_0_10":               "persuasao_etica_0_10",
    "compromisso_proximos_passos_0_15": "conducao_fechamento_0_20",
    "fechamento_0_15":             "conducao_fechamento_0_20",
    "clareza_0_5":                 "clareza_compliance_0_5",
}

# ══════════════════════════════════════════════════════════════════════════════
# 2. DIMENSÕES DO LEAD — chaves canônicas (somam 100) + legacy
# ══════════════════════════════════════════════════════════════════════════════

_DIMS_LEAD: Dict[str, tuple] = {
    "fit_0_30":                 ("Fit Presencial/Live", 30),
    "intencao_0_30":            ("Intenção / Micro-momentos", 30),
    "orientacao_valor_0_20":    ("Orientação a Valor", 20),
    "abertura_0_10":            ("Abertura à Personalização", 10),
    "restricoes_invertido_0_10": ("Restrições (invertido)", 10),
}

_DIMS_LEAD_LEGACY: Dict[str, str] = {
    "intencao_micro_momentos_0_30":     "intencao_0_30",
    "abertura_personalizacao_0_10":     "abertura_0_10",
    "restricoes_barreiras_0_10_invertido": "restricoes_invertido_0_10",
}

# ══════════════════════════════════════════════════════════════════════════════
# 3. LISTAS FECHADAS — a IA escolhe EXATAMENTE um destes textos.
#    Motivo: agregação limpa nos dashboards (contagem por texto idêntico).
#    Estrutura: itens COMUNS aos dois canais + extras por canal.
# ══════════════════════════════════════════════════════════════════════════════

_FORTES_COMUM: Dict[str, List[str]] = {
    "rapport": [
        "Abertura empática e personalizada ao perfil do lead",
        "Estabeleceu conexão inicial amigável e interesse genuíno",
        "Criou conexão usando dado pessoal ou regional do lead",
        "Confirmou interesse do lead e deu sequência natural",
        "Escuta ativa com confirmações ao longo da conversa",
    ],
    "qualificacao": [
        "Leu o contexto do lead sem interrogá-lo desnecessariamente",
        "Mapeou concurso-alvo e adequou toda a conversa ao perfil",
        "Identificou rotina e disponibilidade do lead",
        "Mapeou tentativas anteriores e dificuldades vivenciadas",
        "Qualificou rápido e direcionou pra modalidade certa",
        "Reconheceu a urgência declarada e agiu de acordo",
    ],
    "valor": [
        "Ancorou valor antes de apresentar o preço",
        "Produto indicado alinhado ao perfil e concurso do lead",
        "Benefícios conectados a necessidades explícitas do lead",
        "Apresentou tradição e histórico de aprovações como diferencial",
        "Diferenciou modalidades com benefícios concretos",
        "Destacou carga horária, material e estrutura como valor",
    ],
    "persuasao": [
        "Autoridade e aprovações usadas com naturalidade",
        "Prova social com aprovações em concursos similares",
        "Urgência ética com base em prazo ou calendário real",
        "Escassez ética com vagas ou data de início da turma",
    ],
    "objecao": [
        "Antecipou objeção antes que surgisse",
        "Tratou objeção com empatia e evidência concreta",
        "Contornou restrição financeira sem desqualificar o lead",
    ],
    "fechamento": [
        "Próximo passo concreto proposto com data ou horário",
        "Resumiu necessidade + solução antes do fechamento",
        "Obteve compromisso de pagamento ou matrícula na conversa",
        "Encaminhou para visita à unidade ou aula experimental",
        "Enviou proposta ou link com prazo claro para decisão",
    ],
    "clareza": [
        "Comunicação clara, objetiva e adaptada ao lead",
        "Informações precisas sem promessas inadequadas",
    ],
}

_FORTES_EXTRA_WHATSAPP: Dict[str, List[str]] = {
    "fechamento": [
        "Enviou link de pagamento e acompanhou até a confirmação",
        "Reativou conversa parada com follow-up no timing certo",
    ],
    "clareza": [
        "Mensagens curtas e escaneáveis, sem blocos de texto",
    ],
}

_FORTES_EXTRA_LIGACAO: Dict[str, List[str]] = {
    "fechamento": [
        "Manteve o lead na linha até garantir o compromisso",
    ],
}

_MELHORIAS_COMUM: Dict[str, List[str]] = {
    "rapport": [
        "Personalizar abertura ao perfil específico do lead",
        "Reduzir falas longas e ouvir mais o lead",
    ],
    "qualificacao": [
        "Identificar concurso e perfil antes de apresentar produto",
        "Confirmar cronograma do concurso e alinhar expectativas",
        "Verificar pré-requisitos antes da proposta",
        "Mapear tentativas anteriores e dificuldades vivenciadas",
        "Tratar com prioridade o lead que declarou alta urgência",
    ],
    "valor": [
        "Ancorar valor do produto antes de apresentar o preço",
        "Conectar benefícios a necessidades explícitas do lead",
        "Reforçar diferenciais: tradição, professores, aprovações",
        "Apresentar diferencial da modalidade frente ao custo",
    ],
    "persuasao": [
        "Criar urgência ética com base em prazo real",
        "Usar prova social em momento oportuno",
        "Mencionar aprovações em concursos similares ao do lead",
    ],
    "objecao": [
        "Antecipar objeções previsíveis antes que surjam",
        "Aprofundar valor antes de ceder em desconto",
    ],
    "fechamento": [
        "Definir próximo passo concreto antes de encerrar",
        "Resumir necessidade + solução antes do fechamento",
        "Obter mini-compromisso concreto antes de encerrar",
    ],
    "clareza": [
        "Simplificar explicações e evitar jargões",
        "Confirmar valores corretos antes de processar pagamento",
    ],
}

_MELHORIAS_EXTRA_WHATSAPP: Dict[str, List[str]] = {
    "fechamento": [
        "Não deixar a conversa morrer sem follow-up agendado",
        "Enviar link de pagamento no pico de interesse do lead",
    ],
    "clareza": [
        "Quebrar blocos longos de texto em mensagens curtas",
    ],
}

_MELHORIAS_EXTRA_LIGACAO: Dict[str, List[str]] = {
    "rapport": [
        "Contextualizar o motivo da ligação logo na abertura",
    ],
}

_ERROS_CAROS_COMUM: List[str] = [
    "Apresentou preço sem ancoragem de valor",
    "Não investigou contexto suficientemente antes da oferta",
    "Encerrou a conversa sem definir próximo passo concreto",
    "Perdeu momento de fechamento sem aproveitamento",
    "Deixou objeção principal sem tratamento",
    "Não contornou objeção de preço com evidências de valor",
    "Indicou produto fora do perfil e objetivo do lead",
    "Confundiu valores ou condições de modalidades",
    "Fez promessa inadequada ou com risco de compliance",
    "Ignorou a urgência declarada pelo lead na qualificação",
    "Nenhum erro crítico identificado",
]


def _merge_listas(base: Dict[str, List[str]], extra: Dict[str, List[str]]) -> Dict[str, List[str]]:
    out = {k: list(v) for k, v in base.items()}
    for cat, itens in extra.items():
        out.setdefault(cat, [])
        out[cat].extend(itens)
    return out


def listas_fechadas(canal: str) -> Dict[str, Dict[str, List[str]]]:
    """Retorna as listas fechadas completas do canal ('whatsapp' | 'ligacao')."""
    if canal == "whatsapp":
        fortes = _merge_listas(_FORTES_COMUM, _FORTES_EXTRA_WHATSAPP)
        melhorias = _merge_listas(_MELHORIAS_COMUM, _MELHORIAS_EXTRA_WHATSAPP)
    else:
        fortes = _merge_listas(_FORTES_COMUM, _FORTES_EXTRA_LIGACAO)
        melhorias = _merge_listas(_MELHORIAS_COMUM, _MELHORIAS_EXTRA_LIGACAO)
    return {"fortes": fortes, "melhorias": melhorias, "erros": {"geral": list(_ERROS_CAROS_COMUM)}}


def _render_listas(canal: str) -> str:
    """Renderiza as listas fechadas em texto de prompt."""
    ls = listas_fechadas(canal)
    linhas = ["PONTOS FORTES — escolha 3, use EXATAMENTE um destes textos:", ""]
    for cat, itens in ls["fortes"].items():
        linhas.append(f"{cat}:")
        linhas.extend([f'  "{t}"' for t in itens])
        linhas.append("")
    linhas.append("MELHORIAS — escolha 3, use EXATAMENTE um destes textos:")
    linhas.append("")
    for cat, itens in ls["melhorias"].items():
        linhas.append(f"{cat}:")
        linhas.extend([f'  "{t}"' for t in itens])
        linhas.append("")
    linhas.append("ERRO MAIS CARO — use EXATAMENTE um destes textos:")
    linhas.extend([f'  "{t}"' for t in ls["erros"]["geral"]])
    return "\n".join(linhas)


# ══════════════════════════════════════════════════════════════════════════════
# 4. SYSTEM PROMPTS — base compartilhada + bloco específico do canal.
#    O texto base é idêntico nos dois canais (mesma régua, mesmo juiz).
# ══════════════════════════════════════════════════════════════════════════════

_SYSTEM_BASE = """Você é avaliador sênior de qualidade (QA) de vendas e coach de performance comercial de um curso preparatório para concursos com +4 décadas de história e +140 mil aprovações.

METODOLOGIA: Venda Consultiva Adaptada (B2C Educacional). NÃO use SPIN selling puro. O lead vem de tráfego pago com intenção declarada. O bom vendedor LÊ o contexto (não interroga), ANCORA VALOR (não pula pro preço) e CONDUZ AO FECHAMENTO (não deixa a conversa morrer).

CONTEXTO DO NEGÓCIO — MODALIDADES (CRÍTICO, NÃO CONFUNDA):
1. PRESENCIAL (PRIORIDADE MÁXIMA) — Ticket ~R$2.000. Aulas na unidade física.
2. LIVE (PRIORIDADE ALTA) — Ticket ~R$1.000. Aulas AO VIVO online, com interação em tempo real. NÃO é EAD. Fechar Live é BOM resultado; não penalize o vendedor por fechar Live.
3. EAD (SECUNDÁRIO) — Ticket ~R$300. Aulas GRAVADAS. "Curso online" / "aula gravada" = EAD.
Outros produtos: Passaporte (~R$3.500+, todas as modalidades + estudar até passar), Smart (acesso digital full: EAD + Live + questões).
HIERARQUIA DE VALOR: Presencial > Passaporte > Live > Smart > EAD.
REGRA: "Live" / "aula ao vivo" → LIVE. Se o lead pedir "curso online" sem especificar, assuma EAD até o contexto provar o contrário.

QUALIFICAÇÃO PRÉVIA DO BOT (quando presente no contexto adicional):
Antes da conversa humana, o lead pode ter respondido a duas perguntas no bot: P1 (urgência para começar) e P2 (prontidão de investimento), gerando um score declarado.
- USE esses dados EXCLUSIVAMENTE para avaliar o VENDEDOR: um lead que declarou alta urgência e prontidão exige tratamento prioritário, ancoragem de valor imediata e condução firme ao fechamento. Vendedor que trata lead declaradamente quente como frio deve perder pontos em Qualificação e Fechamento.
- É PROIBIDO usar a qualificação prévia para pontuar o LEAD. O score do lead reflete APENAS o comportamento observado nesta conversa. Se o comportamento contradisser o declarado, pontue pelo comportamento — a divergência será analisada fora desta avaliação.
- Se não houver qualificação prévia no contexto, trate normalmente e marque "nao_aplicavel".

COMPLIANCE:
- Aceitar pagamento com cartão de terceiros NÃO é problema. Prática comum no B2C.
- Alerte APENAS para: promessa de aprovação garantida, informação enganosa, pressão indevida, desrespeito ao cliente.

REGRAS GERAIS:
- Não invente informações. Use "Não mencionado" quando ausente.
- Justifique notas com EVIDÊNCIAS da conversa (citações de até 15 palavras; dados sensíveis como [DADO_SENSIVEL]).
- Responda APENAS em JSON válido, sem markdown.

Retorne sempre JSON válido."""

_SYSTEM_WHATSAPP = """

CANAL: WHATSAPP (conversa escrita).
PRÉ-PROCESSAMENTO: Mensagens de bots (Ariel, OctaBot, dicas) já foram REMOVIDAS. Você lê apenas interação humana. Não penalize falta de rapport inicial — o bot já fez a triagem.
Mensagens curtas e escaneáveis são qualidade neste canal; blocos longos de texto são defeito."""

_SYSTEM_LIGACAO = """

CANAL: LIGAÇÃO TELEFÔNICA (transcrição de áudio).
ENTRADA: Transcrição com rótulos "Vendedor:" e "Cliente:" (ou nomes). Os rótulos PODEM estar invertidos por falha na transcrição. Identifique o vendedor pelo contexto (quem apresenta produto/benefícios/preço). NÃO penalize por trechos com rótulos trocados.
Se o contexto indicar LIGAÇÃO ATIVA, o lead pode não saber por que ligaram: contextualização e qualificação inicial pesam mais. Se RECEPTIVA, o lead ligou com intenção: leitura rápida e condução pesam mais."""


def system_prompt(canal: str) -> str:
    """System prompt canônico do canal ('whatsapp' | 'ligacao')."""
    bloco = _SYSTEM_WHATSAPP if canal == "whatsapp" else _SYSTEM_LIGACAO
    return _SYSTEM_BASE + bloco


# ══════════════════════════════════════════════════════════════════════════════
# 5. SCHEMA JSON DE SAÍDA — unificado (mesmo esqueleto nos dois canais)
# ══════════════════════════════════════════════════════════════════════════════

_SCHEMA_MINIMO = '{"tipo":"<tipo>","motivo":"<frase curta>"}'

_SCHEMA_VENDA = """{
  "tipo": "venda",
  "motivo": "...",
  "canal": "whatsapp|ligacao",
  "regua_versao": "%(regua)s",
  "contexto_recebido": {"qualificacao_previa": false, "tipo_ligacao": "receptivo|ativo|nao_informado"},
  "qualidade_entrada": {
    "iqh_0_100": 0, "nivel": "Alta|Média|Baixa", "precisa_reparacao": false,
    "problemas_detectados": ["..."],
    "quem_e_vendedor": "...", "quem_e_lead": "...", "confianca_identificacao_papeis_0_1": 0.0
  },
  "resumo_da_conversa": ["..."],
  "extracao": {
    "concurso_area": "...", "prazo_prova": "...", "nivel_atual": "...", "tempo_estudo": "...",
    "dores_principais": ["..."], "restricoes": ["..."], "tomador_decisao": "...",
    "produtos_citados": [{
      "produto": "Presencial|Live|EAD|Passaporte|Smart",
      "foi_indicado_por_que": "...", "ancoragem_de_valor": "...",
      "respeitou_prioridade_presencial_live": "...", "evidencias": ["..."]
    }]
  },
  "avaliacao_vendedor": {
    "nota_final_0_100": 0,
    "notas_por_categoria": {
      "rapport_conexao_0_10": 0,
      "qualificacao_leitura_contexto_0_15": 0,
      "construcao_valor_diferenciacao_0_30": 0,
      "persuasao_etica_0_10": 0,
      "objecoes_0_10": 0,
      "conducao_fechamento_0_20": 0,
      "clareza_compliance_0_5": 0
    },
    "pontos_fortes": [{"categoria": "...", "ponto": "texto EXATO da lista", "evidencia": "até 15 palavras"}],
    "melhorias": [{"categoria": "...", "melhoria": "texto EXATO da lista", "como_fazer": "...", "evidencia_do_gap": "até 15 palavras"}],
    "erro_mais_caro": {"categoria": "...", "descricao": "texto EXATO da lista", "evidencia": "até 15 palavras"},
    "tratamento_lead_qualificado": {"status": "adequado|parcial|subaproveitado|nao_aplicavel", "evidencia": "..."},
    "alertas": ["..."]
  },
  "vendedor_disclaimer": "2-3 frases: causa→efeito da nota do vendedor, incluindo a nota",
  "avaliacao_lead": {
    "lead_score_0_100": 0, "classificacao": "A|B|C|D",
    "dimensoes": {
      "fit_0_30": 0, "intencao_0_30": 0, "orientacao_valor_0_20": 0,
      "abertura_0_10": 0, "restricoes_invertido_0_10": 0
    },
    "sinais_quente": [{"sinal": "...", "evidencia": "..."}],
    "sinais_frio": [{"sinal": "...", "evidencia": "..."}],
    "perguntas_que_faltaram": ["..."]
  },
  "lead_disclaimer": "2-3 frases: sinais concretos que justificam a classificação do lead",
  "recomendacao_final": {
    "melhor_proximo_passo": "...", "produto_principal": "Presencial|Live|EAD|Passaporte|Smart|Não identificado",
    "produto_alternativo": "...", "justificativa": "...",
    "risco_desalinhamento": "...", "mensagem_pronta": "msg ≤240 chars para follow-up"
  },
  "confianca_avaliacao": 0.0,
  "motivo_baixa_confianca": "preencher se < 0.70"
}""" % {"regua": REGUA_VERSAO}


# ══════════════════════════════════════════════════════════════════════════════
# 6. USER PROMPT — builders por canal (etapas idênticas; triagem por canal)
# ══════════════════════════════════════════════════════════════════════════════

_TRIAGEM_WHATSAPP = """ETAPA 0 — CLASSIFICAÇÃO:
Determine o tipo: "venda" (diálogo real sobre cursos/matrículas com resposta substantiva do lead), "suporte", "duvida_geral", "cancelamento", "sem_interacao" (lead não respondeu ou só monossilábico), "outros".
Se NÃO for "venda", retorne o JSON MÍNIMO e pare."""

_TRIAGEM_LIGACAO = """ETAPA 0 — TRIAGEM:
Confirme se houve conversa de venda real e suficiente.
NÃO AVALIAR se: <6 turnos, só um lado fala, cliente ocupado/encerra rápido, apenas URA/caixa postal, conversa administrativa sem venda.
Tipos: "venda", "ura", "dialogo_incompleto", "dados_insuficientes", "ligacao_interna", "chamada_errada", "cancelamento", "suporte", "outros".
Se NÃO for "venda", retorne o JSON MÍNIMO e pare."""

_ETAPAS_CORPO = """ETAPA 1 — IDENTIFICAR PARTICIPANTES + IQH:
Quem é vendedor, quem é lead. Se rótulos parecerem invertidos, normalize mentalmente.
IQH (0-100): Rotulagem(0-25) + Ordem(0-15) + Legibilidade(0-20) + Cobertura(0-20) + Coerência(0-20).

ETAPA 2 — EXTRAÇÃO: concurso/área, prazo, nível, tempo de estudo, dores, restrições, tomador de decisão, produtos citados (qual modalidade, por quê, ancoragem, se respeitou prioridade Presencial>Live). ATENÇÃO: Live NÃO é EAD. Se o lead pediu Live e o vendedor fechou Live, marque "respeitou_prioridade" como "Sim".

ETAPA 3 — SCORE VENDEDOR (0-100):
Categorias (somam 100):
- Rapport e conexão (0-10): Abertura natural? Confiança? Usou nome? Tom adaptado?
- Qualificação e leitura de contexto (0-15): Identificou concurso, modalidade, urgência, restrições? Se o lead já trouxe infos (na conversa OU na qualificação prévia do bot), reconheceu e usou — NÃO precisa interrogar. Lead decidido exige leitura, não interrogatório.
- Construção de valor e diferenciação (0-30): CATEGORIA MAIS IMPORTANTE. Apresentou diferenciais (tradição, aprovações, professores, método)? Ancorou valor ANTES do preço? Explicou por que vale o investimento? Conectou o produto à dor/objetivo do lead? Se pulou direto pro preço sem construir valor, penalize pesado.
- Persuasão ética (0-10): Prova social, autoridade, urgência real (não fabricada), reciprocidade.
- Tratamento de objeções (0-10): Acolheu resistência? Contornou com empatia + evidência? Ofereceu alternativas (parcelamento, outra modalidade)?
- Condução ao fechamento (0-20): CTA claro e proporcional ao estágio? Próximo passo concreto (visita, matrícula, proposta, follow-up com data)? Facilitou pagamento? Conversa morta sem compromisso = nota baixa.
- Clareza e compliance (0-5): Comunicação clara? Sem promessas irreais? Dados sensíveis protegidos?

Além das notas: 3 pontos fortes, 3 melhorias e o erro mais caro — ESCOLHIDOS DAS LISTAS FECHADAS ABAIXO, texto exato, cada um com evidência (≤15 palavras). Para cada melhoria, inclua "como_fazer" com uma mensagem/fala pronta (≤240 chars).

TRATAMENTO DO LEAD QUALIFICADO (campo "tratamento_lead_qualificado"):
- Se houver qualificação prévia no contexto: julgue se o vendedor tratou a temperatura declarada — "adequado" (agiu à altura), "parcial" (reconheceu mas não converteu em ação), "subaproveitado" (tratou lead quente como frio). Evidência obrigatória.
- Sem qualificação prévia: status "nao_aplicavel".

ETAPA 4 — SCORE LEAD (0-100, classificação A/B/C/D):
ATENÇÃO — JUIZ CEGO: pontue o lead APENAS pelo comportamento nesta conversa. IGNORE completamente a qualificação prévia do bot nesta etapa.
Dimensões: Fit Presencial/Live(0-30) + Intenção/micro-momentos(0-30) + Orientação a valor(0-20) + Abertura à personalização(0-10) + Restrições invertido(0-10).
Classes: A(80-100), B(60-79), C(40-59), D(0-39).
Liste sinais quentes/frios com evidência + perguntas que o vendedor deveria ter feito (até 5, baseadas no contexto que faltou explorar).

ETAPA 5 — RECOMENDAÇÃO: melhor próximo passo, produto principal, alternativo, justificativa, risco de desalinhamento, mensagem pronta (≤240 chars).

ETAPA 6 — DISCLAIMERS (OBRIGATÓRIO):
vendedor_disclaimer (2-3 frases): POR QUE essa nota. Causa (o que fez/deixou de fazer, com exemplo) → efeito (impacto na nota). Inclua a nota.
lead_disclaimer (2-3 frases): POR QUE essa classificação. Sinais concretos.

ETAPA 7 — CONFIANÇA: base 0.90. Descontos: <10 turnos(-0.20), ruído/transcrição confusa(-0.15), atores ambíguos(-0.15), concurso não identificado(-0.10), conversa unilateral(-0.10), produto não mencionado(-0.10). Mín 0.30, Máx 0.90.

ECO DE CONTEXTO: preencha "contexto_recebido" com o que de fato chegou no contexto adicional (qualificacao_previa true/false; tipo_ligacao quando aplicável)."""


def build_user_prompt(canal: str, conteudo: str, contexto_adicional_json: str = "") -> str:
    """
    Monta o user prompt canônico.
      canal: 'whatsapp' | 'ligacao'
      conteudo: transcrição limpa (chat) ou transcrição da ligação
      contexto_adicional_json: string JSON já serializada (ou vazio)
    """
    triagem = _TRIAGEM_WHATSAPP if canal == "whatsapp" else _TRIAGEM_LIGACAO
    rotulo = "CONVERSA (WhatsApp):" if canal == "whatsapp" else "TRANSCRIÇÃO DA LIGAÇÃO:"
    ctx = ""
    if contexto_adicional_json:
        ctx = "DADOS ADICIONAIS (contexto operacional e qualificação prévia — siga as regras de uso do system prompt):\n" + contexto_adicional_json + "\n\n"

    partes = [
        f"TAREFA ÚNICA: Classifique E avalie esta conversa de {'WhatsApp' if canal == 'whatsapp' else 'venda por telefone'} em uma única análise.",
        "",
        triagem,
        "",
        _ETAPAS_CORPO,
        "",
        _render_listas(canal),
        "",
        'SE tipo != "venda", retorne APENAS:',
        _SCHEMA_MINIMO,
        "",
        'SE tipo == "venda", retorne o JSON completo:',
        _SCHEMA_VENDA,
        "",
        ctx + rotulo,
        conteudo,
    ]
    return "\n".join(partes)


# ══════════════════════════════════════════════════════════════════════════════
# 7. QUALIFICAÇÃO PRÉVIA (P1/P2) — régua de referência e builder de contexto
# ══════════════════════════════════════════════════════════════════════════════

# Régua vigente (spec 10/07/2026 entregue ao dev). Máximos: P1=60, P2=30 → 90.
P1_MAX = 60
P2_MAX = 30
SCORE_BOT_MAX = P1_MAX + P2_MAX  # 90
SCORE_BOT_CORTE = 45

_P1_LABELS = {
    60: "Quero começar agora",
    45: "Ainda este mês",
    25: "Quando sair o edital / resposta livre",
    0:  "Só pesquisando",
}
_P2_LABELS = {
    30: "Tem como investir agora",
    20: "Consegue com planejamento",
    5:  "Hesitou / abandonou a P2",
    0:  "Não tem como investir no momento (veto)",
}


def _to_float(valor) -> Optional[float]:
    """Converte com tolerância a NaN, vazio e vírgula decimal (exports Seducar)."""
    if valor is None:
        return None
    s = str(valor).strip()
    if s == "" or s.lower() in ("nan", "none", "null"):
        return None
    try:
        import math
        f = float(s.replace(",", "."))
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _rotular(valor: Optional[float], tabela: Dict[int, str]) -> str:
    f = _to_float(valor)
    if f is None:
        return "não respondida"
    v = int(round(f))
    return tabela.get(v, f"{v} pontos")


def montar_contexto_qualificacao(
    p1_pontos: Optional[float] = None,
    p2_pontos: Optional[float] = None,
    score_total: Optional[float] = None,
    etapa_crm: Optional[str] = None,
    tipo_ligacao: Optional[str] = None,
    origem: Optional[str] = None,
    canal_octa: Optional[str] = None,
    empresa: Optional[str] = None,
) -> Dict:
    """
    Monta o dict de contexto_adicional canônico para os analyzers.
    Inclui a qualificação prévia SOMENTE se houver ao menos uma resposta.
    Os analyzers serializam este dict em JSON e injetam no user prompt.
    """
    ctx: Dict = {}
    if empresa:
        ctx["empresa"] = empresa
    if origem:
        ctx["origem"] = origem
    if canal_octa:
        ctx["canal"] = canal_octa
    if tipo_ligacao:
        ctx["tipo_ligacao"] = str(tipo_ligacao).strip().lower()
    if etapa_crm:
        ctx["etapa_crm"] = etapa_crm

    _p1 = _to_float(p1_pontos)
    _p2 = _to_float(p2_pontos)
    tem_p1 = _p1 is not None
    tem_p2 = _p2 is not None
    if tem_p1 or tem_p2:
        total = _to_float(score_total)
        if total is None:
            total = (_p1 or 0.0) + (_p2 or 0.0)
        ctx["qualificacao_previa_bot"] = {
            "instrucao": ("Dados declarados pelo lead ANTES da conversa. Use APENAS para "
                          "avaliar o tratamento dado pelo VENDEDOR. PROIBIDO usar no score do lead."),
            "p1_urgencia": _rotular(_p1, _P1_LABELS),
            "p2_investimento": _rotular(_p2, _P2_LABELS),
            "score_declarado": total,
            "score_corte_qualificado": SCORE_BOT_CORTE,
            "lead_qualificado_pelo_bot": (total is not None and total >= SCORE_BOT_CORTE),
            "respondeu_ambas": bool(tem_p1 and tem_p2),
        }
    return ctx


def normalizar_score_bot(total: Optional[float]) -> Optional[float]:
    """Score do bot (0-90) → escala 0-100, para comparação com o lead_score da IA."""
    f = _to_float(total)
    if f is None:
        return None
    return round(f / SCORE_BOT_MAX * 100.0, 1)
