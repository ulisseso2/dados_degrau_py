# Documentação Técnica — Pipeline de Avaliação de Vendas

**Versão:** 2.0
**Data:** Abril 2026
**Autor:** Velazquez + Claude (Anthropic)
**Público-alvo:** Ulisses (dev) e equipe técnica

---

## 1. Visão Geral do Sistema

Sistema de avaliação automática de qualidade de vendas por IA para dois canais: **WhatsApp** (via Octadesk) e **Telefone** (transcrições de ligações). A IA avalia o desempenho do vendedor, classifica a qualidade do lead, e gera recomendações acionáveis.

### 1.1 Fluxo Geral

```
[Octadesk / Transcrição]
        ↓
[Pré-processamento Python]  ← filtra bots, verifica avaliabilidade (0 custo)
        ↓
[Claude Sonnet 4-6]         ← 1 API call: classifica + avalia + gera disclaimers
        ↓
[MySQL]                     ← salva avaliação + scores + disclaimers
        ↓
[Streamlit Dashboards]      ← análise individual, macro, treinamento
```

### 1.2 Canais

| Canal | Fonte dos dados | Delay | Analyzer |
|-------|----------------|-------|----------|
| WhatsApp | Octadesk API → SQLite cache → Streamlit | D-3 (3 dias) | `chat_ia_analyzer.py` |
| Telefone | Transcrições no MySQL (`opportunity_transcripts`) | H-1 (1 hora) | `transcricao_analyzer.py` |

### 1.3 Provider de IA

**Claude Sonnet 4-6 (Anthropic)** para ambos os canais. Anteriormente o telefone usava GPT-5.1 (OpenAI) — foi migrado.

- Model string: `claude-sonnet-4-6`
- Pricing: $3/M input tokens, $15/M output tokens
- Batch API: 50% desconto no output
- Configurável via `.env`: `CLAUDE_MODEL=claude-sonnet-4-6`

---

## 2. Metodologia de Avaliação

### 2.1 Framework: Venda Consultiva Adaptada

**NÃO usamos SPIN Selling puro.** O framework foi adaptado para WhatsApp/Telefone B2C educacional, onde o lead vem de tráfego pago com intenção declarada.

Princípios:
- **LER o contexto** (não interrogar) — se o lead já trouxe as informações, reconhecer e usar
- **ANCORAR VALOR** (não pular pro preço) — diferenciais antes de falar custo
- **CONDUZIR AO FECHAMENTO** (não deixar morrer) — CTA claro, próximo passo concreto

### 2.2 Categorias de Avaliação do Vendedor (0-100)

| Chave JSON | Label | Peso | Descrição |
|------------|-------|------|-----------|
| `rapport_conexao_0_10` | Rapport e Conexão | 0-10 | Abertura natural, confiança, tom adaptado |
| `qualificacao_leitura_contexto_0_15` | Qualificação / Leitura | 0-15 | Identificar concurso, modalidade, urgência. NÃO interrogar se lead já trouxe |
| `construcao_valor_diferenciacao_0_30` | Construção de Valor | **0-30** | **MAIOR PESO.** Diferenciais, ancoragem antes do preço, por que vale |
| `persuasao_etica_0_10` | Persuasão Ética | 0-10 | Prova social, autoridade, urgência real |
| `objecoes_0_10` | Tratamento de Objeções | 0-10 | Acolher + contornar com evidência |
| `conducao_fechamento_0_20` | Condução ao Fechamento | **0-20** | CTA claro, próximo passo concreto, compromisso |
| `clareza_compliance_0_5` | Clareza / Compliance | 0-5 | Comunicação limpa, sem promessas irreais |

**IMPORTANTE:** Estas chaves JSON são idênticas nos dois canais (WhatsApp e Telefone). O dashboard pode usar o mesmo mapeamento.

### 2.3 Chaves JSON Legadas (retrocompatibilidade)

Avaliações anteriores à v2 usam chaves diferentes. O dashboard mapeia:

| Chave antiga | Chave nova |
|--------------|------------|
| `abertura_rapport_0_10` | `rapport_conexao_0_10` |
| `investigacao_spin_0_30` | `qualificacao_leitura_contexto_0_15` |
| `valor_capacidade_0_20` | `construcao_valor_diferenciacao_0_30` |
| `compromisso_prox_passos_0_15` | `conducao_fechamento_0_20` |
| `clareza_compliance_whatsapp_0_5` | `clareza_compliance_0_5` |
| `persuasao_etica_0_10` | `persuasao_etica_0_10` (sem mudança) |
| `objecoes_0_10` | `objecoes_0_10` (sem mudança) |

### 2.4 Avaliação do Lead (0-100)

| Chave JSON | Label | Peso |
|------------|-------|------|
| `fit_0_30` | Fit com Presencial/Live | 0-30 |
| `intencao_micro_momentos_0_30` (WhatsApp) / `intencao_0_30` (Telefone) | Intenção | 0-30 |
| `orientacao_valor_0_20` | Orientação a valor | 0-20 |
| `abertura_personalizacao_0_10` (WhatsApp) / `abertura_0_10` (Telefone) | Abertura | 0-10 |
| `restricoes_barreiras_0_10_invertido` (WhatsApp) / `restricoes_invertido_0_10` (Telefone) | Restrições (invertido) | 0-10 |

Classificação: A (80-100), B (60-79), C (40-59), D (0-39)

### 2.5 Modalidades de Estudo (Hierarquia de Prioridade)

| Modalidade | Ticket | Prioridade | Identificação no chat |
|------------|--------|------------|----------------------|
| **Presencial** | ~R$2.000 | MÁXIMA | "presencial", "na unidade" |
| **Passaporte** | ~R$3.500+ | ALTA | "passaporte", "estudar até passar" |
| **Live** | ~R$1.000 | ALTA | "live", "aula ao vivo", "ao vivo online" |
| **Smart** | variável | MÉDIA | "smart", "acesso digital" |
| **EAD** | ~R$300 | SECUNDÁRIO | "EAD", "curso online", "aula gravada", "gravado" |

**REGRA CRÍTICA:** Live ≠ EAD. "Curso online" sem qualificador = EAD. "Aula ao vivo" = Live.

**EXCEÇÃO — Vendedores EAD:** João Vitor Souza e Anderson Gomes são vendedores dedicados ao EAD. Para eles:
- EAD é prioridade (não penalizar)
- Oferecer Live é bônus (bonificar)
- Não penalizar por não tentar Presencial/Live

### 2.6 Regras de Compliance

- Cartão de terceiros para pagamento: **NÃO é problema de compliance** (prática comum B2C)
- Gerar alerta APENAS para: promessa de aprovação garantida, informação enganosa, pressão indevida, desrespeito

### 2.7 Disclaimers

Dois campos de texto livre gerados pela IA em cada avaliação:

| Campo | Propósito | Exemplo |
|-------|-----------|---------|
| `vendedor_disclaimer` | POR QUE o vendedor recebeu aquela nota (causa → efeito, 2-3 frases) | "Vendedor recebeu 68/100. Leu bem o contexto e conduziu o fechamento com agilidade, mas não ancorou valor — pulou da qualificação direto pro preço sem apresentar diferenciais. Perdeu 22 pontos em Construção de Valor." |
| `lead_disclaimer` | POR QUE o lead recebeu aquela classificação (sinais concretos, 2-3 frases) | "Lead B (72/100). Interesse claro em Live pra INSS, mas sem urgência definida e sensível a preço. Pediu boleto e comparou com concorrente." |

---

## 3. Estrutura de Arquivos

### 3.1 Pipeline WhatsApp

