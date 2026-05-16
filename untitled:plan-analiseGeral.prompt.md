## Plan: Análise Geral Integrada

Criar uma nova página Streamlit de análise comercial e de marketing orientada a IA, usando a oportunidade (`seducar.interesteds.id`) como grão principal, separando Degrau e Central em toda a cadeia de dados, e reaproveitando o fluxo já existente de Claude/HTML/histórico de relatórios. O caminho mais coerente com o projeto é usar `consultas/analise_geral/` (não `queries/`) e montar um payload agregado por empresa, com visão comparativa apenas na interface, nunca no prompt principal.

**Steps**

1. Fase 1 — Canonicalização dos dados: definir a oportunidade como hub principal da análise. A nova base deve partir de `seducar.interesteds i`, expondo `i.id` como `oportunidade_id`, `i.customer_id` como `cliente_id`, `i.created_at` como data da oportunidade, `i.school_id` como separador de empresa e os campos de origem/campanha já existentes. Esta etapa bloqueia todas as demais.
2. Fase 1 — Cruzamento de vendas: ligar vendas a oportunidades por `orders.customer_id -> interesteds.customer_id`, preservando a granularidade para evitar duplicidade. Como um cliente pode ter múltiplas oportunidades e múltiplas ordens, a query base deve pré-agregar orders por `cliente_id` e por janela temporal antes do join, ou manter um join controlado com regras explícitas para “primeira venda”, “última venda” e “venda no período”. _depends on 1_
3. Fase 1 — Cruzamento de chats: preferir `seducar.chat_ai_evaluations.opportunity_id` como vínculo primário do chat com a oportunidade, usando `chat_id -> interesteds.chat_id` apenas como fallback. A data analítica obrigatória do chat deve ser `octa_created_at`, nunca `created_at` do registro da avaliação. _depends on 1_
4. Fase 1 — Cruzamento de transcrições: usar `seducar.opportunity_transcripts.opportunity_id = seducar.interesteds.id` e filtrar temporalmente por `ot.date` (`data_ligacao`), nunca pelo horário em que a avaliação foi salva em `transcription_ai_summaries`. _depends on 1_
5. Fase 1 — Relatórios de marketing: criar um loader específico para localizar o relatório mais recente de marketing no histórico atual (`ai_reports`) por `type`, `reference_date` e indício de empresa em `raw_data`, com fallback para indisponível quando não houver correspondência robusta. Não depender de schema novo em `ai_reports` na primeira iteração. _parallel with 2-4 after 1_
6. Fase 2 — Queries dedicadas: criar a pasta `consultas/analise_geral/` com queries focadas e legíveis. Estrutura recomendada: uma query base em grão de oportunidade + queries agregadas complementares apenas quando a agregação em SQL reduzir muito o volume de dados para a IA. Evitar reaproveitar queries antigas com `SELECT *` ou joins que multipliquem linhas. _depends on 2-5_
7. Fase 2 — Normalização temporal: padronizar todas as datas no fuso `America/Sao_Paulo` e usar sempre filtro semiaberto `[data_inicio, data_fim + 1 dia)` na nova página, seguindo o padrão das páginas atuais. Campos canônicos: oportunidade = `criacao`, chat = `data_chat`, ligação = `data_ligacao`, venda = `data_pagamento`. _depends on 6_
8. Fase 2 — Agregações comerciais: montar DataFrames agregados por empresa para vendas/matrículas, oportunidades, funil por etapa, conversão por vendedor, conversão por concurso/modalidade, origem/campanha e atribuição lead→venda. Tratar `dono` da oportunidade e `vendedor` da ordem como papéis distintos, com alerta quando divergirem, em vez de forçar um único “responsável” artificial. _depends on 7_
9. Fase 2 — Agregações de atendimento: reaproveitar a lógica de parsing já existente para chats e transcrições e produzir tabelas e amostras qualitativas curtas: score médio por vendedor, score por categoria, objeções recorrentes, pontos fortes, pontos fracos e erros mais caros. Limitar evidências qualitativas a blocos agregados/top-N; não enviar transcrição bruta completa à IA. _depends on 7_
10. Fase 2 — Métricas condicionais: tratar `speed-to-lead` e `tempo_resposta_chat` como métricas condicionais. Se houver disponibilidade segura do cache Octadesk (por exemplo, `bot.firstHumanResponseAt` ou dados equivalentes), calcular; se não houver fonte confiável para o período, marcar explicitamente como indisponível/inconclusivo no payload e na interface. _depends on 7_
11. Fase 3 — Prompt e payload: criar `utils/prompts/analise_geral_prompt.py` com constantes Python extraídas de `prompt_analise_estrategica.md` e um helper local para transformar DataFrames em tabelas markdown truncadas (ex.: top 50 linhas). O payload deve ser montado separadamente por empresa, obedecendo a estrutura dos 6 blocos do prompt. _depends on 8-10_
12. Fase 3 — Página Streamlit: criar `_pages/analise_geral.py` no padrão visual das páginas atuais, com sidebar para empresa/período/filtros, abas para visão executiva, visão comparativa opcional, payload enviado e relatório IA. A visão comparativa pode existir na UI, mas a chamada de IA deve rodar por empresa para cumprir a regra do prompt de nunca consolidar Degrau e Central. _depends on 11_
13. Fase 3 — IA e persistência: reaproveitar o cliente Anthropic, retry e export HTML do fluxo de `relatorios_ia.py`. Para persistência inicial, salvar o novo relatório usando o mecanismo atual e embutir metadados adicionais (empresa, intervalo, modelo, payload, tokens quando disponíveis) dentro de `raw_data`/JSON ou no fallback local, evitando depender de migração imediata do schema `ai_reports`. _depends on 12_
14. Fase 3 — Navegação: adicionar `analise_geral` ao bloco de imports e ao dicionário `PAGES` em `main.py`, seguindo exatamente o padrão atual de registro de páginas. _parallel with 13 once file name is fixed_
15. Fase 4 — Validação funcional: comparar contagens do novo fluxo com as páginas atuais para o mesmo período/empresa, confirmando equivalência de datas e ausência de duplicidade. Validar especificamente: total de vendas vs `matriculas.py`, cruzamento `cliente_id` e origem/campanha vs `analise_mensal.py`, total de chats vs `analise_chats.py`, total de ligações vs `analise_transcricoes.py`. _depends on 12-14_
16. Fase 4 — Validação do relatório IA: gerar payload curto para cada empresa, revisar volume de tokens, rodar a análise e em seguida o botão “Validar uso dos dados” sugerido no prompt para identificar blocos subutilizados. _depends on 13-15_

