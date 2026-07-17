# IMPLEMENTAÇÃO — Avaliação Comercial IA v2026.07 (régua VCA-2026.07)

**Para:** Ulisses (implementação) · Gabriel (Seducar/CRM)
**De:** Velazquez / Claude
**Data:** 15/07/2026
**Documento canônico:** `canonico_v1_avaliacao_comercial.html` (leia antes deste — explica a lógica; este aqui explica o deploy)

---

## 0. Resumo do que muda (1 minuto)

1. **Um juiz só.** O WhatsApp sai do GPT e passa pro **Claude Sonnet 4.6** — mesmo modelo do telefone. Notas dos dois canais ficam comparáveis.
2. **Uma régua só.** Todo o prompt (categorias, pesos, listas fechadas, schema JSON) agora vive em `utils/venda_consultiva_core.py`. Os dois analyzers só consomem. Mudou a régua → muda num lugar.
3. **P1/P2 entram no prompt** como contexto do VENDEDOR (o lead declarou urgência/investimento — ele tratou à altura?). O score do lead pela IA fica **cego** ao P1/P2 (princípio do juiz cego). A comparação declarado × inferido acontece na tab nova **"Bot × IA"** dos dashboards.
4. **Batch deixa de perder metadados.** Manifest local por batch preserva oportunidade + campos octa entre criação e coleta.
5. **Transcrição volta pro CRM** (tabela nova `crm_lead_interacoes`), com inteligência do LEAD. **Avaliação do vendedor NUNCA vai pro CRM** — whitelist hard-coded no writer (política jurídica).
6. **Radar de ligações corrigido** — passa a usar as notas reais por categoria (a proxy antiga fortes/melhorias era estruturalmente enviesada).

---

## 1. Inventário de arquivos

### Novos (copiar para o projeto)
| Arquivo | Papel |
|---|---|
| `utils/venda_consultiva_core.py` | **Fonte única da régua.** Categorias, pesos, listas fechadas, system/user prompts, schema JSON, régua P1/P2, `montar_contexto_qualificacao()`, `normalizar_score_bot()`. |
| `utils/qualificacao_dashboard.py` | Tab compartilhada "Bot × IA" (usada pelos dois dashboards). |
| `utils/crm_sync_writer.py` | Retorno ao CRM com whitelist jurídica. Desligado por default (`CRM_SYNC_ENABLED`). |
| `utils/cats_vendedor.py` | **Substitui o existente** por um shim que reexporta do core. Faça backup do atual antes. |

### Modificados (substituir — mudanças cirúrgicas, resto byte-idêntico)
| Arquivo | Mudanças |
|---|---|
| `utils/chat_ia_analyzer.py` | v3: OpenAI→Anthropic; prompt do core; contexto P1/P2; batch Anthropic. API pública preservada. |
| `utils/transcricao_analyzer.py` | v2: prompt do core; aceita contexto (tipo_ligacao, empresa, P1/P2); `max_tokens` default 6000. |
| `_pages/octadesk.py` | Contexto de qualificação (tempo real **e** batch); manifest de batch; coleta reidrata oportunidade+metadados; seção batch no protocolo Anthropic (`ended`/`succeeded`, `msgbatch_`); inaptos com score `None` (não 0); hook CRM sync; bloco duplicado de erros removido. |
| `_pages/transcricoes.py` | Contexto nas 3 chamadas de avaliação; decorador `@st.cache_data` órfão removido (estava decorando `_formatar_duracao` por acidente); hook CRM sync. |
| `_pages/analise_transcricoes.py` | Loader extrai `notas_pct` + `tlq_status` do JSON; barra "Notas médias por categoria"; **radar com notas reais**; tab "🤝 Bot × IA". |
| `_pages/analise_chats.py` | Loader extrai `tlq_status`; tab "🤝 Bot × IA". |

