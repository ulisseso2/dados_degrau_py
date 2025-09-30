#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Verificador de Permissões da API do Facebook

Este script verifica se as credenciais do Facebook estão configuradas corretamente
e se as permissões necessárias foram concedidas para acessar dados de campanhas e FBclids.

Uso:
    python verificar_permissoes_facebook.py

O script irá verificar:
1. Se as credenciais básicas estão configuradas
2. Se o token de acesso é válido
3. Se as permissões necessárias foram concedidas
4. Se há acesso às campanhas
5. Se há acesso aos pixels e eventos de conversão
6. Se é possível consultar informações de atribuição
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

# Variáveis para cores no terminal
VERMELHO = "\033[91m"
VERDE = "\033[92m"
AMARELO = "\033[93m"
AZUL = "\033[94m"
RESET = "\033[0m"
NEGRITO = "\033[1m"

def imprimir_titulo(texto):
    """Imprime um título formatado"""
    separador = "=" * 70
    print(f"\n{AZUL}{NEGRITO}{separador}")
    print(f" {texto}")
    print(f"{separador}{RESET}")

def imprimir_sucesso(texto):
    """Imprime uma mensagem de sucesso"""
    print(f"{VERDE}✅ {texto}{RESET}")

def imprimir_erro(texto):
    """Imprime uma mensagem de erro"""
    print(f"{VERMELHO}❌ {texto}{RESET}")

def imprimir_aviso(texto):
    """Imprime uma mensagem de aviso"""
    print(f"{AMARELO}⚠️ {texto}{RESET}")

def imprimir_info(texto):
    """Imprime uma mensagem informativa"""
    print(f"{AZUL}ℹ️ {texto}{RESET}")

def verificar_credenciais():
    """Verifica se as credenciais básicas estão configuradas"""
    imprimir_titulo("VERIFICAÇÃO DE CREDENCIAIS")
    
    credenciais = {
        'FB_ACCESS_TOKEN': os.getenv('FB_ACCESS_TOKEN'),
        'FB_PIXEL_ID': os.getenv('FB_PIXEL_ID'),
        'FB_AD_ACCOUNT_ID': os.getenv('FB_AD_ACCOUNT_ID'),
        'FB_APP_ID': os.getenv('FB_APP_ID'),
        'FB_APP_SECRET': os.getenv('FB_APP_SECRET')
    }
    
    todas_configuradas = True
    
    print("Verificando credenciais configuradas:")
    for nome, valor in credenciais.items():
        if valor:
            # Mascarar tokens e secrets para segurança
            if 'TOKEN' in nome or 'SECRET' in nome:
                valor_exibido = f"{valor[:6]}...{valor[-4:]}" if len(valor) > 10 else "***"
                imprimir_sucesso(f"{nome}: {valor_exibido}")
            else:
                imprimir_sucesso(f"{nome}: {valor}")
        else:
            imprimir_erro(f"{nome}: Não configurado")
            todas_configuradas = False
    
    return todas_configuradas, credenciais

def verificar_token_acesso(token):
    """Verifica se o token de acesso é válido"""
    imprimir_titulo("VERIFICAÇÃO DO TOKEN DE ACESSO")
    
    if not token:
        imprimir_erro("Token de acesso não fornecido.")
        return False, {}
    
    # Verifica o token usando o endpoint de debug
    url = "https://graph.facebook.com/debug_token"
    params = {
        'input_token': token,
        'access_token': token
    }
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        if 'error' in data:
            imprimir_erro(f"Erro ao verificar token: {data['error'].get('message')}")
            return False, {}
        
        if 'data' in data:
            token_data = data['data']
            
            # Verifica se o token é válido
            if token_data.get('is_valid', False):
                imprimir_sucesso("Token de acesso é válido!")
                
                # Verifica a data de expiração
                expira_em = token_data.get('expires_at')
                if expira_em:
                    data_expiracao = datetime.fromtimestamp(expira_em)
                    agora = datetime.now()
                    
                    if data_expiracao > agora:
                        dias_restantes = (data_expiracao - agora).days
                        imprimir_info(f"Token expira em: {data_expiracao.strftime('%d/%m/%Y')} ({dias_restantes} dias)")
                    else:
                        imprimir_erro(f"Token expirado em: {data_expiracao.strftime('%d/%m/%Y')}")
                else:
                    imprimir_info("Token não tem data de expiração (token de longa duração)")
                
                # Verifica o app associado
                app_id = token_data.get('app_id')
                if app_id:
                    imprimir_info(f"Token associado ao App ID: {app_id}")
                
                # Verifica o tipo de token
                token_type = token_data.get('type')
                if token_type:
                    imprimir_info(f"Tipo de token: {token_type}")
                
                return True, token_data
            else:
                imprimir_erro("Token de acesso é inválido!")
                if 'error' in token_data:
                    imprimir_erro(f"Erro: {token_data['error'].get('message')}")
                return False, token_data
        else:
            imprimir_erro("Resposta inválida ao verificar token.")
            return False, {}
    
    except Exception as e:
        imprimir_erro(f"Erro ao verificar token: {str(e)}")
        return False, {}

