# 🤖 Sistema de Avaliação IA — Documentação Técnica

> **Última atualização:** Fevereiro 2026
> **Modelos em produção:** GPT-5.1 (avaliação SPIN) + GPT-5-nano (classificação)

---

## 📋 Visão Geral

O sistema de avaliação IA processa transcrições de ligações de vendas em **dois estágios**:

1. **Classificação** — GPT-5-nano identifica o tipo de ligação (venda, URA, cancelamento etc.)
2. **Avaliação SPIN** — GPT-5.1 avalia o desempenho do vendedor e qualifica o lead

Arquivo principal: `utils/transcricao_analyzer.py`  
Classe em produção: `TranscricaoOpenAIAnalyzer`

---

## 🔑 Configuração dos Modelos

### Variáveis de Ambiente

| Variável | Valor | Onde é lida |
|---|---|---|
| `OPENAI_API_KEY` | `sk-proj-...` | secrets / .env |
| `OPENAI_MODEL` | `gpt-5.1` | avaliação SPIN |
| `OPENAI_MODEL_CLASSIFICACAO` | `gpt-5-nano` | classificação |
| `OPENAI_TEMPERATURE` | `0.2` | somente avaliação |
| `OPENAI_MAX_TOKENS` | `8000` | `max_completion_tokens` avaliação |
| `OPENAI_MAX_INPUT_CHARS` | `25000` | truncagem transcrição avaliação |
| `OPENAI_MAX_INPUT_CHARS_CLASSIFICACAO` | `4000` | truncagem transcrição classificação |

### Ordem de Lookup de Secrets

```python
# 1. st.secrets["openai"]["api_key"]        ← estrutura aninhada Streamlit
# 2. st.secrets["OPENAI_API_KEY"]           ← flat Streamlit
# 3. os.getenv("OPENAI_API_KEY")            ← .env / variável de ambiente
```

---

## ⚠️ Restrições Críticas dos Modelos GPT-5

| Parâmetro da API | GPT-5.1 | GPT-5-nano | Observação |
|---|---|---|---|
| `temperature` | ✅ Aceita | ❌ **Não aceita** | HTTP 400 se enviado para nano |
| `max_completion_tokens` | ✅ | ✅ | Parâmetro correto para ambos |
| `max_tokens` | ❌ | ❌ | Parâmetro legado — gera erro HTTP 400 |
| `response_format` | ❌ | ❌ | Não suportado — gera erro HTTP 400 |
| `stream` | ✅ | ✅ | Não usado no sistema atual |

> **Atenção:** Qualquer parâmetro inválido causa **HTTP 400 BadRequest** — a ligação não é avaliada silenciosamente se não houver tratamento de erro.

---

## 🔀 Fluxo de Classificação (`classificar_ligacao`)

### Etapa 1 — Heurística (zero custo de tokens)

Executada antes de qualquer chamada à API:

| Condição | Resultado | Confiança |
|---|---|---|
| `len(tx) < 15` | `dados_insuficientes` | 0.95 |
| Texto contém padrão de caixa postal/URA | `ura` | 0.90 |
| Contém "indisponível" + sem marcadores de venda | `dialogo_incompleto` | 0.80 |
| `len(tx) < 80` | `dialogo_incompleto` | 0.70 |
| Nenhuma condição acima | `None` → vai para GPT-5-nano | — |

**Padrões de URA detectados (regex case-insensitive):**
- `"caixa postal"`, `"grave seu recado"`, `"deixe a sua mensagem"`
- `"não receber recados"`, `"mensagem na caixa postal"`

**Marcadores de venda** (evitam falso-positivo em `dialogo_incompleto`):
```
proposta, matrícula, desconto, parcela, valor, orçamento,
boleto, cartão, pagar, curso, convite de matrícula
```

**Validação pós-classificação:**
- Se classificou como `"ura"` mas há padrão `Vendedor: ... Cliente: ...` com len >= 255 → força `"venda"` ou `"outros"`

### Etapa 2 — GPT-5-nano com Retry

```python
for tentativa in range(2):
    try:
        response = client.chat.completions.create(
            model=self.model_classificacao,       # gpt-5-nano
            messages=[system_msg, user_msg],
            max_completion_tokens=300             # SEM temperature, SEM response_format
        )
        content = response.choices[0].message.content.strip()
        if not content:
            if tentativa == 0: continue           # retry silencioso
            return fallback_venda
        resultado = json.loads(content)
        # valida campos obrigatórios: tipo, confianca, deve_avaliar
        ...
    except json.JSONDecodeError:
        if tentativa == 0: continue               # retry silencioso
        return fallback_venda

# fallback_venda = {"tipo": "venda", "confianca": 0.5, "deve_avaliar": True}
```

