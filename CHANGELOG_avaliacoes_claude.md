# Changelog — Correções no Pipeline de Avaliação de Chats

## Resumo Executivo

5 problemas identificados, 3 arquivos corrigidos, 1 nova camada de IA adicionada.

**Antes:** Bot templates contaminavam transcrição → Haiku classificava errado → Sonnet avaliava lixo → JSON explodia CSV/XLSX → dados inutilizáveis.

**Depois:** Pré-processamento filtra bots → verificação de avaliabilidade por contagem humana → Haiku recebe só diálogo real → Sonnet avalia interação limpa → exportação com colunas expandidas.

---

## Arquivo 1: `chat_ia_analyzer.py`

### Mudança 1.1 — Novas funções de pré-processamento (NOVO)

Adicionadas 3 funções exportáveis no topo do módulo:

- `NOMES_BOT` / `TEMPLATES_BOT`: constantes com nomes de bots e templates reconhecíveis
- `filtrar_mensagens_bot(transcricao)`: parseia cada linha, identifica remetente, classifica como bot ou humano, retorna dict com transcrição limpa + stats
- `verificar_avaliabilidade(filtro, agent_name)`: verifica se há interação bilateral suficiente (mín. 2 remetentes humanos, turnos de agente + cliente, >300 chars humanos)

**Por que:** Antes, toda a transcrição (incluindo Ariel, OctaBot, dicas) ia direto para a IA. Agora o ruído é removido ANTES de qualquer chamada de API.

### Mudança 1.2 — Limite de chars da classificação: 4000 → 10000

```python
# ANTES
self.max_input_chars_classificacao = int(os.getenv("CLAUDE_MAX_INPUT_CHARS_CLASSIFICACAO", "4000"))

# DEPOIS
self.max_input_chars_classificacao = int(os.getenv("CLAUDE_MAX_INPUT_CHARS_CLASSIFICACAO", "10000"))
```

**Por que:** Com a transcrição limpa (sem bot), 10K chars é suficiente para capturar toda a conversa humana. Antes, 4K chars de transcrição bruta era quase todo bot.

### Mudança 1.3 — Prompt de classificação atualizado

Adicionado bloco:
```
IMPORTANTE — PRÉ-PROCESSAMENTO JÁ REALIZADO:
Esta transcrição já foi filtrada: mensagens de bots (Ariel, OctaBot, dicas) foram REMOVIDAS.
```

E critério mais rígido para "venda":
```
Respostas monossilábicas como apenas "Sim", "Ok", "Não" sem continuidade contam como sem_interacao.
```

### Mudança 1.4 — Prompt de avaliação atualizado

Adicionado:
```
NÃO penalize o vendedor por falta de rapport inicial se a conversa começa abruptamente — o bot já fez a triagem.
```

**Por que:** Sem as mensagens do Ariel, a conversa parece começar do nada. O Sonnet precisa saber que o rapport inicial foi feito pelo bot.

### Mudança 1.5 — `avaliar_chat()` reescrito com 4 camadas

Pipeline anterior:
1. Classifica com Haiku (transcrição bruta, 4K chars)
2. Se "venda" → avalia com Sonnet (transcrição bruta, 25K chars)

Pipeline novo:
1. **Filtra bot** (`filtrar_mensagens_bot`) — Python puro, sem API
2. **Verifica avaliabilidade** (`verificar_avaliabilidade`) — regras, sem API
3. **Classifica com Haiku** (transcrição LIMPA, 10K chars)
4. **Avalia com Sonnet** (transcrição LIMPA, 25K chars)

Novo parâmetro `agent_name` permite identificar quem é agente vs cliente na contagem de turnos.

Retorno agora inclui `filtro_stats` com métricas de pré-processamento (msgs_total, msgs_humanas, msgs_bot, chars_humanos, turnos_agente, turnos_cliente).

---

## Arquivo 2: `octadesk.py`

### Mudança 2.1 — Import das novas funções

```python
# ANTES
from utils.chat_ia_analyzer import ChatIAAnalyzer

# DEPOIS
from utils.chat_ia_analyzer import ChatIAAnalyzer, filtrar_mensagens_bot, verificar_avaliabilidade
```

