# 📋 INSTRUÇÕES PARA CONFIGURAR SECRETS NO STREAMLIT CLOUD

## ⚠️ IMPORTANTE: Você precisa atualizar os secrets no Streamlit Cloud

Acesse: **Settings → Secrets** no seu app do Streamlit Cloud

---

## 🔑 Estrutura dos Secrets Necessários

### 1. Octadesk API
```toml
[octadesk_api]
token = "SEU_TOKEN_OCTADESK"
base_url = "https://SEU_SUBDOMINIO.api001.octadesk.services"
```

### 2. OpenAI API
```toml
openai_api_key = "sk-proj-SEU_TOKEN_OPENAI"
openai_model = "gpt-4o-mini"
openai_temperature = "0.2"
openai_max_tokens = "4000"
```

### 3. Facebook API
⚠️ **IMPORTANTE:** Gere um token de longa duração válido!

```toml
[facebook_api]
app_id = "SEU_APP_ID"
app_secret = "SEU_APP_SECRET"
access_token = "SEU_TOKEN_DE_LONGA_DURACAO"
ad_account_id = "act_SEU_ACCOUNT_ID"
pixel_id = "SEU_PIXEL_ID"
```

**Para gerar um novo token:**
1. Execute localmente: `python gerar_token_rapido.py`
2. Ou acesse: https://developers.facebook.com/tools/explorer/
3. Solicite permissões: `ads_read`, `ads_management`, `business_management`
4. Gere e estenda o token para longa duração

### 4. Google Ads
```toml
[google_ads]
developer_token = "SEU_DEVELOPER_TOKEN"
client_id = "SEU_CLIENT_ID.apps.googleusercontent.com"
client_secret = "SEU_CLIENT_SECRET"
refresh_token = "SEU_REFRESH_TOKEN"
login_customer_id = "SEU_LOGIN_CUSTOMER_ID"
customer_id = "SEU_CUSTOMER_ID"
use_proto_plus = true
```

### 5. Google Cloud Platform
```toml
[gcp_service_account]
type = "service_account"
project_id = "SEU_PROJECT_ID"
private_key_id = "SUA_PRIVATE_KEY_ID"
private_key = "-----BEGIN PRIVATE KEY-----\nSUA_CHAVE_PRIVADA\n-----END PRIVATE KEY-----\n"
client_email = "seu-email@projeto.iam.gserviceaccount.com"
client_id = "SEU_CLIENT_ID"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/seu-email%40projeto.iam.gserviceaccount.com"
universe_domain = "googleapis.com"
```

### 6. Database (MySQL)
```toml
[database]
host = "seu-host.rds.amazonaws.com"
user = "seu-usuario"
password = "sua-senha"
db_name = "seu-banco"
port = "3306"

[database_secundario]
host = "seu-host-secundario.rds.amazonaws.com"
user = "seu-usuario"
password = "sua-senha"
db_name = "seu-banco"
port = "3306"

[database_escrita]
host = "seu-host.rds.amazonaws.com"
user = "seu-usuario-escrita"
password = "sua-senha"
db_name = "seu-banco"
port = "3306"
```

### 7. Usuários do Sistema
```toml
[users.nome_usuario]
password = "senha"
pages = '["Página 1", "Página 2"]'
```

---

## 📝 Como Aplicar

1. Copie a estrutura acima
2. **Substitua TODOS os valores de exemplo pelas suas credenciais reais**
3. Acesse: https://share.streamlit.io/
4. Seu App → Menu "⋮" → Settings → Secrets
5. Cole o conteúdo atualizado
6. Clique em Save

---

## 🔒 Segurança

- ⚠️ **NUNCA** commite arquivos com credenciais reais no Git
- ✅ Use `.env` localmente (já está no .gitignore)
- ✅ Use Streamlit Secrets para produção
- ✅ Mantenha seus tokens atualizados

---

## 🆘 Problemas Comuns

### Token do Facebook Expirado
Execute: `python gerar_token_rapido.py`

### OpenAI não funciona
Verifique se `openai_api_key` está configurado corretamente

### Octadesk Base URL
Certifique-se de usar `base_url` (não `octadesk_base_url`)

---

## 📚 Referências

- [Streamlit Secrets](https://docs.streamlit.io/streamlit-community-cloud/deploy-your-app/secrets-management)
- [Facebook Access Tokens](https://developers.facebook.com/docs/facebook-login/access-tokens)
- [Google Ads API](https://developers.google.com/google-ads/api/docs/start)