**Relevant files**

- `/var/home/ulissesoliveira/dados_degrau_py/_pages/analise_geral.py` — nova página principal; conterá filtros, loaders, agregações, montagem de payload e acionamento da IA
- `/var/home/ulissesoliveira/dados_degrau_py/main.py` — import e registro da nova página no menu
- `/var/home/ulissesoliveira/dados_degrau_py/consultas/analise_geral/base_oportunidades.sql` — query canônica em grão de oportunidade, com joins controlados de vendas/chats/transcrições
- `/var/home/ulissesoliveira/dados_degrau_py/consultas/analise_geral/vendas_agregadas.sql` — agregações de vendas/matrículas por período, vendedor, modalidade e concurso, se a redução via SQL trouxer ganho real
- `/var/home/ulissesoliveira/dados_degrau_py/consultas/analise_geral/atendimento_chats.sql` — agregados e evidências curtas de chats, priorizando `opportunity_id` e `octa_created_at`
- `/var/home/ulissesoliveira/dados_degrau_py/consultas/analise_geral/atendimento_ligacoes.sql` — agregados e evidências curtas de transcrições, usando `ot.opportunity_id` e `ot.date`
- `/var/home/ulissesoliveira/dados_degrau_py/consultas/analise_geral/marketing_report_lookup.sql` — lookup do relatório de marketing no histórico atual, com fallback controlado
- `/var/home/ulissesoliveira/dados_degrau_py/utils/prompts/analise_geral_prompt.py` — constantes do system prompt e template do user prompt
- `/var/home/ulissesoliveira/dados_degrau_py/_pages/relatorios_ia.py` — reutilizar cliente Anthropic, renderização HTML e padrão de histórico; modificar só se a extração de helpers for realmente necessária
- `/var/home/ulissesoliveira/dados_degrau_py/_pages/analise_mensal.py` — referência de cruzamento `cliente_id`, GCLID, oportunidades e transcrições
- `/var/home/ulissesoliveira/dados_degrau_py/_pages/analise_chats.py` — referência de parsing/normalização dos campos de avaliação de chat
- `/var/home/ulissesoliveira/dados_degrau_py/_pages/analise_transcricoes.py` — referência de parsing/normalização dos campos de avaliação de transcrição
- `/var/home/ulissesoliveira/dados_degrau_py/_pages/octadesk.py` — referência do fluxo temporal real do chat e do matching operacional com oportunidades
- `/var/home/ulissesoliveira/dados_degrau_py/_pages/transcricoes.py` — referência do fluxo temporal real da ligação e das regras de avaliabilidade

