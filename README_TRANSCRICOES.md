# 📞 Sistema de Transcrições de Ligações — Documentação Completa

> **Última atualização:** Fevereiro 2026
> **Status atual:** ✅ Sistema em produção — GPT-5.1 (avaliação) + GPT-5-nano (classificação)

---

## 📋 Visão Geral

O sistema de transcrições é composto por **duas páginas Streamlit** principais que consomem dados do banco MySQL (`seducar`) e utilizam a API da OpenAI para classificação e avaliação automática de ligações de vendas:

| Página | Arquivo | Função |
|---|---|---|
| 📞 Transcrições | `_pages/transcricoes.py` | Seleção, avaliação em lote e revisão individual |
| 📊 Análise de Desempenho | `_pages/analise_transcricoes.py` | Dashboards, ranking, SPIN, relatório individual |

---

## 🗂️ Arquitetura de Arquivos

```
dados_degrau_py/
├── _pages/
│   ├── transcricoes.py              ← Página 1: Avaliar / Ver avaliações / Exportar
│   └── analise_transcricoes.py      ← Página 2: Dashboards analíticos completos
├── utils/
│   ├── transcricao_analyzer.py      ← Engine IA: classificação + avaliação SPIN
│   ├── transcricao_mysql_writer.py  ← Gravação no MySQL (upsert duplo)
│   └── sql_loader.py                ← Utilitário genérico de carga SQL
├── consultas/transcricoes/
│   ├── transcricoes.sql             ← Query principal (lista completa)
│   ├── transcricao_detalhe.sql      ← Query detalhe individual por ID
│   └── contexto.txt                 ← Prompt-contexto SPIN para GPT-5.1
├── conexao/
│   └── mysql_connector.py           ← Conexão MySQL (leitura + escrita)
└── .env / .streamlit/secrets.toml   ← Variáveis de ambiente e secrets
```

---

## 🔌 Banco de Dados MySQL

### Banco: `seducar`

#### Tabelas envolvidas

| Tabela | Papel |
|---|---|
| `opportunity_transcripts` (ot) | Tabela principal com transcrições |
| `transcription_ai_summaries` (tais) | Resultados da avaliação IA |
| `interesteds` (i) | Lead / oportunidade |
| `customers` (c) | Dados do cliente (nome, telefone) |
| `opportunity_steps` (os) | Etapa do funil de vendas |
| `opportunity_modalities` (om) | Modalidade (Presencial/Live/Online) |
| `opportunity_origins` (oo) | Origem do lead |

#### Colunas relevantes em `opportunity_transcripts`

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | INT | PK — `transcricao_id` no sistema |
| `date` | DATE | Data da ligação |
| `time` | TIME | Hora da ligação |
| `transcript` | LONGTEXT | Transcrição completa (texto bruto) |
| `original_transcript` | JSON | JSON com `$.agente`, `$.duracao`, `$.tipo`, `$.telefone` |
| `school_id` | INT | 1 = Degrau, 2+ = Central |
| `insight_ia` | TEXT | JSON completo da avaliação IA |
| `evaluation_ia` | INT | Nota 0–100 do vendedor |
| `agent` | VARCHAR | Nome do agente (pode ser NULL → usa JSON fallback) |
| `duration` | INT | Duração em segundos (pode ser NULL → usa JSON fallback) |
| `type` | VARCHAR | Tipo da ligação (pode ser NULL → usa JSON fallback) |
| `phone` | VARCHAR | Telefone |

#### Colunas relevantes em `transcription_ai_summaries`

| Coluna | Tipo | Descrição |
|---|---|---|
| `transcription_id` | INT | FK → `opportunity_transcripts.id` |
| `ai_insight` | LONGTEXT | JSON completo da avaliação (armazena tudo) |
| `ai_evaluation` | INT | Nota 0–100 do vendedor |
| `lead_score` | INT | Score do lead 0–100 |
| `lead_classification` | CHAR(1) | A/B/C/D |
| `strengths` | TEXT | Pontos fortes separados por `;` com prefixo `[categoria]` |
| `improvements` | TEXT | Melhorias separadas por `;` com prefixo `[categoria]` |
| `most_expensive_mistake` | TEXT | Erro mais caro em `[categoria] descrição` |
| `main_pain_points` | TEXT | Dores principais separadas por `;` |
| `restrictions` | TEXT | Restrições do lead |
| `contest_area` | VARCHAR | Área/concurso de interesse |
| `main_product` | VARCHAR | Produto principal recomendado |

