# Configuração de Múltiplos Bancos de Dados

## 📋 Visão Geral

Este projeto agora suporta conexões com múltiplos bancos de dados MySQL, mantendo a estratégia híbrida de configuração (`.env` local + `st.secrets` em produção).

## 🔧 Configuração Local (.env)

Adicione as credenciais do novo banco no arquivo `.env`:

```bash
# Banco de dados principal
DB_HOST=seducar-api-prod.compeceogyzg.us-east-2.rds.amazonaws.com
DB_USER=seducar-readonly
DB_PASSWORD=C2A9lfa#_-rIG0#=sE0W
DB_NAME=seducar
DB_PORT=3306

# Banco de dados secundário
DB_SECUNDARIO_HOST=seducar-api-hml.compeceogyzg.us-east-2.rds.amazonaws.com
DB_SECUNDARIO_USER=admincrm
DB_SECUNDARIO_PASSWORD=imWupcKOc4VkJ2
DB_SECUNDARIO_NAME=dump_central
DB_SECUNDARIO_PORT=3306
```

## ☁️ Configuração Streamlit Cloud (secrets.toml)

No Streamlit Cloud, adicione no painel de Secrets:

```toml
[database]
host = "seducar-api-prod.compeceogyzg.us-east-2.rds.amazonaws.com"
user = "seducar-readonly"
password = "C2A9lfa#_-rIG0#=sE0W"
db_name = "seducar"
port = "3306"

[database_secundario]
host = "seu-host-secundario.rds.amazonaws.com"
user = "seu-usuario"
password = "sua-senha"
db_name = "nome-do-banco"
port = "3306"
```

## 💻 Como Usar no Código

### Exemplo 1: Consulta no banco principal

```python
from utils.sql_loader import carregar_dados

# Carrega dados do banco principal
df_principal = carregar_dados("consultas/minha_consulta.sql")
st.dataframe(df_principal)
```

### Exemplo 2: Consulta no banco secundário

```python
from utils.sql_loader import carregar_dados_secundario

# Carrega dados do banco secundário
df_secundario = carregar_dados_secundario("consultas/consulta_secundaria.sql")
st.dataframe(df_secundario)
```

### Exemplo 3: Comparação entre bancos

```python
from utils.sql_loader import carregar_dados, carregar_dados_secundario

# Carrega dados de ambos os bancos
df_principal = carregar_dados("consultas/relatorio_principal.sql")
df_secundario = carregar_dados_secundario("consultas/relatorio_secundario.sql")

# Merge ou comparação
df_combinado = pd.merge(df_principal, df_secundario, on='id', how='outer')
st.dataframe(df_combinado)
```

### Exemplo 4: Conexão direta (sem arquivo SQL)

```python
import pandas as pd
from conexao.mysql_connector import conectar_mysql_secundario

engine = conectar_mysql_secundario()
if engine:
    query = "SELECT * FROM tabela WHERE data > '2024-01-01'"
    df = pd.read_sql(query, engine)
    st.dataframe(df)
```

## 📁 Estrutura de Arquivos SQL

Organize suas consultas SQL por banco:

```
consultas/
├── banco_principal/
│   ├── relatorio_vendas.sql
│   └── analise_alunos.sql
└── banco_secundario/
    ├── dados_externos.sql
    └── integracao_api.sql
```

## 🔐 Segurança

- ⚠️ **NUNCA** commite o arquivo `.env` no Git
- ✅ Mantenha `.env` no `.gitignore`
- ✅ Use variáveis de ambiente em produção
- ✅ Use contas readonly sempre que possível

## 🆕 Adicionando Mais Bancos

Para adicionar um terceiro banco, siga o padrão:

1. **Em `mysql_connector.py`**, adicione:

```python
def conectar_mysql_terceiro():
    creds = {}
    try:
        creds = st.secrets["database_terceiro"]
    except st.errors.StreamlitAPIException:
        creds = {
            "user": os.getenv("DB_TERCEIRO_USER"),
            "password": os.getenv("DB_TERCEIRO_PASSWORD"),
            "host": os.getenv("DB_TERCEIRO_HOST"),
            "port": os.getenv("DB_TERCEIRO_PORT"),
            "db_name": os.getenv("DB_TERCEIRO_NAME")
        }
    # ... resto do código igual
```

2. **Em `sql_loader.py`**, adicione:

```python
@st.cache_data(ttl=600)
def carregar_dados_terceiro(caminho_sql):
    query = carregar_sql(caminho_sql)
    engine = conectar_mysql_terceiro()
    # ... resto do código igual
```

3. **Configure `.env` e `secrets.toml`** seguindo o padrão acima

## 🎯 Boas Práticas

✅ Use cache (`@st.cache_data`) para otimizar performance
✅ Defina TTL apropriado para cada tipo de consulta
✅ Feche conexões automaticamente usando engines do SQLAlchemy
✅ Trate erros de conexão gracefully
✅ Use nomes descritivos para funções de conexão
✅ Documente qual banco cada consulta SQL utiliza

## 🐛 Troubleshooting

### Erro: "As credenciais não foram encontradas"

- Verifique se o `.env` está na raiz do projeto
- Verifique se as variáveis estão nomeadas corretamente
- Em produção, verifique os Secrets no Streamlit Cloud

### Erro de conexão

- Verifique se o host está acessível
- Verifique se as credenciais estão corretas
- Verifique se a porta está aberta no firewall

### Cache não atualiza

- Limpe o cache do Streamlit: `st.cache_data.clear()`
- Ajuste o TTL conforme necessário
- Use `Ctrl+C` para limpar o cache durante desenvolvimento
