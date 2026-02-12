# 🤖 Sistema de Avaliação de Transcrições com IA

## 📋 Visão Geral

Sistema para avaliar automaticamente transcrições de ligações de vendas usando IA (OpenAI GPT-4o-mini), com armazenamento local temporário em SQLite antes da sincronização com o banco principal.

## 🏗️ Arquitetura

```
┌─────────────────────┐
│  transcricoes.py    │  ← Interface Streamlit
│  (Frontend)         │
└──────────┬──────────┘
           │
           ├─────────────────────────────────┐
           │                                 │
           v                                 v
┌──────────────────────────┐   ┌──────────────────────────┐
│ transcricao_ia_analyzer  │   │ transcricao_avaliacao_db │
│ (Análise com IA)         │   │ (SQLite Local)           │
└──────────────────────────┘   └──────────────────────────┘
           │                                 │
           │                                 │
           v                                 v
    [OpenAI API]                  [transcricoes_avaliacoes.db]
                                              │
                                              │ (Posteriormente)
                                              v
                                  [seducar.opportunity_transcripts]
```

## 📦 Componentes

### 1. **transcricao_ia_analyzer.py**

**Responsabilidade:** Análise de transcrições usando IA

**Características:**

- ✅ Prompt otimizado (consome ~500-1000 tokens por análise)
- ✅ Resposta estruturada em JSON
- ✅ Análise focada em pontos essenciais
- ✅ Suporte a análise em lote

**Campos Analisados:**

- **Classificação:** válida | correio_voz | desligou | nao_atendeu | erro
- **Qualidade:** excelente | boa | regular | ruim
- **Pontos Positivos:** Lista breve (máx 3 itens)
- **Pontos de Melhoria:** Lista breve (máx 3 itens)
- **SPIN Selling:** Avalia 4 etapas (Situação, Problema, Implicação, Necessidade)
- **Resumo:** 1-2 frases sobre a ligação

**Otimizações:**

- Limita transcrição a 2000 caracteres
- Usa `response_format={"type": "json_object"}` para garantir JSON
- Configurável via `.env` (model, temperature, max_tokens)

### 2. **transcricao_avaliacao_db.py**

**Responsabilidade:** Gerenciamento do banco SQLite local

**Tabela: `avaliacoes_transcricoes`**

```sql
- oportunidade_id (chave única)
- transcricao, ramal, origem_ramal, nome_lead, telefone_lead
- classificacao_ligacao, qualidade_atendimento
- pontos_positivos, pontos_melhoria
- spin_situacao, spin_problema, spin_implicacao, spin_necessidade
- notas_ia, comentarios_usuario
- avaliado_em, atualizado_em, status, sincronizado
```

**Métodos Principais:**

- `salvar_avaliacao()` - Insere/atualiza avaliação
- `buscar_avaliacao()` - Busca por oportunidade_id
- `listar_avaliacoes()` - Lista todas (com filtro opcional)
- `marcar_sincronizado()` - Marca como enviado ao banco principal
- `exportar_nao_sincronizados()` - CSV para importação
- `estatisticas()` - Métricas do sistema

### 3. **transcricoes.py (modificado)**

**Responsabilidade:** Interface Streamlit

**Novas Funcionalidades:**

- 📊 Dashboard com estatísticas de avaliações
- 🎤 Expansores por transcrição (mostra primeiros 20)
- 🤖 Botão "Avaliar com IA" para cada registro
- ✅ Indicador visual de avaliações concluídas
- 📝 Campo para comentários adicionais do usuário
- 💾 Botões de exportação (todas / pendentes sincronização)

## 🚀 Fluxo de Uso

### 1. **Carregar Página**

```
Usuario acessa transcricoes.py
↓
Sistema carrega dados do MySQL (consulta SQL)
↓
Exibe dashboard com métricas e filtros
```

### 2. **Avaliar Transcrição**

```
Usuario clica em "🤖 Avaliar com IA"
↓
TranscricaoIAAnalyzer.analisar_transcricao()
↓
OpenAI processa prompt otimizado
↓
Retorna JSON estruturado
↓
TranscricaoAvaliacaoDB.salvar_avaliacao()
↓
Dados salvos em SQLite local
↓
Interface atualiza (st.rerun())
```

### 3. **Revisar Avaliação**

```
Usuario clica em "Ver Avaliação"
↓
Sistema busca dados do SQLite
↓
Exibe resultados da IA
↓
Usuario adiciona comentários
↓
Salva comentários no SQLite
```

### 4. **Exportar para Sincronização**

```
Usuario clica em "Baixar Pendentes de Sincronização"
↓
Sistema exporta CSV com avaliacoes não sincronizadas
↓
[FUTURO] Importa CSV para seducar.opportunity_transcripts
↓
Marca registros como sincronizados
```