def verificar_permissoes(token):
    """Verifica as permissões concedidas ao token"""
    imprimir_titulo("VERIFICAÇÃO DE PERMISSÕES")
    
    if not token:
        imprimir_erro("Token de acesso não fornecido.")
        return False
    
    url = "https://graph.facebook.com/v18.0/me/permissions"
    params = {
        'access_token': token
    }
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        if 'error' in data:
            imprimir_erro(f"Erro ao verificar permissões: {data['error'].get('message')}")
            return False
        
        if 'data' in data:
            permissoes = data['data']
            
            if not permissoes:
                imprimir_aviso("Nenhuma permissão encontrada. Isso pode indicar um token de aplicativo em vez de um token de usuário.")
                return True  # Tokens de aplicativo podem não ter permissões listadas aqui
            
            # Permissões necessárias para acesso completo
            permissoes_necessarias = [
                'ads_management',
                'ads_read',
                'attribution_read',
                'business_management',
                'public_profile',
                'leads_retrieval'
            ]
            
            permissoes_concedidas = []
            permissoes_negadas = []
            
            # Classifica as permissões
            for perm in permissoes:
                nome = perm.get('permission')
                status = perm.get('status')
                
                if status == 'granted':
                    permissoes_concedidas.append(nome)
                else:
                    permissoes_negadas.append(nome)
            
            # Verifica as permissões necessárias
            permissoes_faltantes = [p for p in permissoes_necessarias if p not in permissoes_concedidas]
            
            imprimir_info(f"Total de permissões concedidas: {len(permissoes_concedidas)}")
            
            # Exibe as permissões concedidas
            if permissoes_concedidas:
                print("\nPermissões concedidas:")
                for perm in permissoes_concedidas:
                    if perm in permissoes_necessarias:
                        imprimir_sucesso(f"- {perm} (necessária)")
                    else:
                        imprimir_info(f"- {perm}")
            
            # Exibe as permissões negadas
            if permissoes_negadas:
                print("\nPermissões negadas:")
                for perm in permissoes_negadas:
                    imprimir_erro(f"- {perm}")
            
            # Exibe as permissões faltantes
            if permissoes_faltantes:
                print("\nPermissões necessárias faltantes:")
                for perm in permissoes_faltantes:
                    imprimir_aviso(f"- {perm}")
                
                print("\nPara solicitar permissões adicionais:")
                print("1. Acesse https://developers.facebook.com/apps/")
                print("2. Selecione seu aplicativo")
                print("3. Vá para Revisão do Aplicativo > Permissões e Recursos")
                print("4. Solicite as permissões faltantes")
            
            return len(permissoes_faltantes) == 0
        else:
            imprimir_erro("Resposta inválida ao verificar permissões.")
            return False
    
    except Exception as e:
        imprimir_erro(f"Erro ao verificar permissões: {str(e)}")
        return False