---

## 📄 Queries SQL

### `consultas/transcricoes/transcricoes.sql` — Query principal

```sql
SELECT
    ot.id                   AS transcricao_id,
    ot.created_at           AS data_trancricao,
    ot.date                 AS data_ligacao,
    ot.time                 AS hora_ligacao,
    ot.opportunity_id       AS oportunidade,
    ot.transcript           AS transcricao,
    CASE WHEN ot.school_id = 1 THEN 'Degrau' ELSE 'Central' END AS empresa,
    c.full_name             AS nome_lead,
    c.cellphone             AS telefone_lead,
    os.name                 AS etapa,
    om.name                 AS modalidade,
    oo.name                 AS origem,
    tais.ai_evaluation      AS evaluation_ia,
    tais.lead_score         AS lead_score,
    tais.lead_classification AS lead_classification,
    tais.strengths          AS strengths,
    tais.improvements       AS improvements,
    tais.most_expensive_mistake AS most_expensive_mistake,
    tais.contest_area       AS concurso_area,
    tais.main_product       AS produto_recomendado,
    tais.main_pain_points   AS principais_dores,
    tais.ai_insight         AS insight_ia,
    JSON_UNQUOTE(JSON_EXTRACT(tais.ai_insight, '$.classificacao_ligacao'))  AS tipo_classificacao_ia,
    CAST(JSON_EXTRACT(tais.ai_insight, '$.confianca_classificacao') AS DECIMAL(4,2)) AS confianca_classificacao,
    -- COALESCE: lê coluna direta primeiro, fallback para JSON original se NULL
    COALESCE(ot.agent,    JSON_UNQUOTE(JSON_EXTRACT(ot.original_transcript, '$.agente')))   AS agente,
    COALESCE(ot.duration, JSON_UNQUOTE(JSON_EXTRACT(ot.original_transcript, '$.duracao'))) AS duracao,
    COALESCE(ot.type,     JSON_UNQUOTE(JSON_EXTRACT(ot.original_transcript, '$.tipo')))    AS tipo_ligacao,
    CASE
        WHEN ot.transcript IS NULL OR CHAR_LENGTH(ot.transcript) < 500 THEN 0
        ELSE 1
    END AS avaliavel
FROM seducar.opportunity_transcripts ot
LEFT JOIN seducar.interesteds i            ON ot.opportunity_id = i.id
LEFT JOIN seducar.customers c              ON i.customer_id = c.id
LEFT JOIN seducar.opportunity_steps os     ON i.opportunity_step_id = os.id
LEFT JOIN seducar.opportunity_modalities om ON i.opportunity_modality_id = om.id
LEFT JOIN seducar.opportunity_origins oo   ON i.opportunity_origin_id = oo.id
LEFT JOIN seducar.transcription_ai_summaries tais ON ot.id = tais.transcription_id
```

**Notas importantes:**
- `avaliavel = 1` quando `CHAR_LENGTH(transcript) >= 500`
- COALESCE em `agent/duration/type`: registros legados têm NULL nas colunas diretas — o `JSON_EXTRACT` de `original_transcript` garante o fallback
- `confianca_classificacao` é NULL em registros antigos (apenas novos têm o campo no JSON)

### `consultas/transcricoes/transcricao_detalhe.sql` — Detalhe individual

Carregado sob demanda (cache 1h) ao selecionar uma ligação específica:

```sql
SELECT
    ot.id                   AS transcricao_id,
    ot.transcript           AS transcricao,
    JSON_UNQUOTE(JSON_EXTRACT(ot.original_transcript, '$.agente'))   AS agente,
    JSON_UNQUOTE(JSON_EXTRACT(ot.original_transcript, '$.duracao'))  AS duracao,
    JSON_UNQUOTE(JSON_EXTRACT(ot.original_transcript, '$.telefone')) AS telefone,
    JSON_UNQUOTE(JSON_EXTRACT(ot.original_transcript, '$.tipo'))     AS tipo,
    tais.ai_insight AS insight_ia
FROM seducar.opportunity_transcripts ot
LEFT JOIN seducar.transcription_ai_summaries tais ON ot.id = tais.transcription_id
WHERE ot.id IN ({ids})
```