**Verification**

1. Comparar o total de vendas por empresa/período da nova base com `consultas/orders/orders.sql` filtrada pela mesma lógica de `matriculas.py`.
2. Comparar o total de oportunidades por empresa/período com `consultas/oportunidades/oportunidades.sql` e conferir que a data usada é `criacao`.
3. Comparar o total de chats por empresa/período com `consultas/analise_chats/analise_chats.sql`, garantindo uso de `data_chat` e não `data_criacao_sistema`.
4. Comparar o total de transcrições por empresa/período com `consultas/transcricoes/transcricoes.sql`, garantindo uso de `data_ligacao` e não `data_trancricao`.
5. Fazer teste dirigido com um cliente que tenha múltiplas oportunidades e múltiplas ordens para provar que o join por `cliente_id` não duplica receita nem volume.
6. Fazer teste dirigido com um chat que tenha `opportunity_id` salvo em `chat_ai_evaluations` e outro que dependa de fallback por `chat_id`, confirmando consistência do `oportunidade_id` final.
7. Verificar que Degrau e Central geram payloads separados e que a chamada da IA nunca mistura métricas das duas empresas.
8. Verificar que métricas não suportadas por fonte confiável (especialmente `speed-to-lead`) aparecem explicitamente como indisponíveis/inconclusivas, e não como estimativas inventadas.
9. Validar o lookup do relatório de marketing: se houver correspondência robusta por período/empresa, ele entra no payload; se não houver, a interface e o payload registram ausência do dado.
10. Rodar a validação pós-relatório (“Validar uso dos dados”) em um período curto e revisar se o prompt de fato utilizou os blocos 1 a 6.

**Decisions**

- Caminho de queries: usar `consultas/analise_geral/`, porque o padrão do projeto inteiro é `consultas/`, não `queries/`.
- Chave canônica de oportunidade: `seducar.interesteds.id` (`oportunidade` / `oportunidade_id`).
- Chave de venda: `customer_id`, normalizado como `cliente_id`; não há evidência encontrada de `custumer_id` no código investigado.
- Chave de chat: preferir `chat_ai_evaluations.opportunity_id`; usar `chat_id` apenas como fallback ou reconciliação.
- Chave de transcrição: `opportunity_transcripts.opportunity_id`.
- Datas canônicas: oportunidade=`i.created_at`; chat=`c.octa_created_at`; ligação=`ot.date`; venda=`o.paid_at`.
- Separação por empresa: Degrau e Central sempre analisadas separadamente no payload e na IA; comparação consolidada, se existir, fica restrita à UI.
- Escopo inicial: não alterar queries antigas nem quebrar páginas existentes; reaproveitar o que já funciona e criar superfícies novas isoladas.
- Persistência inicial: não depender de migração imediata da tabela `ai_reports`; usar o schema atual com metadados serializados quando necessário.

**Further Considerations**

1. O schema atual de `ai_reports` não guarda empresa/data_inicio/data_fim em colunas próprias; isso permite uma primeira versão com lookup heurístico, mas não garante rastreabilidade forte. Se o uso recorrente da análise geral virar rotina, uma migração dedicada de histórico passa a ser recomendável.
2. `speed-to-lead` real parece depender de dados do Octadesk/cache (`bot.firstHumanResponseAt` e correlatos), não das tabelas SQL analíticas hoje usadas pelas páginas de análise. A primeira versão deve tratar essa métrica como condicional e nunca inferi-la sem fonte explícita.
3. Para métricas por vendedor, vale preservar dois eixos no payload: `dono` da oportunidade (responsável pelo funil) e `vendedor` da ordem (responsável pela venda), porque o projeto atual já trata esses papéis separadamente em queries e páginas existentes.
