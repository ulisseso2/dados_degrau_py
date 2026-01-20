#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script para renovar o token do Facebook usando as credenciais existentes
"""

import requests
from datetime import datetime

# Credenciais do arquivo .facebook_credentials.env
FB_APP_ID = "706283637471142"
FB_APP_SECRET = "fd67f5083bc4791b06eccf6b08ccf437"
FB_ACCESS_TOKEN = "EAAKCXHlSd6YBPwEIIgLhLFxJZAoZAgU6zBgWnCzlHnWKNrSZAocZB9TCpdck8ijJVjSgTCZB7SBf7VvdjT4JQpnBL99bSuXeiIh498aV9zkRR7nrNsqvT9VhYnFoIZAnybspt7jO7FdWuy1qeAJnrWjl9KNowKLBgz6yddtuoWEZAsngef1seSY0liZCtZCkfvBG6744RvngZD"

print("=" * 80)
print("RENOVADOR DE TOKEN DO FACEBOOK")
print("=" * 80)

# Passo 1: Verificar o token atual
print("\n1. Verificando token atual...")
debug_url = "https://graph.facebook.com/debug_token"
debug_params = {
    'input_token': FB_ACCESS_TOKEN,
    'access_token': FB_ACCESS_TOKEN
}

try:
    response = requests.get(debug_url, params=debug_params)
    data = response.json()
    
    if 'data' in data and data['data'].get('is_valid'):
        token_info = data['data']
        print(f"✅ Token atual é válido")
        
        if 'expires_at' in token_info:
            expira_em = datetime.fromtimestamp(token_info['expires_at'])
            dias_restantes = (expira_em - datetime.now()).days
            print(f"   Expira em: {expira_em.strftime('%d/%m/%Y')} ({dias_restantes} dias restantes)")
        else:
            print(f"   Token sem expiração definida")
            
        print(f"   App ID: {token_info.get('app_id')}")
        print(f"   Tipo: {token_info.get('type')}")
    else:
        print(f"❌ Token atual é inválido ou expirado")
        print(f"   Resposta: {data}")
        
except Exception as e:
    print(f"❌ Erro ao verificar token: {e}")

# Passo 2: Obter novo token de longa duração
print("\n2. Obtendo novo token de longa duração...")
exchange_url = "https://graph.facebook.com/v18.0/oauth/access_token"
exchange_params = {
    'grant_type': 'fb_exchange_token',
    'client_id': FB_APP_ID,
    'client_secret': FB_APP_SECRET,
    'fb_exchange_token': FB_ACCESS_TOKEN
}

try:
    response = requests.get(exchange_url, params=exchange_params)
    data = response.json()
    
    if 'error' in data:
        print(f"❌ Erro ao trocar token: {data['error'].get('message')}")
        print(f"   Código: {data['error'].get('code')}")
        print(f"   Tipo: {data['error'].get('type')}")
        print("\n📝 SOLUÇÃO:")
        print("   1. Acesse: https://developers.facebook.com/tools/explorer/")
        print("   2. Selecione o App: 706283637471142")
        print("   3. Gere um novo token com as permissões:")
        print("      - ads_read")
        print("      - ads_management")
        print("      - read_insights")
        print("   4. Copie o novo token")
        print("   5. Execute este script novamente com o novo token:")
        print(f"      python3 renovar_token_facebook_agora.py SEU_NOVO_TOKEN")
    elif 'access_token' in data:
        novo_token = data['access_token']
        print(f"✅ Novo token obtido com sucesso!")
        
        # Verificar o novo token
        print("\n3. Verificando novo token...")
        verify_params = {
            'input_token': novo_token,
            'access_token': novo_token
        }
        
        response = requests.get(debug_url, params=verify_params)
        verify_data = response.json()
        
        if 'data' in verify_data and verify_data['data'].get('is_valid'):
            token_info = verify_data['data']
            
            if 'expires_at' in token_info:
                expira_em = datetime.fromtimestamp(token_info['expires_at'])
                dias_validade = (expira_em - datetime.now()).days
                print(f"✅ Token válido até: {expira_em.strftime('%d/%m/%Y')} ({dias_validade} dias)")
            else:
                print(f"✅ Token sem expiração (token permanente)")
        
        # Exibir o token
        print("\n" + "=" * 80)
        print("NOVO TOKEN DE LONGA DURAÇÃO:")
        print("=" * 80)
        print(f"\n{novo_token}\n")
        print("=" * 80)
        
        print("\n📝 PRÓXIMOS PASSOS:")
        print("1. Copie o token acima")
        print("2. Atualize o arquivo .facebook_credentials.env com:")
        print(f"   FB_ACCESS_TOKEN={novo_token}")
        print("\n3. Atualize os Secrets do Streamlit Cloud:")
        print("   - Acesse: https://share.streamlit.io/")
        print("   - Vá em Settings > Secrets")
        print("   - Atualize a seção [facebook_api]")
        print(f"   - access_token = \"{novo_token}\"")
        print("\n4. Salve e reinicie o app")
        
        # Criar arquivo de atualização
        with open('.facebook_credentials_NOVO.env', 'w') as f:
            f.write(f"FB_APP_ID={FB_APP_ID}\n")
            f.write(f"FB_APP_SECRET={FB_APP_SECRET}\n")
            f.write(f"FB_ACCESS_TOKEN={novo_token}\n")
            f.write(f"FB_AD_ACCOUNT_ID=act_567906076722542\n")
            f.write(f"FB_PIXEL_ID=872436769567154\n")
        
        print("\n✅ Arquivo '.facebook_credentials_NOVO.env' criado com o novo token!")
        print("   Renomeie este arquivo para '.facebook_credentials.env' quando estiver pronto")
        
    else:
        print(f"❌ Resposta inesperada: {data}")
        
except Exception as e:
    print(f"❌ Erro ao trocar token: {e}")

print("\n" + "=" * 80)
print("FIM")
print("=" * 80)