---

## ⚙️ Configuração de Ambiente

### `.env` (desenvolvimento local)

```env
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-5.1
OPENAI_MODEL_CLASSIFICACAO=gpt-5-nano
OPENAI_TEMPERATURE=0.2
OPENAI_MAX_TOKENS=8000
OPENAI_MAX_INPUT_CHARS=25000
OPENAI_MAX_INPUT_CHARS_CLASSIFICACAO=4000
```

### `.streamlit/secrets.toml` (produção Streamlit Cloud)

```toml
OPENAI_API_KEY = "sk-proj-..."
openai_model = "gpt-5.1"
openai_model_classificacao = "gpt-5-nano"
openai_temperature = "0.2"
openai_max_tokens = "8000"
openai_max_input_chars = "25000"
openai_max_input_chars_classificacao = "4000"
```

---

## 🤖 Engine de IA — `utils/transcricao_analyzer.py`

### Classes disponíveis

#### `TranscricaoAnalyzer` (legado — não usado em produção)
Classe original com análise quantitativa. Lê `json_completo`. Não é instanciada pelas páginas de produção.

#### `TranscricaoOpenAIAnalyzer` ✅ (classe em produção)

Fluxo de 2 etapas sequenciais:
```
1. classificar_ligacao()  → GPT-5-nano  (triagem rápida)
       ↓ deve_avaliar = True?
2. analisar_transcricao() → GPT-5.1    (avaliação SPIN completa)
```

**Parâmetros configuráveis:**

| Parâmetro | Valor padrão | Descrição |
|---|---|---|
| `model` | `gpt-5.1` | Modelo avaliação SPIN |
| `model_classificacao` | `gpt-5-nano` | Modelo classificação |
| `temperature` | `0.2` | Temperatura (somente avaliação) |
| `max_tokens` | `8000` | Tokens saída avaliação (`max_completion_tokens`) |
| `max_input_chars` | `25000` | Máx. chars transcrição para avaliação |
| `max_input_chars_classificacao` | `4000` | Máx. chars para classificação |

**Restrições dos modelos GPT-5:**

| Parâmetro | GPT-5.1 | GPT-5-nano |
|---|---|---|
| `temperature` | ✅ Suportado | ❌ NÃO suportado |
| `max_completion_tokens` | ✅ | ✅ |
| `max_tokens` (legado) | ❌ | ❌ |
| `response_format` | ❌ | ❌ |

---

### Classificação de Ligações (`classificar_ligacao`)

#### Etapa 1 — Heurística (zero tokens)

```python
def _classificar_por_heuristica(transcricao):
    # len < 15 chars           → dados_insuficientes (confianca=0.95)
    # padrões de caixa postal  → ura (confianca=0.9)
    # indisponível + sem venda → dialogo_incompleto (confianca=0.8)
    # len < 80 chars           → dialogo_incompleto (confianca=0.7)
    # else                     → None (passa para GPT-5-nano)
```

**Padrões URA detectados:**
`"caixa postal"`, `"grave seu recado"`, `"deixe a sua mensagem"`, `"não receber recados"`, `"mensagem na caixa postal"`

**Marcadores de venda** (evitam falso-positivo em `dialogo_incompleto`):
`proposta, matrícula, desconto, parcela, valor, orçamento, boleto, cartão, pagar, curso, convite de matrícula`

#### Etapa 2 — GPT-5-nano com retry (2 tentativas)

```python
for tentativa in range(2):
    response = client.chat.completions.create(
        model=self.model_classificacao,
        messages=[system_msg, user_msg],
        max_completion_tokens=300
        # SEM temperature, SEM response_format
    )
    content = response.choices[0].message.content.strip()
    if not content:
        if tentativa == 0: continue          # tenta de novo
        return {"tipo": "venda", "confianca": 0.5, "deve_avaliar": True}
    resultado = json.loads(content)
    ...
except json.JSONDecodeError:
    if tentativa == 0: continue              # tenta de novo
    return {"tipo": "venda", "confianca": 0.5, "deve_avaliar": True}
```

**JSON esperado do modelo:**
```json
{
  "tipo": "venda",
  "motivo": "Conversa comercial com proposta de matrícula",
  "confianca": 0.92,
  "deve_avaliar": true
}
```

