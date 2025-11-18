#!/usr/bin/env python3
"""
Script para verificar a validade e data de expiração do token do Facebook
"""

import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Carrega as credenciais
load_dotenv('.facebook_credentials.env')

def verificar_token():
    """Verifica informações sobre o token de acesso"""
    
    access_token = os.getenv('FB_ACCESS_TOKEN')
    app_id = os.getenv('FB_APP_ID')
    
    if not access_token or not app_id:
        print("❌ Erro: Credenciais não encontradas no arquivo .facebook_credentials.env")
        return
    
    print("=" * 60)
    print("  VERIFICAÇÃO DE TOKEN DO FACEBOOK")
    print("=" * 60)
    print()
    
    # Verifica informações do token usando o debug_token endpoint
    url = f"https://graph.facebook.com/v18.0/debug_token"
    params = {
        "input_token": access_token,
        "access_token": f"{app_id}|{os.getenv('FB_APP_SECRET')}"
    }
    
    try:
        response = requests.get(url, params=params)
        
        if response.status_code != 200:
            print(f"⚠️  Erro ao verificar token: {response.status_code}")
            print(f"   {response.text}")
            return
        
        data = response.json().get('data', {})
        
        # Informações básicas
        print("📋 INFORMAÇÕES DO TOKEN:")
        print(f"   App ID: {data.get('app_id', 'N/A')}")
        print(f"   Válido: {'✅ Sim' if data.get('is_valid') else '❌ Não'}")
        print(f"   Tipo: {data.get('type', 'N/A')}")
        print(f"   Usuário ID: {data.get('user_id', 'N/A')}")
        print()
        
        # Data de expiração
        expires_at = data.get('expires_at')
        data_expires_at = data.get('data_access_expires_at')
        
        if expires_at:
            expiry_date = datetime.fromtimestamp(expires_at)
            days_remaining = (expiry_date - datetime.now()).days
            
            print("📅 EXPIRAÇÃO DO TOKEN:")
            print(f"   Data de expiração: {expiry_date.strftime('%d/%m/%Y %H:%M:%S')}")
            print(f"   Dias restantes: {days_remaining}")
            
            if days_remaining < 0:
                print(f"   Status: ❌ TOKEN EXPIRADO!")
            elif days_remaining <= 7:
                print(f"   Status: ⚠️  ATENÇÃO! Token expira em breve!")
            elif days_remaining <= 15:
                print(f"   Status: ⚠️  Considere renovar em breve")
            else:
                print(f"   Status: ✅ Token válido")
        else:
            print("📅 EXPIRAÇÃO DO TOKEN:")
            print("   ⚠️  Informação de expiração não disponível")
            print("   Tokens de longa duração geralmente expiram em ~60 dias")
        
        if data_expires_at:
            data_expiry = datetime.fromtimestamp(data_expires_at)
            print()
            print("📅 EXPIRAÇÃO DE ACESSO A DADOS:")
            print(f"   Data: {data_expiry.strftime('%d/%m/%Y %H:%M:%S')}")
        
        print()
        
        # Escopos/Permissões
        scopes = data.get('scopes', [])
        if scopes:
            print("🔐 PERMISSÕES CONCEDIDAS:")
            for scope in sorted(scopes):
                print(f"   ✓ {scope}")
        else:
            print("⚠️  Nenhuma permissão encontrada")
        
        print()
        
        # Teste de acesso à conta de anúncios
        print("🔍 TESTANDO ACESSO À CONTA DE ANÚNCIOS...")
        ad_account_id = os.getenv('FB_AD_ACCOUNT_ID')
        
        if ad_account_id:
            test_url = f"https://graph.facebook.com/v18.0/{ad_account_id}"
            test_params = {
                "access_token": access_token,
                "fields": "name,account_id,account_status"
            }
            
            test_response = requests.get(test_url, params=test_params)
            
            if test_response.status_code == 200:
                account_data = test_response.json()
                print(f"   ✅ Acesso concedido")
                print(f"   Nome da conta: {account_data.get('name', 'N/A')}")
                print(f"   Status: {account_data.get('account_status', 'N/A')}")
            else:
                print(f"   ❌ Erro ao acessar conta: {test_response.status_code}")
                error_data = test_response.json()
                if 'error' in error_data:
                    print(f"   {error_data['error'].get('message', '')}")
        
        print()
        print("=" * 60)
        
        # Aviso final se precisar renovar
        if expires_at:
            if days_remaining < 0:
                print()
                print("⚠️  AÇÃO NECESSÁRIA: Token expirado!")
                print("   Execute: ./renovar_token_facebook.sh TOKEN_DE_CURTA_DURACAO")
            elif days_remaining <= 15:
                print()
                print("💡 RECOMENDAÇÃO: Renove o token em breve")
                print("   Execute: ./renovar_token_facebook.sh TOKEN_DE_CURTA_DURACAO")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro na requisição: {e}")
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")

if __name__ == "__main__":
    verificar_token()
