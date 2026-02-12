# Análise de Transcrições de Ligações

## 📋 Visão Geral

Sistema completo de análise de transcrições de ligações de vendas com:

- **Análise Quantitativa**: Métricas, gráficos e estatísticas
- **Análise Qualitativa com IA**: Classificação automática de ligações (válidas, caixa postal, etc.)
- **Avaliação SPIN Selling**: Análise detalhada usando metodologia SPIN (Situação, Problema, Implicação, Necessidade)
- **Sistema de Avaliações**: Banco de dados SQLite para armazenar avaliações de transcrições com IA (Groq API)

## 🚨 ESTADO ATUAL - Janeiro 2026

### ⚠️ PROBLEMAS CRÍTICOS IDENTIFICADOS (NÃO RESOLVIDOS)

#### 1. BUG CRÍTICO: Migration Script com Dados Incorretos

**Status**: 🔴 CRÍTICO - Bloqueando funcionalidade de avaliações

**Problema**: O script de migração `migrar_transcricoes_hash.py` populou a coluna `transcricao_hash` com o TEXTO COMPLETO das transcrições ao invés dos hashes MD5.

**Evidência**:

```python
# Output do banco de dados:
Primeiros hashes salvos: ['Vendedor: De grau cultural, Marilene, boa tarde...']
# ^ Isso é TEXTO, deveria ser: 'd35a09cb262c8ee65787bf846978a7f7'

# Output correto sendo gerado na UI:
Primeiros hashes gerados: ['38fa4cc9ff84ec498d18c2deebab7eb5', 'be2ec5230fd5f8d689521280d07b4cef']
# ^ Estes são hashes MD5 válidos
```

**Impacto**:

- Comparação de hashes falhando (compara MD5 vs texto completo)
- Status "Avaliada" nunca aparece na tabela
- Sistema não consegue detectar transcrições já avaliadas

**Próxima Ação Necessária**:

1. Corrigir `migrar_transcricoes_hash.py` para gerar hashes MD5 corretamente
2. Re-executar migração em todos os 11-12 registros existentes
3. Verificar que transcricao_hash agora contém strings de 32 caracteres hexadecimais

#### 2. BUG CRÍTICO: Análise IA Retornando Erros

**Status**: 🔴 CRÍTICO - Bloqueando novas avaliações

**Problema**: O `TranscricaoIAAnalyzer.analisar_transcricao()` está retornando `{'erro', 'classificacao_ligacao'}` ao invés de uma avaliação válida.

**Evidência**:

```python
Análise retornada: ['erro', 'classificacao_ligacao']
# Esperado: dict com chaves como 'nota_vendedor', 'lead_score', 'avaliacao_completa', etc.
```

**Possíveis Causas**:

- Chave API Groq inválida ou expirada
- Formato do prompt incompatível com modelo atual
- Mudança na API do Groq (resposta em formato diferente)
- Limite de tokens/rate limit atingido
- Erro de parsing do JSON retornado pela IA

**Próxima Ação Necessária**:

1. Verificar arquivo `utils/transcricao_ia_analyzer.py` linhas 46-103
2. Testar chamada à API Groq isoladamente
3. Verificar variáveis de ambiente com chaves da API
4. Adicionar tratamento de erro mais robusto
5. Logar resposta bruta da API antes do parsing

### ✅ MELHORIAS IMPLEMENTADAS (ÚLTIMAS 24H)

#### Correções de Bugs

1. **IndentationError Corrigido**: Alinhamento incorreto em `transcricao_ia_analyzer.py:85`
2. **Database Locked Resolvido**: Adicionado `timeout=30.0` em todas as conexões SQLite
3. **NOT NULL Constraint Corrigido**: Tornado `oportunidade_id` nullable no schema
4. **Duplicate Streamlit Keys**: Adicionado `idx` nos keys de checkboxes e botões

#### Novas Funcionalidades

1. **Sistema de Hashing**:
   - Função `gerar_hash()` usando MD5 para identificar transcrições unicamente
   - Coluna `transcricao_hash` adicionada ao banco
   - Permite identificar transcrições sem oportunidade_id

2. **UI de Seleção**:
   - Checkboxes para selecionar quais transcrições avaliar
   - Botão "👁️ Ver" para preview antes de avaliar
   - Coluna "Avaliada" mostrando status (Sim/Pendente)

3. **Migração de Dados**:
   - Script `migrar_transcricoes_hash.py` criado
   - 12 registros migrados com sucesso
   - Schema atualizado (oportunidade_id nullable + transcricao_hash)

#### Debug e Monitoramento

- Logging extensivo adicionado em `_pages/transcricoes.py`
- Logging em `utils/transcricao_avaliacao_db.py`
- Prints de debug mostrando fluxo de dados completo

