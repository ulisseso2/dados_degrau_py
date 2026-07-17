# Migração: Serviço de Avaliação de Ligações/Chats via IA → API para o Vue

> Handoff para o Claude Code do projeto **seducar-api** (AdonisJS 5 / TypeScript). Este documento mapeia tudo que as páginas Streamlit `_pages/transcricoes.py`, `_pages/analise_transcricoes.py` e `_pages/analise_chats.py` fazem hoje em Python, para que a mesma capacidade seja exposta como endpoints REST consumidos pelo front Vue.

---

## 1. Visão geral das 3 páginas

| Página | Papel | Fonte de dados | Escreve no banco? |
|---|---|---|---|
| `_pages/transcricoes.py` | Operacional: lista ligações, dispara avaliação por IA (individual/lote), reavaliação econômica, consulta/coleta de **Batch API** da Anthropic | `consultas/transcricoes/transcricoes.sql` + `transcricao_detalhe.sql` | Sim — grava avaliação |
| `_pages/analise_transcricoes.py` | BI somente-leitura sobre ligações já avaliadas (ranking, radar de competências, relatório individual, exportação) | mesmas queries acima | Não |
| `_pages/analise_chats.py` | BI somente-leitura sobre chats Octadesk (WhatsApp) já avaliados | `consultas/analise_chats/analise_chats.sql` | Não |

Só a página **transcricoes.py** dispara chamadas de IA e grava resultado. As outras duas são puramente dashboards (leitura + agregações + gráficos) — na migração viram só `GET`s com filtros, sem lógica de negócio nova.

O pipeline de avaliação de **chats do WhatsApp** (Octadesk) roda hoje fora do Streamlit (cron/serviço separado), mas usa o mesmo padrão de analyzer + writer (`ChatIAAnalyzer` / `chat_mysql_writer.py`) e a página `analise_chats.py` só lê o resultado. Incluí aqui porque a lógica é gêmea da de transcrições e provavelmente entra no mesmo módulo da API.

---

## 2. Inventário de funções e scripts

### 2.1 `utils/transcricao_analyzer.py` — `TranscricaoAnalyzer` (Anthropic/Claude — ligações telefônicas)
Motor principal usado pela página `transcricoes.py`.