**Validação pós-classificação:**
- Se `tipo == "ura"` mas há diálogo `Vendedor:` + `Cliente:` e texto >= 255 chars → corrige para `"venda"` ou `"outros"`

#### Categorias e comportamento

| Tipo | Descrição | TIPOS_SKIP? | Avalia? |
|---|---|---|---|
| `venda` | Ligação comercial com contexto | ❌ | ✅ Sempre |
| `outros` | Não se encaixa em nenhum | ❌ | ✅ Sempre |
| `ura` | Apenas URA/música/caixa postal | ✅ | ❌ |
| `dialogo_incompleto` | Conversa muito curta | ✅ | ❌ |
| `dados_insuficientes` | Diálogo sem contexto mínimo | ✅ | ❌ |
| `ligacao_interna` | Entre colaboradores | ✅ | ❌ |
| `chamada_errada` | Engano/número errado | ✅ | ❌ |
| `cancelamento` | Cancelar/estornar/reembolsar | ✅ | ❌ |
| `suporte` | Suporte pós-venda cliente ativo | ✅ | ❌ |

`TIPOS_SKIP = {'ura', 'dados_insuficientes', 'dialogo_incompleto', 'ligacao_interna', 'chamada_errada', 'cancelamento', 'suporte'}`

---

### Avaliação SPIN (`analisar_transcricao`)

1. Chama `classificar_ligacao()` → obtém `tipo`, `confianca`, `deve_avaliar`
2. Se `tipo in TIPOS_SKIP` → retorna `retorno_minimo` (nota=0, lead=D, sem chamar GPT-5.1)
3. Monta prompt: `contexto.txt` + transcrição (até `max_input_chars` chars)
4. Chama GPT-5.1 com `temperature=0.2`, `max_completion_tokens=8000`
5. Parse do JSON + injeção de `classificacao_ligacao`, `motivo_classificacao`, `confianca_classificacao`
6. Soma tokens (classificação + avaliação)

**Retorno de `analisar_transcricao`:**
```python
{
    'avaliacao_completa': '{ ... }',       # JSON string armazenado em ai_insight
    'tokens_usados': 1250,
    'nota_vendedor': 72,                   # avaliacao_vendedor.nota_final_0_100
    'lead_score': 65,                      # avaliacao_lead.lead_score_0_100
    'lead_classificacao': 'B',             # avaliacao_lead.classificacao
    'concurso_area': 'ENEM',               # extracao.concurso_area
    'produto_recomendado': 'Live',         # recomendacao_final.produto_principal.produto
    'classificacao_ligacao': 'venda',
    'motivo_classificacao': '...',
    'confianca_classificacao': 0.87,
}
```

**Estrutura JSON em `avaliacao_completa` / `ai_insight`:**
```json
{
  "avaliacao_vendedor": {
    "nota_final_0_100": 72,
    "pontos_fortes": [
      { "categoria": "rapport", "ponto": "Boa abertura e empatia inicial" }
    ],
    "melhorias": [
      { "categoria": "investigacao_spin", "melhoria": "Faltou explorar dores implícitas" }
    ],
    "erro_mais_caro": {
      "categoria": "fechamento",
      "descricao": "Não propôs próximo passo concreto com data"
    }
  },
  "avaliacao_lead": {
    "lead_score_0_100": 65,
    "classificacao": "B"
  },
  "extracao": {
    "concurso_area": "ENEM",
    "dores_principais": ["Dificuldade de organização", "Falta tempo para estudar"],
    "restricoes": ["Preço alto"]
  },
  "recomendacao_final": {
    "produto_principal": { "produto": "Live" },
    "justificativa": "Flexibilidade de horário para o perfil do lead"
  },
  "classificacao_ligacao": "venda",
  "motivo_classificacao": "Conversa comercial completa com proposta",
  "confianca_classificacao": 0.87
}
```

---

## 💾 Gravação — `utils/transcricao_mysql_writer.py`

### `atualizar_avaliacao_transcricao()`

Executa **upsert duplo** em uma única transação:

