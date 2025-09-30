# 📚 Análise de Disciplinas e Tópicos - MongoDB

## 📋 Descrição

Sistema de análise de disciplinas e tópicos baseado na view `subjectXtopics_total` do MongoDB. Permite visualizar estatísticas de questões por disciplina e análise detalhada de tópicos.

## 🏗️ Estrutura dos Dados

### View: `subjectXtopics_total`

```json
{
  "topics": [
    {
      "name": "Campos Interdisciplinares", 
      "total": 9
    },
    {
      "name": "Subcampos Específicos",
      "total": 5
    }
  ],
  "total": 23,
  "name": "Astronomia"
}
```

## 🚀 Funcionalidades

### 📊 Visão Geral

- ✅ Métricas principais (total disciplinas, questões, média)
- ✅ Top 20 disciplinas por número de questões
- ✅ Gráfico de barras interativo

### 🔍 Análise Detalhada por Disciplina

- ✅ Seleção de disciplina específica
- ✅ Gráfico de pizza com distribuição de tópicos
- ✅ Gráfico de barras dos tópicos
- ✅ Tabela detalhada com percentuais

### 🔄 Análise Comparativa

- ✅ Comparação entre múltiplas disciplinas
- ✅ Estatísticas comparativas (maior, menor, média, mediana)
- ✅ Gráfico de comparação horizontal

### 📋 Dados Completos

- ✅ Filtro por número mínimo de questões
- ✅ Ordenação (alfabética, mais/menos questões)
- ✅ Exportação para CSV
- ✅ Tabela completa com todos os dados

## 🔧 Configuração

### 1. Variáveis de Ambiente (.env)

```env
MONGO_DB_URI="mongodb://admin:senha@host:port/admin?authSource=admin&replicaSet=ReplicaSet&readPreference=primary&ssl=true"
MONGO_DB_NAME="eduqc"
```

### 2. Dependências

```bash
pip install pymongo==4.8.0
pip install streamlit==1.46.1
pip install plotly==6.2.0
pip install pandas==2.3.1
```

## 📁 Arquivos Criados

```
/conexao/mongo_connection.py    # Conexão e operações MongoDB
/_pages/analise_disciplinas.py  # Interface Streamlit
```

## 🎯 Como Usar

### 1. Executar Dashboard Individual

```bash
cd /home/ulisses/dados_degrau_py
streamlit run _pages/analise_disciplinas.py --server.port 8502
```

### 2. Integrado ao Sistema Principal

- Acesse o sistema principal via `main.py`
- Menu lateral → "Análise Disciplinas"

## 📈 Estatísticas Disponíveis

### Métricas Principais

- **Total de Disciplinas**: Número total de subjects
- **Total de Questões**: Soma de todas as questões
- **Média por Disciplina**: Questões/disciplina

### Por Disciplina

- **Total de Questões**: Soma dos tópicos
- **Número de Tópicos**: Contagem de topics
- **Distribuição por Tópico**: Percentual de cada tópico

### Análises Visuais

- 📊 Gráfico de barras horizontal (top 20)
- 🥧 Gráfico de pizza (distribuição tópicos)
- 📈 Gráfico comparativo entre disciplinas
- 📋 Tabelas interativas

## 🔍 Filtros e Funcionalidades

### Filtros Disponíveis

- **Disciplina Específica**: Dropdown com todas as disciplinas
- **Múltiplas Disciplinas**: Multiselect para comparação
- **Mínimo de Questões**: Filtro numérico
- **Ordenação**: Alfabética, mais/menos questões

### Recursos Avançados

- 🔄 **Cache**: Dados atualizados a cada 10 minutos
- 📥 **Exportação**: Download em CSV
- 🎨 **Gráficos Interativos**: Plotly com zoom e hover
- 📱 **Responsivo**: Interface adaptável

## 🛠️ Tecnologias Utilizadas

- **Backend**: Python 3.12+
- **Database**: MongoDB (pymongo)
- **Frontend**: Streamlit
- **Visualização**: Plotly Express
- **Dados**: Pandas
- **Cache**: Streamlit cache_data

## 📊 Performance

- ✅ **Cache**: 10 minutos TTL
- ✅ **Conexão**: Pool de conexões MongoDB
- ✅ **Queries**: Otimizadas com projeção
- ✅ **Interface**: Lazy loading de dados

## 🔐 Segurança

- ✅ **Credenciais**: Variáveis de ambiente
- ✅ **Conexão**: SSL/TLS habilitado
- ✅ **Autenticação**: MongoDB com usuário/senha
- ✅ **Logs**: Sistema de logging configurado

## 📝 Logs e Debugging

```python
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
```

Logs disponíveis:

- Conexão estabelecida
- Dados encontrados
- Erros de conexão
- Performance de queries

## 🚀 Próximas Funcionalidades

- [ ] Filtros avançados por área/campo
- [ ] Análise temporal (se dados históricos disponíveis)
- [ ] Dashboard executivo com KPIs
- [ ] Relatórios automáticos por email
- [ ] API REST para integração externa

## 💡 Dicas de Uso

1. **Performance**: Use o cache - evite recarregar desnecessariamente
2. **Visualização**: Use filtros para focar em dados específicos
3. **Exportação**: Baixe dados para análises offline
4. **Comparação**: Selecione até 10 disciplinas para melhor visualização
5. **Mobile**: Interface responsiva funciona bem em tablets

---

## 📞 Suporte

Para dúvidas ou problemas:

- Verifique logs de conexão MongoDB
- Confirme variáveis de ambiente
- Teste conexão isoladamente via `mongo_connection.py`