def verificar_acesso_campanhas(token, account_id):
    """Verifica o acesso às campanhas"""
    imprimir_titulo("VERIFICAÇÃO DE ACESSO ÀS CAMPANHAS")
    
    if not token:
        imprimir_erro("Token de acesso não fornecido.")
        return False
    
    if not account_id:
        imprimir_erro("ID da conta de anúncios não fornecido.")
        return False
    
    # Remove 'act_' do início do ID, se presente
    account_id = account_id.replace('act_', '')
    
    url = f"https://graph.facebook.com/v18.0/act_{account_id}/campaigns"
    params = {
        'access_token': token,
        'fields': 'name,id,status',
        'limit': 5
    }
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        if 'error' in data:
            imprimir_erro(f"Erro ao acessar campanhas: {data['error'].get('message')}")
            
            # Orientações específicas com base no código de erro
            error_code = data['error'].get('code')
            
            if error_code == 200:
                imprimir_aviso("Esse erro geralmente indica problemas de permissão.")
                imprimir_aviso("Verifique se o aplicativo foi adicionado como parceiro da conta de anúncios:")
                imprimir_aviso("1. Acesse https://business.facebook.com/settings/ad-accounts")
                imprimir_aviso("2. Selecione a conta de anúncios")
                imprimir_aviso("3. Clique em 'Atribuir Parceiros'")
                imprimir_aviso("4. Adicione o ID do seu aplicativo e conceda as permissões necessárias")
            
            return False
        
        if 'data' in data:
            campanhas = data['data']
            
            if campanhas:
                imprimir_sucesso(f"Acesso às campanhas confirmado! Encontradas {len(campanhas)} campanhas.")
                
                print("\nExemplos de campanhas:")
                for i, campanha in enumerate(campanhas[:3], 1):
                    nome = campanha.get('name', 'Sem nome')
                    status = campanha.get('status', 'Desconhecido')
                    campanha_id = campanha.get('id', 'Sem ID')
                    
                    print(f"{i}. {nome} (Status: {status}, ID: {campanha_id})")
                
                return True
            else:
                imprimir_aviso("Nenhuma campanha encontrada. A conta pode não ter campanhas ativas.")
                return True  # Retorna True porque o acesso foi confirmado, apenas não há campanhas
        else:
            imprimir_erro("Resposta inválida ao acessar campanhas.")
            return False
    
    except Exception as e:
        imprimir_erro(f"Erro ao acessar campanhas: {str(e)}")
        return False

def verificar_acesso_pixel(token, pixel_id):
    """Verifica o acesso ao pixel e eventos de conversão"""
    imprimir_titulo("VERIFICAÇÃO DE ACESSO AO PIXEL")
    
    if not token:
        imprimir_erro("Token de acesso não fornecido.")
        return False
    
    if not pixel_id:
        imprimir_erro("ID do Pixel não fornecido.")
        return False
    
    url = f"https://graph.facebook.com/v18.0/{pixel_id}"
    params = {
        'access_token': token,
        'fields': 'name,id,is_created_by_business,last_fired_time'
    }
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        if 'error' in data:
            imprimir_erro(f"Erro ao acessar pixel: {data['error'].get('message')}")
            
            # Orientações específicas
            imprimir_aviso("Verifique se o aplicativo tem acesso ao pixel:")
            imprimir_aviso("1. Acesse https://business.facebook.com/settings/pixels")
            imprimir_aviso("2. Selecione o pixel")
            imprimir_aviso("3. Clique em 'Atribuir Parceiros'")
            imprimir_aviso("4. Adicione o ID do seu aplicativo e conceda as permissões necessárias")
            
            return False
        
        imprimir_sucesso(f"Acesso ao Pixel confirmado!")
        imprimir_info(f"Nome do Pixel: {data.get('name')}")
        
        if 'last_fired_time' in data:
            last_fired = datetime.fromisoformat(data['last_fired_time'].replace('Z', '+00:00'))
            imprimir_info(f"Último disparo: {last_fired.strftime('%d/%m/%Y %H:%M:%S')}")
        
        # Agora verifica os eventos do pixel
        print("\nVerificando eventos do pixel...")
        
        stats_url = f"https://graph.facebook.com/v18.0/{pixel_id}/stats"
        stats_params = {
            'access_token': token,
            'aggregation': 'event_name'
        }
        
        stats_response = requests.get(stats_url, params=stats_params)
        stats_data = stats_response.json()
        
        if 'error' in stats_data:
            imprimir_aviso(f"Não foi possível acessar as estatísticas do pixel: {stats_data['error'].get('message')}")
            return True  # Retorna True porque o acesso ao pixel foi confirmado
        
        if 'data' in stats_data:
            eventos = stats_data['data']
            
            if eventos:
                imprimir_sucesso(f"Encontrados {len(eventos)} tipos de eventos.")
                
                print("\nExemplos de eventos:")
                for i, evento in enumerate(eventos[:5], 1):
                    nome = evento.get('event_name', 'Sem nome')
                    contagem = evento.get('count', 0)
                    
                    print(f"{i}. {nome} ({contagem} ocorrências)")
            else:
                imprimir_aviso("Nenhum evento encontrado para este pixel.")
        
        return True
    
    except Exception as e:
        imprimir_erro(f"Erro ao acessar pixel: {str(e)}")
        return False