### Mudança 2.2 — `_check_avaliavel()` reescrito (linha ~1071)

**ANTES:**
```python
def _check_avaliavel(row):
    agent = str(row.get('agent.name', '')).lower().strip()
    if agent in ['bot', 'ariel', 'octabot', 'none']:
        return False, "Atendido apenas por robô"
    # ... check human response ...
    transcricao = str(row.get('transcricao', '')).strip()
    if len(transcricao) < 1200:
        return False, f"Muito curta ({len(transcricao)} chars)"
    return True, "Apto para IA"
```

**DEPOIS:**
```python
def _check_avaliavel(row):
    agent = str(row.get('agent.name', '')).lower().strip()
    if agent in ['bot', 'ariel', 'octabot', 'none']:
        return False, "Atendido apenas por robô"
    # ... check human response (mantido) ...
    transcricao = str(row.get('transcricao', '')).strip()
    if not transcricao:
        return False, "Sem transcrição"
    filtro = filtrar_mensagens_bot(transcricao)
    avaliavel, motivo = verificar_avaliabilidade(filtro, agent_name=agent)
    if not avaliavel:
        return False, motivo
    return True, f"Apto para IA ({filtro['stats']['chars_humanos']} chars humanos)"
```

**Por que:** O filtro antigo contava `len(transcricao) < 1200` incluindo templates de bot. Um chat com 800 chars de Ariel + 400 chars humanos passava. Agora conta apenas interação humana real.

### Mudança 2.3 — `avaliar_chat()` recebe `agent_name`

```python
# ANTES
eval_result = analyzer.avaliar_chat(transcript, contexto_extra)

# DEPOIS
eval_result = analyzer.avaliar_chat(transcript, contexto_extra, agent_name=agent_name)
```

**Por que:** O analyzer agora filtra bots internamente e precisa saber quem é o agente para distinguir de cliente na contagem de turnos.

---

## Arquivo 3: `chat_mysql_writer.py`

### Mudança 3.1 — Funções de exportação segura (NOVO)

Adicionadas 3 funções no final do arquivo:

- `exportar_avaliacoes_para_df(engine)`: Carrega do MySQL, parseia ai_evaluation JSON, extrai campos principais como colunas separadas (vendor_score_calc, lead_score_calc, lead_classificacao, vendedor_identificado, lead_identificado, concurso_area, produto_indicado, erro_mais_caro, notas por categoria)
- `exportar_para_csv(filepath)`: Exporta com `csv.QUOTE_ALL` para evitar que vírgulas do JSON quebrem colunas
- `exportar_para_xlsx(filepath)`: Exporta sem a coluna JSON bruta (que é muito grande e causa corrupção)

**Por que:** O problema original de dados corrompidos no CSV/XLSX era causado pelo JSON do ai_evaluation contendo vírgulas que explodiam a estrutura de colunas. Agora o JSON é parseado em Python e os campos úteis viram colunas separadas.

### Nota sobre `salvar_avaliacao_chat()`

A função de gravação no MySQL **NÃO foi alterada**. Ela já faz `json.dumps()` corretamente. O problema era na exportação/leitura, não na gravação.

---

## Impacto nas métricas

| Métrica | Antes | Depois (estimado) |
|---------|-------|--------------------|
| Chats classificados como "venda" (falso positivo) | ~238 de 2578 (muitos são só bot) | Redução de 50-70% em falsos positivos |
| Chamadas ao Sonnet desperdiçadas | Alta (avaliando chats de bot) | Redução proporcional → economia de tokens |
| vendor_score recuperável do export | 0 de 238 | 100% (colunas extraídas do JSON) |
| Tempo de processamento por chat | Igual (2 API calls) | Maior em pré-processamento Python (~ms), menor em API (menos chats passam) |

---

## Como testar

1. Substituir os 3 arquivos no projeto
2. Rodar com um lote pequeno (5-10 chats) que você já conhece o resultado esperado
3. Verificar no dashboard que:
   - Chats só-bot aparecem como "Inapto" com motivo claro
   - Chats com conversa real passam e são avaliados
   - vendor_score e lead_score aparecem como números inteiros no banco
4. Exportar com `exportar_para_xlsx()` e verificar que as colunas estão corretas
