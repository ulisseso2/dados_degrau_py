# 🤖 Prompt para Agente IA — Projeto Degrau Transcrições

> **Uso:** Cole este prompt no início de uma nova conversa com qualquer agente de IA (GitHub Copilot, Claude, GPT, etc.) para que ele entenda o projeto e possa dar continuidade sem precisar re-explorar o código.

---

## PROMPT PARA COPIAR

```
Você é um assistente especialista em Python/Streamlit/MySQL e vai continuar
o desenvolvimento de um sistema de análise de transcrições de ligações de vendas.

LEIA OBRIGATORIAMENTE antes de qualquer ação:
1. README_TRANSCRICOES.md   — arquitetura completa, banco, SQL, páginas, gráficos
2. SISTEMA_AVALIACAO_IA.md  — modelos GPT, fluxo IA, restrições de API, troubleshooting

Resumo do projeto para contexto rápido:

SISTEMA:
- Streamlit multi-página rodando na Streamlit Cloud (Python 3.11)
- Banco: MySQL `seducar` (RDS ou instância gerenciada)
- IA: OpenAI GPT-5.1 (avaliação SPIN) + GPT-5-nano (classificação)
- Repositório: /home/ulisses/dados_degrau_py (branch master)

ARQUIVOS PRINCIPAIS:
- _pages/transcricoes.py          → Página: avaliar ligações em lote
- _pages/analise_transcricoes.py  → Página: dashboards (5 abas + relatório)
- utils/transcricao_analyzer.py   → Engine IA (TranscricaoOpenAIAnalyzer)
- utils/transcricao_mysql_writer.py → Persistência MySQL (upsert duplo)
- consultas/transcricoes/transcricoes.sql  → Query principal
- consultas/transcricoes/contexto.txt      → Prompt SPIN para GPT-5.1

REGRAS CRÍTICAS DE NÃO QUEBRAR:
1. GPT-5-nano NÃO aceita `temperature` nem `response_format` — HTTP 400
2. GPT-5.1 usa `max_completion_tokens`, NÃO `max_tokens` (legado) — HTTP 400
3. `type_` ao salvar avaliação: SEMPRE de `row_data.get('tipo_ligacao')` (banco), nunca da IA
4. `_sanitize()` DEVE ser chamada antes de qualquer valor numérico ir ao MySQL (NaN crash)
5. `st.cache_data.clear()` deve ser chamado após qualquer avaliação bem-sucedida
6. "outros" NÃO está em TIPOS_SKIP — sempre avalia com GPT-5.1
7. SQL usa COALESCE(coluna, JSON_EXTRACT(original_transcript, '$.campo')) para agent/duration/type

MODELOS EM USO:
- Avaliação: gpt-5.1, temperature=0.2, max_completion_tokens=8000
- Classificação: gpt-5-nano, max_completion_tokens=300, SEM temperature

BANCO DE DADOS:
- Tabela principal: seducar.opportunity_transcripts (ot)
- Tabela avaliações: seducar.transcription_ai_summaries (tais)
- Campo JSON bruto: ot.original_transcript ($.agente, $.duracao, $.tipo, $.telefone)
- Campo JSON avaliação: tais.ai_insight (estrutura SPIN completa)

ESTRUTURA DO JSON ai_insight:
{
  "avaliacao_vendedor": {
    "nota_final_0_100": int,
    "pontos_fortes": [{"categoria": str, "ponto": str}],
    "melhorias": [{"categoria": str, "melhoria": str}],
    "erro_mais_caro": {"categoria": str, "descricao": str}
  },
  "avaliacao_lead": {"lead_score_0_100": int, "classificacao": "A|B|C|D"},
  "extracao": {"concurso_area": str, "dores_principais": [], "restricoes": []},
  "recomendacao_final": {"produto_principal": {"produto": str}, "justificativa": str},
  "classificacao_ligacao": str,
  "motivo_classificacao": str,
  "confianca_classificacao": float
}

CATEGORIAS SPIN: rapport, investigacao_spin, valor_produto, gatilho_mental,
                 objecao, fechamento, clareza, outros

TIPOS_SKIP (não avalia com GPT-5.1):
ura, dados_insuficientes, dialogo_incompleto, ligacao_interna,
chamada_errada, cancelamento, suporte

GRÁFICOS EXISTENTES (NÃO recriar sem razão):
- Aba 1 Visão Geral: stacked bar+line diário, pie donut leads, bar duração, bar produtos
- Aba 2 Ranking: bar horizontal notas, bubble scatter vol×qualidade, stacked bar A/B/C/D
- Aba 3 Qualidade Leads: bar classificação, box plot, scatter nota×score, bar áreas, area chart
- Aba 4 SPIN: bar fortes, bar melhorias, radar scatterpolar top-5 agentes
- Aba 5 Relatório Individual: line evolução, pie leads, bar produtos, pontos, tabela, HTML/PDF

DEPENDÊNCIAS (requirements.txt):
streamlit, pandas, plotly, openai>=1.0, sqlalchemy, pymysql, python-dotenv

Estou pronto para receber sua tarefa específica.
```