```
projeto/
├── _pages/
│   ├── octadesk.py                  # Página Streamlit: buscar chats, filtrar, enviar pra IA
│   ├── analise_chats.py             # Dashboard de avaliações WhatsApp
│   ├── treinamento_vendedor.py      # Gerador de treinamento 1:1 (WhatsApp + Telefone)
│   └── relatorio_macro.py           # Relatório macro do time (WhatsApp + Telefone)
├── utils/
│   ├── chat_ia_analyzer.py          # Core: filtro bot, avaliabilidade, Claude API
│   └── chat_mysql_writer.py         # Gravação no MySQL + exportação segura
├── consultas/
│   └── chat_oportunidades/
│       ├── analise_chats.sql
│       ├── avaliacoes_existentes.sql
│       └── buscar_oportunidades_match.sql  (chat_oportunidades.sql)
├── octadesk_db.py                   # Cache SQLite para chats/mensagens da Octadesk
├── data_cache/
│   └── octadesk_cache.db            # SQLite (gerado automaticamente)
└── avaliar_diario.py                # Cron job: batch API diário às 23:30
```

### 3.2 Pipeline Telefone

```
projeto/
├── _pages/
│   ├── transcricoes.py              # Página Streamlit: selecionar transcrições, avaliar
│   └── analise_transcricoes.py      # Dashboard de avaliações telefone
├── utils/
│   ├── transcricao_analyzer.py      # Core: heurística, Claude API
│   └── transcricao_mysql_writer.py  # Gravação no MySQL
└── consultas/
    └── transcricao/
        ├── transcricoes.sql
        └── transcricao_detalhe.sql
```

---

## 4. Banco de Dados MySQL

### 4.1 Tabela: `seducar.chat_ai_evaluations` (WhatsApp)

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | INT AUTO_INCREMENT | PK |
| `uuid` | VARCHAR(36) | UUID único da avaliação |
| `opportunity_id` | INT NULL | FK para `interesteds.id` (pode ser NULL) |
| `chat_id` | VARCHAR(255) | ID do chat na Octadesk (unique key) |
| `classification` | VARCHAR(50) | Tipo: `venda`, `suporte`, `inapto_regra`, `sem_interacao`, `outros`, `falha_avaliacao` |
| `classification_reason` | TEXT | Motivo da classificação |
| `ai_evaluation` | LONGTEXT | JSON completo da avaliação (bruto) |
| `transcript` | LONGTEXT | Transcrição completa do chat |
| `lead_score` | INT NULL | Score do lead (0-100) |
| `vendor_score` | INT NULL | Score do vendedor (0-100) |
| `main_product` | VARCHAR(100) | Produto principal recomendado |
| `vendedor_disclaimer` | TEXT NULL | Resumo executivo da nota do vendedor |
| `lead_disclaimer` | TEXT NULL | Resumo executivo da classificação do lead |
| `octa_agent` | VARCHAR(255) | Nome do agente na Octadesk |
| `octa_channel` | VARCHAR(50) | Canal (whatsapp, instagram, etc.) |
| `octa_status` | VARCHAR(50) | Status do chat (closed, talking, etc.) |
| `octa_tags` | TEXT | Tags separadas por vírgula |
| `octa_group` | VARCHAR(255) | Grupo de atendimento |
| `octa_origin` | VARCHAR(255) | Origem da conversa (Whats Degrau, Whats Central, etc.) |
| `octa_contact_name` | VARCHAR(255) | Nome do contato |
| `octa_contact_phone` | VARCHAR(50) | Telefone do contato |
| `octa_bot_name` | VARCHAR(255) | Nome do bot que atendeu inicialmente |
| `octa_created_at` | VARCHAR(50) | Data de criação do chat na Octadesk |
| `octa_closed_at` | VARCHAR(50) | Data de fechamento |
| `octa_survey_response` | TEXT | Resposta da pesquisa de satisfação |
| `created_at` | TIMESTAMP | Data de criação no sistema |
| `updated_at` | TIMESTAMP | Data de atualização |

**Unique Key:** `chat_id` (ON DUPLICATE KEY UPDATE)