**JSON esperado da classificação:**
```json
{
  "tipo": "venda",
  "motivo": "Conversa comercial com proposta de matrícula",
  "confianca": 0.92,
  "deve_avaliar": true
}
```

### Categorias de Classificação

| Tipo | Avalia (SPIN)? | Está em TIPOS_SKIP? |
|---|---|---|
| `venda` | ✅ Sim | ❌ Não |
| `outros` | ✅ Sim | ❌ Não |
| `ura` | ❌ | ✅ |
| `dialogo_incompleto` | ❌ | ✅ |
| `dados_insuficientes` | ❌ | ✅ |
| `ligacao_interna` | ❌ | ✅ |
| `chamada_errada` | ❌ | ✅ |
| `cancelamento` | ❌ | ✅ |
| `suporte` | ❌ | ✅ |

```python
TIPOS_SKIP = {
    'ura', 'dados_insuficientes', 'dialogo_incompleto',
    'ligacao_interna', 'chamada_errada', 'cancelamento', 'suporte'
}
# "outros" NÃO está em TIPOS_SKIP — sempre avalia
```

---

## 🧠 Avaliação SPIN (`analisar_transcricao`)

### Prompt System

Carregado de `consultas/transcricoes/contexto.txt`.
Se o arquivo não existir, usa prompt genérico de fallback.

**Conteúdo do contexto:** Metodologia SPIN Selling, critérios de avaliação de rapport, investigação, apresentação de valor, gatilhos mentais, tratamento de objeções, fechamento, clareza de comunicação. Inclui escala de lead scoring A/B/C/D.

### Chamada API — GPT-5.1

```python
response = client.chat.completions.create(
    model=self.model,                      # gpt-5.1
    messages=[
        {"role": "system", "content": contexto_spin},
        {"role": "user", "content": transcricao_truncada}
    ],
    temperature=self.temperature,          # 0.2
    max_completion_tokens=self.max_tokens  # 8000
    # SEM response_format, SEM max_tokens (legado)
)
```

### Estrutura JSON de Resposta

```json
{
  "avaliacao_vendedor": {
    "nota_final_0_100": 72,
    "pontos_fortes": [
      { "categoria": "rapport", "ponto": "Estabeleceu vínculo inicial com sucesso" },
      { "categoria": "valor_produto", "ponto": "Destacou benefícios do Live" }
    ],
    "melhorias": [
      { "categoria": "investigacao_spin", "melhoria": "Não explorou dores implícitas" },
      { "categoria": "fechamento", "melhoria": "Encerrou sem próximo passo definido" }
    ],
    "erro_mais_caro": {
      "categoria": "fechamento",
      "descricao": "Não propôs data e hora para retorno após objeção de preço"
    }
  },
  "avaliacao_lead": {
    "lead_score_0_100": 65,
    "classificacao": "B"
  },
  "extracao": {
    "concurso_area": "ENEM",
    "dores_principais": ["Dificuldade de organização", "Falta de tempo"],
    "restricoes": ["Preço", "Horário"]
  },
  "recomendacao_final": {
    "produto_principal": { "produto": "Live" },
    "justificativa": "Flexibilidade de horário"
  },
  "classificacao_ligacao": "venda",
  "motivo_classificacao": "Conversa comercial completa",
  "confianca_classificacao": 0.87
}
```

### Categorias SPIN Avaliadas

| Chave | Label exibido |
|---|---|
| `rapport` | 🤝 Rapport |
| `investigacao_spin` | 🔍 Investigação SPIN |
| `valor_produto` | 💎 Valor do Produto |
| `gatilho_mental` | ⚡ Gatilho Mental |
| `objecao` | 🛡️ Objeção |
| `fechamento` | 🤝 Fechamento |
| `clareza` | 🗣️ Clareza |
| `outros` | ❓ Outros |

### Classificação de Leads

| Classificação | Perfil |
|---|---|
| **A** | Alta intenção, sem restrições, score 80–100 |
| **B** | Boa intenção, algumas restrições, score 60–79 |
| **C** | Interesse moderado, restrições relevantes, score 40–59 |
| **D** | Baixo interesse ou muitas restrições, score 0–39 |

Cores no dashboard: `A=#00CC96`, `B=#636EFA`, `C=#FFA15A`, `D=#EF553B`

---

## 💾 Persistência — `utils/transcricao_mysql_writer.py`

### Sanitização de Dados (`_sanitize`)

Converte valores NaN/Inf vindos do numpy/pandas para `None` antes de enviar ao MySQL:

```python
import math

def _sanitize(v):
    if v is None:
        return None
    try:
        if math.isnan(float(v)) or math.isinf(float(v)):
            return None
    except (TypeError, ValueError):
        pass
    return v
```

