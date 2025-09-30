#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script para consultar campanhas do Facebook usando a API de Conversões.
Este script envia um evento de conversão com o FBclid e depois
imprime a resposta da API, que pode conter informações sobre a campanha.
"""

import os
import sys
import time
import uuid
import requests
import json
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()
load_dotenv('.facebook_credentials.env')

# Configurações da API do Facebook
FB_ACCESS_TOKEN = os.getenv('FB_ACCESS_TOKEN')
PIXEL_ID = os.getenv('FB_PIXEL_ID')

def enviar_evento_conversao(fbclid):
    """
    Envia um evento para a API de Conversões do Facebook com o FBclid fornecido
    
    Args:
        fbclid: O FBclid a ser incluído no evento
        
    Returns:
        A resposta da API de Conversões
    """
    # Verifica se o FBclid está formatado corretamente
    if not fbclid.startswith('fb.'):
        # Se não estiver formatado, adiciona o formato padrão
        timestamp = int(time.time())
        formatted_fbclid = f"fb.1.{timestamp}.{fbclid}"
    else:
        formatted_fbclid = fbclid
    
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
        
        return response.json()
    
    except Exception as e:
        return {"error": str(e)}

def main():
    """Função principal do script"""
    print("=" * 70)
    print(" CONSULTA DE CAMPANHA VIA API DE CONVERSÕES")
    print("=" * 70)
    
    # Verifica se as credenciais estão configuradas
    if not FB_ACCESS_TOKEN or not PIXEL_ID:
        print("\nErro: Credenciais do Facebook não configuradas.")
        print("Configure as variáveis FB_ACCESS_TOKEN e FB_PIXEL_ID no arquivo .facebook_credentials.env")
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
    
    # Envia um evento de conversão com o FBclid
    print(f"\nEnviando evento de conversão para FBclid: {fbclid}")
    
    response = enviar_evento_conversao(fbclid)
    
    # Exibe a resposta completa da API
    print("\n" + "=" * 70)
    print(" RESPOSTA DA API DE CONVERSÕES")
    print("=" * 70)
    
    print(json.dumps(response, indent=2))
    
    # Verifica se o evento foi recebido com sucesso
    if 'events_received' in response and response['events_received'] > 0:
        print(f"\n✅ Evento recebido com sucesso! ({response['events_received']} eventos)")
        print("\nA plataforma da Meta processará este evento e tentará atribuí-lo a uma campanha.")
        print("Você pode verificar a atribuição no Gerenciador de Eventos do Facebook.")
    else:
        error_msg = response.get('error', {}).get('message', 'Erro desconhecido')
        print(f"\n❌ Erro ao enviar evento: {error_msg}")
    
    print("\nConsulta concluída!")

if __name__ == "__main__":
    main()
