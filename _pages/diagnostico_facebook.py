import streamlit as st
import os
from dotenv import load_dotenv
from datetime import datetime

st.set_page_config(page_title="Diagnóstico Facebook API", page_icon="🔍")

st.title("🔍 Diagnóstico das Credenciais do Facebook")

# Carrega .env
load_dotenv()

st.header("1. Verificando Streamlit Secrets")

try:
    fb_secrets = st.secrets["facebook_api"]
    st.success("✅ Secrets do Facebook encontrados!")
    
    st.subheader("Credenciais nos Secrets:")
    
    # Exibe parcialmente para segurança
    app_id = fb_secrets.get("app_id", "")
    app_secret = fb_secrets.get("app_secret", "")
    access_token = fb_secrets.get("access_token", "")
    ad_account_id = fb_secrets.get("ad_account_id", "")
    
    st.write(f"**App ID:** `{app_id}`")
    st.write(f"**App Secret:** `{app_secret[:10]}...` (primeiros 10 caracteres)")
    st.write(f"**Access Token:** `{access_token[:20]}...` (primeiros 20 caracteres)")
    st.write(f"**Ad Account ID:** `{ad_account_id}`")
    
    # Verifica se é o token correto (novo)
    if access_token.startswith("EAAKCXHlSd6YBPwEIIgLhLFx"):
        st.success("✅ Token CORRETO detectado! (novo token válido até 17/01/2026)")
    elif access_token.startswith("EAANnrfKJ0ZC0BPNmqLoENo6"):
        st.error("❌ Token EXPIRADO detectado! Atualize os Secrets!")
    else:
        st.warning("⚠️ Token desconhecido. Verifique se é o token correto.")
    
except Exception as e:
    st.error(f"❌ Erro ao ler Secrets: {e}")
    st.info("Secrets não encontrados. A aplicação tentará usar variáveis de ambiente (.env)")

st.divider()

st.header("2. Verificando Variáveis de Ambiente (.env)")

env_app_id = os.getenv("FB_APP_ID")
env_app_secret = os.getenv("FB_APP_SECRET")
env_access_token = os.getenv("FB_ACCESS_TOKEN")
env_ad_account_id = os.getenv("FB_AD_ACCOUNT_ID")

if env_access_token:
    st.warning("⚠️ Variáveis de ambiente detectadas (usadas apenas em desenvolvimento local)")
    st.write(f"**App ID:** `{env_app_id}`")
    st.write(f"**Access Token:** `{env_access_token[:20]}...`")
else:
    st.info("ℹ️ Nenhuma variável de ambiente .env detectada (normal em produção)")

st.divider()

st.header("3. Teste de Conexão com a API")

if st.button("🔌 Testar Conexão com Facebook API"):
    try:
        from facebook_business.api import FacebookAdsApi
        from facebook_business.adobjects.adaccount import AdAccount
        
        # Tenta obter credenciais
        try:
            creds = st.secrets["facebook_api"]
            app_id = creds["app_id"]
            app_secret = creds["app_secret"]
            access_token = creds["access_token"]
            ad_account_id = creds["ad_account_id"]
            source = "Streamlit Secrets"
        except:
            app_id = os.getenv("FB_APP_ID")
            app_secret = os.getenv("FB_APP_SECRET")
            access_token = os.getenv("FB_ACCESS_TOKEN")
            ad_account_id = os.getenv("FB_AD_ACCOUNT_ID")
            source = "Variáveis de Ambiente"
        
        st.info(f"Usando credenciais de: **{source}**")
        
        # Inicializa a API
        FacebookAdsApi.init(app_id=app_id, app_secret=app_secret, access_token=access_token)
        account = AdAccount(ad_account_id)
        
        # Tenta buscar informações básicas
        account_info = account.api_get(fields=['name', 'account_id', 'account_status'])
        
        st.success("✅ Conexão com a API do Facebook estabelecida com sucesso!")
        st.json({
            "Nome da Conta": account_info.get('name'),
            "ID da Conta": account_info.get('account_id'),
            "Status": account_info.get('account_status')
        })
        
    except Exception as e:
        st.error(f"❌ Erro ao conectar com a API do Facebook:")
        st.code(str(e))
        
        error_str = str(e)
        if "expired" in error_str.lower():
            st.error("🔴 O TOKEN EXPIROU! Você precisa atualizar o access_token nos Secrets do Streamlit.")
        elif "190" in error_str:
            st.error("🔴 Erro de autenticação (código 190). Token inválido ou expirado.")

st.divider()

st.header("4. Informações do Sistema")

col1, col2 = st.columns(2)

with col1:
    st.metric("Data/Hora Atual", datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    
with col2:
    # Verifica se está em produção
    is_production = "STREAMLIT_SHARING_MODE" in os.environ or "HOSTNAME" in os.environ
    st.metric("Ambiente", "Produção ☁️" if is_production else "Local 💻")

st.divider()

st.header("5. Instruções de Atualização")

st.info("""
**Para atualizar o token em produção (Streamlit Cloud):**

1. Acesse: https://share.streamlit.io/
2. Encontre seu app e vá em **Settings > Secrets**
3. Atualize a seção `[facebook_api]` com:

```toml
[facebook_api]
app_id = "706283637471142"
app_secret = "fd67f5083bc4791b06eccf6b08ccf437"
access_token = "EAAKCXHlSd6YBPwEIIgLhLFxJZAoZAgU6zBgWnCzlHnWKNrSZAocZB9TCpdck8ijJVjSgTCZB7SBf7VvdjT4JQpnBL99bSuXeiIh498aV9zkRR7nrNsqvT9VhYnFoIZAnybspt7jO7FdWuy1qeAJnrWjl9KNowKLBgz6yddtuoWEZAsngef1seSY0liZCtZCkfvBG6744RvngZD"
ad_account_id = "act_567906076722542"
pixel_id = "872436769567154"
```

4. Clique em **Save**
5. O app reiniciará automaticamente
6. Execute este diagnóstico novamente para confirmar
""")

st.success("Token válido até: **17 de Janeiro de 2026**")
