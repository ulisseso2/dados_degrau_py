# generate_facebook_refresh_token.py
"""
Este script auxilia na geração de um token de acesso de longa duração para a API do Facebook.
O token de acesso comum expira após algumas horas, mas podemos gerar um token
de longa duração que dura aproximadamente 60 dias.

Instruções:
1. Obtenha um token de acesso curto no Facebook for Developers
2. Execute este script passando o token curto como argumento
3. O token de longa duração será exibido e pode ser usado no arquivo .env ou secrets

Para mais informações, consulte:
https://developers.facebook.com/docs/facebook-login/access-tokens/refreshing
"""

import requests
import argparse
import os
from dotenv import load_dotenv

# Carrega as variáveis do .env
load_dotenv()

def generate_long_lived_token(app_id, app_secret, short_lived_token):
    """
    Gera um token de acesso de longa duração para a API do Facebook.
    
    Args:
        app_id (str): ID do aplicativo do Facebook
        app_secret (str): Chave secreta do aplicativo
        short_lived_token (str): Token de acesso de curta duração
        
    Returns:
        str: Token de acesso de longa duração ou None em caso de erro
    """
    url = "https://graph.facebook.com/v17.0/oauth/access_token"
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_lived_token
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json().get("access_token")
    except requests.exceptions.RequestException as e:
        print(f"Erro ao obter token de longa duração: {e}")
        if response:
            print(f"Resposta: {response.text}")
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gera um token de acesso de longa duração para a API do Facebook")
    parser.add_argument("--token", help="Token de acesso de curta duração")
    parser.add_argument("--app_id", help="ID do aplicativo do Facebook")
    parser.add_argument("--app_secret", help="Chave secreta do aplicativo do Facebook")
    
    args = parser.parse_args()
    
    # Usa os argumentos da linha de comando ou as variáveis de ambiente
    app_id = args.app_id or os.getenv("FB_APP_ID")
    app_secret = args.app_secret or os.getenv("FB_APP_SECRET")
    short_lived_token = args.token or os.getenv("FB_SHORT_LIVED_TOKEN")
    
    if not app_id or not app_secret or not short_lived_token:
        print("Erro: Você deve fornecer o app_id, app_secret e token de curta duração")
        print("Você pode passar como argumentos ou definir as variáveis de ambiente FB_APP_ID, FB_APP_SECRET e FB_SHORT_LIVED_TOKEN")
        exit(1)
    
    long_lived_token = generate_long_lived_token(app_id, app_secret, short_lived_token)
    
    if long_lived_token:
        print("\n=====================================")
        print("Token de longa duração gerado com sucesso!")
        print("=====================================\n")
        print(f"FB_ACCESS_TOKEN={long_lived_token}\n")
        print("Adicione este token ao seu arquivo .env ou aos secrets do Streamlit")
        print("Este token é válido por aproximadamente 60 dias\n")
    else:
        print("Falha ao gerar o token de longa duração")