def verificar_acesso_atribuicao(token, account_id):
    """Verifica o acesso às informações de atribuição"""
    imprimir_titulo("VERIFICAÇÃO DE ACESSO À ATRIBUIÇÃO")
    
    if not token:
        imprimir_erro("Token de acesso não fornecido.")
        return False
    
    if not account_id:
        imprimir_erro("ID da conta de anúncios não fornecido.")
        return False
    
    # Remove 'act_' do início do ID, se presente
    account_id = account_id.replace('act_', '')
    
    # Tenta acessar a API de insights de atribuição
    url = f"https://graph.facebook.com/v18.0/act_{account_id}/ads_conversion_stats"
    params = {
        'access_token': token,
        'fields': 'total_conversion_value,total_conversion_count,campaign_id,campaign_name',
        'limit': 5
    }
    
    try:
        imprimir_info("Testando acesso às estatísticas de conversão...")
        response = requests.get(url, params=params)
        data = response.json()
        
        if 'error' in data:
            error_msg = data['error'].get('message')
            error_code = data['error'].get('code')
            
            if error_code == 100:
                imprimir_aviso("API de atribuição não disponível ou não suportada para esta conta.")
                imprimir_aviso("Este é um comportamento esperado para algumas contas.")
                
                # Tenta uma API alternativa para verificar o acesso básico de atribuição
                imprimir_info("Tentando método alternativo de verificação de atribuição...")
                
                alt_url = f"https://graph.facebook.com/v18.0/act_{account_id}/insights"
                alt_params = {
                    'access_token': token,
                    'fields': 'impressions,clicks,action_values,actions',
                    'level': 'campaign',
                    'limit': 5
                }
                
                alt_response = requests.get(alt_url, params=alt_params)
                alt_data = alt_response.json()
                
                if 'error' in alt_data:
                    imprimir_erro(f"Erro no método alternativo: {alt_data['error'].get('message')}")
                    return False
                
                if 'data' in alt_data and alt_data['data']:
                    imprimir_sucesso("Acesso básico a insights de atribuição confirmado via método alternativo!")
                    return True
                else:
                    imprimir_aviso("Não foi possível confirmar acesso à atribuição.")
                    return False
            else:
                imprimir_erro(f"Erro ao acessar informações de atribuição: {error_msg}")
                return False
        
        if 'data' in data:
            conversoes = data['data']
            
            if conversoes:
                imprimir_sucesso(f"Acesso às informações de atribuição confirmado! Encontradas {len(conversoes)} entradas.")
                
                print("\nExemplos de dados de conversão:")
                for i, conversao in enumerate(conversoes[:3], 1):
                    campanha = conversao.get('campaign_name', 'Sem nome')
                    valor = conversao.get('total_conversion_value', 0)
                    contagem = conversao.get('total_conversion_count', 0)
                    
                    print(f"{i}. {campanha} ({contagem} conversões, valor total: {valor})")
                
                return True
            else:
                imprimir_aviso("Nenhum dado de conversão encontrado. Isso pode ser normal para campanhas sem conversões recentes.")
                return True
        else:
            imprimir_erro("Resposta inválida ao acessar informações de atribuição.")
            return False
    
    except Exception as e:
        imprimir_erro(f"Erro ao acessar informações de atribuição: {str(e)}")
        return False