### Fora deste pacote, mas afetados (ação sua)
| Item | Ação |
|---|---|
| `avaliar_diario.py` (cron 23:30) | Ver §5. Não recebi o arquivo — instruções abaixo. |
| SQLs (`consultas/…`) | Ver §3. |
| `.env` | Ver §4. |
| Seducar (Gabriel) | DDL §6 + exibir timeline da oportunidade. |

---

## 2. Ordem de deploy (siga a sequência)

1. **Backup** dos 6 arquivos que serão substituídos + `utils/cats_vendedor.py`.
2. Copiar os 4 utils novos + 6 substituídos.
3. Atualizar `.env` (§4). **Sem isso o WhatsApp para** (a chave OpenAI não é mais lida).
4. `pip show anthropic` — precisa estar instalado (já está, o canal telefone usa).
5. Atualizar SQLs (§3). *Os códigos funcionam sem as colunas novas (fallback gracioso), mas a tab Bot × IA e o contexto P1/P2 só ligam quando o SQL entregar.*
6. Ajustar `avaliar_diario.py` (§5).
7. Smoke test (§7).
8. (Fase 2, com Gabriel) DDL do CRM (§6) + `CRM_SYNC_ENABLED=1`.

---

## 3. SQLs — colunas novas (aliases canônicos)

> Eu **não** tenho os nomes físicos das colunas de P1/P2 no schema do Seducar — vocês implementaram o armazenamento. Os exports mostram `Pontuação P1`, `Pontuação P2`, `Total Score`, `Etapa`. Mapeie os campos físicos para **estes aliases exatos** (é o contrato que o Python espera):

### 3.1 `consultas/chat_oportunidades/buscar_oportunidades_match.sql`
Adicionar ao SELECT (mantendo as colunas atuais `oportunidade_id`, `chat_id`, `email`, `telefone`):
```sql
SELECT
    o.id                    AS oportunidade_id,
    o.chat_id               AS chat_id,
    i.email                 AS email,
    i.telefone              AS telefone,
    -- ▼ NOVAS (mapear para os campos físicos reais)
    o.<campo_p1>            AS p1_pontos,
    o.<campo_p2>            AS p2_pontos,
    o.<campo_total_score>   AS score_bot_total,
    e.<nome_etapa>          AS etapa_crm
FROM ...
```
Atenção: `Total Score` usa **vírgula decimal** nos exports — o core trata (`_to_float`), mas prefira entregar numérico do banco.

### 3.2 `consultas/transcricoes/transcricoes.sql`
Adicionar (via join com a oportunidade — chave `seducar.interesteds.id` já usada no projeto):
```sql
    o.id                    AS oportunidade_id,
    o.<campo_p1>            AS p1_pontos,
    o.<campo_p2>            AS p2_pontos,
    o.<campo_total_score>   AS score_bot_total
```
*(a coluna `etapa` já existe nessa consulta — mantida como está)*
**Match ligação→oportunidade:** se ainda não existir join direto, use o telefone normalizado (mesma regra do `octadesk.py`: dígitos, remove `55` inicial quando len>11) **com janela temporal** — a oportunidade mais recente criada até 30 dias antes da ligação. Telefone repete entre leads ao longo do tempo; sem janela dá falso positivo.

### 3.3 `consultas/analise_chats/analise_chats.sql`
A tabela de avaliações de chat já grava `opportunity_id`. Adicionar o join para expor:
```sql
    a.opportunity_id        AS oportunidade_id,
    o.<campo_p1>            AS p1_pontos,
    o.<campo_p2>            AS p2_pontos,
    o.<campo_total_score>   AS score_bot_total,
    e.<nome_etapa>          AS etapa_crm
```

### 3.4 Gate no front
As páginas checam `if 'score_bot_total' in df.columns` — enquanto o SQL não entregar, a tab Bot × IA mostra instrução em vez de quebrar. Zero risco de regressão por ordem de deploy.

---

## 4. Variáveis de ambiente

