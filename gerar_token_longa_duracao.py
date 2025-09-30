#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gerador de Token de Acesso de Longa Duração para Facebook API

Este script converte um token de acesso de curta duração em um token de longa duração
usando a API de troca de tokens do Facebook. Os tokens de longa duração geralmente
duram cerca de 60 dias, em vez das 2 horas dos tokens de curta duração.

Uso:
    python gerar_token_longa_duracao.py [token_curto]
    
Se nenhum token for fornecido como argumento, o script tentará usar o token
configurado no arquivo .facebook_credentials.env.
"""

import os
import sys
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()
load_dotenv('.facebook_credentials.env')

def obter_token_longa_duracao(token_curto, app_id, app_secret):
    """
    Converte um token de acesso de curta duração em um token de longa duração
    
    Args:
        token_curto: Token de curta duração obtido do Graph API Explorer
        app_id: ID do aplicativo Facebook
        app_secret: Chave secreta do aplicativo Facebook
        
    Returns:
        Token de longa duração ou None em caso de erro
    """
    print(f"Convertendo token de curta duração em token de longa duração...")
    
    url = "https://graph.facebook.com/v18.0/oauth/access_token"
    params = {
        'grant_type': 'fb_exchange_token',
        'client_id': app_id,
        'client_secret': app_secret,
        'fb_exchange_token': token_curto
    }
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        if 'error' in data:
            print(f"Erro ao trocar token: {data['error'].get('message')}")
            return None
        
        if 'access_token' in data:
            novo_token = data['access_token']
            print("Token de longa duração obtido com sucesso!")
            return novo_token
        else:
            print("Resposta inválida ao trocar token.")
            return None
    
    except Exception as e:
        print(f"Erro ao trocar token: {str(e)}")
        return None

def verificar_info_token(token):
    """
    Verifica informações sobre um token de acesso
    
    Args:
        token: Token de acesso do Facebook
        
    Returns:
        Informações do token ou None em caso de erro
    """
    print(f"Verificando informações do token...")
    
    url = "https://graph.facebook.com/debug_token"
    params = {
        'input_token': token,
        'access_token': token
    }
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        if 'error' in data:
            print(f"Erro ao verificar token: {data['error'].get('message')}")
            return None
        
        if 'data' in data:
            token_data = data['data']
            
            # Verifica se o token é válido
            if token_data.get('is_valid', False):
                print("Token é válido!")
                
                # Verifica a data de expiração
                expira_em = token_data.get('expires_at')
                if expira_em:
                    data_expiracao = datetime.fromtimestamp(expira_em)
                    agora = datetime.now()
                    
                    if data_expiracao > agora:
                        dias_restantes = (data_expiracao - agora).days
                        print(f"Token expira em: {data_expiracao.strftime('%d/%m/%Y')} ({dias_restantes} dias)")
                    else:
                        print(f"Token expirado em: {data_expiracao.strftime('%d/%m/%Y')}")
                else:
                    print("Token não tem data de expiração (token de longa duração ou nunca expira)")
                
                # Verifica o app associado
                app_id = token_data.get('app_id')
                if app_id:
                    print(f"Token associado ao App ID: {app_id}")
                
                # Verifica o tipo de token
                token_type = token_data.get('type')
                if token_type:
                    print(f"Tipo de token: {token_type}")
                
                return token_data
            else:
                print("Token é inválido!")
                if 'error' in token_data:
                    print(f"Erro: {token_data['error'].get('message')}")
                return None
        else:
            print("Resposta inválida ao verificar token.")
            return None
    
    except Exception as e:
        print(f"Erro ao verificar token: {str(e)}")
        return None

def salvar_token_em_env(token, arquivo='.facebook_credentials.env'):
    """
    Salva o token no arquivo de configuração
    
    Args:
        token: Token de longa duração a ser salvo
        arquivo: Caminho para o arquivo .env
        
    Returns:
        True se salvo com sucesso, False caso contrário
    """
    try:
        # Verifica se o arquivo existe
        if os.path.exists(arquivo):
            # Lê o conteúdo atual
            with open(arquivo, 'r') as f:
                linhas = f.readlines()
            
            # Substitui a linha do token ou adiciona no final
            token_atualizado = False
            for i, linha in enumerate(linhas):
                if linha.startswith('FB_ACCESS_TOKEN='):
                    linhas[i] = f'FB_ACCESS_TOKEN={token}\n'
                    token_atualizado = True
                    break
            
            if not token_atualizado:
                linhas.append(f'\nFB_ACCESS_TOKEN={token}\n')
            
            # Salva o arquivo atualizado
            with open(arquivo, 'w') as f:
                f.writelines(linhas)
        else:
            # Cria um novo arquivo
            with open(arquivo, 'w') as f:
                f.write(f'FB_ACCESS_TOKEN={token}\n')
        
        print(f"Token salvo com sucesso no arquivo {arquivo}!")
        return True
    
    except Exception as e:
        print(f"Erro ao salvar token: {str(e)}")
        return False

def main():
    """Função principal"""
    print("=" * 70)
    print(" GERADOR DE TOKEN DE ACESSO DE LONGA DURAÇÃO PARA FACEBOOK API")
    print("=" * 70)
    
    # Verifica se as credenciais do aplicativo estão configuradas
    app_id = os.getenv('FB_APP_ID')
    app_secret = os.getenv('FB_APP_SECRET')
    
    if not app_id or not app_secret:
        print("\nErro: ID do aplicativo ou chave secreta não configurados.")
        print("Configure as variáveis FB_APP_ID e FB_APP_SECRET no arquivo .facebook_credentials.env")
        
        print("\nPara configurar as credenciais, adicione ao arquivo .facebook_credentials.env:")
        print("FB_APP_ID=seu_app_id_aqui")
        print("FB_APP_SECRET=seu_app_secret_aqui")
        
        print("\nVocê pode encontrar essas informações em:")
        print("1. Acesse https://developers.facebook.com/apps/")
        print("2. Selecione seu aplicativo")
        print("3. Vá para Configurações > Básico")
        return
    
    # Verifica se um token foi fornecido como argumento
    if len(sys.argv) > 1:
        token_curto = sys.argv[1]
    else:
        # Se não houver argumento, tenta usar o token configurado
        token_curto = os.getenv('FB_ACCESS_TOKEN')
        
        if not token_curto:
            print("\nErro: Nenhum token de acesso fornecido.")
            print("Forneça um token como argumento ou configure a variável FB_ACCESS_TOKEN no arquivo .facebook_credentials.env")
            
            print("\nPara obter um token de curta duração:")
            print("1. Acesse https://developers.facebook.com/tools/explorer/")
            print("2. Selecione seu aplicativo")
            print("3. Gere um token com as permissões necessárias")
            print("4. Copie o token e execute novamente este script com o token como argumento:")
            print("   python gerar_token_longa_duracao.py SEU_TOKEN_AQUI")
            return
    
    # Verifica o token atual
    print("\nVerificando o token fornecido...")
    info_token = verificar_info_token(token_curto)
    
    if not info_token:
        return
    
    # Verifica se já é um token de longa duração
    expira_em = info_token.get('expires_at')
    if expira_em:
        data_expiracao = datetime.fromtimestamp(expira_em)
        agora = datetime.now()
        dias_restantes = (data_expiracao - agora).days
        
        if dias_restantes > 30:
            print("\nO token fornecido já parece ser um token de longa duração.")
            
            salvar = input("\nDeseja salvar este token no arquivo de configuração? (s/n): ")
            if salvar.lower() == 's':
                salvar_token_em_env(token_curto)
            
            return
    
    # Obtém um token de longa duração
    print("\nObtendo token de longa duração...")
    token_longo = obter_token_longa_duracao(token_curto, app_id, app_secret)
    
    if not token_longo:
        return
    
    # Verifica o novo token
    print("\nVerificando o novo token de longa duração...")
    info_novo_token = verificar_info_token(token_longo)
    
    if not info_novo_token:
        return
    
    # Exibe o token
    print("\n" + "=" * 70)
    print(" NOVO TOKEN DE LONGA DURAÇÃO")
    print("=" * 70)
    print(f"\n{token_longo}\n")
    
    # Pergunta se deseja salvar o token
    salvar = input("\nDeseja salvar este token no arquivo de configuração? (s/n): ")
    if salvar.lower() == 's':
        salvar_token_em_env(token_longo)
    else:
        print("\nToken não salvo. Lembre-se de copiar e usar o token conforme necessário.")
    
    print("\nProcesso concluído!")

if __name__ == "__main__":
    main()
