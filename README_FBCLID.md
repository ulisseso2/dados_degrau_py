# Sistema de Rastreamento de FBclids

Este conjunto de scripts permite rastrear e processar Facebook Click IDs (FBclids) utilizando a API de Conversões da Meta.

## Visão Geral

A Meta não fornece uma API direta para consultar campanhas a partir de FBclids. O método recomendado é enviar eventos para a API de Conversões com os FBclids formatados corretamente.

## Arquivos Principais

- `fbclid_db.py`: Funções para gerenciar o banco de dados de FBclids
- `test_fbclid_api.py`: Script para testar o envio de FBclids para a API
- `fbclid_conversions.py`: Script para processar FBclids em lote
- `fbclid_dashboard.py`: Dashboard Streamlit para visualização e gerenciamento
- `check_fbclid_db.py`: Utilitário para verificar a estrutura do banco de dados
- `create_test_fbclid.py`: Cria um FBclid de teste para experimentação

## Configuração

1. Crie um arquivo `.facebook_credentials.env` na raiz do projeto com suas credenciais:

```
FB_ACCESS_TOKEN=seu_access_token_aqui
FB_APP_ID=seu_app_id_aqui
FB_APP_SECRET=seu_app_secret_aqui
FB_PIXEL_ID=seu_pixel_id_aqui
FB_AD_ACCOUNT_ID=seu_ad_account_id_aqui
```

Você pode usar o arquivo `facebook_credentials.example.env` como modelo.

2. Instale as dependências:

```bash
pip install -r requirements.txt
```

## Uso

### Verificar a Estrutura do Banco de Dados

Execute o script `check_fbclid_db.py` para verificar e configurar o banco de dados:

```bash
python check_fbclid_db.py
```

### Testar a API

Execute o script `test_fbclid_api.py` para testar a integração com a API da Meta:

```bash
python test_fbclid_api.py
```

### Processar FBclids em Lote

Execute o script `fbclid_conversions.py` para processar FBclids em lote:

```bash
python fbclid_conversions.py --days 30 --limit 500 --batch 50
```

Opções:
- `--days`: Número de dias para trás a considerar
- `--limit`: Limite de FBclids a processar
- `--batch`: Tamanho do lote para envio
- `--db`: Caminho para o banco de dados SQLite
- `--output`: Arquivo para salvar os resultados (JSON)

### Dashboard de Visualização

Execute o dashboard Streamlit para visualizar e gerenciar FBclids:

```bash
streamlit run fbclid_dashboard.py
```

## Formato do FBclid

Os FBclids devem ser formatados conforme a especificação da Meta:

```
fb.subdomainIndex.creationTime.fbclid
```

Onde:
- `fb` é sempre o prefixo
- `subdomainIndex` é 1 (para domínio principal)
- `creationTime` é o timestamp em segundos
- `fbclid` é o valor original do parâmetro

Exemplo:
```
fb.1.1672531200.sample_fbclid_123
```

## Limitações

- A Meta não permite consulta direta por FBclid na API Graph
- A API de Conversões é utilizada para enviar eventos, não para consultar campanhas
- Para rastreamento preciso, implemente UTM em seus links

## Recomendações

Para rastreamento preciso de campanhas, considere:

1. Usar parâmetros UTM em todos os seus links do Facebook
2. Configurar o Facebook Pixel no seu site
3. Implementar a API de Conversões diretamente no seu site
4. Considerar usar um sistema de atribuição de terceiros

## Documentação da Meta

- [Parâmetros fbp e fbc](https://developers.facebook.com/docs/marketing-api/conversions-api/parameters/fbp-and-fbc/)
- [API de Conversões](https://developers.facebook.com/docs/marketing-api/conversions-api/)
