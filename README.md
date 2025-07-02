# 📊 Dashboard de Análise Seducar

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python)
![Streamlit](https://img.shields.io/badge/Streamlit-1.45.1-FF4B4B?style=for-the-badge&logo=Streamlit)
![Plotly](https://img.shields.io/badge/Plotly-6.1.2-3D42B3?style=for-the-badge&logo=plotly)
![Licença](https://img.shields.io/badge/licença-MIT-green?style=for-the-badge)

Ferramenta de Business Intelligence para análise de performance comercial e financeira da Degrau Cultural e Central de Concursos, com sistema de login e permissões por usuário.

***

## 📌 Sobre o Projeto

Este projeto oferece um dashboard interativo e seguro qsue centraliza análises de dados cruciais para a tomada de decisão estratégica. A aplicação conta com um sistema de autenticação próprio, garantindo que diferentes perfis de usuário (vendas, financeiro, diretoria) tenham acesso apenas aos relatórios pertinentes às suas funções.

## ✨ Funcionalidades Principais

-   **Sistema de Login Seguro:** Autenticação de usuários com permissões de acesso por página.
-   **Dashboard de Oportunidades:**
    -   Funil de Vendas para análise de conversão.
    -   Análise "Top N" de concursos para identificar os mais relevantes.
-   **Dashboard Financeiro:**
    -   Tabela hierárquica e interativa (AG-Grid) para análise de despesas.
    -   Filtros em cascata por Unidades, Centro de Custo e Categorias.
    -   Exportação completa para Excel com múltiplas abas.
-   **Dashboard de Tendências:**
    -   Análise comparativa de performance Mês vs. Mês Anterior.
    -   Análise de "zoom" em janelas de tempo específicas para os principais concursos.
-   **Tratamento de Fuso Horário:** Todas as análises são ajustadas para o fuso horário de Brasília (`America/Sao_Paulo`), garantindo precisão dos dados.

## 🛠️ Tecnologias Utilizadas

-   **Interface e Dashboard:** Streamlit
-   **Visualização de Dados:** Plotly
-   **Manipulação de Dados:** Pandas, NumPy
-   **Tabelas Avançadas:** Streamlit-AgGrid
-   **Conexão com Banco de Dados:** SQLAlchemy, MySQL Connector
-   **Gerenciamento de Segredos:** Streamlit Secrets, python-dotenv (para ambiente local)

## 🚀 Começando

Siga os passos para configurar e executar o projeto.

### 1. Configuração do Ambiente de Produção (Streamlit Cloud)

1.  **Fork ou Clone o Repositório:** Tenha o código no seu GitHub.
2.  **Crie um App no Streamlit Cloud:** Conecte seu repositório.
3.  **Configure os Segredos:** No painel do seu app, vá em **Settings > Secrets** e cole suas credenciais de banco de dados e de usuários, seguindo o formato abaixo:
    ```toml
    # Segredos para a Conexão com o Banco de Dados
    [database]
    host = "seu_host_remoto"
    user = "seu_usuario"
    password = "sua_senha"
    db_name = "seducar"
    port = "3306"

    # Segredos para a Autenticação de Usuários
    [users]
    [users.nome_de_usuario_1]
    password = "senha_1"
    pages = '["all"]' # Acesso total

    [users.nome_de_usuario_2]
    password = "senha_2"
    pages = '["Oportunidades", "Tendencias"]' # Acesso limitado
    ```

### 2. Configuração do Ambiente Local (Desenvolvimento)

1.  **Clone o repositório:**
    ```bash
    git clone [https://github.com/ulisseso2/dados_degrau_py.git](https://github.com/ulisseso2/dados_degrau_py.git)
    cd dados_degrau_py
    ```
2.  **Crie e ative o ambiente virtual:**
    ```bash
    python -m venv .venv
    # Windows
    .\.venv\Scripts\activate
    # Linux/Mac
    source .venv/bin/activate
    ```
3.  **Instale as dependências:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Crie o arquivo `.env`:** Na raiz do projeto, crie um arquivo `.env` para suas credenciais locais.
    ```env
    # Credenciais do Banco para o ambiente local
    DB_HOST=seu_host_local
    DB_USER=seu_usuario_local
    DB_PASSWORD=sua_senha_local
    DB_NAME=seducar
    DB_PORT=3306

    # Usuários de teste para o ambiente local (JSON em uma única linha)
    LOCAL_USERS_DB='{"ulisses": {"password": "123", "pages": ["all"]}, "vendedor": {"password": "456", "pages": ["Oportunidades"]}}'
    ```

## 🖥️ Executando o Projeto

Com o ambiente local configurado, rode o comando:
```bash
streamlit run main.py
```
A aplicação abrirá no seu navegador, começando pela tela de login.

## 🏗️ Estrutura do Projeto

A aplicação utiliza uma arquitetura de roteamento manual para controlar o acesso às páginas.
```
dados_degrau_py/
├── _pages/                 # <-- Note o underscore: desativa o menu automático
│   ├── oportunidades.py
│   ├── financeiro.py
│   └── tendencias.py
├── conexao/
│   └── mysql_connector.py
├── consultas/
│   └── ...
├── main.py                 # <-- Roteador principal e tela de login
├── .env                    # <-- Segredos locais (não vai para o Git)
├── requirements.txt
└── README.md
```

## ✉️ Contato

Ulisses Oliveira - [ulissesrce@gmail.com](mailto:ulissesrce@gmail.com)