---

## Guia de Uso

### Quando usar este prompt

- Ao iniciar uma **nova sessão** com um agente IA
- Após perda de contexto em conversas longas
- Ao compartilhar o projeto com outro desenvolvedor usando IA

### O que o agente vai saber após ler

✅ Quais modelos GPT usar e suas restrições  
✅ Estrutura do banco de dados MySQL  
✅ Quais arquivos modificar para cada tipo de tarefa  
✅ Regras de negócio críticas (TIPOS_SKIP, COALESCE, sanitize, cache)  
✅ Estrutura JSON completa do `ai_insight`  
✅ Todos os gráficos existentes (evita duplicação)  

### Arquivos de referência completa

Para tarefas mais complexas, peça ao agente para ler:

```
README_TRANSCRICOES.md    → Documentação completa (arquitetura, SQL, páginas, gráficos)
SISTEMA_AVALIACAO_IA.md   → Engine IA, restrições API, troubleshooting
```

### Exemplos de tarefas para pedir ao agente

**Novos gráficos:**
> "Leia README_TRANSCRICOES.md e adicione na Aba 3 um gráfico de funil mostrando conversão por etapa."

**Novos filtros:**
> "Leia SISTEMA_AVALIACAO_IA.md e README_TRANSCRICOES.md. Adicione na sidebar da analise_transcricoes.py um filtro por nota mínima."

**Bug fix:**
> "Há um erro X na linha Y de _pages/transcricoes.py. Leia o README_TRANSCRICOES.md para entender o contexto antes de corrigir."

**Nova feature de IA:**
> "Leia SISTEMA_AVALIACAO_IA.md. Quero adicionar um campo 'proximos_passos' no JSON de avaliação. Me mostre o que precisa mudar."

---

## Histórico de Decisões Técnicas

Mantenha atualizado para o agente entender o contexto histórico:

| Data | Decisão | Motivo |
|---|---|---|
| Fev 2026 | Migração gpt-4o → gpt-5.1 | Melhor qualidade de avaliação SPIN |
| Fev 2026 | Migração gpt-4o-mini → gpt-5-nano | Classificação mais rápida e barata |
| Fev 2026 | Removido `response_format` de ambas as chamadas | GPT-5 não suporta este parâmetro |
| Fev 2026 | Removido `temperature` da classificação | GPT-5-nano não aceita este parâmetro |
| Fev 2026 | `max_tokens` → `max_completion_tokens` | GPT-5 usa nova nomenclatura |
| Fev 2026 | `_sanitize()` adicionado ao writer | np.float64(nan) crashava o MySQL |
| Fev 2026 | `"outros"` removido do TIPOS_SKIP | Ligações "outros" precisam de SPIN |
| Fev 2026 | `type_` vem sempre do banco, não da IA | Preserva tipo original do sistema de telefonia |
| Fev 2026 | SQL COALESCE agent/duration/type | Registros legados têm NULL nas colunas diretas |
| Fev 2026 | Retry loop na classificação | GPT-5-nano retornava vazio ocasionalmente |
| Fev 2026 | `_gerar_html_relatorio` recebe `df_raw` | PDF precisava dos dados brutos para gráficos CSS |
