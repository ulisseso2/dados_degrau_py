#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script para verificar a validade do token de acesso e do Pixel ID do Facebook.
"""

import os
import sys
import json
from pathlib import Path
import requests
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo principal e depois do arquivo específico do Facebook
load_dotenv()
load_dotenv('.facebook_credentials.env')  # Carrega as credenciais específicas do Facebook

def check_access_token(token):
    """Verifica se o token de acesso é válido"""
    print("\nVerificando token de acesso...")
    url = "https://graph.facebook.com/v18.0/me"
    params = {"access_token": token}
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        if "error" in data:
            print(f"❌ Token inválido: {data['error']['message']}")
            return False
        else:
            print(f"✅ Token válido! Conectado como: {data.get('name', 'Usuário')}")
            print(f"   ID: {data.get('id')}")
            return True
    
    except Exception as e:
        print(f"❌ Erro ao verificar token: {e}")
        return False

def check_pixel(token, pixel_id):
    """Verifica se o Pixel ID é válido"""
    print("\nVerificando Pixel ID...")
    url = f"https://graph.facebook.com/v18.0/{pixel_id}"
    params = {"access_token": token}
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        if "error" in data:
            print(f"❌ Pixel ID inválido: {data['error']['message']}")
            return False
        else:
            print(f"✅ Pixel ID válido! Nome: {data.get('name', 'Pixel')}")
            print(f"   ID: {data.get('id')}")
            return True
    
    except Exception as e:
        print(f"❌ Erro ao verificar Pixel ID: {e}")
        return False

def main():
    """Função principal"""
    print("=" * 80)
    print(" VERIFICAÇÃO DE CREDENCIAIS DO FACEBOOK")
    print("=" * 80)
    
    # Verifica o token de acesso
    token = os.getenv("FB_ACCESS_TOKEN")
    if not token:
        print("❌ Token de acesso não encontrado nos arquivos de configuração")
        token = input("\nDigite o token de acesso do Facebook: ").strip()
    else:
        print(f"📝 Token de acesso encontrado: {token[:10]}...{token[-4:]}")
    
    # Verifica o Pixel ID
    pixel_id = os.getenv("FB_PIXEL_ID")
    if not pixel_id:
        print("❌ Pixel ID não encontrado nos arquivos de configuração")
        pixel_id = input("\nDigite o Pixel ID do Facebook: ").strip()
    else:
        print(f"📝 Pixel ID encontrado: {pixel_id}")
    
    # Testa as credenciais
    token_valid = check_access_token(token)
    
    if token_valid:
        pixel_valid = check_pixel(token, pixel_id)
        
        if pixel_valid:
            print("\n✅ Todas as credenciais são válidas!")
            
            # Pergunta se deseja atualizar o arquivo de credenciais
            if token != os.getenv("FB_ACCESS_TOKEN") or pixel_id != os.getenv("FB_PIXEL_ID"):
                save = input("\nDeseja salvar essas credenciais no arquivo .facebook_credentials.env? (s/N): ").strip().lower()
                
                if save == "s":
                    try:
                        with open(".facebook_credentials.env", "w") as f:
                            f.write(f"FB_ACCESS_TOKEN={token}\n")
                            f.write(f"FB_PIXEL_ID={pixel_id}\n")
                        print("✅ Credenciais salvas com sucesso!")
                    except Exception as e:
                        print(f"❌ Erro ao salvar credenciais: {e}")
        else:
            print("\n❌ Verifique o Pixel ID e tente novamente.")
    else:
        print("\n❌ Verifique o token de acesso e tente novamente.")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