## 🚀 Como Usar

### 1. Configuração Inicial

#### Dependências Principais

```bash
pip install streamlit pandas plotly groq python-dotenv
# Groq API para análise com IA (substituiu OpenAI)
```

#### Configurar variáveis de ambiente

Crie um arquivo `.env` na raiz do projeto:

```bash
# API Groq para análise de transcrições
GROQ_API_KEY=sua_chave_groq_aqui
GROQ_MODEL=llama-3.3-70b-versatile

# (Opcional) OpenAI - se ainda usar para outras análises
OPENAI_API_KEY=sua_chave_openai_aqui
OPENAI_MODEL=gpt-4o
OPENAI_TEMPERATURE=0.2
OPENAI_MAX_TOKENS=6000
OPENAI_MAX_INPUT_CHARS=12000
OPENAI_MAX_INPUT_CHARS_CLASSIFICACAO=4000
```

### 2. Executar a Análise

Execute o Streamlit:

```bash
streamlit run main.py
```

Navegue até: **📞 Transcrições**

### 3. Sistema de Avaliações (Nova Funcionalidade)

#### Banco de Dados: `transcricoes_avaliacoes.db` (SQLite)

**Schema da Tabela `avaliacoes`**:

```sql
CREATE TABLE avaliacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    oportunidade_id INTEGER,  -- NULLABLE (nem todas transcrições têm oportunidade)
    transcricao_hash TEXT UNIQUE NOT NULL,  -- MD5 hash para identificação única
    transcricao TEXT NOT NULL,
    ramal TEXT,
    origem_ramal TEXT,
    nome_lead TEXT,
    telefone_lead TEXT,
    avaliacao_completa TEXT,  -- JSON completo da resposta da IA
    nota_vendedor REAL,
    lead_score REAL,
    lead_classificacao TEXT,
    concurso_area TEXT,
    produto_recomendado TEXT,
    data_avaliacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX idx_transcricao_hash ON avaliacoes(transcricao_hash);
```

#### Workflow de Avaliação

1. **Tab "Avaliar Transcrições"**:
   - Carrega transcrições do banco MySQL (opportunity_transcripts)
   - Exibe checkboxes para seleção
   - Botão "👁️ Ver" para preview da transcrição
   - Coluna "Avaliada" mostra status (Sim/Pendente)
   - Botão "Avaliar Selecionadas" processa em lote

2. **Processamento**:
   - Gera hash MD5 da transcrição: `hashlib.md5(texto.encode()).hexdigest()`
   - Verifica se hash já existe no banco (evita duplicatas)
   - Envia para Groq API para análise
   - Salva resultado no SQLite

3. **Tab "Ver Avaliações"**:
   - Lista todas as avaliações salvas
   - Mostra: Nota, Lead Score, Classificação, Produto Recomendado
   - Permite expandir para ver avaliação completa (JSON)

4. **Tab "Exportar Dados"**:
   - Download em CSV de todas as avaliações

#### Funções Principais (`utils/transcricao_avaliacao_db.py`)

```python
def salvar_avaliacao(transcricao_hash, dados_avaliacao, oportunidade_id=None)
    # Salva ou atualiza avaliação usando transcricao_hash como chave única
    # INSERT OR REPLACE para evitar duplicatas

def listar_avaliacoes()
    # Retorna DataFrame com todas as avaliações

def buscar_avaliacao(transcricao_hash)
    # Busca avaliação específica por hash

def existe_avaliacao(transcricao_hash)
    # Verifica se transcrição já foi avaliada
```

#### Hash System (`_pages/transcricoes.py`)

```python
def gerar_hash(transcricao: str) -> str:
    """Gera hash MD5 da transcrição para identificação única"""
    return hashlib.md5(transcricao.encode('utf-8')).hexdigest()

# Uso:
hash_gerado = gerar_hash(df_row['transcricao'])
ja_avaliada = hash_gerado in lista_hashes_salvos
```

## 📊 Funcionalidades

### Sistema de Avaliações (NOVO - Janeiro 2026)

**Status**: ⚠️ Em desenvolvimento - 2 bugs críticos impedem uso completo

**Funcionalidades Implementadas**:

- ✅ Seleção de transcrições com checkboxes
- ✅ Preview de transcrição antes de avaliar (botão "👁️ Ver")
- ✅ Avaliação em lote via Groq API
- ✅ Armazenamento em SQLite local
- ✅ Visualização de avaliações salvas
- ✅ Export para CSV
- ✅ Coluna "Avaliada" para mostrar status

**Bugs Ativos**:

- 🔴 Hash MD5 armazenado como texto completo (comparação quebrada)
- 🔴 API Groq retornando erro ao invés de avaliação válida

**Campos da Avaliação**:

- Nota do Vendedor (0-100)
- Lead Score (0-100)
- Lead Classificação (Quente/Morno/Frio/Não Qualificado)
- Concurso/Área de Interesse
- Produto Recomendado
- Avaliação Completa (JSON com análise detalhada)

### 1. Visão Geral (Análise Quantitativa) - LEGADO

**Métricas Principais:**

- Total de ligações
- Ligações com transcrição
- Leads identificados
- Agentes únicos

**Análises Disponíveis:**

- Distribuição por empresa (Degrau/Central)
- Ligações por etapa do funil
- Ligações por modalidade (Presencial/Live/Online)
- Top 10 agentes mais ativos
- Análise temporal (por data e hora)
- Ligações por origem

**Dados Extraídos do JSON:**

- Data e hora da ligação
- UUID da chamada
- Ramal utilizado
- Agente responsável
- Telefone do contato

### 2. Análise com IA - LEGADO (OpenAI)

**Classificação Automática:**
A IA classifica cada ligação em:

- ✅ **Válida**: Conversa completa com conteúdo relevante
- 📞 **Caixa Postal**: Caiu em secretária eletrônica
- ❌ **Não Atendeu**: Apenas música/URA
- 🔌 **Desconexão**: Problemas técnicos
- ⚠️ **Inválida**: Outros motivos (trote, muito curta, etc.)

**Métricas Geradas:**

- Quantidade de cada tipo
- Taxa de sucesso (ligações válidas)
- Distribuição em gráfico de pizza
- Motivo da classificação para cada ligação

### 3. Avaliação SPIN Selling - LEGADO (OpenAI)

**Metodologia SPIN:**

- **S**ituação: Perguntas sobre contexto do cliente
- **P**roblema: Identificação de dores e insatisfações
- **I**mplicação: Consequências de não resolver o problema
- **N**ecessidade: Benefícios da solução (need-payoff)

**Scores Avaliados:**

- Score Total (0-100)
- Score de Investigação SPIN
- Score de Necessidades
- Score de Demonstração de Valor
- Score de Compromisso/Avanço
- Score de Gatilhos Mentais

**Análise Detalhada Inclui:**

- Produto principal abordado (Presencial/Live/EAD)
- Contagem de perguntas SPIN (S/P/I/N)
- Necessidades implícitas vs explícitas
- Features, vantagens e benefícios apresentados
- Compromisso obtido (avanço/continuação)
- Gatilhos mentais utilizados (ethos/pathos/logos)
- Pontos fortes e pontos a melhorar
- Plano de ação com top 5 recomendações
- Alertas de compliance (promessas irreais, pressão excessiva, etc.)

**Classificação de Qualidade:**

- 90-100: Execução excelente
- 75-89: Bom, com ajustes pontuais
- 60-74: Mediano, necessita melhorias
- <60: Fraco, requer treinamento

## 🔧 Arquitetura Técnica

### Arquivos do Sistema de Avaliações

1. **`utils/transcricao_ia_analyzer.py`** (127 linhas)
   - Classe `TranscricaoIAAnalyzer`
   - Integração com **Groq API** (não OpenAI)
   - Método principal: `analisar_transcricao(transcricao: str) -> dict`
   - Retorna: nota_vendedor, lead_score, lead_classificacao, concurso_area, produto_recomendado, avaliacao_completa
   - **⚠️ BUG ATIVO**: Atualmente retornando `{'erro', 'classificacao_ligacao'}`

2. **`utils/transcricao_avaliacao_db.py`** (282 linhas)
   - Gerenciamento do banco SQLite
   - Conexões com `timeout=30.0` para evitar "database is locked"
   - CRUD completo: salvar, listar, buscar, existe, deletar
   - **⚠️ BUG ATIVO**: Coluna transcricao_hash contém texto completo ao invés de MD5

3. **`_pages/transcricoes.py`** (594+ linhas)
   - Interface Streamlit com 3 tabs principais
   - **Tab 1 - Avaliar**: Seleção com checkboxes, preview, avaliação em lote
   - **Tab 2 - Ver Avaliações**: Lista todas as avaliações salvas
   - **Tab 3 - Exportar**: Download CSV
   - Lógica de hash: `gerar_hash()` função local
   - Comparação: `df_com_transcricao['avaliada'] = hash in hashes_salvos`

4. **`migrar_transcricoes_hash.py`**
   - Script de migração de schema
   - Adiciona coluna `transcricao_hash`
   - Torna `oportunidade_id` nullable
   - Migra registros existentes
   - **⚠️ BUG ATIVO**: Salvou texto completo ao invés de hash MD5
   - Executado com sucesso: 12 registros migrados