**1. Upsert em `transcription_ai_summaries`:**
```sql
INSERT INTO seducar.transcription_ai_summaries (
    transcription_id, uuid, created_at, updated_at,
    ai_insight, ai_evaluation, lead_score, lead_classification,
    strengths, improvements, most_expensive_mistake,
    main_pain_points, restrictions, contest_area, main_product
) VALUES (...)
ON DUPLICATE KEY UPDATE
    ai_insight = VALUES(ai_insight),
    ai_evaluation = VALUES(ai_evaluation),
    ...
    updated_at = CURRENT_TIMESTAMP
```

**2. Update em `opportunity_transcripts`:**
```sql
UPDATE seducar.opportunity_transcripts
SET
    insight_ia    = :ai_insight,
    evaluation_ia = :ai_evaluation,
    agent         = COALESCE(:agent, agent),
    duration      = COALESCE(:duration, duration),
    phone         = COALESCE(:phone, phone),
    type          = COALESCE(:type_, type)
WHERE id = :transcricao_id
```

**Sanitização NaN/Inf (numpy/pandas):**
```python
import math
def _sanitize(v):
    if v is None: return None
    try:
        if math.isnan(float(v)) or math.isinf(float(v)): return None
    except (TypeError, ValueError): pass
    return v

duration = _sanitize(duration)
evaluation_ia = _sanitize(evaluation_ia)
```

**Campos extraídos do JSON (`_extrair_campos`):**

| Campo MySQL | Origem no JSON |
|---|---|
| `strengths` | `avaliacao_vendedor.pontos_fortes` → `"[categoria] ponto; ..."` |
| `improvements` | `avaliacao_vendedor.melhorias` → `"[categoria] melhoria; ..."` |
| `most_expensive_mistake` | `avaliacao_vendedor.erro_mais_caro` → `"[categoria] descrição"` |
| `lead_score` | `avaliacao_lead.lead_score_0_100` |
| `lead_classification` | `avaliacao_lead.classificacao` |
| `main_pain_points` | `extracao.dores_principais` → lista em `;` |
| `restrictions` | `extracao.restricoes` → lista em `;` |
| `contest_area` | `extracao.concurso_area` |
| `main_product` | `recomendacao_final.produto_principal.produto` |

---

## 🖥️ Página 1: `_pages/transcricoes.py`

### Cache de dados
```python
@st.cache_data(ttl=21600)  # 6h — lista completa
def carregar_transcricoes_base() -> pd.DataFrame

@st.cache_data(ttl=3600)   # 1h — detalhe de uma ligação específica
def carregar_detalhe_transcricao(transcricao_id: int) -> dict
```

### Sidebar (Filtros)
- **Empresa**: radio (Degrau / Central) — padrão: primeiro com "Degrau"
- **Período**: date_input [hoje-7d, hoje]
- Ambos com `on_change=_limpar_selecao` (limpa seleção ao mudar)

### Métricas Globais (4 cards)
```
Total de ligações | Avaliáveis | Avaliadas | Pendentes
```

### Gráfico de Barras Rápido
- Ligações por dia no período selecionado (px.bar, altura=200px)

### Abas

#### Tab 1 — 🤖 Avaliar

**Filtros adicionais:**
- Radio: `Avaliáveis / Todas`
- Radio: `Pendentes / Avaliadas / Todas`
- Paginação: selectbox 20/50/100 por página + number_input de página

**Ações rápidas na tabela:**
- `☑️ Selecionar pendentes desta página` — IDs sem avaliação
- `🔁 Selecionar avaliadas desta página` — IDs já avaliados (para reavaliar)
- `🤖 Avaliar N selecionada(s)` (aparece quando n_sel > 0, type=primary)

**Tabela compacta (`st.dataframe`):**

| ID | Data | Lead | Agente | Etapa | Status | Avaliável | Transcrição |
|---|---|---|---|---|---|---|---|
| int | dd/MM/yyyy HH:mm | str | str | str | ✅/⏳ | 🟢/🔴 | TextColumn |

**Detalhe sob demanda (selectbox por ID):**
- Linha 1: Lead, Telefone, Etapa, Modalidade, Origem
- Linha 2: Status (✅/⏳) + checkbox `[Incluir / 🔁 Reavaliar]`
- Linha 3 (após carregar detalhe): Agente | Duração | Tipo
- `📝 Transcrição` em expander com `st.container(height=250)` + `_renderizar_transcricao()`

