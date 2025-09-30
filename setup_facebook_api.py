#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script para configuração das credenciais da API do Facebook
necessárias para o envio de FBclids para a API de Conversões.

Este script solicita ao usuário o Access Token e o Pixel ID
e os salva no arquivo .env e nas secrets do Streamlit.
"""

import os
import sys
import json
from pathlib import Path
import requests

def check_token(access_token):
    """
    Verifica se o token de acesso é válido
    """
    try:
        url = f"https://graph.facebook.com/v17.0/me"
        params = {"access_token": access_token}
        response = requests.get(url, params=params)
        data = response.json()
        
        if 'error' in data:
            print(f"\n❌ Erro na validação do token: {data['error']['message']}")
            return False
        
        print(f"\n✅ Token válido! Conectado como: {data.get('name', 'Usuário')}")
        return True
    
    except Exception as e:
        print(f"\n❌ Erro ao validar token: {str(e)}")
        return False

def check_pixel(access_token, pixel_id):
    """
    Verifica se o Pixel ID é válido
    """
    try:
        url = f"https://graph.facebook.com/v17.0/{pixel_id}"
        params = {"access_token": access_token}
        response = requests.get(url, params=params)
        data = response.json()
        
        if 'error' in data:
            print(f"\n❌ Erro na validação do Pixel ID: {data['error']['message']}")
            return False
        
        print(f"\n✅ Pixel ID válido! Nome: {data.get('name', 'Pixel')}")
        return True
    
    except Exception as e:
        print(f"\n❌ Erro ao validar Pixel ID: {str(e)}")
        return False

def save_to_env(access_token, pixel_id):
    """
    Salva as credenciais no arquivo .env
    """
    try:
        env_path = Path('.env')
        
        # Verifica se o arquivo já existe
        if env_path.exists():
            # Lê o conteúdo atual
            with open(env_path, 'r') as f:
                lines = f.readlines()
            
            # Atualiza as linhas existentes ou adiciona novas
            updated_access_token = False
            updated_pixel_id = False
            
            for i, line in enumerate(lines):
                if line.startswith('FB_ACCESS_TOKEN='):
                    lines[i] = f'FB_ACCESS_TOKEN={access_token}\n'
                    updated_access_token = True
                elif line.startswith('PIXEL_ID='):
                    lines[i] = f'PIXEL_ID={pixel_id}\n'
                    updated_pixel_id = True
            
            # Adiciona as linhas que não existiam
            if not updated_access_token:
                lines.append(f'FB_ACCESS_TOKEN={access_token}\n')
            if not updated_pixel_id:
                lines.append(f'PIXEL_ID={pixel_id}\n')
            
            # Escreve de volta no arquivo
            with open(env_path, 'w') as f:
                f.writelines(lines)
        else:
            # Cria um novo arquivo .env
            with open(env_path, 'w') as f:
                f.write(f'FB_ACCESS_TOKEN={access_token}\n')
                f.write(f'PIXEL_ID={pixel_id}\n')
        
        print(f"\n✅ Credenciais salvas com sucesso no arquivo .env")
        return True
    
    except Exception as e:
        print(f"\n❌ Erro ao salvar no arquivo .env: {str(e)}")
        return False

def save_to_streamlit_secrets(access_token, pixel_id):
    """
    Salva as credenciais nas secrets do Streamlit
    """
    try:
        # Caminho para o diretório .streamlit
        streamlit_dir = Path('.streamlit')
        streamlit_dir.mkdir(exist_ok=True)
        
        # Caminho para o arquivo de secrets
        secrets_path = streamlit_dir / 'secrets.toml'
        
        # Conteúdo para o arquivo de secrets
        secrets_content = f"""[facebook]
access_token = "{access_token}"
pixel_id = "{pixel_id}"
"""
        
        # Escreve no arquivo
        with open(secrets_path, 'w') as f:
            f.write(secrets_content)
        
        print(f"\n✅ Credenciais salvas com sucesso nas secrets do Streamlit")
        return True
    
    except Exception as e:
        print(f"\n❌ Erro ao salvar nas secrets do Streamlit: {str(e)}")
        return False

def main():
    """
    Função principal
    """
    print("\n" + "=" * 80)
    print(" CONFIGURAÇÃO DE CREDENCIAIS PARA API DO FACEBOOK")
    print("=" * 80)
    print("\nEste script irá configurar as credenciais necessárias para o envio de FBclids")
    print("para a API de Conversões do Facebook.")
    print("\nVocê precisará de:")
    print("1. Um Access Token com permissões de leitura e escrita")
    print("2. O ID do Pixel do Facebook")
    print("\nPara obter um Access Token de longa duração, visite:")
    print("https://developers.facebook.com/tools/explorer/")
    print("\nPara encontrar o ID do seu Pixel, acesse:")
    print("https://business.facebook.com/events_manager/")
    
    # Solicita o Access Token
    access_token = input("\nDigite o Access Token do Facebook: ").strip()
    
    # Verifica se o token é válido
    if not check_token(access_token):
        print("\n⚠️ O token informado parece inválido. Deseja continuar mesmo assim? (s/N): ", end="")
        if input().lower() != 's':
            print("\n❌ Configuração cancelada.")
            return
    
    # Solicita o Pixel ID
    pixel_id = input("\nDigite o ID do Pixel do Facebook: ").strip()
    
    # Verifica se o Pixel ID é válido
    if access_token and not check_pixel(access_token, pixel_id):
        print("\n⚠️ O Pixel ID informado parece inválido. Deseja continuar mesmo assim? (s/N): ", end="")
        if input().lower() != 's':
            print("\n❌ Configuração cancelada.")
            return
    
    # Salva as credenciais
    env_saved = save_to_env(access_token, pixel_id)
    streamlit_saved = save_to_streamlit_secrets(access_token, pixel_id)
    
    if env_saved and streamlit_saved:
        print("\n" + "=" * 80)
        print(" CONFIGURAÇÃO CONCLUÍDA COM SUCESSO!")
        print("=" * 80)
        print("\nAgora você pode executar:")
        print("- python fbclid_conversions.py (para envio em lote via terminal)")
        print("- streamlit run fbclid_dashboard.py (para o dashboard interativo)")
    else:
        print("\n" + "=" * 80)
        print(" CONFIGURAÇÃO PARCIAL!")
        print("=" * 80)
        print("\nAlguns erros ocorreram durante a configuração.")
        print("Verifique as mensagens acima e tente novamente.")

if __name__ == "__main__":
    main()