## ⚙️ Configuração

### Arquivo `.env`

```env
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o
OPENAI_TEMPERATURE=0.2
OPENAI_MAX_TOKENS=6000
OPENAI_MAX_INPUT_CHARS=12000
OPENAI_MAX_INPUT_CHARS_CLASSIFICACAO=4000
```

### Banco SQLite

- **Localização:** `transcricoes_avaliacoes.db` (raiz do projeto)
- **Criação:** Automática na primeira execução
- **Backup:** Recomendado backup periódico do arquivo .db

## 📊 Custo Estimado

**Por Análise:**

- Tokens de entrada: ~400-600 (prompt + transcrição limitada)
- Tokens de saída: ~200-400 (resposta JSON)
- **Total médio:** 600-1000 tokens

**Custo GPT-4o-mini:**

- Input: $0.150 / 1M tokens
- Output: $0.600 / 1M tokens
- **~$0.0003 - $0.0005 por análise** (~R$ 0,0015 - R$ 0,0025)

**Para 1000 análises:** ~$0.30-$0.50 (~R$ 1,50 - R$ 2,50)

## 🔄 Próximos Passos

### Fase 1: Testes (Atual)

- ✅ Sistema básico funcional
- ✅ Armazenamento local SQLite
- ✅ Interface de avaliação
- ⏳ Testes com amostras pequenas (20-50 registros)

### Fase 2: Refinamento

- 🔄 Ajuste do prompt baseado em feedback
- 🔄 Adicionar mais filtros (por classificação, qualidade)
- 🔄 Dashboard de análise de avaliações
- 🔄 Gráficos de distribuição (classificação, qualidade, SPIN)

### Fase 3: Sincronização

- ⏳ Script de importação CSV → MySQL
- ⏳ Atualização de `seducar.opportunity_transcripts`
- ⏳ Adicionar colunas necessárias no banco principal
- ⏳ Processo de sincronização automática

### Fase 4: Produção

- ⏳ Análise em lote (múltiplas transcrições)
- ⏳ Agendamento automático (cron job)
- ⏳ Notificações de ligações com qualidade ruim
- ⏳ Integração com CRM para ações automáticas

## 🐛 Troubleshooting

### Erro: "cannot access local variable"

**Causa:** Variável usada antes de ser definida
**Solução:** Verificar ordem de definição no código

### Erro: "No API key provided"

**Causa:** OPENAI_API_KEY não configurada
**Solução:** Verificar arquivo `.env` e carregar com `load_dotenv()`

### Erro: "JSONDecodeError"

**Causa:** IA retornou resposta mal formatada
**Solução:** Sistema já trata com try/except, retorna classificacao='erro'

### Banco SQLite travado

**Causa:** Múltiplas escritas simultâneas
**Solução:** SQLite é single-writer, sistema já sequencial

## 📝 Exemplo de Uso

```python
# Inicializar componentes
from utils.transcricao_avaliacao_db import TranscricaoAvaliacaoDB
from utils.transcricao_ia_analyzer import TranscricaoIAAnalyzer

db = TranscricaoAvaliacaoDB()
ia = TranscricaoIAAnalyzer()

# Analisar transcrição
transcricao = "Cliente: Olá, quero saber sobre o curso..."
analise = ia.analisar_transcricao(transcricao)

# Salvar resultado
avaliacao = {
    'oportunidade_id': 12345,
    'transcricao': transcricao,
    **analise
}
db.salvar_avaliacao(avaliacao)

# Buscar avaliação
resultado = db.buscar_avaliacao(12345)
print(resultado['classificacao_ligacao'])

# Exportar pendentes
pendentes = db.exportar_nao_sincronizados()
pendentes.to_csv('pendentes.csv', index=False)
```

## 📌 Observações Importantes

1. **Limites:** Interface mostra apenas 20 primeiros registros (performance)
2. **Token Limit:** Transcrições truncadas em 2000 caracteres
3. **Filtragem:** Checkbox "Mostrar apenas registros com transcrição" ativo por padrão
4. **Reprocessamento:** Pode reavaliar registros já avaliados (sobrescreve)
5. **Backup:** SQLite é arquivo único, fácil de fazer backup/restaurar

## 🎯 Métricas de Sucesso

- ✅ Tempo médio de análise: 2-5 segundos
- ✅ Custo por análise: <R$ 0,003
- ✅ Taxa de erro: <5%
- ✅ Cobertura SPIN: identificado em 80%+ das ligações válidas

---

**Criado em:** Janeiro 2026  
**Versão:** 1.0  
**Autor:** Sistema de Análise de Transcrições