5. **`transcricoes_avaliacoes.db`**
   - Banco SQLite local
   - Tabela: `avaliacoes`
   - 11-12 registros atualmente
   - Índice único: `idx_transcricao_hash`

### Arquivos Legados (Sistema Antigo)

1. **`utils/transcricao_analyzer.py`**
   - Sistema antigo com OpenAI
   - Análise SPIN Selling completa
   - Classificação de ligações
   - Ainda em uso nas tabs de análise quantitativa

2. **`_pages/transcricoes.py`** (mesma página)
   - Tabs de "Visão Geral" e "Análise com IA" ainda usam sistema antigo
   - Tab de "Avaliação SPIN" usa OpenAI
   - Novo sistema de avaliações é adicional, não substituição completa

### Fluxo de Dados Atual

```
┌─────────────────────────────────────────────────────────┐
│ MySQL (opportunity_transcripts)                         │
│ - Transcrições de ligações                             │
│ - JSON com ramal, agente, telefone                     │
└────────────────┬────────────────────────────────────────┘
                 │
                 ↓ SELECT query
┌─────────────────────────────────────────────────────────┐
│ DataFrame Pandas (_pages/transcricoes.py)              │
│ - Extrai JSON: ramal, origem, telefone                 │
│ - Gera hash MD5: gerar_hash(transcricao)               │
└────────────────┬────────────────────────────────────────┘
                 │
      ┌──────────┴──────────┐
      │                     │
      ↓                     ↓
┌──────────────┐    ┌──────────────────────────┐
│  Análise     │    │  Sistema de Avaliações   │
│  Quantitativa│    │  (Nova Funcionalidade)   │
│  (Legado)    │    └──────────┬───────────────┘
└──────────────┘               │
                               ↓ Usuario seleciona com checkbox
                     ┌─────────────────────────┐
                     │ TranscricaoIAAnalyzer   │
                     │ (Groq API)              │
                     │ ⚠️ Retornando erro     │
                     └──────────┬──────────────┘
                                │
                                ↓ Resultado da análise
                     ┌─────────────────────────┐
                     │ transcricao_avaliacao_  │
                     │ db.salvar_avaliacao()   │
                     └──────────┬──────────────┘
                                │
                                ↓ INSERT OR REPLACE
                     ┌─────────────────────────┐
                     │ SQLite                  │
                     │ transcricoes_avaliacoes │
                     │ .db                     │
                     │ ⚠️ Hash = texto completo│
                     └─────────────────────────┘
                                │
                                ↓ SELECT *
                     ┌─────────────────────────┐
                     │ Tab "Ver Avaliações"    │
                     │ - Lista resultados      │
                     │ - Export CSV            │
                     └─────────────────────────┘
```

### Conexões e Dependências

```python
# MySQL - Banco principal
from conexao.conexao_seducar import conectar_banco_dados

# SQLite - Avaliações locais
import sqlite3
conn = sqlite3.connect('transcricoes_avaliacoes.db', timeout=30.0)

# APIs Externas
from groq import Groq  # Para avaliações novas
import openai  # Para análise SPIN (legado)

# Processamento
import pandas as pd
import hashlib  # Para MD5 das transcrições
import json
import plotly.express as px
```

## 🎯 Plano de Ação - Próximos Passos

### PRIORIDADE 1 - CRÍTICO 🔴

#### 1. Corrigir Bug do Migration Script

**Arquivo**: `migrar_transcricoes_hash.py`
**Problema**: Salvando texto completo ao invés de hash MD5

**Código Atual (ERRADO)**:

```python
# Provavelmente está assim:
cursor.execute("""
    UPDATE avaliacoes 
    SET transcricao_hash = ? 
    WHERE id = ?
""", (row['transcricao'], row['id']))  # ❌ Salvando transcrição completa
```

**Código Correto (ESPERADO)**:

```python
import hashlib

def gerar_hash(transcricao: str) -> str:
    return hashlib.md5(transcricao.encode('utf-8')).hexdigest()

# No loop de migração:
cursor.execute("""
    UPDATE avaliacoes 
    SET transcricao_hash = ? 
    WHERE id = ?
""", (gerar_hash(row['transcricao']), row['id']))  # ✅ Salvando hash MD5
```

**Ações**:

1. Abrir e revisar `migrar_transcricoes_hash.py`
2. Corrigir lógica de geração de hash
3. Re-executar script em TODOS os registros
4. Validar: `SELECT LENGTH(transcricao_hash) FROM avaliacoes LIMIT 1` deve retornar 32 (tamanho de MD5 em hex)

#### 2. Debugar Erro da API Groq

**Arquivo**: `utils/transcricao_ia_analyzer.py` (linhas 46-103)
**Problema**: Retornando `{'erro', 'classificacao_ligacao'}` ao invés de dict válido

**Investigação Necessária**:

1. Verificar se `GROQ_API_KEY` está definida em `.env`
2. Testar chamada à API isoladamente:

```python
from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Testar com transcrição simples
response = client.chat.completions.create(...)
print(response)  # Ver formato da resposta bruta
```

1. Verificar parsing do JSON retornado
2. Adicionar try/except robusto:

```python
try:
    resultado = json.loads(resposta_texto)
except json.JSONDecodeError as e:
    print(f"Erro ao parsear JSON: {e}")
    print(f"Resposta bruta: {resposta_texto}")
    return {'erro': str(e), 'resposta_bruta': resposta_texto}
```

1. Verificar limites da API (rate limit, tokens)
2. Testar com modelo diferente se necessário

**Possíveis Causas**:

- Chave API inválida/expirada
- Prompt muito longo (limite de tokens)
- Formato de resposta mudou
- Modelo `llama-3.3-70b-versatile` indisponível
- Rate limit atingido

### PRIORIDADE 2 - MELHORIAS 🟡

#### 3. Remover Debug Logging

Após correções, limpar prints de debug:

- `_pages/transcricoes.py` (múltiplos prints)
- `utils/transcricao_avaliacao_db.py` (logging SQL)

#### 4. Validação de Dados

Adicionar validações:

```python
def validar_hash(hash_str: str) -> bool:
    """Valida se string é um hash MD5 válido"""
    return len(hash_str) == 32 and all(c in '0123456789abcdef' for c in hash_str.lower())

# Ao salvar:
if not validar_hash(transcricao_hash):
    raise ValueError(f"Hash inválido: {transcricao_hash}")
```

#### 5. Tratamento de Erros Melhorado

```python
def salvar_avaliacao(transcricao_hash, dados_avaliacao, oportunidade_id=None):
    try:
        # ... código existente ...
    except sqlite3.IntegrityError as e:
        if 'UNIQUE constraint' in str(e):
            # Tentar UPDATE ao invés de INSERT
            atualizar_avaliacao(transcricao_hash, dados_avaliacao)
        else:
            raise
    except Exception as e:
        logging.error(f"Erro ao salvar avaliação: {e}")
        raise
```

### PRIORIDADE 3 - FUTURO 🟢

#### 6. Melhorias de Performance

- Cache de hashes salvos (evitar query repetida)
- Batch insert para múltiplas avaliações
- Índices adicionais se necessário

#### 7. UI Enhancements

- Progress bar durante avaliação em lote
- Mensagem de sucesso/erro mais clara
- Filtros na tab "Ver Avaliações"
- Ordenação por data, nota, etc.

#### 8. Testes Automatizados

```python
# tests/test_transcricao_hash.py
def test_gerar_hash():
    texto = "Teste de transcrição"
    hash1 = gerar_hash(texto)
    hash2 = gerar_hash(texto)
    
    assert len(hash1) == 32
    assert hash1 == hash2  # Mesmo texto = mesmo hash
    assert hash1 != gerar_hash("Outro texto")
```

## � Histórico de Desenvolvimento (Janeiro 2026)

### Dia 1 - Problemas de Conectividade

- Usuário reportou instabilidade de internet
- App Streamlit com erros não especificados
- Sessão interrompida

### Dia 2 - Sessão de Correção Intensiva

#### Problema 1: IndentationError

**Erro**: `IndentationError: expected an indented block after 'except' statement on line 85`
**Arquivo**: `utils/transcricao_ia_analyzer.py`
**Solução**: Corrigido alinhamento com 8 espaços corretos
**Status**: ✅ Resolvido

#### Problema 2: Database is Locked

**Erro**: `sqlite3.OperationalError: database is locked`
**Causa**: Múltiplas conexões SQLite simultâneas sem timeout
**Solução**: Adicionado `timeout=30.0` em TODAS as chamadas `sqlite3.connect()`
**Arquivos Modificados**:

- `utils/transcricao_avaliacao_db.py` (todas as 15+ ocorrências)
**Status**: ✅ Resolvido

#### Problema 3: NOT NULL Constraint Failed

**Erro**: `IntegrityError: NOT NULL constraint failed: avaliacoes.oportunidade_id`
**Causa**: Nem todas as transcrições têm um `oportunidade_id` vinculado
**Solução**:

1. Tornado `oportunidade_id` nullable no schema
2. Criado script de migração `migrar_transcricoes_hash.py`
3. Migrados 12 registros existentes
**Status**: ✅ Resolvido (mas migration tem bug)

#### Problema 4: Sistema de Identificação Única

**Requisito**: Identificar transcrições sem oportunidade_id
**Solução Implementada**:

1. Adicionada coluna `transcricao_hash TEXT UNIQUE NOT NULL`
2. Função `gerar_hash()` usando MD5: `hashlib.md5(texto.encode()).hexdigest()`
3. Índice único: `CREATE UNIQUE INDEX idx_transcricao_hash ON avaliacoes(transcricao_hash)`
4. Script de migração para popular hashes em registros existentes
**Status**: ⚠️ Implementado mas com bug (hash = texto completo)

#### Problema 5: Streamlit Duplicate Keys

**Erro**: `StreamlitDuplicateElementKey: There are multiple identical st.checkbox widgets with the same generated key`
**Causa**: Loop sem identificador único nas keys dos widgets
**Solução**: Adicionado `idx` do loop em todas as keys:

```python
# Antes:
st.checkbox("Selecionar", key=f"select_{row['oportunidade_id']}")

# Depois:
st.checkbox("Selecionar", key=f"select_{idx}_{row['oportunidade_id']}")
```

**Arquivos Modificados**: `_pages/transcricoes.py`
**Status**: ✅ Resolvido

#### Problema 6: Falta de Preview

**Requisito**: "Gostaria de poder ver a transcrição antes de rodar a avaliação"
**Solução**: Botão "👁️ Ver" com `st.expander()` mostrando transcrição completa
**Status**: ✅ Implementado

#### Problema 7: Seleção Individual

**Requisito**: "Coloque um select para que eu possa selecionar quais quero avaliar"
**Solução**: Checkboxes em cada linha da tabela
**Status**: ✅ Implementado

#### Problema 8: Status de Avaliação

**Requisito**: "Mantenha as transcrições avaliadas na tabela, com uma coluna, Avaliada"
**Solução**:

1. Coluna "Avaliada" com valores "Sim" ou "Pendente"
2. Lógica: compara hash MD5 da transcrição com hashes salvos no banco

```python
df_com_transcricao['avaliada'] = df_com_transcricao['hash_gerado'].apply(
    lambda x: 'Sim' if x in hashes_salvos else 'Pendente'
)
```

**Status**: ⚠️ Implementado mas não funciona (bug de comparação hash)

#### Problema 9: Avaliações Não Salvam

**Erro**: "Não está salvando as avaliações e nem mudando o status para avaliada"
**Debug Adicionado**:

- Prints extensivos em `_pages/transcricoes.py`
- Logging em `transcricao_avaliacao_db.py`
- Rastreamento de fluxo completo

**Bugs Descobertos**:

1. **Migration Bug**: `transcricao_hash` contém texto completo, não MD5
2. **API Error**: Groq retornando `{'erro', 'classificacao_ligacao'}` ao invés de avaliação válida

**Status**: 🔴 NÃO RESOLVIDO - Dois bugs críticos bloqueando

### Linha do Tempo de Commits/Changes

1. **Fix IndentationError** → transcricao_ia_analyzer.py
2. **Add timeout=30.0** → transcricao_avaliacao_db.py (15+ locais)
3. **Make oportunidade_id nullable** → Schema change
4. **Create migration script** → migrar_transcricoes_hash.py
5. **Run migration** → 12 records migrated ⚠️ com bug
6. **Add checkboxes UI** → _pages/transcricoes.py
7. **Add preview button** → _pages/transcricoes.py
8. **Add "Avaliada" column** → _pages/transcricoes.py
9. **Fix duplicate keys** → _pages/transcricoes.py (idx in keys)
10. **Add debug logging** → _pages/transcricoes.py + transcricao_avaliacao_db.py
11. **Discover bugs** → Terminal output analysis

### Estado Atual do Código

**Funcionando**:

- ✅ App inicia sem erros
- ✅ Conexões SQLite estáveis (sem "database is locked")
- ✅ UI de seleção com checkboxes
- ✅ Botão de preview funciona
- ✅ Banco aceita transcrições sem oportunidade_id
- ✅ Migração executada (12 registros)

**Quebrado**:

- 🔴 Hashes no banco = texto completo (deveria ser MD5)
- 🔴 Groq API retornando erro ao invés de avaliação
- 🔴 Status "Avaliada" sempre mostra "Pendente" (comparação hash falha)
- 🔴 Novas avaliações não salvam (API retorna erro)

### Análise Quantitativa (Diária)

- Monitorar volume de ligações
- Identificar agentes mais ativos
- Acompanhar horários de pico
- Analisar distribuição por modalidade

### Classificação com IA (Semanal)

- Avaliar taxa de sucesso nas ligações
- Identificar problemas técnicos recorrentes
- Otimizar horários de ligação
- Limite sugerido: 50-100 ligações por vez

### Avaliação SPIN (Mensal/Por Demanda)

- Avaliação detalhada de qualidade
- Treinamento de vendedores
- Identificação de melhores práticas
- Feedback individualizado
- Limite sugerido: 5-20 ligações por vez (análise mais demorada)