**Adicionar / conferir:**
```
ANTHROPIC_API_KEY=...            # já existe (canal telefone)
CLAUDE_MODEL=claude-sonnet-4-6   # juiz único dos dois canais
CLAUDE_TEMPERATURE=0.2
CLAUDE_MAX_TOKENS=6000           # subiu de 4096 (schema maior; evita truncar)
CLAUDE_MAX_INPUT_CHARS=25000
CLAUDE_MAX_WORKERS=2             # ligações (era 1)
CHAT_CLAUDE_MAX_WORKERS=2        # chats tempo-real
CLAUDE_THROTTLE_SECONDS=4        # era 8; o tier atual aguenta
CRM_SYNC_ENABLED=0               # ligar só na Fase 2 (com o Gabriel)
CRM_SYNC_TABLE=crm_lead_interacoes
```
**Deprecar (podem ser removidas após o smoke test):**
```
OCTADESK_OPENAI_API_KEY, OCTADESK_OPENAI_MODEL, OCTADESK_OPENAI_TEMPERATURE,
OCTADESK_OPENAI_MAX_OUTPUT_TOKENS, OCTADESK_OPENAI_MAX_INPUT_CHARS,
OCTADESK_OPENAI_MAX_WORKERS, OCTADESK_OPENAI_THROTTLE_SECONDS,
OCTADESK_OPENAI_REASONING_EFFORT
```

---

## 5. `avaliar_diario.py` (cron 23:30) — ajustes obrigatórios

Não recebi o arquivo, então aplique por analogia (é o mesmo padrão da página):

1. **Chats:** ao montar cada item do lote, buscar a oportunidade (mesma query do match) e preencher `contexto_adicional=montar_contexto_qualificacao(p1_pontos=…, p2_pontos=…, score_total=…, etapa_crm=…, origem=…, canal_octa=…)`.
2. **Ligações:** idem com `tipo_ligacao=…, empresa=…, etapa_crm=…` + P1/P2 quando o SQL de transcrições expuser.
3. **Se usa Batch:** gravar o **manifest** (chat_id → opportunity_id + metadados + transcript) ao criar, e reidratar na coleta — copie `_salvar_manifest_batch`/`_carregar_manifest_batch` do `_pages/octadesk.py` (ou mova para um util comum).
4. **Coleta de chats:** o `salvar_avaliacao_chat` deve receber `opportunity_id` e os `octa_*` do manifest (hoje o batch salvava tudo `None` — era o bug que deixava as avaliações do cron órfãs).
5. **CRM sync:** após salvar com sucesso e se `CRM_SYNC_ENABLED=1`, chamar `montar_payload_crm` + `sincronizar_interacao_crm` (exemplos prontos nas duas páginas).
6. A classificação de batch da Anthropic usa `processing_status == 'ended'` e `request_counts.succeeded/errored/processing` (não `completed/pending/failed` da OpenAI).

---

## 6. CRM (Gabriel) — Fase 2

DDL proposto (ajuste nome/schema se o padrão do Seducar exigir):
```sql
CREATE TABLE IF NOT EXISTS crm_lead_interacoes (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    opportunity_id  BIGINT NOT NULL,
    school_id       TINYINT NULL,
    canal           VARCHAR(16) NOT NULL,
    origem_id       VARCHAR(64) NOT NULL,
    data_evento     DATETIME NULL,
    agente          VARCHAR(128) NULL,
    transcript      MEDIUMTEXT NULL,
    lead_score      TINYINT UNSIGNED NULL,
    lead_class      CHAR(1) NULL,
    lead_disclaimer TEXT NULL,
    proximo_passo   TEXT NULL,
    mensagem_pronta VARCHAR(512) NULL,
    regua_versao    VARCHAR(16) NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_origem (canal, origem_id),
    KEY idx_opp (opportunity_id),
    KEY idx_data (data_evento)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```
