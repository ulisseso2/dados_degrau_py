# 📞 Pipeline de Análise de Transcrições com LLM

Sistema automatizado para extrair informações estruturadas de transcrições de conversas telefônicas usando LLM (Large Language Models).

## 🎯 Funcionalidades

O sistema extrai automaticamente as seguintes informações de cada transcrição:

1. **Consultor**: Nome do vendedor/atendente
2. **Interlocutor**: Nome do cliente/lead
3. **Assunto**: Tema principal da conversa
4. **Concurso de Interesse**: Concurso público mencionado
5. **Oferta Proposta**: Produto/curso oferecido
6. **Objeção**: Principal objeção do cliente
7. **Resposta do Consultor**: Como foi tratada a objeção

## 🚀 Configuração Inicial

### 1. Instalar Dependências

Todas as dependências já foram instaladas, mas caso precise reinstalar:

```bash
pip install python-docx spacy pandas python-dotenv anthropic openai ollama streamlit
```

### 2. Configurar API do LLM

Você tem 3 opções de provedor:

#### **Opção A: Anthropic Claude (Recomendado - Melhor Qualidade)**

1. Obtenha sua chave em: https://console.anthropic.com/
2. Crie um arquivo `.env` na pasta `consultas/scripts/`:

```bash
cd consultas/scripts/
cp .env.example .env
nano .env  # ou use seu editor preferido
```

3. Adicione sua chave:
```
ANTHROPIC_API_KEY=sk-ant-seu_token_aqui
LLM_PROVIDER=anthropic
```

#### **Opção B: OpenAI GPT**

1. Obtenha sua chave em: https://platform.openai.com/api-keys
2. No arquivo `.env`:
```
OPENAI_API_KEY=sk-seu_token_aqui
LLM_PROVIDER=openai
```

#### **Opção C: Ollama (Local - Grátis)**

1. Instale o Ollama: https://ollama.com/
2. Baixe um modelo:
```bash
ollama pull llama3.2
```
3. No arquivo `.env`:
```
LLM_PROVIDER=ollama
```

## 📊 Como Usar

### Teste Rápido (3 transcrições)

Primeiro, teste com apenas 3 transcrições para validar a configuração:

```bash
cd /home/ulisses/dados_degrau_py
.venv/bin/python consultas/scripts/main_teste.py
```

### Pipeline Completo

Se o teste foi bem-sucedido, processe todas as 45 transcrições:

```bash
.venv/bin/python consultas/scripts/main.py
```

### Visualizar Resultados

Inicie a interface web com Streamlit:

```bash
streamlit run consultas/scripts/visualizar_analises.py
```

A interface permite:
- ✅ Visualizar dados estruturados em tabela
- ✅ Filtrar por consultor, concurso, objeções
- ✅ Ver métricas e estatísticas
- ✅ Gráficos de top consultores e concursos
- ✅ Download dos dados em CSV

## 📁 Estrutura de Arquivos

```
consultas/
├── telefonia/                           # 45 arquivos .docx com transcrições
├── scripts/
│   ├── processar_transcricoes.py        # Lê arquivos .docx
│   ├── extrair_informacoes_llm.py       # Extração com LLM
│   ├── analisar_dados.py                # Salva em CSV
│   ├── main.py                          # Pipeline completo
│   ├── main_teste.py                    # Pipeline de teste
│   ├── visualizar_analises.py           # Interface Streamlit
│   ├── .env.example                     # Exemplo de configuração
│   └── .env                             # Suas credenciais (criar)
└── resultados/
    ├── analises.csv                     # Output do pipeline completo
    └── analises_teste.csv               # Output do teste
```

## 🔧 Solução de Problemas

### Erro: "No module named 'anthropic/openai/ollama'"

As dependências já foram instaladas, mas se precisar reinstalar:
```bash
.venv/bin/pip install anthropic openai ollama
```

### Erro: "ANTHROPIC_API_KEY não encontrada"

Certifique-se de:
1. Criar o arquivo `.env` em `consultas/scripts/`
2. Adicionar sua chave no formato correto
3. Não deixar espaços antes/depois do `=`

### Erro: "Can't find model 'llama3.2'" (Ollama)

Baixe o modelo primeiro:
```bash
ollama pull llama3.2
```

### Resultados ruins com Ollama

Modelos locais (Ollama) podem ter qualidade inferior. Considere usar Claude ou GPT para melhor precisão.

## 💰 Custos Estimados

- **Anthropic Claude**: ~$0.01 por transcrição (mais preciso)
- **OpenAI GPT-4o-mini**: ~$0.005 por transcrição
- **Ollama**: Grátis (modelo local, qualidade pode variar)

Para 45 transcrições:
- Claude: ~$0.45
- GPT: ~$0.23
- Ollama: $0 (grátis)

## 🎓 Próximos Passos

1. ✅ Configurar API do LLM
2. ✅ Executar teste com 3 transcrições
3. ✅ Validar qualidade dos resultados
4. ✅ Executar pipeline completo
5. ✅ Analisar dados no Streamlit
6. 🔄 Ajustar prompt se necessário
7. 🔄 Processar novas transcrições periodicamente

## 📝 Notas

- O processamento pode levar alguns minutos dependendo do número de transcrições
- Os dados são salvos em CSV para fácil integração com outras ferramentas
- A interface Streamlit atualiza automaticamente quando o CSV é modificado
- Para privacidade máxima, use Ollama (modelos locais)
