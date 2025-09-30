#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Ferramenta completa para consulta de FBclids e campanhas do Facebook.
Este script combina diferentes métodos para tentar encontrar informações
sobre campanhas associadas a um FBclid:

1. Consulta direta da Graph API
2. Envio de evento via API de Conversões
3. Consulta de insights de campanha

Uso:
    python consulta_fbclid_completa.py [fbclid]
"""

import os
import sys
import time
import uuid
import json
import requests
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()
load_dotenv('.facebook_credentials.env')

# Configurações da API do Facebook
FB_ACCESS_TOKEN = os.getenv('FB_ACCESS_TOKEN')
PIXEL_ID = os.getenv('FB_PIXEL_ID')
AD_ACCOUNT_ID = os.getenv('FB_AD_ACCOUNT_ID')

def format_fbclid(fbclid):
    """Formata o FBclid no padrão da Meta: fb.subdomainIndex.creationTime.fbclid"""
    if fbclid and isinstance(fbclid, str):
        # Verifica se já está no formato correto
        if fbclid.startswith('fb.') and len(fbclid.split('.')) >= 4:
            return fbclid
        
        # Formata o FBclid
        timestamp = int(time.time()) + random.randint(1, 100)
        return f"fb.1.{timestamp}.{fbclid}"
    
    return fbclid

def consultar_graph_api(fbclid):
    """Tenta encontrar a campanha consultando diretamente a Graph API"""
    print("\n[MÉTODO 1] Consultando a Graph API...")
    
    # Formata o FBclid
    formatted_fbclid = format_fbclid(fbclid)
    print(f"FBclid formatado: {formatted_fbclid}")
    
    # Consulta a API Graph
    graph_url = "https://graph.facebook.com/v18.0/search"
    params = {
        'access_token': FB_ACCESS_TOKEN,
        'type': 'adcampaign',
        'q': formatted_fbclid,
        'fields': 'name,id,adsets{name,id,ads{name,id}}'
    }
    
    try:
        response = requests.get(graph_url, params=params)
        data = response.json()
        
        # Verifica se houve erro
        if 'error' in data:
            print(f"API Graph retornou erro: {data['error'].get('message')}")
            return None
        
        # Verifica se encontrou alguma campanha
        if 'data' in data and len(data['data']) > 0:
            print(f"Encontradas {len(data['data'])} campanhas na Graph API!")
            return data
        else:
            print("Nenhuma campanha encontrada via Graph API.")
            return None
    
    except Exception as e:
        print(f"Erro ao consultar Graph API: {e}")
        return None

def enviar_evento_conversao(fbclid):
    """Envia um evento para a API de Conversões e retorna a resposta"""
    print("\n[MÉTODO 2] Enviando evento para a API de Conversões...")
    
    # Formata o FBclid
    formatted_fbclid = format_fbclid(fbclid)
    print(f"FBclid formatado: {formatted_fbclid}")
    
    # Gera um ID de evento único
    event_id = str(uuid.uuid4())
    print(f"ID do evento: {event_id}")
    
    # Define o timestamp atual
    event_time = int(time.time())
    
    # Cria um evento para a API de Conversões
    event_data = {
        "data": [{
            "event_name": "PageView",
            "event_time": event_time,
            "event_id": event_id,
            "action_source": "website",
            "event_source_url": "https://degrauculturalidiomas.com.br/",
            "user_data": {
                "fbc": formatted_fbclid,
                "client_ip_address": "127.0.0.1",
                "client_user_agent": "Mozilla/5.0"
            }
        }]
    }
    
    # URL da API de Conversões
    url = f"https://graph.facebook.com/v18.0/{PIXEL_ID}/events"
    
    try:
        # Envia o evento
        response = requests.post(
            url, 
            params={'access_token': FB_ACCESS_TOKEN},
            json=event_data
        )
        
        data = response.json()
        
        # Verifica se o evento foi recebido com sucesso
        if 'events_received' in data and data['events_received'] > 0:
            print(f"Evento recebido com sucesso! ({data['events_received']} eventos)")
            return data
        else:
            error_msg = data.get('error', {}).get('message', 'Erro desconhecido')
            print(f"Erro ao enviar evento: {error_msg}")
            return None
    
    except Exception as e:
        print(f"Erro ao usar a API de Conversões: {e}")
        return None

def consultar_campanhas_recentes(fbclid):
    """
    Consulta campanhas recentes na conta de anúncios para tentar
    encontrar a que está associada ao FBclid
    """
    print("\n[MÉTODO 3] Consultando campanhas recentes na conta de anúncios...")
    
    if not AD_ACCOUNT_ID:
        print("ID da conta de anúncios não configurado. Pulando este método.")
        return None
    
    # Remove 'act_' do início do ID da conta, se presente
    account_id = AD_ACCOUNT_ID.replace('act_', '')
    
    # Calcula a data de 30 dias atrás
    data_inicio = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    data_fim = datetime.now().strftime('%Y-%m-%d')
    
    print(f"Consultando campanhas de {data_inicio} até {data_fim}")
    
    # URL da API Graph para campanhas
    url = f"https://graph.facebook.com/v18.0/act_{account_id}/campaigns"
    
    params = {
        'access_token': FB_ACCESS_TOKEN,
        'fields': 'name,id,objective,status,created_time,insights{clicks,impressions,spend}',
        'time_range': json.dumps({'since': data_inicio, 'until': data_fim}),
        'limit': 50  # Limita a 50 campanhas mais recentes
    }
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        # Verifica se houve erro
        if 'error' in data:
            print(f"Erro ao consultar campanhas: {data['error'].get('message')}")
            return None
        
        # Verifica se encontrou campanhas
        if 'data' in data and len(data['data']) > 0:
            print(f"Encontradas {len(data['data'])} campanhas recentes!")
            return data
        else:
            print("Nenhuma campanha recente encontrada.")
            return None
    
    except Exception as e:
        print(f"Erro ao consultar campanhas recentes: {e}")
        return None

def main():
    """Função principal do script"""
    print("=" * 70)
    print(" CONSULTA COMPLETA DE FBCLID E CAMPANHAS")
    print("=" * 70)
    
    # Verifica se as credenciais estão configuradas
    if not FB_ACCESS_TOKEN:
        print("\nErro: Token de acesso do Facebook não configurado.")
        print("Configure a variável FB_ACCESS_TOKEN no arquivo .facebook_credentials.env")
        return
    
    # Verifica se um FBclid foi fornecido como argumento
    if len(sys.argv) > 1:
        fbclid = sys.argv[1]
    else:
        # Se não houver argumento, solicita ao usuário
        fbclid = input("\nDigite o FBclid para consultar: ")
    
    if not fbclid:
        print("Nenhum FBclid fornecido. Saindo.")
        return
    
    print(f"\nConsultando informações para o FBclid: {fbclid}")
    
    # Método 1: Consulta direta da Graph API
    graph_result = consultar_graph_api(fbclid)
    
    # Método 2: Envio de evento via API de Conversões
    conversion_result = enviar_evento_conversao(fbclid)
    
    # Método 3: Consulta de campanhas recentes
    campaigns_result = consultar_campanhas_recentes(fbclid)
    
    # Exibe um resumo dos resultados
    print("\n" + "=" * 70)
    print(" RESUMO DOS RESULTADOS")
    print("=" * 70)
    
    print("\n[Resultados da Graph API]")
    if graph_result and 'data' in graph_result and len(graph_result['data']) > 0:
        for i, campaign in enumerate(graph_result['data']):
            print(f"Campanha {i+1}: {campaign.get('name')} (ID: {campaign.get('id')})")
            
            # Exibe conjuntos de anúncios
            if 'adsets' in campaign and 'data' in campaign['adsets']:
                for adset in campaign['adsets']['data']:
                    print(f"  - Conjunto: {adset.get('name')}")
    else:
        print("Nenhuma campanha encontrada diretamente via Graph API.")
    
    print("\n[Resultados da API de Conversões]")
    if conversion_result and 'events_received' in conversion_result:
        print(f"Evento enviado com sucesso. Eventos recebidos: {conversion_result['events_received']}")
        print("A atribuição de campanha será processada pelo Facebook e estará disponível no Gerenciador de Eventos.")
    else:
        print("Falha ao enviar evento de conversão.")
    
    print("\n[Campanhas Recentes na Conta]")
    if campaigns_result and 'data' in campaigns_result:
        print(f"Encontradas {len(campaigns_result['data'])} campanhas recentes:")
        
        # Exibe até 5 campanhas mais recentes
        for i, campaign in enumerate(campaigns_result['data'][:5]):
            created_time = campaign.get('created_time', '').split('T')[0]
            status = campaign.get('status', 'Desconhecido')
            
            print(f"{i+1}. {campaign.get('name')} (Status: {status}, Criado em: {created_time})")
            
            # Exibe insights se disponíveis
            if 'insights' in campaign and 'data' in campaign['insights'] and len(campaign['insights']['data']) > 0:
                insights = campaign['insights']['data'][0]
                clicks = insights.get('clicks', 0)
                impressions = insights.get('impressions', 0)
                spend = insights.get('spend', '0')
                
                print(f"   Cliques: {clicks}, Impressões: {impressions}, Gasto: R$ {spend}")
    else:
        print("Nenhuma campanha recente encontrada na conta.")
    
    print("\nConsulta concluída!")
    print("\nNota: O FBclid fornecido pode estar associado a uma campanha que não está")
    print("acessível pela API atual ou que requer permissões adicionais.")
    print("\nPara verificar suas permissões de API e configurá-las corretamente:")
    print("1. Execute o verificador de permissões: python verificar_permissoes_facebook.py")
    print("2. Consulte o guia detalhado: facebook_api_permissoes.md")

if __name__ == "__main__":
    main()