### 4.2 Tabela: `seducar.transcription_ai_summaries` (Telefone)

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | INT AUTO_INCREMENT | PK |
| `transcription_id` | INT | FK para `opportunity_transcripts.id` (unique key) |
| `uuid` | VARCHAR(36) | UUID único |
| `ai_insight` | LONGTEXT | JSON completo da avaliação (bruto) |
| `ai_evaluation` | INT | Score do vendedor (0-100) |
| `lead_score` | INT | Score do lead (0-100) |
| `lead_classification` | VARCHAR(5) | Classe: A, B, C, D |
| `strengths` | TEXT | Pontos fortes (formato: `[categoria] texto; [categoria] texto`) |
| `improvements` | TEXT | Melhorias (mesmo formato) |
| `most_expensive_mistake` | TEXT | Erro mais caro (formato: `[categoria] descrição`) |
| `main_pain_points` | TEXT | Dores principais (separadas por `;`) |
| `restrictions` | TEXT | Restrições (separadas por `;`) |
| `contest_area` | VARCHAR(255) | Concurso/área alvo |
| `main_product` | VARCHAR(100) | Produto principal |
| `vendedor_disclaimer` | TEXT NULL | Resumo executivo da nota do vendedor |
| `lead_disclaimer` | TEXT NULL | Resumo executivo da classificação do lead |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**Unique Key:** `transcription_id`

### 4.3 Tabela: `seducar.opportunity_transcripts` (fonte de transcrições)

| Coluna relevante | Descrição |
|------------------|-----------|
| `id` | PK (referenciado como `transcription_id`) |
| `transcript` | Transcrição completa da ligação |
| `original_transcript` | JSON com metadados: `{agente, duracao, telefone, tipo}` |
| `agent` | Nome do agente |
| `duration` | Duração da ligação |
| `phone` | Telefone |
| `type` | Tipo da ligação (receptivo/ativo) |
| `date` | Data da ligação |
| `time` | Hora da ligação |
| `school_id` | 1 = Central, 2 = Degrau |
| `opportunity_id` | FK para `interesteds.id` |
| `insight_ia` | JSON da avaliação (campo legado, atualizado junto) |
| `evaluation_ia` | Score do vendedor (campo legado, atualizado junto) |

### 4.4 Tabela: `seducar.interesteds` (oportunidades/CRM)

| Coluna relevante | Descrição |
|------------------|-----------|
| `id` | PK (= opportunity_id) |
| `chat_id` | ID do chat Octadesk (join com `chat_ai_evaluations`) |
| `school_id` | 1 = Degrau (confira no seu banco), 2 = Central |
| `customer_id` | FK para `customers` |
| `owner_id` | FK para `users` (dono da oportunidade) |
| `opportunity_step_id` | Etapa no funil |
| `opportunity_modality_id` | Modalidade |
| `opportunity_origin_id` | Origem |

**ATENÇÃO sobre `school_id`:** Nos SQLs atuais, o mapeamento é:
- `transcricoes.sql`: `school_id = 1 → Degrau, ELSE → Central`
- `treinamento_vendedor.py` (SQL embutido): `school_id = 1 → Central, school_id = 2 → Degrau`

**Precisa validar qual é o correto e alinhar.** Pode ser inconsistência — verificar no banco.

---

## 5. JSON de Avaliação — Schema Completo

### 5.1 WhatsApp (`ai_evaluation` na `chat_ai_evaluations`)