- `__init__()` — lê env vars, instancia `anthropic.Anthropic`.
- `_limpar_markdown(content)` — remove cercas ```json de respostas.
- `_build_prompt(transcricao, contexto_adicional)` — monta prompt final a partir de `_USER_PROMPT_TEMPLATE`.
- `_call_claude(transcricao, contexto_adicional)` — chamada única ao Claude, com retry (3x), throttle por thread, cache de system prompt (`cache_control: ephemeral`), tratamento de `RateLimitError` com backoff exponencial.
- `analisar_transcricao(transcricao, contexto_adicional=None) -> Dict` — **pipeline completo**: heurística de triagem (0 tokens) → detecção de inversão vendedor/cliente → 1 chamada Claude que classifica *e* avalia. Retorna dict com `classificacao_ligacao`, `deve_avaliar`, `avaliacao_completa` (JSON string), `nota_vendedor`, `lead_score`, `lead_classificacao`, `concurso_area`, `produto_recomendado`, `vendedor_disclaimer`, `lead_disclaimer`, `confianca_avaliacao`.
- `analisar_lote_paralelo(transcricoes, max_workers=None, callback=None)` — roda várias em paralelo (`ThreadPoolExecutor`), usado no botão "Avaliar N selecionadas".
- `consultar_batch(batch_id)` / `criar_batch(transcricoes)` / `coletar_resultados_batch(batch_id)` — integração com a **Anthropic Message Batches API** (50% de desconto, processamento assíncrono até 24h).

Funções livres no módulo (fora da classe, sem estado — portam 1:1 para qualquer linguagem):
- `_heuristica_triagem(transcricao)` — regras de string (URA, poucos turnos, ligação interna, cancelamento etc.) que evitam gastar tokens.
- `_detectar_troca_interlocutores(transcricao)` — heurística para saber se os rótulos "vendedor:"/"cliente:" estão trocados.

O **prompt** (system + user template) é o coração do produto: ~250 linhas de regras de negócio (modalidades Presencial/Live/EAD, metodologia de pontuação 0-100 por categoria, textos fixos de pontos fortes/melhorias/erro mais caro, disclaimers). Isso precisa ser portado **literalmente**, não reescrito — é o que garante consistência das notas.

### 2.2 `utils/transcricao_ia_analyzer.py` — `TranscricaoIAAnalyzer` (OpenAI, alternativa)
Implementação paralela usando OpenAI (`gpt-5.1`) em vez de Claude, com **2 chamadas** (classificação leve + avaliação completa), em vez de 1. Não é chamada por nenhuma das 3 páginas analisadas (não há `import` dela em `transcricoes.py`/`analise_transcricoes.py`/`analise_chats.py`) — parece ser uma versão anterior/alternativa mantida no repo. **Confirme com quem mantém o projeto se ela ainda está em uso em algum cron antes de decidir portar.**

### 2.3 `utils/chat_ia_analyzer.py` — `ChatIAAnalyzer` (OpenAI — chats Octadesk/WhatsApp)
Motor usado pelo pipeline de avaliação de chats (consumido indiretamente por `analise_chats.py`, que só lê o resultado já gravado).

- `filtrar_mensagens_bot(transcricao)` — separa mensagens humanas de bots (Ariel/OctaBot), por nome de remetente e por templates de texto conhecidos (`NOMES_BOT`, `TEMPLATES_BOT`).
- `verificar_avaliabilidade(filtro, agent_name)` — regra de negócio: exige ≥2 participantes humanos, ≥2 mensagens de cada lado (ou uma regra alternativa), ≥800 chars de conteúdo humano.
- `ChatIAAnalyzer.__init__()` — lê env vars `OCTADESK_OPENAI_*`, decide entre **Responses API** ou **Chat Completions API** da OpenAI conforme o client suporta.
- `avaliar_chat(chat_text, contexto_adicional=None, agent_name='') -> Dict` — pipeline: filtro bot → verificação de avaliabilidade → 1 chamada OpenAI que classifica e avalia. Retorna `classificacao`, `ai_evaluation` (dict), `lead_score`, `vendor_score`, `main_product`, `vendedor_disclaimer`, `lead_disclaimer`, `filtro_stats`.
- `avaliar_lote_paralelo(chats, max_workers=None, callback=None)`.
- `criar_batch(chats)` / `consultar_batch(batch_id)` / `coletar_resultados_batch(batch_id)` — **OpenAI Batch API** (JSONL via `client.files.create` + `client.batches.create`).

Prompt também é extenso (~180 linhas) e específico do canal WhatsApp (IQH — Índice de Qualidade do Histórico, pré-processamento removendo bots). Portar literalmente.

### 2.4 `utils/transcricao_mysql_writer.py` — grava avaliação de **ligação**
- `atualizar_avaliacao_transcricao(transcricao_id, insight_ia, evaluation_ia, uuid=None, created_at=None, agent=None, duration=None, phone=None, type_=None, vendedor_disclaimer=None, lead_disclaimer=None) -> (bool, erro)`
  - Faz `_sanitize()` de NaN/Inf (herança do pandas — em Node não é necessário, `undefined`/`null` resolve).
  - Faz parsing do JSON de avaliação (`_extrair_campos`) para extrair `lead_score`, `lead_classification`, `strengths`, `improvements`, `most_expensive_mistake`, `main_pain_points`, `restrictions`, `contest_area`, `main_product` — concatenando itens de lista com `"; "` e prefixando com `[categoria]`.
  - **Grava em duas tabelas na mesma transação:**
    1. `seducar.transcription_ai_summaries` — `INSERT ... ON DUPLICATE KEY UPDATE` (upsert por `transcription_id`), com `created_at`/`updated_at = CURRENT_TIMESTAMP` sempre no momento da avaliação.
    2. `seducar.opportunity_transcripts` — `UPDATE` de `insight_ia`, `evaluation_ia`, `agent`, `duration`, `phone`, `type` (com `COALESCE` para não sobrescrever com `NULL`).

### 2.5 `utils/chat_mysql_writer.py` — grava avaliação de **chat**
- `salvar_avaliacao_chat(opportunity_id, chat_id, classification, classification_reason, ai_evaluation, transcript=None, lead_score=None, vendor_score=None, main_product=None, vendedor_disclaimer=None, lead_disclaimer=None, octa_agent=None, octa_channel=None, octa_status=None, octa_tags=None, octa_group=None, octa_origin=None, octa_contact_name=None, octa_contact_phone=None, octa_bot_name=None, octa_created_at=None, octa_closed_at=None, octa_survey_response=None) -> (bool, erro)`
  - `_ensure_opportunity_id_nullable(engine)` — auto-migração defensiva (`ALTER TABLE ... MODIFY opportunity_id NULL`, `ADD COLUMN vendedor_disclaimer/lead_disclaimer`), roda uma vez por processo com `try/except` silencioso. **Não precisa portar como está** — na API nova isso deve virar uma migration real do AdonisJS (Lucid), rodada uma vez, não a cada request.
  - `INSERT ... ON DUPLICATE KEY UPDATE` em `seducar.chat_ai_evaluations`, chave de upsert por `chat_id`.

### 2.6 `utils/octadesk_mysql_writer.py` — sincronização bruta do Octadesk (fora do escopo das 3 páginas, mas alimenta a tabela que `chat_ai_evaluations` referencia indiretamente)
- `save_chats_mysql(chats_list, cached_at=None)` → upsert em `seducar.octadesk_chats`.
- `save_messages_mysql(chat_id, messages_list, cached_at=None)` → upsert em `seducar.octadesk_messages`.
- `log_sync_mysql(...)` → insere log em `seducar.octadesk_sync_log`.
- Tem fallback de conexão via `.env` (`DB_WRITE_*`) para rodar fora do Streamlit (cron). Interessante como referência de que a conexão de escrita já era pensada para rodar "headless".

### 2.7 `utils/transcricoes_loader.py`, `utils/sql_loader.py` — leitura (read-only)
- `carregar_dados(caminho_sql)` / `carregar_dados_secundario(caminho_sql)` — executa um `.sql` de arquivo contra o engine MySQL (cache Streamlit 10 min).
- `carregar_detalhe_transcricao(transcricao_id)` — usa `transcricao_detalhe.sql` (troca `{ids}` por interpolação de string — **atenção**: hoje é seguro porque `transcricao_id` é `int(...)` antes de interpolar, mas se portar precisa continuar sendo um inteiro validado, nunca concatenação direta de string do usuário).

### 2.8 `utils/analise_helpers.py`, `utils/cats_vendedor.py` — puramente apresentação/agregação (sem I/O)
- `_safe_pct`, `_cor_nota`, `_top_items`, `_strip_cat`/`_extract_cat` (regex `^\[categoria\]\s*`), `_gerar_html_relatorio` (gera HTML para exportar como PDF via impressão do navegador — na versão Vue isso vira um componente de relatório, não precisa gerar HTML no back).
- `_CATS_VENDEDOR` / `_CATS_LEGACY` — dicionário de categorias de nota (chave JSON → label + nota máxima) e mapeamento de retrocompatibilidade com formato antigo de avaliação. **Precisa existir também no back novo** (ou ser embutido no payload de resposta) porque tanto o ranking quanto o radar de competências dependem dele para normalizar notas em %.

### 2.9 `utils/transcricao_avaliacao_db.py` — `TranscricaoAvaliacaoDB` (SQLite local)
Cache/staging local em SQLite (`transcricoes_avaliacoes.db`), usado historicamente para acumular avaliações antes de sincronizar com o MySQL principal (`sincronizado` flag). **Não é usado pelas 3 páginas atuais** (elas gravam direto no MySQL via `transcricao_mysql_writer.py`). Não portar, é resquício de uma versão anterior do fluxo — confirme antes de descartar.

### 2.10 Conexão com banco — `conexao/mysql_connector.py`
- `conectar_mysql()` — leitura, banco principal.
- `conectar_mysql_secundario()` — leitura, banco secundário.
- `conectar_mysql_writer()` — escrita (credenciais separadas, propositalmente um usuário com menos ou mais privilégio).
- Todas tentam primeiro `st.secrets[...]` (Streamlit Cloud) e caem para `.env` — esse dualismo não existe mais na API Node, só use variáveis de ambiente diretamente.

---

## 3. Variáveis de ambiente usadas

### Anthropic (Claude) — ligações telefônicas
| Variável | Default no código | Uso |
|---|---|---|
| `ANTHROPIC_API_KEY` | — (obrigatória) | Autenticação do client Anthropic |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | Modelo usado |
| `CLAUDE_TEMPERATURE` | `0.2` | Temperatura |
| `CLAUDE_MAX_TOKENS` | `4096` | Máx tokens de saída |
| `CLAUDE_MAX_INPUT_CHARS` | `25000` | Trunca transcrição na entrada |
| `CLAUDE_MAX_WORKERS` | `1` | Threads em paralelo (lote) |
| `CLAUDE_THROTTLE_SECONDS` | `8` | Intervalo mínimo entre chamadas por thread |

### OpenAI — `TranscricaoIAAnalyzer` (não usado pelas 3 páginas hoje, ver §2.2)
| Variável | Default | Uso |
|---|---|---|
| `OPENAI_API_KEY` | — | Auth |
| `OPENAI_MODEL` | `gpt-5.1` | Modelo de avaliação completa |
| `OPENAI_MODEL_CLASSIFICACAO` | = `OPENAI_MODEL` | Modelo de triagem |
| `OPENAI_TEMPERATURE` | `0.2` | Temperatura |
| `OPENAI_MAX_TOKENS` | `8000` | Máx tokens de saída |

### OpenAI — `ChatIAAnalyzer` (chats Octadesk/WhatsApp)
| Variável | Default | Uso |
|---|---|---|
| `OCTADESK_OPENAI_API_KEY` | — | Auth (chave separada da acima, propositalmente) |
| `OCTADESK_OPENAI_MODEL` | `gpt-5.4` | Modelo |
| `OCTADESK_OPENAI_TEMPERATURE` | `0.2` | Temperatura |
| `OCTADESK_OPENAI_MAX_OUTPUT_TOKENS` | `8000` | Máx tokens |
| `OCTADESK_OPENAI_MAX_INPUT_CHARS` | `25000` | Trunca entrada |
| `OCTADESK_OPENAI_MAX_WORKERS` | `3` | Paralelismo do lote |
| `OCTADESK_OPENAI_THROTTLE_SECONDS` | `0` | Intervalo entre chamadas |
| `OCTADESK_OPENAI_REASONING_EFFORT` | `low` | `none\|low\|medium\|high\|xhigh` — usado só se o client suportar Responses API |

### Banco de dados (MySQL `seducar`)
| Variável | Uso |
|---|---|
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | Conexão de **leitura** (banco principal) |
| `DB_SECUNDARIO_HOST`, `DB_SECUNDARIO_PORT`, `DB_SECUNDARIO_USER`, `DB_SECUNDARIO_PASSWORD`, `DB_SECUNDARIO_NAME` | Conexão de leitura, banco **secundário** (não usado pelas 3 páginas analisadas, mas existe no loader) |
| `DB_WRITE_HOST`, `DB_WRITE_PORT`, `DB_WRITE_USER`, `DB_WRITE_PASSWORD`, `DB_WRITE_NAME` | Conexão de **escrita** — usuário/credencial dedicada só para os `writer`s |

---

### Proposta de simplificação (confirmada após acesso ao `seducar-api`/`seducar-dashboard`)

Com os dois projetos reais em mãos (§11), dá pra cortar boa parte dessas variáveis em vez de só "traduzir" 1:1:

**Banco de dados — zero variáveis novas.** O `seducar-api` já usa **uma única conexão** MySQL (`config/database.ts`, credenciais `MYSQL_HOST/PORT/USER/PASSWORD/DB_NAME`), sem separação leitura/escrita — é o mesmo `Database` facade usado por `TranscriptionsController`, `DashboardController` (financeiro, oportunidades) etc. **Não replicar** a separação `DB_WRITE_*`/`DB_SECUNDARIO_*` do Python — é particularidade do app Streamlit (users diferentes por página), sem equivalente nem necessidade aqui. As novas rotas de avaliação usam a mesma conexão que todo o resto do Adonis já usa.

**IA — dois blocos de 6 variáveis cada, em vez de 21 (7 delas mortas).** Hoje: 7 `CLAUDE_*` (ligações) + 7 `OPENAI_*` sem `OCTADESK_` (não usadas — `TranscricaoIAAnalyzer` morto, ver §2.2) + 7 `OCTADESK_OPENAI_*` (chats). Proposta — eliminar o bloco morto e trocar os dois prefixos inconsistentes (`CLAUDE_*` nomeia o provedor; `OCTADESK_OPENAI_*` nomeia domínio+provedor) por um esquema paralelo `AI_<DOMINIO>_*`, já que o histórico dos changelogs (§10) mostra que o provedor **já trocou pelo menos 2 vezes** (OpenAI→Claude em ligações, Claude→OpenAI em chats) — nomear pela função, não pelo provedor do momento, evita renomear tudo de novo na próxima troca:

| Variável proposta | Substitui | Domínio |
|---|---|---|
| `AI_TRANSCRIPTION_PROVIDER` | (novo — hoje implícito por qual classe é instanciada) | ligações — `anthropic` |
| `AI_TRANSCRIPTION_API_KEY` | `ANTHROPIC_API_KEY` | ligações |
| `AI_TRANSCRIPTION_MODEL` | `CLAUDE_MODEL` | ligações |
| `AI_TRANSCRIPTION_TEMPERATURE` | `CLAUDE_TEMPERATURE` | ligações |
| `AI_TRANSCRIPTION_CONCURRENCY` | `CLAUDE_MAX_WORKERS` | ligações |
| `AI_TRANSCRIPTION_THROTTLE_MS` | `CLAUDE_THROTTLE_SECONDS` | ligações |
| `AI_CHAT_PROVIDER` | (novo) | chats — `openai` |
| `AI_CHAT_API_KEY` | `OCTADESK_OPENAI_API_KEY` | chats |
| `AI_CHAT_MODEL` | `OCTADESK_OPENAI_MODEL` | chats |
| `AI_CHAT_TEMPERATURE` | `OCTADESK_OPENAI_TEMPERATURE` | chats |
| `AI_CHAT_CONCURRENCY` | `OCTADESK_OPENAI_MAX_WORKERS` | chats |
| `AI_CHAT_THROTTLE_MS` | `OCTADESK_OPENAI_THROTTLE_SECONDS` | chats |

**Cortar por completo (não portar):**

- Todo o bloco `OPENAI_*` sem prefixo (`OPENAI_MODEL`, `OPENAI_MODEL_CLASSIFICACAO`, `OPENAI_TEMPERATURE`, `OPENAI_MAX_TOKENS`, `OPENAI_MAX_INPUT_CHARS`) — pertence ao `TranscricaoIAAnalyzer`/`TranscricaoOpenAIAnalyzer`, que **não é o código em produção** das 3 páginas (confirmado em §2.2 e §10).
- `DB_WRITE_*`, `DB_SECUNDARIO_*` (ver acima).
- `OCTADESK_OPENAI_REASONING_EFFORT` — só existe porque o código Python decide entre Responses API/Chat Completions em runtime; se a API nova só implementar uma via (Chat Completions, mais simples e já é dependência instalada), essa variável não tem função.

**Manter como constante no código, não env var** (candidatos, a confirmar com o time se algum já foi ajustado em produção por incidente):

- `*_MAX_TOKENS` e `*_MAX_INPUT_CHARS` — nos dois domínios, nunca aparecem diferentes do default no `.env.example` real do projeto Python; são limites estruturais do prompt, não parâmetros operacionais que alguém ajusta por ambiente. Se preferir manter configurável por segurança, ok — mas não é obrigatório.

**Resultado:** de 21 variáveis de IA + 15 de banco (36 no total, das quais 12 mortas/não usadas por essas 3 páginas) para **12 variáveis de IA + 0 novas de banco** — menos da metade, com nomes que não amarram no provedor atual.

---

## 4. Funções que gravam no banco (resumo de tabelas)

| Tabela | Função gravadora | Chave de upsert | Observação |
|---|---|---|---|
| `seducar.transcription_ai_summaries` | `atualizar_avaliacao_transcricao` | `transcription_id` | Guarda o resultado estruturado da avaliação de ligação |
| `seducar.opportunity_transcripts` | `atualizar_avaliacao_transcricao` | `id` (UPDATE simples) | Tabela "fonte" da transcrição bruta; recebe só as colunas de avaliação + agent/duration/phone/type via `COALESCE` |
| `seducar.chat_ai_evaluations` | `salvar_avaliacao_chat` | `chat_id` | Avaliação de chat Octadesk + todos os metadados `octa_*` |
| `seducar.octadesk_chats` | `save_chats_mysql` | `id` | Sync bruto do Octadesk (fora do escopo direto, mas é dependência de dados) |
| `seducar.octadesk_messages` | `save_messages_mysql` | `id` | Idem |
| `seducar.octadesk_sync_log` | `log_sync_mysql` | — (insert simples) | Log de sincronização |

Tabelas **lidas** pelas 3 páginas (via as queries em `consultas/`): `opportunity_transcripts`, `interesteds`, `customers`, `opportunity_steps`, `opportunity_modalities`, `opportunity_origins`, `transcription_ai_summaries`, `chat_ai_evaluations`, `users`.

---

## 5. Recomendação de linguagem/arquitetura para a nova API

> **Correção do usuário (prevalece sobre o texto anterior desta seção):** não reaproveitar o `seducar-api` existente — a intenção é criar **uma API nova, separada, dedicada só à parte de análises** (Transcrições/Chats agora; Marketing/GCLIDs e `relatorios_ia.py` depois, ver §12). O texto abaixo foi ajustado para essa decisão. O inventário de convenções do `seducar-api` em §11 continua válido e valioso — não como código a estender, mas como **referência de padrão a espelhar** no serviço novo (mesmo estilo de rotas, mesmo formato de resposta, mesma stack), pra o front não precisar tratar as duas APIs de forma diferente.

### ✅ Serviço novo, em TypeScript/Node, banco compartilhado com o `seducar-api`

- **Mesma stack (Node/TS), projeto separado.** Continua fazendo sentido usar Node/TypeScript em vez de Python/FastAPI pelos mesmos motivos técnicos de antes (SDKs oficiais Anthropic/OpenAI em Node, sem runtime duplicado do zero) — só que agora como um **novo repositório/serviço** dedicado a análises, não dentro do `seducar-api`. Pode ser AdonisJS de novo (reaproveita o conhecimento do time) num preset mais enxuto (API-only, sem `@adonisjs/view`/`@adonisjs/mail` etc.) ou algo mais leve (Fastify/Express) já que não precisa de admin de CRM completo — decisão de gosto do time, não bloqueia o resto do plano.
- **Mesmo banco `seducar` (MySQL), leitura e escrita nas mesmas tabelas** que o Python já usa hoje (`opportunity_transcripts`, `transcription_ai_summaries`, `chat_ai_evaluations`, `interesteds`, `customers`...) — não é um banco novo, é um segundo *serviço de aplicação* falando com o banco existente. As tabelas já existem e têm dado real de produção (o Python grava nelas todo dia); a API nova não recria dados, só passa a ler/escrever no lugar do Python.
- **Convenções a espelhar do `seducar-api`** (documentadas em §11, agora como referência e não como arquivo a editar): prefixo de rota `/v1/admin/<domínio>` (ou equivalente combinado com o time), envelope `{ data, meta? }`, raw SQL parametrizado pra dashboards agregados. Reaproveitar o *padrão* mantém o front simples — o Vue chama as duas APIs (core e análises) do mesmo jeito, só muda a base URL.

### Duas decisões reais em aberto (não dá pra assumir sem confirmar)

1. **Autenticação compartilhada.** O `seducar-dashboard` já loga contra o `seducar-api` (JWT via `@adonisjs/auth`). A API nova precisa validar o mesmo token — ou reaproveitando o mesmo segredo/`APP_KEY` pra verificar o JWT localmente (sem round-trip), ou chamando o `seducar-api` pra validar a cada request. A primeira opção é mais simples e mais rápida; só precisa confirmar que dá pra compartilhar o segredo entre os dois serviços com segurança (variável de ambiente própria da API nova, não committada).
2. **Quem passa a "dono" das migrations de `transcription_ai_summaries`/`chat_ai_evaluations`.** Essas 2 tabelas já existem fisicamente no banco `seducar` (o Python grava nelas hoje) e já têm migrations **commitadas no `seducar-api`** (§11.1) — mas nunca ligadas a nenhum controller lá. Como agora é a API nova que vai possuir essa funcionalidade, faz sentido que ela também passe a possuir o histórico de migration dessas 2 tabelas dali pra frente (incluindo a migration pendente das colunas `vendedor_disclaimer`/`lead_disclaimer`, §11.1) — sem recriar as tabelas (já existem), só assumindo o rastreio de mudanças de schema. As migrations do `seducar-api` para essas 2 tabelas podem ficar como estão (não fazem mal) ou ser removidas de lá depois, mas isso é decisão do time, não algo pra decidir sozinho.

**O que fica igual, independente da arquitetura escolhida:**

- As chamadas às **Batch APIs** (Anthropic e OpenAI) são assíncronas por natureza (`criar_batch` → poll de status → `coletar_resultados_batch`) — viram endpoints que dependem de um job agendado (cron/worker do serviço novo) ou endpoint manual de "consultar/coletar" espelhando o botão que já existe no Streamlit.
- Two-phase commit (upsert em 2 tabelas na mesma transação) — usar transação nativa do driver/ORM escolhido, igual ao `engine.begin()` do SQLAlchemy no Python.

---

## 6. Endpoints propostos (mapeamento Streamlit → REST)

**Convenção real confirmada** (não mais hipótese): prefixo `/v1/admin/<domínio>`, middleware `['auth', 'schoolDetect']`, um arquivo de rota por domínio importado em `start/admin/index.ts`, controller fino delegando pra um `Service` (listagem/CRUD) ou direto pra `DashboardController` com `Database.rawQuery()` (dashboards agregados tipo Financeiro/Oportunidades). Envelope de resposta: `{ data: [...] }` (raw query) ou `{ data, meta }` (quando usa `.paginate()` do Lucid). Ver §11 para os arquivos exatos que definem esse padrão.

| Ação hoje no Streamlit | Endpoint sugerido | Convenção a seguir |
| --- | --- | --- |
| Carregar lista de ligações (filtros período/agente) | `GET /v1/admin/transcriptions/list` (**já existe** — só falta juntar `transcription_ai_summaries` no `preload`/`select` e expor os campos de avaliação) | Estender `TranscriptionService.list()` |
| Ver detalhe de 1 ligação (transcrição completa) | `GET /v1/admin/transcriptions/:id` (novo método no mesmo controller) | `TranscriptionsController` |
| Avaliar 1 ou N ligações selecionadas | `POST /v1/admin/transcriptions/evaluate` `{ ids: number[] }` | Novo `TranscriptionEvaluationService` (ou método em `TranscriptionService`), chamando o client Anthropic + upsert nas 2 tabelas via `Database.transaction()` |
| Reavaliar período | `POST /v1/admin/transcriptions/reevaluate` `{ ids: number[] }` | mesma lógica de `evaluate` |
| Batch Anthropic (criar/status/coletar) | `POST /v1/admin/transcriptions/batch`, `GET /v1/admin/transcriptions/batch/:batchId`, `POST /v1/admin/transcriptions/batch/:batchId/collect` | idem |
| Dashboard "Análise de Ligações" (ranking, competências, individual) | Novo grupo `GET /v1/admin/transcription-analytics/...` — seguir o padrão de `DashboardController.oportunidades()`/`contasAPagar()`: SQL quase idêntico ao `.sql` do Python, parametrizado com `school.id`, retorno `{ data: result[0] }` | Método(s) novo(s) em `DashboardController` |
| Escrita/avaliação de chats (Octadesk) | `POST /v1/admin/chats/evaluate`, `GET /v1/admin/chats/list`, batch equivalente | Novo `ChatsController`/`ChatEvaluationService`, mesma convenção — ainda não inventariado função a função (ver §10.1, `_pages/octadesk.py`/`chat_oportunidades.py`) |
| Dashboard "Análise de Chats" | `GET /v1/admin/chat-analytics/...` | Idem, `DashboardController` |
| Exportar CSV/relatório individual | Client-side (o front já gera com `xlsx`/`jspdf-autotable`, ver §9.1) — não precisa de endpoint dedicado | — |

**Ponto em aberto real, não técnico:** os endpoints de Financeiro/Oportunidades usam `request.input('school')`, preenchido pelo middleware `SchoolDetect` a partir da **escola do usuário logado** — não é um filtro `?empresa=Degrau|Central` livre como no Streamlit (onde o Ulisses alterna manualmente entre as duas). Se o mesmo usuário admin precisa ver Degrau e Central nas telas de Transcrições/Chats como hoje, isso é uma decisão de produto/permissão a resolver com o time (ex.: usuário com múltiplas escolas, ou um override de `school_id` só para quem tem uma permissão específica) — não dá pra assumir e seguir sem confirmar.

---

## 7. Onde fica a agregação dos dashboards — decidido: opção A (confirmado pela página Financeiro)

Hoje o Streamlit carrega o dataset **bruto** (todas as linhas do período) e faz toda agregação (ranking por agente, radar de competências, distribuição de notas por categoria) **no cliente Python com pandas**, a cada troca de filtro.

A migração já feita da página **Financeiro** (`_pages/financeiro_sp.py` → componente Vue com `FinanceiroService`) segue exatamente esse padrão do lado do Vue: `carregarBase()` busca os datasets quase-brutos uma vez (`contasAPagar()`, `contasBancarias()`) e **todo o resto — opções de filtro em cascata, KPIs, árvore hierárquica, dados dos gráficos — é `computed`**, recalculado no cliente a cada mudança de filtro, sem novo round-trip. Isso confirma a opção (A) como o padrão já estabelecido no projeto, não uma escolha nova:

- **API devolve dataset quase bruto** (uma linha por ligação/chat avaliado, já com os campos parseados do JSON — `lead_score`, `strengths`, `notas_pct`, etc.), e o **Vue faz toda a agregação** (ranking, radar, distribuição por categoria) via `computed`, igual a `agrupaDespesa`/`kpiApagar`/`arvoreDespesas` no exemplo do Financeiro.
- Replicar no front a lógica de parsing do JSON de avaliação (`_extrair_campos` em `transcricao_mysql_writer.py`, `_CATS_VENDEDOR`/`_CATS_LEGACY`, `_extract_notas_pct` em `analise_chats.py`) — ver §9.2 para a listagem completa do que precisa existir em JS.
- **Exceção que também tem precedente**: a seção "Movimento de Caixa" do Financeiro *não* segue o padrão client-side puro — ela reconsulta a API a cada mudança de `movInicio`/`movFim` (`watch` → `buscarMovimento()`), porque o **saldo anterior** é uma agregação que depende de todo o histórico até a data de início, não só do período visível — calcular isso no cliente exigiria trazer o histórico inteiro. O equivalente aqui seria: se algum gráfico futuro precisar de dado fora da janela do período selecionado (ex.: comparação com médias históricas), ele vira endpoint próprio com `watch`, os demais continuam 100% `computed`.

---

## 8. Pontos de atenção na migração

1. **Prompt é o produto.** Qualquer diferença de wording no `_SYSTEM_PROMPT`/`_USER_PROMPT_TEMPLATE` muda a distribuição de notas. Copiar literalmente, não "melhorar" durante a porta.
2. **JSON de avaliação tem 2 formatos** (atual `notas_por_categoria` com chaves novas, e legado via `_CATS_LEGACY`) — o parser em TS precisa replicar esse fallback (`_extract_notas_pct` em `analise_chats.py`, `_extrair_campos` em `transcricao_mysql_writer.py`).
3. **`transcricao_id` interpolado como string em SQL** (`transcricao_detalhe.sql`, placeholder `{ids}`) — na API nova, usar **sempre** bind parameter (`?`/`:id`), nunca concatenar string, mesmo validando que é inteiro antes.
4. **Rate limit / retry** — Claude e OpenAI implementam backoff exponencial próprio (3 tentativas, `2^(n+2)` segundos) e throttle mínimo entre chamadas por thread. Replicar isso (ou usar as opções nativas de retry dos SDKs oficiais, que já existem em `@anthropic-ai/sdk` e `openai`).
5. **Paralelismo do lote** — Python usa `ThreadPoolExecutor(max_workers=4)` fixo no botão "Avaliar N selecionadas" (`_pages/transcricoes.py`, função `_executar_avaliacoes`) e `CLAUDE_MAX_WORKERS`/`OCTADESK_OPENAI_MAX_WORKERS` para os analyzers. Em Node, isso vira `Promise.all` com um limitador de concorrência (ex.: `p-limit`), não threads reais — mas o comportamento observável (throttle + retry) deve ser preservado.
6. **Duas credenciais de banco distintas (leitura vs. escrita)** — parece intencional (menor privilégio). Confirmar se a `seducar-api` já segue essa separação ou se usa uma única credencial; se for para manter o padrão de segurança, replicar.
7. **`TranscricaoIAAnalyzer` (OpenAI, ligações) e `TranscricaoAvaliacaoDB` (SQLite local)** não são usados pelas 3 páginas atuais — confirmar com o time se ainda rodam em algum cron isolado antes de decidir não portar.

---

## 9. Convenções de front observadas (referência: página Financeiro) e como aplicá-las aqui

Baseado no componente Vue já migrado da página Financeiro (`b-card`/BootstrapVue + `FinanceiroService`), o Claude Code do front deve seguir o mesmo padrão para Transcrições/Análise de Ligações/Análise de Chats. Isto **não é código a implementar aqui** — é a especificação de contrato/formato que a API TypeScript (seção 5) precisa satisfazer para o front conseguir reaproveitar exatamente esse padrão.

### 9.1 Stack de UI já em uso (replicar, não trocar)

- **BootstrapVue** (`b-card`, `b-form`, `b-row`/`b-col`, `b-button`, `b-spinner`, `b-alert`) para layout e estado de loading/erro.
- **`vue-select`** para os multiselects de filtro (empresa/agente/tipo/classificação — equivalente a `ueSel`/`unSel`/`ccSel` no exemplo).
- **`vue-flatpickr-component`** com locale `Portuguese` (`flatpickr/dist/l10n/pt`) para os seletores de período — mesmo padrão de `despInicio`/`despFim`.
- **`vue-echarts`** (`ECharts` + imports seletivos de `echarts/lib/...`) para todos os gráficos — pizza (classificação de leads, situação), barras (ranking por agente, top categorias), como em `chartSituacao`/`chartBarras`.
- **`xlsx`** para exportar Excel (equivalente a `exportarDespesasExcel`/`exportarExtratoExcel`) e **`jspdf` + `jspdf-autotable`** para exportar PDF (equivalente a `exportarExtratoPdf`). A página `analise_transcricoes.py`/`analise_chats.py` já geram um "PDF" hoje via HTML+impressão (`_gerar_html_relatorio`) — no Vue isso deveria ser substituído por `jspdf-autotable`, seguindo o padrão do Financeiro, e não portar a geração de HTML.

### 9.2 Camada de serviço (`@/_services/Http/*.js`)

Um arquivo por domínio, mesmo padrão de `FinanceiroService`. Propor:

- `@/_services/Http/transcricoes.js` — `listar({ empresa, data_ini, data_fim })`, `detalhe(id)`, `avaliar({ ids })`, `reavaliar({ ids })`, `batch.criar({ ids })`, `batch.status(batchId)`, `batch.coletar(batchId)`.
- `@/_services/Http/chats.js` — `listar({ empresa, data_ini, data_fim })`, `detalhe(chatId)`.

Cada método chama um endpoint da seção 6 e devolve o array quase-bruto (não agregado), para alimentar `computed` no componente — igual `FinanceiroService.contasAPagar()`.

### 9.3 Padrão de carregamento e agregação client-side

Replicar a estrutura do exemplo:

```js
data() {
  return {
    loading: true,
    erro: '',
    registros: [], // dataset quase-bruto (1 linha por ligação/chat avaliado)
    // filtros: empresa, período, agente[], tipo[], classificação[]
  }
},
computed: {
  // opções de filtro derivadas do dataset carregado (uniq(...))
  agentesOpts() { return uniq(this.registros.map(r => r.agente)) },
  // dataset filtrado
  registrosFiltrados() { /* aplica todos os filtros selecionados */ },
  // agregações para KPIs e gráficos — equivalentes a kpiApagar/agrupaDespesa
  ranking() { /* group by agente: nota média, lead_score médio, contagem A/B/C/D */ },
  radarCompetencias() { /* média de notas_pct por categoria, top N agentes */ },
  chartClassificacaoLeads() { /* pizza A/B/C/D */ },
},
async mounted() { await this.carregarBase() },
methods: {
  async carregarBase() { this.registros = (await TranscricoesService.listar({...})).data },
}
```

Isso significa que os campos que hoje só existem depois do parsing Python do JSON (`lead_score`, `lead_classification`, `strengths`, `improvements`, `most_expensive_mistake`, `notas_pct` por categoria, `vendedor_disclaimer`, `lead_disclaimer`) **precisam vir já parseados e achatados no payload da API** — o Vue não deve receber o JSON bruto de avaliação e reimplementar `_extrair_campos`/`_extract_notas_pct` para cada card; a API TS já faz esse parsing (reaproveitando a lógica de `transcricao_mysql_writer.py`/`analise_chats.py` descrita no §2.4 e §2.8) e devolve um objeto "achatado" por registro.

### 9.4 Ações que escrevem (avaliar/reavaliar/batch)

No exemplo do Financeiro não há mutação (é só leitura/export), mas o padrão de "loading local + reconsulta ao final" da seção Movimento de Caixa (`movLoading` + `buscarMovimento()` no `watch`) é o modelo a seguir para os botões de avaliação:

```js
async avaliarSelecionados(ids) {
  this.avaliando = true
  try {
    await TranscricoesService.avaliar({ ids })
    await this.carregarBase() // re-busca pra refletir o novo insight_ia/evaluation_ia
  } finally {
    this.avaliando = false
  }
}
```

Sem WebSocket/polling de progresso por enquanto (o Streamlit tem uma barra de progresso por causa do processamento síncrono em thread; no Vue, um `b-spinner` + mensagem "Avaliando N ligações..." é suficiente para o MVP — like `movLoading` no exemplo).

### 9.5 Helpers a centralizar

No exemplo do Financeiro, `formatBRL`/`formatDate` são declarados localmente no `.vue`. Como as 3 páginas de IA vão precisar de formatação equivalente (nota 0-100 com emoji de cor — `_cor_nota` — e possivelmente `formatDate`), vale avaliar centralizar em `@/_helpers/format.js` compartilhado em vez de duplicar por componente, já que aqui são pelo menos 3 telas usando os mesmos helpers (ao contrário do Financeiro, que é uma tela só). Decisão de estilo do time front, não bloqueia a API.

---

## 10. Aviso importante: documentação existente desatualizada

Durante a investigação apareceram 3 documentos **já existentes neste repo** que descrevem uma versão **anterior e diferente** do pipeline de avaliação — não confiar neles sem checar a data:

| Documento | Última alteração (git) | O que descreve (desatualizado) | Realidade atual do código |
|---|---|---|---|
| `README_TRANSCRICOES.md` | 2026-02-27 | Classe `TranscricaoOpenAIAnalyzer`, pipeline 2 chamadas OpenAI (GPT-5-nano classificação + GPT-5.1 avaliação SPIN) | `_pages/transcricoes.py` importa `TranscricaoAnalyzer` de `utils/transcricao_analyzer.py` (**Anthropic Claude**, 1 chamada, última alteração 2026-06-18) — classe e métodos com nomes diferentes dos descritos no README |
| `SISTEMA_AVALIACAO_IA.md` | 2026-02-27 | Mesmo pipeline OpenAI acima, com detalhes de `max_completion_tokens`, restrições GPT-5 | Idem — não reflete o Claude Analyzer atual |
| `CHANGELOG_avaliacoes_claude.md` | 2026-04-09 | Menciona modelos "Haiku" (classificação) e "Sonnet" (avaliação) no pipeline de **chats** | `utils/chat_ia_analyzer.py` (última alteração 2026-04-28, **depois** do changelog) usa exclusivamente OpenAI (`OCTADESK_OPENAI_MODEL=gpt-5.5`), não Anthropic — o changelog ficou desatualizado em relação ao próprio arquivo que documenta |

**Conclusão prática:** os §§1–9 deste documento foram escritos lendo o **código-fonte atual**, não esses READMEs — é a fonte confiável. Se o time mencionar esses documentos como referência, avisar que estão obsoletos (todos de 1 a 4 meses antes da última alteração dos arquivos `.py` que descrevem).

### 10.1 Achados adicionais nesta rodada

- **O pipeline de avaliação de chats NÃO roda num cron externo** (correção ao §2.3): as páginas Streamlit `_pages/octadesk.py` (1644 linhas) e `_pages/chat_oportunidades.py` (718 linhas) são o **caminho de escrita real** — chamam `ChatIAAnalyzer`/`salvar_avaliacao_chat` da mesma forma que `transcricoes.py` faz para ligações (avaliação individual, lote, batch). Se a migração da API também for cobrir a escrita de chats (não só leitura via `analise_chats.py`), essas duas páginas precisam do mesmo tratamento dado a `transcricoes.py` no §2.1–2.4 — ainda não foram inventariadas função a função.
- **`.env.example`** revela mais contexto útil não coberto no §3:
  - `LOCAL_USERS_DB` — mapa de usuário → senha → páginas permitidas (`{"vendedor": {..., "pages": ["Oportunidades", "Tendencias", "Matriculas"]}, "financeiro": {..., "pages": [...]}}`). É o "sistema de permissão" atual do Streamlit — ao desenhar auth/`Bouncer` na API nova, decidir quem (qual papel) pode ver/avaliar Transcrições e Chats equivalente a isso.
  - `GROQ_MODEL` e `MONGO_DB_URI` existem no `.env.example` mas **não são usados** por nenhum dos módulos das 3 páginas analisadas — ruído, ignorar para este escopo.
- **`vue_oportunidades/api.py`** (88 linhas, já neste repo) é um backend FastAPI **propositalmente descartável** — 1 endpoint, sem auth, CORS aberto, cache em memória — construído só para prototipar o Vue localmente antes da integração real. Não é precedente contra a recomendação do §5 (TypeScript no `seducar-api`); é só um atalho de prototipagem que já existia no repo.

### 10.2 Pendências de acesso — resolvidas em §11

A lista original de "o que falta o usuário fornecer" foi resolvida depois que os projetos `seducar-api` (`/api`) e `seducar-dashboard` (`/dashboard`) foram adicionados ao workspace. Ver §11 para os achados reais. Únicas pendências genuínas que sobraram: o catálogo de permissões (`user_permission_id`/`getPermissions` — quais papéis existem e quais deveriam ganhar acesso a Transcrições/Chats) e a questão do `school`/empresa (§6) — nenhuma das duas dá pra resolver só lendo código, são decisões de produto/acesso.

---

## 11. Achados reais no `seducar-api` e `seducar-dashboard` (após acesso aos dois projetos)

Localização: backend em `/var/home/ulissesoliveira/api` (`seducar-api`), front em `/var/home/ulissesoliveira/dashboard` (`seducar-dashboard`, Vue 2 + BootstrapVue + Vuex — mesma stack do exemplo Financeiro do §9, não é um projeto separado).

> **Leitura correta desta seção após a decisão do §5:** o `seducar-api` **não vai ser editado** para a parte de análises — o que vem abaixo é o levantamento do schema/convenções já existentes (banco compartilhado + padrão de API do time), que a API **nova** deve espelhar e, no caso das 2 tabelas de IA, passar a possuir.

### 11.1 O que já existe no `seducar-api` para essas tabelas (schema real + gaps a herdar)

| Peça | Arquivo | Estado |
| --- | --- | --- |
| Rota de listagem | `start/admin/transcription/index.ts` → `GET /v1/admin/transcriptions/list` | ✅ Funcional |
| Controller | `app/Controllers/Http/Admin/TranscriptionsController.ts` | ✅ Só `index()` (listagem paginada) |
| Service | `app/Services/TranscriptionService.ts` | ✅ Usa Lucid query builder + `.paginate(page, limit)`, filtros `search`/`rangeDate`/`opportunityId`/`schoolId` |
| Model | `app/Models/OpportunityTranscript.ts` | ⚠️ Existe, mas **não declara** as colunas `agent`, `duration`, `phone`, `type` (adicionadas pela migration `1772132655884_add_fields_to_opportunity_transcripts.ts`, mas nunca refletidas no model — precisa de 4 `@column()` novas) |
| Model | `TranscriptionAiSummary` (tabela `transcription_ai_summaries`) | ❌ **Não existe** — só a migration. Precisa criar o model Lucid |
| Model | `ChatAiEvaluation` (tabela `chat_ai_evaluations`) | ❌ **Não existe** — só a migration |
| Migration `transcription_ai_summaries` | `1739350800000_create_transcription_ai_summaries.ts` | ⚠️ **Sem** `vendedor_disclaimer`/`lead_disclaimer` (colunas que o Python adicionou depois via `ALTER TABLE` em runtime, §2.4) — falta uma migration nova |
| Migration `chat_ai_evaluations` | `1783191870000_chat_ai_evaluations.ts` | ⚠️ Mesma lacuna: sem `vendedor_disclaimer`/`lead_disclaimer`. Já tem `opportunity_id` nullable com FK `ON DELETE SET NULL` pra `interesteds` — o hack defensivo do Python (`_ensure_opportunity_id_nullable`, §2.5) já **não é necessário**, a migration Adonis já nasceu certa nesse ponto |
| Uso de `openai`/`@anthropic-ai/sdk` no código | — | ❌ Nenhum (`openai` é dependência declarada, zero `import` no projeto) |

**Ação concreta decorrente:** ao construir a API nova, antes de escrever controllers ela precisa (a) rodar/possuir 1 migration adicionando as 2 colunas de disclaimer nas 2 tabelas (elas já existem fisicamente, só faltam essas colunas — ver §5, decisão 2), (b) criar seus próprios models/tipos equivalentes a `TranscriptionAiSummary` e `ChatAiEvaluation`, (c) para escrever em `opportunity_transcripts` (colunas `agent`/`duration`/`phone`/`type`, que já existem na tabela via migration do `seducar-api`), usar as colunas diretamente por SQL/ORM — não precisa que o `seducar-api` "exponha" nada, é acesso direto ao mesmo banco.

### 11.2 Convenções confirmadas (não são mais hipótese)

- **Rotas**: 1 arquivo por domínio em `start/admin/<dominio>/index.ts`, importado em `start/admin/index.ts` (que hoje importa ~60 domínios — `transcription`, `financeiro`, `oportunidades` já estão lá). Padrão: `Route.group(() => {...}).prefix('/v1/admin/<dominio>').middleware(['auth', 'schoolDetect'])`.
- **Dois estilos de controller convivem no projeto**, e ambos servem de referência:
  - **CRUD/listagem** → controller dedicado + Lucid query builder + `.paginate()` (exemplo: `TranscriptionsController`/`TranscriptionService`). Envelope: `{ data: [...], meta: {...} }`.
  - **Dashboard agregado** → método adicionado direto em `app/Controllers/Http/Admin/DashboardController.ts` (909 linhas, um por domínio: `oportunidades()`, `contasAPagar()`, `contasBancarias()`, `movimentoCaixa()`...), com a query SQL declarada como constante `SQL_X` (template string) no topo do arquivo e execução via `Database.rawQuery(SQL_X, [bindings])`. Envelope: `response.status(200).send({ data: result[0] })` (mais chaves extras quando precisa, ex. `movimentoCaixa` retorna `{ data, saldo_anterior }` — o mesmo formato que o `.vue` de Financeiro já consome). **Este é o padrão a seguir para os dashboards "Análise de Ligações"/"Análise de Chats"** — o SQL do Python (`transcricoes.sql`, `analise_chats.sql`) migra quase copiado, só trocando `WHERE` fixo por bindings parametrizados e `empresa` pelo `school.id` do middleware.
- **`school` não é um filtro do usuário** — vem do middleware `SchoolDetect` (`app/Middleware/SchoolDetect.ts`), que resolve a escola do usuário autenticado (`user.related('school')`) e injeta em `request.all().school`. Controllers fazem `const school = request.input('school')`. Isso é a fonte da observação em §6 sobre o filtro "Empresa" não ter equivalente direto — hoje o modelo é 1 usuário = 1 escola, não um seletor livre.
- **Permissão/role**: também via `SchoolDetect` — `user.user_permission_id` → `role.related('getPermissions')` → `user.role = { name, permissions }`. É **RBAC real no banco**, não o `LOCAL_USERS_DB` hardcoded do Streamlit (§10.1) — mais robusto, mas significa que expor as novas telas exige cadastrar a permissão certa no catálogo existente (tabela de permissões), não só codar o middleware. Não achei o catálogo de valores possíveis nesta rodada — perguntar ao time qual papel deve ganhar acesso a Transcrições/Chats (vendedor? um papel "QA comercial" novo?).
- **Banco de dados**: uma única conexão (`config/database.ts`, `MYSQL_HOST/PORT/USER/PASSWORD/DB_NAME`, driver `mysql2`), sem separação leitura/escrita. Existe também `MYSQL_2_*` no `.env.example` (provável equivalente ao `DB_SECUNDARIO_*` do Python), mas não usado pelas rotas revisadas.
- **Front**: `seducar-dashboard` é Vue 2 + Vuex + BootstrapVue (mesma stack do exemplo Financeiro do §9 — não havia dois projetos Vue diferentes, era o mesmo). Confirma tudo que §9 já descrevia: `_services/Http/<dominio>/index.js` chamando `ApiService.get(...)` (axios wrapper em `_services/Http/axios.js`) e resolvendo com `res.data` (ou seja, o componente recebe o envelope `{ data, meta? }` inteiro, não desembrulhado) — bate exatamente com o exemplo do Financeiro. Vuex (`store/<dominio>/index.js`) existe para a maioria dos domínios (inclusive já um `store/transcription`) mas é uma camada fina que só repassa pra `_services/Http` — pode ou não ser replicado pras novas telas, é convenção do projeto, não obrigatório tecnicamente.
- **Menu/ACL do front**: `src/libs/acl/config.js` define só a `initialAbility` (ability mínima antes do login); a lista real de abilities por usuário vem do backend (via `SchoolDetect`/permissões) e é injetada em runtime no `@casl/vue` — **não é hardcoded no front**, então não precisa editar esse arquivo pra liberar acesso às novas páginas, só a permissão no backend + registrar a rota Vue com o `meta.action`/`meta.resource` correspondente (padrão do `@casl/vue`, ver `libs/acl/routeProtection.js`).

### 11.3 Impacto na proposta de simplificação de env vars (§3)

Reforça a proposta já escrita em §3, com um ajuste dado a decisão do §5 (API nova, não dentro do `seducar-api`): a API nova precisa do seu próprio `.env` com as credenciais do banco `seducar` (mirando o único connection do `seducar-api` — `MYSQL_HOST/PORT/USER/PASSWORD/DB_NAME`, sem inventar split leitura/escrita), então "zero variáveis novas" vira "reaproveitar os mesmos 5 nomes de variável de banco do `seducar-api`, num `.env` próprio, com os mesmos valores". Não existe nenhum uso prévio de `openai`/Anthropic em código pra colidir com nomenclatura — **os nomes `AI_TRANSCRIPTION_*`/`AI_CHAT_*` propostos em §3 estão livres para usar exatamente como sugerido** no `.env` da API nova.

---

## 12. Próxima fase do roadmap (registrado, ainda não analisado)

O usuário confirmou que a migração deste repo (`dados_degrau_py`) para a API nova continua além de Transcrições/Chats:

1. **Marketing / GCLIDs / `_pages/relatorios_ia.py`** — próximo passo depois desta parte de análises comerciais. Ainda **não foi lido/inventariado** neste documento — precisa de uma rodada própria de análise (funções, scripts, variáveis de ambiente, gravações no banco), no mesmo formato usado aqui pra Transcrições/Chats.
2. **Migração do SQLite de GCLIDs** — há um banco SQLite local (fora do MySQL `seducar`) usado hoje pelo pipeline de GCLID/marketing que também precisa ser portado, para a API nova conseguir operar sem depender do arquivo local. Ainda não identificado neste documento qual arquivo/módulo gerencia esse SQLite — fica para a rodada de análise do item 1.

Este documento (`MIGRACAO_API_IA.md`) cobre só Transcrições/Chats (§1–11). Quando a análise de Marketing/GCLIDs/`relatorios_ia.py` for feita, deve virar um documento próprio (ex. `MIGRACAO_API_MARKETING.md`) seguindo o mesmo formato, não uma seção emendada aqui — os domínios são independentes.