**Por que é necessário:** O pandas representa campos vazios como `np.float64(nan)`. O driver PyMySQL não converte automaticamente — resulta em erro de binding SQL.

### Upsert Duplo em Transação Única

```python
with engine.begin() as conn:
    # 1. transcription_ai_summaries — todos os campos IA
    conn.execute(insert_summary_sql, params_summary)
    # 2. opportunity_transcripts — nota + COALESCE campos legado
    conn.execute(update_transcript_sql, params_transcript)
```

### COALESCE para Campos Legados

```sql
agent    = COALESCE(:agent, agent),
duration = COALESCE(:duration, duration),
phone    = COALESCE(:phone, phone),
type     = COALESCE(:type_, type)
```

**Motivo:** Registros criados antes da migração têm `agent/duration/type = NULL` e os dados corretos estão em `original_transcript` (JSON). O COALESCE preserva o valor existente se o novo for NULL.

---

## 📊 Como os Dados são Exibidos

### Fonte de Tipo de Ligação nas Avaliações

> **IMPORTANTE:** O campo `type_` gravado no banco ao avaliar **sempre vem do banco de dados** (`row_data.get('tipo_ligacao')`), nunca da classificação IA. Isso preserva o tipo original registrado pelo sistema de telefonia.

### `evaluation_ia = 0` → Tratado como "não avaliado"

No dashboard de análise (`analise_transcricoes.py`):
```python
df['evaluation_ia'] = df['evaluation_ia'].replace(0, np.nan)
```

Isso evita que ligações não avaliadas (nota=0) poluam médias e rankings.

### Cache Compartilhado

Ambas as páginas (`transcricoes.py` e `analise_transcricoes.py`) usam `st.cache_data(ttl=21600)` com a mesma query. Após qualquer avaliação:
```python
st.cache_data.clear()  # invalida cache de ambas as páginas
st.rerun()
```

---

## 💰 Estimativa de Custo por Ligação

| Etapa | Modelo | Tokens input | Tokens output | Observação |
|---|---|---|---|---|
| Classificação | gpt-5-nano | ~500 | ~100 | Limitado a 4000 chars + prompt |
| Avaliação SPIN | gpt-5.1 | ~2000-6000 | ~1500-2500 | Limitado a 25000 chars |
| Pulado (TIPOS_SKIP) | — | 0 | 0 | Heurística detectou tipo |

Ligações classificadas como `ura/dialogo_incompleto` **não consomem tokens do GPT-5.1** — apenas os ~500+100 tokens da classificação (quando a heurística não resolve).

---

## 🔧 Troubleshooting

| Erro | Causa | Solução |
|---|---|---|
| `HTTP 400 BadRequest` em classificação | `temperature` enviado para GPT-5-nano | Remover `temperature` da chamada do model_classificacao |
| `HTTP 400 BadRequest` em avaliação | `max_tokens` legado ou `response_format` | Usar `max_completion_tokens`, remover `response_format` |
| `DataError: can't adapt type numpy.float64` | NaN não sanitizado antes do MySQL | `_sanitize()` já resolve — verificar se está sendo chamada |
| Classificação retorna vazio | Resposta em branco do GPT-5-nano | Retry automático (2 tentativas) + fallback para "venda" |
| "outros" não é avaliado | Estava em TIPOS_SKIP incorretamente | "outros" deve estar FORA do TIPOS_SKIP |
| `agent/duration/type` NULL no banco | Registro legado sem colunas diretas | SQL usa COALESCE com JSON_EXTRACT de original_transcript |
| `confianca_classificacao` NULL | Registro avaliado antes da feature | Normal para registros antigos — CAST retorna NULL graciosamente |
| Cache não atualiza após avaliar | `st.cache_data.clear()` não chamado | Verificar que é chamado após sucesso em `_executar_avaliacoes` |

---

## 🔄 Integração com as Páginas

```
TranscricaoOpenAIAnalyzer
        │
        ├── classificar_ligacao(tx)
        │       └── retorna: {tipo, confianca, deve_avaliar, motivo}
        │
        └── analisar_transcricao(tx)
                ├── chama classificar_ligacao()
                ├── se TIPOS_SKIP → retorno_minimo (nota=0, D, sem API)
                └── chama GPT-5.1 → retorna dict completo

atualizar_avaliacao_transcricao(transcricao_id, insight_ia, evaluation_ia,
                                 agent, duration, phone, type_)
        ├── _sanitize() em todos os numerics
        ├── _extrair_campos() do JSON
        ├── INSERT/ON DUPLICATE KEY → transcription_ai_summaries
        └── UPDATE + COALESCE → opportunity_transcripts
```
