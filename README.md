# 📊 Dashboard Seducar - Degrau & Central de Concursos

📌 Visão Geral
Dashboard interativo para análise de oportunidades da Degrau Cultural e Central de Concursos, desenvolvido com Streamlit e Plotly.


🚀 Começando
Pré-requisitos
Python 3.8+
MySQL Server (para conexão com o banco de dados)

📥 Instalação
1- Clone o repositório:

```bash
git clone https://github.com/ulisseso2/dados_degrau_py.git
cd seducar-projeto
```

2- Crie e ative o ambiente virtual:

```bash
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activatec
```

3- Instale as dependências:

```bash
pip install -r requirements.txt
```

🔧 Configuração

1- Crie um arquivo .env na raiz do projeto com as credenciais do MySQL:

```env
DB_HOST=seu_host
DB_PORT=sua_porta
DB_USER=seu_usuario
DB_PASSWORD=sua_senha
DB_NAME=seducar
```

2- Certifique-se que seu .gitignore contém:

```
.env
.venv/
__pycache__/
```

🏗️ Estrutura do Projeto

```
seducar-projeto/
├── conexao/
│   └── mysql_connector.py
├── consultas/
│   ├── oportunidades/
│   │    └── oportunidades.sql
│   └── orders/
│        └── orders.sql
├── data/
├── notebooks/
├── pages/
│   └── oportunidades_unidades.py
│   └── tabela_unidades.py
├── utils/
│   └── sql_loader.py
├── main.py
├── .env
├── .gitignore
├── requirements.txt
└── README.md
```

🖥️ Executando o Projeto

```bash
streamlit run main.py
```

Acesse: http://localhost:8501

📊 Funcionalidades Principais

- Filtros interativos por:
  - Empresa (Degrau/Central)
  - Unidade
  - Etapa do funil
  - Período temporal
  - ...

- Visualizações:
  - Métricas
  - Tabelas
  - Gráfico

🛠️ Desenvolvimento

- Adicionar nova consulta:
  - Crie seu arquivo SQL em `consultas/`
  - Importe no dashboard: `df = carregar_dados("consultas/nova_consulta.sql")`

- Criando novos dashboards:
  - Adicione um arquivo `.py` em `pages/`
  - Use a estrutura básica:
    ```python
    import streamlit as st
    from utils.sql_loader import carregar_dados
    st.title("Novo Dashboard")
    df = carregar_dados("consultas/nova_consulta.sql")
    ```

📚 Referências

- [Plotly Python](https://plotly.com/python/)
- [Streamlit Documentation](https://docs.streamlit.io/)

📄 Licença

MIT License - Veja `LICENSE`

✉️ Contato:

Equipe de Analytics - [ulissesrce@gmail.com](mailto:ulissesrce@gmail.com)