```json
{
  "tipo": "venda",
  "motivo": "Diálogo sobre matrícula no curso presencial TJSP",
  "canal": "whatsapp",
  "qualidade_entrada": {
    "iqh_0_100": 85,
    "nivel": "Alta",
    "precisa_reparacao": false,
    "problemas_detectados": [],
    "quem_e_vendedor": "Cintia Margareth",
    "quem_e_lead": "Sthefani",
    "confianca_identificacao_papeis_0_1": 0.95
  },
  "resumo_da_conversa": [
    "Lead chegou interessada no concurso TJSP presencial...",
    "Vendedora apresentou valores e fechou matrícula..."
  ],
  "extracao": {
    "concurso_area": "TJSP - Escrevente",
    "prazo_prova": "Previsão 2027",
    "nivel_atual": "Não mencionado",
    "tempo_estudo": "Não mencionado",
    "dores_principais": ["Precisa de estrutura de estudo"],
    "restricoes": ["Não mencionado"],
    "tomador_decisao": "A própria lead",
    "produtos_citados": [
      {
        "produto": "Presencial",
        "foi_indicado_por_que": "Lead pediu presencial",
        "ancoragem_de_valor": "Mencionou aprovações e tradição",
        "respeitou_prioridade_presencial_live": "Sim",
        "evidencias": ["'quero o presencial de manhã'"]
      }
    ]
  },
  "avaliacao_vendedor": {
    "nota_final_0_100": 72,
    "notas_por_categoria": {
      "rapport_conexao_0_10": 8,
      "qualificacao_leitura_contexto_0_15": 12,
      "construcao_valor_diferenciacao_0_30": 18,
      "persuasao_etica_0_10": 6,
      "objecoes_0_10": 7,
      "conducao_fechamento_0_20": 16,
      "clareza_compliance_0_5": 5
    },
    "pontos_fortes": [
      {"ponto": "Leu o contexto da lead sem interrogá-la", "evidencia": "..."},
      {"ponto": "Conduziu matrícula com agilidade", "evidencia": "..."},
      {"ponto": "Comunicação clara e objetiva", "evidencia": "..."}
    ],
    "melhorias": [
      {"melhoria": "Ancorar valor antes do preço", "como_fazer": "...", "evidencia_do_gap": "..."},
      {"melhoria": "Apresentar diferenciais da estrutura", "como_fazer": "...", "evidencia_do_gap": "..."},
      {"melhoria": "Usar prova social em momento oportuno", "como_fazer": "...", "evidencia_do_gap": "..."}
    ],
    "erro_mais_caro": {"descricao": "Apresentou preço sem ancoragem de valor", "evidencia": "..."},
    "alertas": []
  },
  "vendedor_disclaimer": "Vendedora recebeu 72/100. Forte em leitura de contexto e fechamento — identificou rápido o que a lead queria e conduziu a matrícula. Mas pulou ancoragem de valor: foi direto pro preço de R$3.148 sem apresentar diferenciais. Perdeu 12 pontos em Construção de Valor.",
  "avaliacao_lead": {
    "lead_score_0_100": 85,
    "classificacao": "A",
    "dimensoes": {
      "fit_0_30": 28,
      "intencao_micro_momentos_0_30": 27,
      "orientacao_valor_0_20": 12,
      "abertura_personalizacao_0_10": 10,
      "restricoes_barreiras_0_10_invertido": 8
    },
    "sinais_quente": [
      {"sinal": "Já sabia o concurso e modalidade", "evidencia": "..."}
    ],
    "sinais_frio": [
      {"sinal": "Não verbalizou dores", "evidencia": "..."}
    ],
    "perguntas_que_faltaram": ["Você já estudou pra esse concurso antes?"]
  },
  "lead_disclaimer": "Lead A (85/100). Chegou decidida — TJSP presencial manhã — e pagou R$3.148 à vista em menos de 1h. Compra puramente transacional.",
  "recomendacao_final": {
    "melhor_proximo_passo": "Follow-up de boas-vindas em 48h",
    "produto_principal_indicado": "Presencial",
    "produto_alternativo_indicado": "Passaporte",
    "justificativa": "...",
    "risco_desalinhamento": "Baixo",
    "mensagem_pronta_para_enviar_agora": "Oi Sthefani! Tudo certo com a matrícula..."
  }
}
```

### 5.2 Telefone (`ai_insight` na `transcription_ai_summaries`)