## ⚠️ Considerações Importantes

### Sistema de Avaliações (NOVO)

1. **API Groq**:
   - Modelo: `llama-3.3-70b-versatile`
   - Custo estimado: ~$0.001-0.005 por avaliação
   - Tempo: ~5-10 segundos por avaliação
   - **⚠️ ATENÇÃO**: Atualmente retornando erros - verificar chave API

2. **Banco de Dados SQLite**:
   - Arquivo: `transcricoes_avaliacoes.db` (local)
   - Timeout: 30 segundos (evita "database is locked")
   - Identificação única: hash MD5 da transcrição
   - **⚠️ BUG ATIVO**: Hashes armazenados como texto completo

3. **Limitações**:
   - Transcrições sem oportunidade_id: Suportado via hash MD5
   - Duplicatas: Previstas por índice único em transcricao_hash
   - **⚠️ BUG**: Status "Avaliada" sempre mostra "Pendente" devido ao bug de hash

### Sistema Legado (OpenAI)

1. **Custo da API OpenAI:**
   - Classificação: ~$0.001-0.002 por ligação
   - Avaliação SPIN: ~$0.01-0.03 por ligação (mais tokens)
   - Use com moderação e defina limites

2. **Tempo de Processamento:**
   - Classificação: ~2-5 segundos por ligação
   - Avaliação SPIN: ~10-20 segundos por ligação

3. **Qualidade dos Dados:**
   - Transcrições vazias são automaticamente classificadas como inválidas
   - Transcrições muito curtas (<50 caracteres) podem ter classificação imprecisa

4. **Privacidade:**
   - Os dados são enviados para a API da OpenAI
   - Certifique-se de estar em conformidade com políticas de privacidade

## 📈 Próximos Passos

### Correções Urgentes (Janeiro 2026)

- [ ] **CRÍTICO**: Corrigir migration script para gerar hash MD5 real
- [ ] **CRÍTICO**: Debugar erro da API Groq e corrigir resposta
- [ ] Re-executar migração com hash correto em todos os 11-12 registros
- [ ] Validar que status "Avaliada" funciona corretamente
- [ ] Testar salvamento de novas avaliações end-to-end
- [ ] Remover debug logging após correções

### Melhorias Futuras (Sistema de Avaliações)

- [ ] Progress bar durante avaliação em lote
- [ ] Cache de hashes para performance
- [ ] Validação de hash MD5 ao salvar
- [ ] Filtros e ordenação na tab "Ver Avaliações"
- [ ] Tratamento de erros mais robusto
- [ ] Testes automatizados
- [ ] Re-avaliação de transcrições já avaliadas (com confirmação)
- [ ] Comparação entre avaliações (antes/depois)
- [ ] Dashboard com estatísticas das avaliações

### Melhorias Futuras (Sistema Legado)

- [ ] Cache de avaliações no banco de dados
- [ ] Análise de sentimento
- [ ] Identificação de objeções comuns
- [ ] Comparação entre vendedores (ranking)
- [ ] Alertas automáticos para ligações problemáticas
- [ ] Integração com sistema de treinamento
- [ ] Dashboard executivo com KPIs

## 🆘 Troubleshooting

### Problemas Resolvidos

**❌ "IndentationError: expected an indented block"**

- Causa: Alinhamento incorreto em transcricao_ia_analyzer.py:85
- Solução: Corrigido para 8 espaços
- Status: ✅ Resolvido

**❌ "sqlite3.OperationalError: database is locked"**

- Causa: Múltiplas conexões simultâneas sem timeout
- Solução: Adicionado `timeout=30.0` em TODAS as conexões SQLite
- Arquivo: utils/transcricao_avaliacao_db.py
- Status: ✅ Resolvido

**❌ "NOT NULL constraint failed: avaliacoes.oportunidade_id"**

- Causa: Schema não aceitava transcrições sem oportunidade
- Solução: Tornado oportunidade_id nullable + sistema de hash MD5
- Status: ✅ Resolvido

**❌ "StreamlitDuplicateElementKey"**

- Causa: Loop sem identificador único nas keys dos widgets
- Solução: Adicionado `idx` em todas as keys (ex: `f"select_{idx}_{id}"`)
- Arquivo: _pages/transcricoes.py
- Status: ✅ Resolvido

### Problemas Ativos

**🔴 Status "Avaliada" sempre mostra "Pendente"**

- Causa: Coluna transcricao_hash contém TEXTO COMPLETO ao invés de hash MD5
- Debug: `SELECT transcricao_hash FROM avaliacoes LIMIT 1` retorna texto longo
- Esperado: String de 32 caracteres (ex: 'd35a09cb262c8ee65787bf846978a7f7')
- Solução: Corrigir migrar_transcricoes_hash.py e re-executar
- Arquivo: migrar_transcricoes_hash.py
- Status: 🔴 NÃO RESOLVIDO

