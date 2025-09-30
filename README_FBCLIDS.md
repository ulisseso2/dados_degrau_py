# Ferramentas para FBclids - Degrau Cultural

Este conjunto de ferramentas permite o processamento de FBclids (Facebook Click IDs) para rastreamento de campanhas do Facebook/Meta, incluindo:

1. **Extração de FBclids** do banco de dados SQLite
2. **Formatação correta** dos FBclids para API da Meta
3. **Envio de eventos** para a API de Conversões da Meta
4. **Visualização e análise** dos dados de FBclids

## Requisitos

- Python 3.8 ou superior
- Acesso à API do Facebook (Access Token)
- Pixel ID do Facebook
- Banco de dados SQLite com FBclids (gclid_cache.db)

## Configuração Inicial

Para começar a usar as ferramentas, execute o script de configuração:

```bash
python setup_facebook_api.py
```

Este script irá:

1. Solicitar seu Facebook Access Token
2. Solicitar seu Pixel ID
3. Verificar se as credenciais são válidas
4. Salvar as credenciais no arquivo `.env` e nas secrets do Streamlit

## Ferramentas Disponíveis

### 1. Teste de FBclids

Para testar o envio de FBclids individuais para a API:

```bash
python test_fbclid_api.py
```

Este script permite:

- Testar FBclids do banco de dados
- Consultar FBclids do CRM
- Testar FBclids inseridos manualmente
- Verificar respostas da API de Conversões

### 2. Processamento em Lote

Para processar múltiplos FBclids em lote:

```bash
python fbclid_conversions.py --days 30 --limit 500
```

Opções disponíveis:

- `--days`: Número de dias para trás a considerar (padrão: 30)
- `--limit`: Limite de FBclids a processar (padrão: 1000)
- `--batch`: Tamanho do lote para envio (padrão: 50)
- `--db`: Caminho para o banco de dados SQLite (padrão: gclid_cache.db)
- `--output`: Arquivo para salvar os resultados em JSON

### 3. Dashboard Interativo

Para visualizar e analisar os FBclids em um dashboard:

```bash
streamlit run fbclid_dashboard.py
```

O dashboard permite:

- Visualizar estatísticas de FBclids
- Filtrar FBclids por data e URL
- Enviar FBclids selecionados para a API
- Analisar resultados do envio
- Exportar resultados em JSON

## Explicação Técnica

### Formato dos FBclids

Os FBclids devem estar no formato `fb.subdomainIndex.creationTime.fbclid`, onde:

- `fb`: Prefixo fixo
- `subdomainIndex`: Índice do subdomínio (geralmente 1)
- `creationTime`: Timestamp de criação
- `fbclid`: Valor original do FBclid

### API de Conversões da Meta

A API de Conversões da Meta é usada para enviar eventos contendo FBclids. Para cada FBclid, é enviado um evento do tipo `PageView` com o parâmetro `fbc` contendo o FBclid formatado.

### Armazenamento de FBclids

Os FBclids são extraídos da tabela `ad_clicks` do banco de dados SQLite `gclid_cache.db`. A tabela deve conter as colunas:

- `fbclid`: O valor do FBclid
- `created_at`: Data e hora de criação
- `client_id`: ID do cliente
- `url`: URL da página visitada

## Dicas de Uso

1. **Formatação de FBclids**: Se seus FBclids não estiverem no formato correto, as ferramentas irão formatá-los automaticamente.

2. **Processamento em Lote**: Para grandes volumes de dados, use o processamento em lote com um valor adequado para `--batch`.

3. **Alternativas de Rastreamento**: A API da Meta tem limitações para recuperar informações detalhadas de campanhas. Considere usar UTM parameters em paralelo.

4. **Dashboard**: Use o dashboard para análises rápidas e para testar pequenos lotes de FBclids.

5. **Log de Eventos**: Os logs são salvos em `fbclid_conversions.log` e contêm informações detalhadas sobre o processamento.

## Solução de Problemas

### Erro "Unsupported get request"

Este erro é esperado ao tentar consultar a API Graph diretamente com FBclids. A API não suporta essa operação.

### Erro de Autenticação

Verifique se seu Access Token tem as permissões necessárias:

- `ads_management`
- `business_management`

### Erro de Pixel ID

Verifique se o Pixel ID está correto e se sua conta tem acesso ao pixel.

### Problemas de Conexão

Verifique sua conexão com a internet e se a API da Meta está disponível.

## Contato e Suporte

Para dúvidas ou suporte, entre em contato com a equipe de TI do Degrau Cultural.