Front: timeline na tela da oportunidade, ordenada por `data_evento`, exibindo canal, agente, transcript (colapsável), classe do lead e a `mensagem_pronta` (botão copiar).

**Política de dados (INEGOCIÁVEL, motivo jurídico-trabalhista):** o writer só grava a whitelist (`crm_sync_writer.py`). `vendor_score`, `vendedor_disclaimer`, notas por categoria, fortes/melhorias, erro mais caro e alertas de compliance **jamais** entram no CRM. Não "melhore" isso adicionando campos — qualquer mudança passa pela diretoria.

**Timestamps:** o ERP grava UTC e o CRM hora local BRT (offset conhecido do projeto). `data_evento` aqui vem do Octadesk/telefonia já convertido para `America/Sao_Paulo` — mantenham assim; não misturem com timestamps do ERP sem converter.

---

## 7. Smoke test (30 min)

1. `python -c "from utils.venda_consultiva_core import build_user_prompt, system_prompt; print(len(system_prompt('whatsapp')), len(build_user_prompt('ligacao','x')))"` → dois números, sem erro.
2. Página Octadesk → escolher **1 chat apto** → "Avaliar Selecionados (Tempo Real)". Conferir no banco: `ai_evaluation` contém `"regua_versao": "VCA-2026.07"` e `"tratamento_lead_qualificado"`.
3. Página Transcrições → avaliar **1 ligação**. Conferir `insight_ia` com os mesmos campos + `contexto_recebido.tipo_ligacao` preenchido.
4. Criar um **batch com 2 chats** → conferir que `batch_manifests/msgbatch_….json` existe → consultar até `ended` → coletar → conferir `opportunity_id` e `octa_agent` gravados.
5. Dashboards abrem sem erro; tab "Bot × IA" mostra instrução (antes do SQL) ou dados (depois).
6. Radar de ligações agora varia de verdade entre agentes (não mais achatado ~50%).

## 8. Validação de qualidade (1ª semana)

- **Amostra paralela:** reavaliar ~30 chats já avaliados pelo GPT com o novo pipeline e comparar distribuição de notas (esperado: correlação alta; nível absoluto pode deslocar alguns pontos — é o novo baseline, documentar no canônico v2).
- **Corte de eras:** análises históricas devem separar antes/depois de 10/07/2026 (mudança da P2) **e** antes/depois do deploy desta versão (mudança de juiz no WhatsApp). O campo `regua_versao` no JSON existe pra isso.
- **Truncamento:** monitorar logs por `max_tokens` — se aparecer, subir `CLAUDE_MAX_TOKENS` para 8000.

## 9. Modelos e custo (referência da decisão)

| Papel | Modelo | Por quê |
|---|---|---|
| Avaliação em massa (diária) | **claude-sonnet-4-6 + Batch (50% off)** | Juiz consistente; caching do system prompt; ~US$0,03/avaliação → ~R$600–800/mês no volume atual dos dois canais. |
| Triagem | **Heurísticas (0 token)** | Já implementado; não usar IA aqui. |
| Piloto de economia (opcional) | claude-haiku-4-5 em 50 avaliações A/B | Só migrar se correlação com Sonnet ≥ 0,9 e disclaimers mantiverem qualidade. ~⅓ do custo. |
| Sínteses estratégicas mensais (analise_geral, auditoria de régua) | Modelo topo (Fable/Opus), pontual | Dezenas de chamadas/mês — custo irrelevante, qualidade máxima. **Nunca** usar em lote diário. |

*Preços de tabela mudam — confirme em docs.claude.com/pricing antes de projetar orçamento.*

## 10. Rollback

Restaurar os backups do §2.1 + `.env` anterior. Os dados gravados pela versão nova continuam legíveis pelos dashboards antigos (schema JSON é retrocompatível — chaves novas são ignoradas por quem não as lê).

---
*Dúvidas de intenção/lógica → HTML canônico. Dúvidas de código → docstrings dos módulos novos.*