**Barra de ação final:** contador + `🗑️ Limpar seleção` + `🤖 Avaliar N`

#### Tab 2 — ✅ Avaliações

**Filtros:**
- Slider: Nota mínima 0–100
- Multiselect: Classificação do lead
- Multiselect: Agente
- Multiselect: Tipo de ligação

**Métricas (3 cards):**
```
Total avaliações | Nota média vendedor | Lead score médio
```

**Tabela resumo:**

| ID | Data | Lead | Agente | Score Lead | Classificação | Etapa | Nota | Transcrição |
|---|---|---|---|---|---|---|---|---|

**Detalhe sob demanda:**
- Linha: Lead | Nota emoji | Score Lead | Classificação
- Caption: Agente | Duração | Tipo
- `📝 Transcrição` (expander)
- `✅ Pontos fortes` (expander, lista de itens)
- `🛠️ Pontos de melhoria` (expander)
- `💸 Erro mais caro` (st.info)
- `🔁 Reavaliar esta ligação` (botão individual)

**Gráficos (st.expander, fechado por padrão):**
- Pie: Classificação do Lead
- Bar: Nota média por Etapa

**Top pontos (st.expander, fechado):**
- 3 colunas: Top Pontos Fortes | Top Melhorias | Top Erros Caros (com contagem entre parênteses)

#### Tab 3 — 📤 Exportar
- `⬇️ Baixar CSV das avaliações` — `avaliações_YYYYMMDD_HHmmss.csv`

### Execução em Lote (`_executar_avaliacoes`)

```python
def _executar_avaliacoes(df_base, ids_selecionados):
    ia = TranscricaoOpenAIAnalyzer()
    bar = st.progress(0)
    for i, tid in enumerate(ids_selecionados):
        row_data = df_base[df_base['transcricao_id'] == tid].iloc[0]
        tx = str(row_data.get('transcricao', '') or '')
        if len(tx.strip()) < 500:
            st.warning(f"Transcrição insuficiente: {nome}")
            continue

        analise = ia.analisar_transcricao(tx)
        if 'erro' not in analise:
            atualizar_avaliacao_transcricao(
                transcricao_id=tid,
                insight_ia=analise.get('avaliacao_completa'),
                evaluation_ia=analise.get('nota_vendedor'),
                agent=row_data.get('agente'),           # SEMPRE do banco
                duration=row_data.get('duracao'),        # SEMPRE do banco
                phone=row_data.get('telefone_lead'),
                type_=row_data.get('tipo_ligacao'),      # SEMPRE do banco, não da IA
            )
        bar.progress((i + 1) / total)
    st.cache_data.clear()   # invalida cache de AMBAS as páginas
    st.rerun()
```

### Helpers da Página

```python
def _formatar_duracao(segundos) -> str:
    # None/float → "--:--" | inteiro → "HH:MM:SS" ou "MM:SS"

def _cor_nota(nota) -> str:
    # >= 75 → "🟢" | >= 50 → "🟡" | < 50 → "🔴"

def _renderizar_transcricao(transcricao: str):
    # Regex: detecta "URA:", "Vendedor:", "Cliente:" (case-insensitive)
    # Formata: URA em negrito | Vendedor com 🎙️ | Cliente com 👤

def _limpar_selecao():
    # Zera session_state.transcricoes_selecionadas e remove todas as keys "sel_*"
```

---

## 🖥️ Página 2: `_pages/analise_transcricoes.py`

### Cache de dados

```python
@st.cache_data(ttl=21600)  # mesma query transcricoes.sql
def _carregar_dados() -> pd.DataFrame:
    # evaluation_ia: 0 → NaN (0 = não avaliado, não é nota)
    # duracao_min = duracao_seg / 60
    # lead_classification: fillna('—')
```

### Constantes

```python
_CAT_LABELS = {
    'rapport':           '🤝 Rapport',
    'investigacao_spin': '🔍 Investigação SPIN',
    'valor_produto':     '💎 Valor do Produto',
    'gatilho_mental':    '⚡ Gatilho Mental',
    'objecao':           '🛡️ Objeção',
    'fechamento':        '🤝 Fechamento',
    'clareza':           '🗣️ Clareza',
    'outros':            '❓ Outros',
}

_CORES_CLASS = {
    'A': '#00CC96', 'B': '#636EFA',
    'C': '#FFA15A', 'D': '#EF553B', '—': '#AAAAAA',
}
```