```json
{
  "tipo": "venda",
  "motivo": "Ligação sobre curso INSS",
  "avaliacao_vendedor": {
    "nota_final_0_100": 65,
    "notas_por_categoria": {
      "rapport_conexao_0_10": 7,
      "qualificacao_leitura_contexto_0_15": 10,
      "construcao_valor_diferenciacao_0_30": 15,
      "persuasao_etica_0_10": 5,
      "objecoes_0_10": 6,
      "conducao_fechamento_0_20": 18,
      "clareza_compliance_0_5": 4
    },
    "pontos_fortes": [
      {"categoria": "fechamento", "ponto": "Próximo passo concreto proposto com data ou horário", "evidencia": "..."}
    ],
    "melhorias": [
      {"categoria": "valor", "melhoria": "Ancorar valor do produto antes de apresentar o preço", "evidencia": "..."}
    ],
    "erro_mais_caro": {"categoria": "valor", "descricao": "Apresentou preço sem ancoragem de valor", "evidencia": "..."},
    "alertas": []
  },
  "vendedor_disclaimer": "Vendedor recebeu 65/100...",
  "avaliacao_lead": {
    "lead_score_0_100": 72,
    "classificacao": "B",
    "dimensoes": {
      "fit_0_30": 22,
      "intencao_0_30": 20,
      "orientacao_valor_0_20": 14,
      "abertura_0_10": 8,
      "restricoes_invertido_0_10": 8
    },
    "sinais_quente": [{"sinal": "...", "evidencia": "..."}],
    "sinais_frio": [{"sinal": "...", "evidencia": "..."}],
    "perguntas_que_faltaram": ["..."]
  },
  "lead_disclaimer": "Lead B (72/100)...",
  "extracao": {
    "concurso_area": "INSS - Técnico do Seguro Social",
    "dores_principais": ["Precisa de horário flexível"],
    "restricoes": ["Orçamento limitado"]
  },
  "recomendacao_final": {
    "produto_principal": "Live",
    "proximo_passo": "Enviar link de matrícula por WhatsApp",
    "mensagem_pronta": "Oi [nome], conforme conversamos..."
  },
  "confianca_avaliacao": 0.85,
  "motivo_baixa_confianca": null
}
```

**DIFERENÇAS ENTRE OS SCHEMAS:**

| Campo | WhatsApp | Telefone |
|-------|----------|----------|
| Onde fica no banco | `ai_evaluation` (JSON string) | `ai_insight` (JSON string) |
| Pontos fortes | `{ponto, evidencia}` | `{categoria, ponto, evidencia}` |
| Melhorias | `{melhoria, como_fazer, evidencia_do_gap}` | `{categoria, melhoria, evidencia}` |
| Erro mais caro | `{descricao, evidencia}` | `{categoria, descricao, evidencia}` |
| Recomendação | `{produto_principal_indicado, produto_alternativo_indicado, mensagem_pronta_para_enviar_agora}` | `{produto_principal, proximo_passo, mensagem_pronta}` |
| Lead dimensões | `intencao_micro_momentos_0_30`, `abertura_personalizacao_0_10`, `restricoes_barreiras_0_10_invertido` | `intencao_0_30`, `abertura_0_10`, `restricoes_invertido_0_10` |
| Campo extra | `qualidade_entrada.iqh_0_100` | `confianca_avaliacao` |
| Perguntas faltantes | `perguntas_que_faltaram` | `perguntas_que_faltaram` |
| Perguntas (legado) | `perguntas_faltantes_spin` | N/A |

**NOTA PARA UNIFICAÇÃO FUTURA:** Idealmente os dois schemas seriam idênticos. As diferenças existem porque o telefone tem campos herdados do formato anterior (com `categoria` nos pontos fortes/melhorias para agregação no dashboard). Se for refatorar, alinhar pro formato do WhatsApp que é mais limpo.

---

## 6. Pré-processamento (WhatsApp)

### 6.1 Filtro de Bot

Função: `filtrar_mensagens_bot(transcricao)` em `chat_ia_analyzer.py`

Bots conhecidos (excluídos da avaliação):
```python
NOMES_BOT = {'ariel', 'octabot', 'dicas', 'bot', 'null', 'none', '', 'dicas octabot'}
```

Templates automáticos (excluídos):
```python
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
```

**Se novos bots ou templates forem adicionados ao Octadesk, atualizar essas listas.**

### 6.2 Verificação de Avaliabilidade

Função: `verificar_avaliabilidade(filtro, agent_name)` em `chat_ia_analyzer.py`

Critérios (todos devem passar):
1. `msgs_humanas > 0` — pelo menos 1 mensagem humana
2. `remetentes_humanos >= 2` — pelo menos 2 participantes humanos (agente + cliente)
3. `turnos_cliente > 0` — cliente respondeu
4. `turnos_agente > 0` — agente respondeu
5. `turnos_cliente >= 2 OR turnos_agente >= 2` — interação mínima
6. `chars_humanos >= 800` — conteúdo mínimo

