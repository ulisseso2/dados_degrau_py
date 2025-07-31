
# 📊 Dashboard de Análise Estratégica - Seducar

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python)
![Streamlit](https://img.shields.io/badge/Streamlit-1.45-FF4B4B?style=for-the-badge&logo=Streamlit)
![Pandas](https://img.shields.io/badge/Pandas-2.3-150458?style=for-the-badge&logo=pandas)
![Plotly](https://img.shields.io/badge/Plotly-6.1-3D42B3?style=for-the-badge&logo=plotly)

Plataforma de Business Intelligence para análise de performance comercial, financeira e de marketing digital, com sistema de login e permissões de acesso por usuário.

***

## 📌 Sobre o Projeto

Este projeto é uma aplicação web de análise de dados construída em Python com Streamlit. Ele se conecta a múltiplas fontes de dados, incluindo um banco de dados MySQL, a API do Google Analytics 4 e a API de Marketing da Meta (Facebook), para centralizar informações e gerar insights estratégicos.

A aplicação conta com um **sistema de autenticação próprio**, garantindo que diferentes perfis de usuário (vendas, financeiro, marketing, diretoria) tenham acesso apenas aos relatórios e dashboards pertinentes às suas funções.

## ✨ Funcionalidades Principais

- **Sistema de Login Seguro:** Autenticação de usuários e senhas com permissões de acesso por página gerenciadas centralmente.
- **Análise de Oportunidades:**
  - Visão geral de leads com filtros avançados.
  - Funil de Vendas para análise de conversão entre etapas.
  - Análise "Top N" de concursos para identificar os mais relevantes.
  - Tabelas dinâmicas (Pivot Tables) cruzando dados de concursos e origens.
- **Análise Financeira:**
  - Tabela hierárquica e interativa (AG-Grid) para análise detalhada de despesas.
  - Filtros em cascata por Unidades, Centro de Custo e Categorias.
  - Gráficos de resumo de custos por diversas dimensões.
  - Exportação de relatórios customizados para Excel com múltiplas abas.
- **Análise de Tendências:**
  - Análise comparativa de performance Mês a Mês.
  - Gráficos de "zoom" em janelas de tempo específicas para os principais concursos.
- **Performance de Marketing Digital (Google & Facebook):**
  - KPIs de saúde do site (Usuários, Sessões, Engajamento).
  - Tabela de Aquisição de Tráfego por Canal.
  - Análise de Custo, CPA e ROAS por campanha.
  - Visão unificada do investimento por "Curso Venda" entre as plataformas.
  - Gráficos de perfil de público (Demografia e Tecnologia).
  - Tabela de consultas do Google Search Console.

## 🛠️ Tecnologias Utilizadas

- **Interface e Dashboard:** Streamlit
- **Manipulação de Dados:** Pandas, NumPy
- **Visualização de Dados:** Plotly
- **Tabelas Avançadas:** Streamlit-AgGrid
- **Conexões com APIs:**
  - **Banco de Dados:** SQLAlchemy, MySQL Connector
  - **Google Analytics:** `google-analytics-data`
  - **Facebook Ads:** `facebook-business`
- **Gerenciamento de Segredos e Ambiente:**
  - Streamlit Secrets (para produção)
  - Python-dotenv (para ambiente local)

## 🚀 Guia de Instalação e Configuração

Siga os passos para configurar e executar o projeto.

### 1. Configuração do Ambiente de Produção (Streamlit Cloud)

1. **Crie um App no Streamlit Cloud** e conecte seu repositório GitHub. Configure o app como **Private**.
2. No painel do seu app, vá em **Settings > Secrets** e cole todas as suas credenciais, seguindo o formato abaixo:

    ```toml
    # Segredos para a Conexão com o Banco de Dados
    [database]
    host = "seu_host_remoto"
    user = "seu_usuario"
    password = "sua_senha"
    db_name = "seducar"
    port = "3306"

    # Credenciais para a API da Meta (Facebook)
    [facebook_api]
    app_id = "seu_app_id"
    app_secret = "seu_app_secret"
    access_token = "seu_token_de_longa_duração"
    ad_account_id = "act_seu_id_da_conta_de_anuncios"

    # Credenciais da Conta de Serviço do Google Cloud (cole o conteúdo do seu JSON aqui)
    [gcp_service_account]
    type = "service_account"
    project_id = "..."
    private_key_id = "..."
    private_key = """-----BEGIN PRIVATE KEY-----\n...-----END PRIVATE KEY-----\n"""
    client_email = "..."
    # ... resto das chaves do arquivo JSON

    # Credenciais para a API do Google Ads (baseado no google-ads.yaml)
    [google_ads]
    developer_token = "SEU_DEVELOPER_TOKEN"
    client_id = "SEU_CLIENT_ID"
    client_secret = "SEU_CLIENT_SECRET"
    refresh_token = "SEU_REFRESH_TOKEN"
    login_customer_id = "SEU_LOGIN_CUSTOMER_ID_DA_MCC"
    customer_id = "SEU_CUSTOMER_ID_DA_CONTA"
    use_proto_plus = true

    # Credenciais de Usuários para o Login do Dashboard
    [users]
    [users.nome_de_usuario_1]
    password = "senha_1"
    pages = '["all"]' # Acesso total

    [users.nome_de_usuario_2]
    password = "senha_2"
    pages = '["Oportunidades", "Tendencias"]' # Acesso limitado
    ```

### 2. Configuração do Ambiente Local (Desenvolvimento)

1. **Clone o repositório:**

    ```bash
    git clone [https://github.com/ulisseso2/dados_degrau_py.git](https://github.com/ulisseso2/dados_degrau_py.git)
    cd dados_degrau_py
    ```

2. **Crie e ative o ambiente virtual:**

    ```bash
    # Use python3 se o comando python não for encontrado
    python -m venv .venv
    # Windows
    .\.venv\Scripts\activate
    # Linux/Mac
    source .venv/bin/activate
    ```

3. **Instale as dependências:**

    ```bash
    pip install -r requirements.txt
    ```

4. **Crie e configure o arquivo `.env`:** Na raiz do projeto, crie um arquivo `.env` com todas as credenciais para o ambiente local.

    ```env
    # Credenciais do Banco de Dados
    DB_HOST=seu_host_local
    DB_USER=seu_usuario_local
    DB_PASSWORD=sua_senha_local
    DB_NAME=seducar
    DB_PORT=3306

    # Credenciais do Facebook
    FB_APP_ID="seu_app_id"
    FB_APP_SECRET="seu_app_secret"
    FB_ACCESS_TOKEN="seu_token_de_longa_duração"
    FB_AD_ACCOUNT_ID="act_seu_id_da_conta_de_anuncios"

    # Caminho para o arquivo de credenciais do Google
    GCP_SERVICE_ACCOUNT_FILE="gcp_credentials.json"

    # Usuários de teste para o login (JSON em uma única linha)
    LOCAL_USERS_DB='{"ulisses": {"password": "123", "pages": ["all"]}, "vendedor": {"password": "456", "pages": ["Oportunidades"]}}'
    ```

5. **Adicione o arquivo de credenciais do Google:** Coloque o arquivo `gcp_credentials.json` que você baixou na raiz do projeto.

## 🖥️ Executando o Projeto

Com o ambiente virtual ativado e o `.env` configurado, execute:

```bash
streamlit run main.py
```

A aplicação abrirá no seu navegador, começando pela tela de login.

## ⚠️ Manutenção e Observações Importantes

### Renovação do Token da API do Facebook

A credencial de acesso (`access_token`) para a **API de Marketing da Meta (Facebook)**, como configurada atualmente, é um **token de usuário de longa duração**, que possui uma validade de aproximadamente **60 dias**.

Isso significa que, após esse período, a conexão com a API do Facebook irá falhar e a página "Análise Facebook" do dashboard apresentará um erro de autenticação.

#### Solução de Curto Prazo: Renovação Manual (a cada ~50 dias)

Para garantir o funcionamento contínuo, o token precisa ser renovado manualmente. **É fortemente recomendado criar um lembrete recorrente no calendário para realizar este processo.**

O passo a passo para a renovação é:

1. Acessar o **Explorador da Graph API** no [Painel de Desenvolvedores da Meta](https://developers.facebook.com/tools/explorer/).
2. No canto superior direito, garantir que o aplicativo `dadosBi` esteja selecionado.
3. No campo "Usuário ou Página", gerar um novo **"Token de Acesso do Usuário"**, garantindo que as permissões `ads_read` e `read_insights` estejam concedidas.
4. Copiar o token gerado (de curta duração).
5. Levar este novo token para a **[Ferramenta de Depuração de Token](https://developers.facebook.com/tools/debug/accesstoken/)**.
6. Clicar no botão **"Estender Token de Acesso"** para gerar o token de longa duração.
7. Copiar o novo token de longa duração gerado.
8. Ir às configurações (**Settings > Secrets**) do seu app no Streamlit Cloud e **atualizar o valor** da chave `access_token` na seção `[facebook_api]`.

#### Solução Definitiva (Longo Prazo)

Para uma solução permanente que não requer renovação manual, a abordagem profissional é utilizar um **Token de Acesso de Usuário do Sistema (System User Access Token)**.

Este tipo de token é projetado para integrações de servidor (server-to-server) como a nossa e não expira. A sua configuração é mais complexa e deve ser feita dentro das "Configurações do Negócio" no Gerenciador de Negócios da Meta. Esta é a evolução recomendada para o projeto no futuro, para eliminar a necessidade de manutenção manual.

## 🏗️ Estrutura do Projeto

A aplicação utiliza uma arquitetura de roteamento manual para controlar o acesso às páginas.

```markdown
├── conexao
│   ├── __init__.py
│   └── mysql_connector.py
├── consultas
│   ├── contas
│   │   └── contas_a_pagar.sql
│   ├── oportunidades
│   │   └── oportunidades.sql
│   └── orders
│       └── orders.sql
├── gcp_credentials.json
├── main.py
├── _pages
│   ├── analise_facebook.py
│   ├── analise_ga.py
│   ├── campogrande_cancelamento.py
│   ├── campogrande.py
│   ├── cancelamentos.py
│   ├── centro_cancelamento.py
│   ├── centro.py
│   ├── financeiro.py
│   ├── gads_face_combinado.py
│   ├── madureira_cancelamento.py
│   ├── madureira.py
│   ├── matriculas.py
│   ├── niteroi_cancelamento.py
│   ├── niteroi.py
│   ├── oportunidades.py
│   └── tendencias.py
├── README.md
├── requirements.txt
└── utils
    └── sql_loader.py
```

## ✉️ Contato

Ulisses Oliveira - [ulissesrce@gmail.com](mailto:ulissesrce@gmail.com)