### Sidebar
- **Empresa**: radio
- **Período**: date_input [hoje-30d, hoje]
- **Agente**: multiselect (dinâmico)
- **Tipo de ligação**: multiselect — inclui sempre registros com `tipo_ligacao IS NULL`

### KPIs Globais
```
Total de ligações | Avaliáveis | Avaliadas
```

### Aba 1 — 📈 Visão Geral

| Gráfico | Tipo | Detalhes |
|---|---|---|
| Evolução Diária | Stacked Bar + Line (Y2) | Barras: Avaliadas/Não-avaliadas; Linha: Nota média diária |
| Classificação dos Leads | Pie Donut (hole=0.45) | Cores _CORES_CLASS, `textinfo='percent+label'` |
| Duração Média por Tipo | Bar vertical | Label: `n={qtd} \| ⭐{nota_media}` |
| Produtos Mais Recomendados | Bar horizontal | Top 10, cor `#19D3F3` |

### Aba 2 — 🏆 Ranking de Agentes

**Agregação por agente:**
```python
df_rank = df_av.groupby('agente').agg(
    ligacoes=('transcricao_id','count'),
    nota_media=('evaluation_ia','mean'),
    nota_min=('evaluation_ia','min'),
    nota_max=('evaluation_ia','max'),
    lead_score_medio=('lead_score','mean'),
)
# + colunas leads_A, leads_B, leads_C, leads_D, leads_ab, pct_ab
```

**Filtro:** Slider "mínimo de ligações avaliadas"

**KPIs (4 cards):** Melhor vendedor | Nota do melhor | Média do time | Agentes avaliados

**Tabela de ranking:**
`Agente | Ligações | Nota Média | Nota Mín | Nota Máx | Score Lead Médio | % Leads A+B | A | B | C | D`

| Gráfico | Tipo | Detalhes |
|---|---|---|
| Nota Média por Agente | Bar horizontal | Escala RdYlGn 0-100, linha tracejada = média time |
| Volume × Qualidade | Bubble scatter | X=nota_media, Y=lead_score_medio, size=ligacoes, cor=pct_ab |
| Distribuição por Agente | Stacked Bar | Empilha A/B/C/D por agente |

### Aba 3 — 🎯 Qualidade de Leads

**KPIs (4 cards):** Leads A% | Leads B% | Score Lead Médio | Leads A+B%

| Gráfico | Tipo | Detalhes |
|---|---|---|
| Distribuição por Classificação | Bar vertical | Cor por classe, texto externo |
| Score do Lead por Classificação | Box plot | Cor por classe, sem legenda |
| Nota Vendedor × Score do Lead | Scatter | Cor = classificação, hover = lead + agente |
| Áreas / Concursos de Interesse | Bar horizontal | Top 12, cor `#FF6692` |
| Evolução Diária do Score | Area chart | Linha tracejada = média geral |

### Aba 4 — 🔍 Análise SPIN

| Gráfico | Tipo | Detalhes |
|---|---|---|
| Pontos Fortes por Categoria | Bar horizontal | Escala Greens |
| Melhorias por Categoria | Bar horizontal | Escala Reds |
| Radar SPIN por Agente (Top 5) | Scatterpolar | fill='toself', score = fortes/(fortes+melhorias)*100 |

**Texto: Top Itens por Coluna (3 colunas):**
- Top Pontos Fortes | Top Melhorias | Top Erros Mais Caros

### Aba 5 — 👤 Relatório Individual

**Seletor:** Agente ordenado por volume de ligações

**KPIs com delta vs time (5 cards):**
```
Ligações avaliadas | Nota Média (±time) | Score Lead (±time) | Leads A+B% (±time) | Ranking #N/total
```

| Gráfico | Tipo | Detalhes |
|---|---|---|
| Evolução da Nota | Line com markers | 2 hlines: média agente (dot) + média time (dash) |
| Classificação de Leads | Pie Donut | Cores _CORES_CLASS |
| Produtos Recomendados Top 5 | Bar horizontal | Cor `#19D3F3` |

**Pontos Fortes e Melhorias (2 colunas, top 8 cada)**

**Erro mais frequente (st.error destacado)**