**🔴 Avaliações não salvam - API retorna erro**

- Sintoma: `Análise retornada: ['erro', 'classificacao_ligacao']`
- Causa: Groq API não retornando dict válido
- Debug necessário:
  1. Verificar GROQ_API_KEY em .env
  2. Testar API isoladamente
  3. Verificar parsing do JSON
  4. Logar resposta bruta da API
- Arquivo: utils/transcricao_ia_analyzer.py (linhas 46-103)
- Status: 🔴 NÃO RESOLVIDO

### Problemas Históricos (Sistema Legado)

**"OPENAI_API_KEY não configurada"**

- Solução: Criar arquivo `.env` com chave da OpenAI

**Erro ao conectar no banco de dados (MySQL)**

- Solução: Verificar configuração em `conexao/conexao_seducar.py`

**Erro ao conectar no banco SQLite**

- Verificar se arquivo `transcricoes_avaliacoes.db` existe
- Verificar permissões de escrita no diretório
- Se persistir, deletar DB e deixar sistema recriar schema

**Análise muito lenta**

- Solução: Reduzir limite de ligações a analisar
- Sistema de avaliações: Selecionar menos transcrições por vez

**JSON inválido na coluna json_completo**

- Sistema trata automaticamente, retornando dados vazios para JSONs inválidos

## 📞 Suporte e Documentação

### Documentação Relacionada

- Arquivo atual: `README_TRANSCRICOES.md`
- Outros READMEs no projeto:
  - `README.md` - Geral do projeto
  - `README_FBCLID.md` - Facebook tracking
  - `README_GCLID_REPROCESSAMENTO.md` - Google tracking

### APIs Utilizadas

- [Documentação Groq](https://console.groq.com/docs) - Sistema de Avaliações (NOVO)
- [Documentação OpenAI](https://platform.openai.com/docs) - Sistema Legado
- [Documentação Streamlit](https://docs.streamlit.io) - Interface

### Arquivos-Chave para Debug

1. `_pages/transcricoes.py` - UI principal
2. `utils/transcricao_ia_analyzer.py` - Integração Groq API
3. `utils/transcricao_avaliacao_db.py` - Operações SQLite
4. `migrar_transcricoes_hash.py` - Script de migração (⚠️ com bug)
5. `transcricoes_avaliacoes.db` - Banco de dados local

### Comandos Úteis

```bash
# Iniciar aplicação
streamlit run main.py

# Verificar banco de dados SQLite
sqlite3 transcricoes_avaliacoes.db "SELECT COUNT(*) FROM avaliacoes;"
sqlite3 transcricoes_avaliacoes.db "SELECT LENGTH(transcricao_hash) FROM avaliacoes LIMIT 1;"

# Ver schema
sqlite3 transcricoes_avaliacoes.db ".schema avaliacoes"

# Ver primeiros registros
sqlite3 transcricoes_avaliacoes.db "SELECT id, oportunidade_id, SUBSTR(transcricao_hash, 1, 50) FROM avaliacoes LIMIT 5;"

# Verificar variáveis de ambiente
cat .env | grep GROQ

# Logs do Streamlit (se houver)
tail -f ~/.streamlit/logs/*.log
```

### Informações para Novo Agente de IA

**Contexto Geral**:

- Projeto Streamlit de análise de transcrições de ligações de vendas
- Dois sistemas coexistindo: Legado (OpenAI) + Novo (Groq + SQLite)
- Usuário teve instabilidade de internet ontem, sessão de debug intensiva hoje

**Estado Atual (30/Jan/2026)**:

- App funciona e inicia corretamente
- UI implementada com seleção, preview e status
- Database aceita dados sem oportunidade_id
- **2 bugs críticos bloqueando funcionalidade completa**

**Bugs Ativos**:

1. Migration script salvou texto completo ao invés de hash MD5 em `transcricao_hash`
2. Groq API retornando `{'erro', 'classificacao_ligacao'}` ao invés de avaliação válida

**Próxima Ação Recomendada**:

1. Revisar e corrigir `migrar_transcricoes_hash.py`
2. Debugar chamada à Groq API em `utils/transcricao_ia_analyzer.py`
3. Re-executar migração
4. Testar fluxo end-to-end de avaliação

**Última Interação**:

- Debug logging extensivo adicionado
- Terminal mostrando evidências dos bugs
- Sistema pronto para correção dos problemas identificados

---

**Documento atualizado em**: 30 de Janeiro de 2026
**Última modificação**: Sessão de debug e documentação completa
**Próxima revisão**: Após correção dos 2 bugs críticos