def main():
    """Função principal"""
    imprimir_titulo("VERIFICADOR DE PERMISSÕES DA API DO FACEBOOK")
    
    print("Este script verifica se as credenciais e permissões necessárias")
    print("estão configuradas corretamente para acessar dados de campanhas e FBclids.")
    print("\nIniciando verificações...")
    
    # Passo 1: Verificar credenciais
    credenciais_ok, credenciais = verificar_credenciais()
    
    if not credenciais_ok:
        imprimir_erro("\nVerificação falhou: Credenciais incompletas.")
        print("\nPara configurar as credenciais, crie um arquivo '.facebook_credentials.env' com:")
        print("FB_ACCESS_TOKEN=seu_token_aqui")
        print("FB_PIXEL_ID=seu_pixel_id_aqui")
        print("FB_AD_ACCOUNT_ID=seu_ad_account_id_aqui")
        print("FB_APP_ID=seu_app_id_aqui")
        print("FB_APP_SECRET=seu_app_secret_aqui")
        return
    
    # Passo 2: Verificar token de acesso
    token_ok, token_info = verificar_token_acesso(credenciais['FB_ACCESS_TOKEN'])
    
    if not token_ok:
        imprimir_erro("\nVerificação falhou: Token de acesso inválido ou expirado.")
        print("\nPara obter um novo token de acesso:")
        print("1. Acesse https://developers.facebook.com/tools/explorer/")
        print("2. Selecione seu aplicativo")
        print("3. Gere um novo token com as permissões necessárias")
        return
    
    # Passo 3: Verificar permissões
    permissoes_ok = verificar_permissoes(credenciais['FB_ACCESS_TOKEN'])
    
    # Passo 4: Verificar acesso às campanhas
    campanhas_ok = verificar_acesso_campanhas(
        credenciais['FB_ACCESS_TOKEN'], 
        credenciais['FB_AD_ACCOUNT_ID']
    )
    
    # Passo 5: Verificar acesso ao pixel
    pixel_ok = verificar_acesso_pixel(
        credenciais['FB_ACCESS_TOKEN'], 
        credenciais['FB_PIXEL_ID']
    )
    
    # Passo 6: Verificar acesso à atribuição
    atribuicao_ok = verificar_acesso_atribuicao(
        credenciais['FB_ACCESS_TOKEN'], 
        credenciais['FB_AD_ACCOUNT_ID']
    )
    
    # Resumo final
    imprimir_titulo("RESUMO DA VERIFICAÇÃO")
    
    print(f"Credenciais: {'✅' if credenciais_ok else '❌'}")
    print(f"Token de acesso: {'✅' if token_ok else '❌'}")
    print(f"Permissões: {'✅' if permissoes_ok else '⚠️'}")
    print(f"Acesso às campanhas: {'✅' if campanhas_ok else '❌'}")
    print(f"Acesso ao pixel: {'✅' if pixel_ok else '❌'}")
    print(f"Acesso à atribuição: {'✅' if atribuicao_ok else '⚠️'}")
    
    # Resultado final
    if credenciais_ok and token_ok and campanhas_ok and pixel_ok:
        imprimir_sucesso("\nConfigurações básicas estão corretas!")
        
        if not permissoes_ok or not atribuicao_ok:
            imprimir_aviso("\nAlgumas permissões avançadas podem estar faltando.")
            imprimir_aviso("Consulte o arquivo 'facebook_api_permissoes.md' para obter instruções sobre como configurar permissões adicionais.")
        else:
            imprimir_sucesso("\nTodas as permissões estão configuradas corretamente!")
    else:
        imprimir_erro("\nVerificação falhou: Algumas configurações essenciais estão incorretas.")
        imprimir_info("Consulte o arquivo 'facebook_api_permissoes.md' para obter instruções detalhadas de configuração.")

if __name__ == "__main__":
    main()