**Tabela detalhada:**
```
ID | Data | Nota | Score Lead | Classificação | Tipo IA | Confiança IA | Etapa | Transcrição
```

**Exportação:**
- `📄 Baixar PDF (HTML)` — arquivo `.html` para imprimir como PDF no navegador
- `⬇️ Exportar CSV`

### Geração de Relatório HTML (`_gerar_html_relatorio`)

```python
def _gerar_html_relatorio(agente, df_tab, periodo_ini, periodo_fim, kpis=None, df_raw=None):
    # 1. KPI cards (CSS flex)
    # 2. Gráficos CSS inline (sem dependências externas):
    #    - Distribuição de notas por faixa: 0–20, 21–40, 41–60, 61–80, 81–100
    #    - Classificação de leads: A, B, C, D
    # 3. Pontos em 3 boxes coloridos:
    #    - Verde: Pontos Fortes Top 5
    #    - Amarelo: Melhorias Top 5
    #    - Vermelho: Erros Mais Caros Top 5
    # 4. Tabela HTML (sem coluna Transcrição)
    # Retorna string HTML completa e auto-contida
```

---

## 🔄 Fluxo Completo de Dados

```
MySQL seducar.opportunity_transcripts
        │
        │  transcricoes.sql  (cache 6h)
        ▼
DataFrame Pandas — df_base
        │
        │  Filtros (empresa, período, agente, tipo)
        ▼
┌──────────────────────────────────────────────┐
│  _pages/transcricoes.py                      │
│  Tab "Avaliar" → seleção de IDs              │
│  _executar_avaliacoes(df_base, ids)          │
└──────────────┬───────────────────────────────┘
               │
               │  TranscricaoOpenAIAnalyzer()
               │
        ┌──────┴──────────────────────────┐
        │  1. classificar_ligacao()        │  GPT-5-nano
        │     heurística → sem tokens     │  max_completion_tokens=300
        │     IA → 2 tentativas           │  SEM temperature
        └──────┬──────────────────────────┘
               │  deve_avaliar = True?
        ┌──────┴──────────────────────────┐
        │  2. analisar_transcricao()       │  GPT-5.1
        │     contexto.txt + transcrição  │  temperature=0.2
        │     Retorna JSON SPIN completo  │  max_completion_tokens=8000
        └──────┬──────────────────────────┘
               │
               ▼
  atualizar_avaliacao_transcricao()
  ├── INSERT/UPDATE transcription_ai_summaries
  └── UPDATE opportunity_transcripts
               │
               │  st.cache_data.clear()
               ▼
  st.rerun() → recarrega UI
               │
               ▼
┌──────────────────────────────────────────────┐
│  _pages/analise_transcricoes.py              │
│  5 abas de análise com Plotly                │
│  Relatório individual em HTML/PDF            │
└──────────────────────────────────────────────┘
```

---

## 📦 Dependências Python

```txt
streamlit>=1.30
pandas>=2.0
plotly>=5.15
openai>=1.0        # GPT-5.1 + GPT-5-nano
sqlalchemy>=2.0
pymysql            # Driver MySQL para SQLAlchemy
python-dotenv
```

---

## ⚠️ Regras Críticas de Manutenção

| Regra | Detalhes |
|---|---|
| `type_` no batch | SEMPRE usa `row_data.get('tipo_ligacao')` (banco), nunca `analise.get('classificacao_ligacao')` |
| `evaluation_ia = 0` | Tratado como NaN no dashboard (0 = não avaliado) |
| Cache compartilhado | `st.cache_data.clear()` limpa ambas as páginas ao avaliar |
| COALESCE agent/duration/type | Registros legados têm NULL nas colunas diretas — JSON é fallback |
| `confianca_classificacao` | NULL em registros antigos — CAST(... AS DECIMAL) retorna NULL graciosamente |
| NaN/Inf do numpy/pandas | `_sanitize()` converte para None antes de persistir no MySQL |
| GPT-5-nano | NÃO aceita `temperature`, NÃO aceita `response_format` |
| GPT-5.1 | Usa `max_completion_tokens`, não `max_tokens` (parâmetro legado) |
| `"outros"` no SPIN | NÃO está em TIPOS_SKIP — sempre avalia |
| Contexto SPIN | Arquivo `consultas/transcricoes/contexto.txt` — se ausente, usa análise genérica |