### 6.3 Triagem Heurística (Telefone)

Função: `_heuristica_triagem(transcricao)` em `transcricao_analyzer.py`

Rejeita sem API call:
- Transcrição < 15 chars
- Caixa postal / URA sem diálogo
- Sem diálogo bilateral e < 255 chars
- Apenas 1 lado fala
- < 6 turnos totais
- Cliente ocupado/dirigindo com < 12 turnos
- Cancelamento/reembolso
- Ligação interna (ramal, sala de reunião, etc.)

---

## 7. Configuração e Performance

### 7.1 Variáveis de Ambiente (.env)

```bash
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-sonnet-4-6

# Performance
CLAUDE_MAX_WORKERS=1          # Workers paralelos (1 pra tier 2, 3+ pra tier 3+)
CLAUDE_MAX_TOKENS=4096        # Max tokens de resposta
CLAUDE_MAX_INPUT_CHARS=25000  # Max chars de transcrição
CLAUDE_THROTTLE_SECONDS=8     # Intervalo mínimo entre requests (ajustar por tier)
CLAUDE_TEMPERATURE=0.2

# MySQL
MYSQL_HOST=...
MYSQL_USER=...
MYSQL_PASSWORD=...
MYSQL_DATABASE=seducar

# Octadesk
OCTADESK_API_TOKEN=...
OCTADESK_BASE_URL=...
```

### 7.2 Tiers da Anthropic (rate limits)

| Tier | Depósito | Output tokens/min (Sonnet) | Workers recomendados | Throttle |
|------|----------|---------------------------|---------------------|----------|
| Tier 1 | $5 | ~8.000 | 1 | 8s |
| Tier 2 | $40 | ~16.000 | 1-2 | 5s |
| **Tier 3** | **$200** | **~32.000** | **3** | **3s** |
| Tier 4 | $400 | ~64.000 | 5-8 | 1s |

### 7.3 Custo Estimado por Avaliação

Sonnet 4-6: ~3k input + ~3k output tokens por avaliação.
- Tempo real: ~$0.054 por avaliação
- Batch API: ~$0.032 por avaliação (50% off output)

### 7.4 Batch API (Cron Job)

Arquivo: `avaliar_diario.py`
Cron: `30 23 * * * cd /caminho/projeto && python avaliar_diario.py`

Fluxo:
1. 23:30 — busca pendentes de WhatsApp e telefone
2. Filtra bots/heurísticas localmente (0 custo)
3. Envia aptos pro Batch API (50% desconto)
4. Poll a cada 30s até conclusão
5. Salva resultados no MySQL
6. Logs em `logs/avaliar_diario_YYYYMMDD.log`

---

## 8. Páginas Streamlit

### 8.1 `octadesk.py` — Operação WhatsApp

**Função:** Buscar chats da Octadesk, filtrar, enviar pra avaliação.
**Depende de:** `chat_ia_analyzer.py`, `chat_mysql_writer.py`, `octadesk_db.py`, SQLs de chat.
**Cache:** SQLite em `data_cache/octadesk_cache.db`.

### 8.2 `analise_chats.py` — Dashboard WhatsApp

**Função:** Visualizar avaliações, ranking, radar de competências, detalhes por chat.
**SQL:** `analise_chats.sql`
**Categorias:** `_CATS_VENDEDOR` (7 categorias + legacy mapping)

### 8.3 `transcricoes.py` — Operação Telefone

**Função:** Selecionar transcrições, enviar pra avaliação.
**Depende de:** `transcricao_analyzer.py`, `transcricao_mysql_writer.py`
**SQL:** `transcricoes.sql`, `transcricao_detalhe.sql`

### 8.4 `analise_transcricoes.py` — Dashboard Telefone

**Função:** Mesma estrutura do analise_chats.py mas pra telefone.
**SQL:** `transcricoes.sql`
**Categorias:** `_CAT_LABELS` (com legacy mapping pra `investigacao_spin`, `valor_produto`, `gatilho_mental`)

### 8.5 `treinamento_vendedor.py` — Treinamento 1:1

