# Configuração de Permissões do Facebook para API de Marketing

Este guia explica como configurar corretamente as permissões necessárias para acessar dados de campanhas e atribuições de FBclids via API do Facebook.

## 1. Requisitos de Permissões

Para acessar completamente os dados de campanhas e atribuições de FBclids, você precisa das seguintes permissões:

- **Marketing API Access**
- **Ads Management Standard Access**
- **Ads Management API Access**
- **Attribution API Permissions**
- **Conversions API Access**

## 2. Configuração no Facebook Developers

### 2.1. Acessar o Painel de Desenvolvedores

1. Acesse [Facebook Developers](https://developers.facebook.com/)
2. Faça login com sua conta do Facebook que tem acesso ao Business Manager
3. Vá para "Meus Aplicativos"

### 2.2. Configurar seu Aplicativo

1. Selecione o aplicativo que você está usando para acessar a API
2. Se ainda não tiver um aplicativo, clique em "Criar Aplicativo" e siga as instruções
   - Escolha o tipo "Business" ou "Other" dependendo do seu caso de uso
   - Complete o processo de criação

### 2.3. Adicionar Produtos ao Aplicativo

No painel do seu aplicativo, adicione os seguintes produtos:

1. **Marketing API**:
   - Vá para "Adicionar produtos" ou "Configurações de produtos"
   - Encontre "Marketing API" e clique em "Configurar"
   - Siga as instruções para ativar a API

2. **Conversions API**:
   - Vá para "Adicionar produtos" ou "Configurações de produtos"
   - Encontre "Conversions API" e clique em "Configurar"
   - Vincule seu Pixel ID ao aplicativo

### 2.4. Solicitar Permissões Avançadas

Para algumas permissões, o Facebook exige uma revisão do aplicativo:

1. Vá para "Revisão do Aplicativo" > "Permissões e Recursos"
2. Solicite as seguintes permissões:
   - `ads_management`
   - `ads_read`
   - `attribution_read`
   - `business_management`
   - `public_profile`
   - `attribution_read`

3. Para cada permissão, você precisará:
   - Explicar como sua aplicação usará a permissão
   - Fornecer instruções de teste detalhadas
   - Possivelmente gravar um vídeo demonstrando o uso

## 3. Configuração no Business Manager

### 3.1. Vincular o Aplicativo ao Business Manager

1. Acesse o [Business Manager](https://business.facebook.com/)
2. Vá para "Configurações de Negócios" > "Contas de Desenvolvedor"
3. Clique em "Adicionar" > "Adicionar uma conta de desenvolvedor"
4. Insira o ID do seu aplicativo e confirme

### 3.2. Atribuir Permissões de Ativos

1. No Business Manager, vá para "Configurações de Negócios" > "Contas de Anúncios"
2. Selecione a conta de anúncios que você deseja acessar
3. Clique em "Atribuir Parceiros"
4. Adicione o ID do seu aplicativo e atribua as seguintes permissões:
   - Gerenciar campanhas
   - Gerenciar anúncios
   - Ver relatórios de desempenho
   - Ver atribuições

5. Repita o mesmo processo para o Pixel:
   - Vá para "Configurações de Negócios" > "Dados" > "Pixels"
   - Selecione seu Pixel
   - Clique em "Atribuir Parceiros"
   - Adicione o ID do seu aplicativo e conceda permissões de "Gerenciar"

## 4. Atualização das Credenciais

Após configurar todas as permissões, atualize seu arquivo `.facebook_credentials.env` com as informações corretas:

```
FB_APP_ID=seu_app_id
FB_APP_SECRET=seu_app_secret
FB_ACCESS_TOKEN=seu_token_de_acesso_longo_prazo
FB_PIXEL_ID=seu_pixel_id
FB_AD_ACCOUNT_ID=seu_ad_account_id
```

### 4.1. Obter um Token de Acesso de Longa Duração

Os tokens de acesso padrão expiram em poucas horas. Para obter um token de longa duração:

1. Acesse o [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
2. Selecione seu aplicativo no menu suspenso
3. Clique em "Gerar Token de Acesso"
4. Selecione todas as permissões necessárias
5. Clique em "Gerar Token"
6. Use o endpoint de troca para converter em um token de longa duração:

```bash
curl -G \
  -d "grant_type=fb_exchange_token" \
  -d "client_id=SEU_APP_ID" \
  -d "client_secret=SEU_APP_SECRET" \
  -d "fb_exchange_token=SEU_TOKEN_CURTO" \
  "https://graph.facebook.com/v18.0/oauth/access_token"
```

## 5. Teste de Permissões

Para verificar se suas permissões estão configuradas corretamente, execute o seguinte teste:

```python
python -c "
import os
import requests
from dotenv import load_dotenv

load_dotenv('.facebook_credentials.env')

# Obtenha seu token de acesso
access_token = os.getenv('FB_ACCESS_TOKEN')
ad_account_id = os.getenv('FB_AD_ACCOUNT_ID')

# Teste de permissões básicas
print('Testando permissões básicas...')
response = requests.get(
    f'https://graph.facebook.com/v18.0/me/permissions',
    params={'access_token': access_token}
)
print(response.json())

# Teste de acesso a campanhas
print('\nTestando acesso a campanhas...')
response = requests.get(
    f'https://graph.facebook.com/v18.0/act_{ad_account_id}/campaigns',
    params={
        'access_token': access_token,
        'fields': 'name,id,status',
        'limit': 5
    }
)
print(response.json())

# Teste de acesso a atribuições
print('\nTestando acesso a conversões...')
pixel_id = os.getenv('FB_PIXEL_ID')
response = requests.get(
    f'https://graph.facebook.com/v18.0/{pixel_id}/stats',
    params={
        'access_token': access_token,
        'aggregation': 'event_name'
    }
)
print(response.json())
"
```

## 6. Solução de Problemas Comuns

### 6.1. Erro de Permissão Negada

Se você receber um erro como `(#200) Requires business_management permission`:

1. Verifique se seu aplicativo tem a permissão solicitada
2. Verifique se seu token de acesso inclui essa permissão
3. Verifique se o usuário que gerou o token tem acesso ao recurso
4. Verifique se o aplicativo está corretamente vinculado ao Business Manager

### 6.2. Erro de Acesso à Conta de Anúncios

Se você receber um erro como `(#17) User request limit reached` ou `(#200) Requires ads_management permission`:

1. Verifique se o aplicativo foi adicionado como parceiro da conta de anúncios
2. Verifique se as permissões corretas foram atribuídas
3. Se o limite de solicitações foi atingido, implemente uma estratégia de limitação de taxa

### 6.3. Erro de Acesso a FBclids

Para problemas específicos com FBclids:

1. Verifique se o aplicativo tem permissão de atribuição
2. Verifique se o Pixel está corretamente configurado e vinculado
3. Lembre-se que nem todos os FBclids são acessíveis via API devido à privacidade

## 7. Recursos Adicionais

- [Documentação da Marketing API](https://developers.facebook.com/docs/marketing-apis/)
- [Documentação da Conversions API](https://developers.facebook.com/docs/marketing-api/conversions-api/)
- [Guia de Melhores Práticas de Tokens de Acesso](https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived/)