**Função:** Gera plano de treinamento personalizado por vendedor com PPTX.
**Dados:** Agrega WhatsApp + Telefone.
**Filtros:** Empresa, canal (multi-select), período, vendedor.
**Dependência extra:** `pip install python-pptx`

### 8.6 `relatorio_macro.py` — Relatório Macro do Time

**Função:** Visão estratégica: gaps coletivos, comparativo por canal, plano de ação 30 dias.
**Dados:** Agrega WhatsApp + Telefone.
**Filtros:** Empresa, canal (multi-select), período.

---

## 9. SQLs de Consulta

### 9.1 `analise_chats.sql`

Retorna avaliações de WhatsApp com JOINs para CRM. Campos chave: `evaluation_ia` (vendor_score), `lead_score`, `ai_evaluation` (JSON), `vendedor_disclaimer`, `lead_disclaimer`, `agente`, `empresa`.

### 9.2 `transcricoes.sql`

Retorna transcrições com JOINs para CRM e summaries. Campos chave: `evaluation_ia`, `lead_score`, `lead_classification`, `strengths`, `improvements`, `insight_ia` (JSON), `vendedor_disclaimer`, `lead_disclaimer`, `agente`, `empresa`.

### 9.3 `avaliacoes_existentes.sql`

Lista chat_ids já avaliados. Usado pelo `octadesk.py` pra marcar chats processados. Sem disclaimers (não precisa).

### 9.4 `chat_oportunidades.sql`

JOINs oportunidades do CRM com avaliações de WhatsApp. Inclui `vendor_score`, `vendedor_disclaimer`, `lead_disclaimer`.

### 9.5 `transcricao_detalhe.sql`

Detalhe de transcrições específicas (por ID). Inclui `vendedor_disclaimer`, `lead_disclaimer`.

---

## 10. Migrações SQL Necessárias

Rodar antes de qualquer deploy:

```sql
-- WhatsApp (se não existirem)
ALTER TABLE seducar.chat_ai_evaluations ADD COLUMN vendedor_disclaimer TEXT NULL;
ALTER TABLE seducar.chat_ai_evaluations ADD COLUMN lead_disclaimer TEXT NULL;

-- Telefone (se não existirem)
ALTER TABLE seducar.transcription_ai_summaries ADD COLUMN vendedor_disclaimer TEXT NULL;
ALTER TABLE seducar.transcription_ai_summaries ADD COLUMN lead_disclaimer TEXT NULL;
```

O `chat_mysql_writer.py` tem migração automática que tenta rodar esses ALTERs na primeira execução, mas é mais seguro rodar manualmente.

---

## 11. Pontos de Atenção para Desenvolvimento

### 11.1 Inconsistência de `school_id`

Verificar no banco: `school_id = 1` é Degrau ou Central? Os SQLs têm mapeamentos diferentes. Alinhar.

### 11.2 Diferenças de Schema entre Canais

Os JSONs de WhatsApp e Telefone têm campos ligeiramente diferentes (ver seção 5). Se for criar dashboards unificados, precisa de normalização.

### 11.3 Novos Bots no Octadesk

Se novos bots forem adicionados (nome diferente de Ariel/OctaBot/dicas), atualizar `NOMES_BOT` em `chat_ia_analyzer.py`.

### 11.4 Novos Vendedores EAD

Se outros vendedores além de João Vitor Souza e Anderson Gomes forem dedicados ao EAD, atualizar o bloco "EXCEÇÃO — VENDEDORES ESPECIALIZADOS EM EAD" no `_SYSTEM_PROMPT` de `chat_ia_analyzer.py`.

### 11.5 Cache do Octadesk

O SQLite em `data_cache/octadesk_cache.db` cresce com o tempo. A API do Octadesk retém ~30 dias. O cache preserva histórico além disso. Considerar política de retenção se necessário.

### 11.6 Prompt Caching da Anthropic

O system prompt usa `cache_control: {"type": "ephemeral"}`. Isso permite que a API reutilize o system prompt entre chamadas consecutivas, economizando ~90% dos tokens de input do system prompt. Funciona melhor com processamento em lote.
