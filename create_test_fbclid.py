#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Este script cria um FBclid de teste no formato correto
e envia um evento para a API de Conversões da Meta.

Uso:
    python create_test_fbclid.py
"""

import os
import time
import uuid
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()
load_dotenv('.facebook_credentials.env')  # Carrega as credenciais específicas do Facebook

def format_fbclid(fbclid_raw, created_at=None):
    """
    Formata o FBclid conforme especificação da Meta:
    fb.subdomainIndex.creationTime.fbclid
    
    Onde:
    - fb é sempre o prefixo
    - subdomainIndex é 1 (para domínio principal)
    - creationTime é o timestamp em segundos
    - fbclid é o valor original do parâmetro
    
    Se o FBclid já estiver formatado, retorna-o como está.
    """
    # Verifica se já está no formato correto (fb.1.timestamp.fbclid)
    if fbclid_raw and isinstance(fbclid_raw, str):
        # Verifica se já está no formato fb.1.timestamp.fbclid
        import re
        if re.match(r'^fb\.\d+\.\d+\.', fbclid_raw):
            print(f"FBclid já está no formato correto: {fbclid_raw}")
            return fbclid_raw
        
        # Determina o timestamp a usar
        if created_at:
            try:
                # Se created_at for string, converte para datetime
                if isinstance(created_at, str):
                    dt = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                else:
                    dt = created_at
                    
                # Converte para timestamp em segundos
                timestamp = int(dt.timestamp())
                print(f"Usando timestamp da data de criação: {timestamp}")
            except Exception as e:
                print(f"Erro ao converter data de criação, usando timestamp atual: {str(e)}")
                timestamp = int(time.time())
        else:
            # Usa o timestamp atual com um pequeno incremento aleatório para garantir unicidade
            import random
            timestamp = int(time.time()) + random.randint(1, 100)
            print(f"Usando timestamp atual com incremento: {timestamp}")
        
        # Formata o FBclid
        formatted = f"fb.1.{timestamp}.{fbclid_raw}"
        print(f"FBclid formatado de '{fbclid_raw}' para '{formatted}'")
        return formatted
    
    return fbclid_raw

def create_test_fbclid():
    """Cria um FBclid de teste com um valor único"""
    # Gera um valor único
    unique_id = str(uuid.uuid4()).replace('-', '')[:12]
    timestamp = int(time.time())
    
    # Cria um FBclid de teste
    fbclid_raw = f"test_{unique_id}_{timestamp}"
    
    # Formata o FBclid
    formatted_fbclid = format_fbclid(fbclid_raw)
    
    return {
        'raw': fbclid_raw,
        'formatted': formatted_fbclid,
        'timestamp': timestamp,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

def send_test_event(fbclid):
    """Envia um evento de teste para a API de Conversões da Meta"""
    # Verifica credenciais
    access_token = os.getenv("FB_ACCESS_TOKEN")
    pixel_id = os.getenv("FB_PIXEL_ID")
    
    if not access_token or not pixel_id:
        print("Erro: Credenciais não encontradas. Configure FB_ACCESS_TOKEN e FB_PIXEL_ID no arquivo .env")
        return None
    
    # Gera um ID de evento único
    event_id = str(uuid.uuid4())
    
    # Define o timestamp atual
    event_time = int(time.time())
    
    # Cria um evento para a API de Conversões
    event_data = {
        "data": [{
            "event_name": "PageView",
            "event_time": event_time,
            "event_id": event_id,
            "action_source": "website",
            "event_source_url": "https://degrauculturalidiomas.com.br/teste",
            "user_data": {
                "fbc": fbclid,
                "client_ip_address": "127.0.0.1",
                "client_user_agent": "Mozilla/5.0"
            }
        }]
    }
    
    # URL da API de Conversões
    url = f"https://graph.facebook.com/v18.0/{pixel_id}/events"
    
    try:
        # Envia o evento
        response = requests.post(
            url, 
            params={'access_token': access_token},
            json=event_data
        )
        
        return {
            'event_id': event_id,
            'event_time': event_time,
            'response': response.json()
        }
    
    except Exception as e:
        return {
            'event_id': event_id,
            'event_time': event_time,
            'error': str(e)
        }

def main():
    print("=" * 80)
    print(" CRIAÇÃO DE FBCLID DE TESTE E ENVIO PARA API DE CONVERSÕES")
    print("=" * 80)
    
    # Cria um FBclid de teste
    fbclid_data = create_test_fbclid()
    
    print("\nFBclid de teste criado:")
    print(f"  Valor original: {fbclid_data['raw']}")
    print(f"  Valor formatado: {fbclid_data['formatted']}")
    print(f"  Timestamp: {fbclid_data['timestamp']}")
    print(f"  Data de criação: {fbclid_data['created_at']}")
    
    # Pergunta se deseja enviar para a API
    send_to_api = input("\nDeseja enviar este FBclid para a API de Conversões? (s/n): ")
    
    if send_to_api.lower() == 's':
        print("\nEnviando evento para a API de Conversões...")
        result = send_test_event(fbclid_data['formatted'])
        
        if result:
            print("\nResultado do envio:")
            print(f"  ID do evento: {result.get('event_id')}")
            print(f"  Timestamp: {result.get('event_time')}")
            
            if 'response' in result:
                print("\nResposta da API:")
                print(json.dumps(result['response'], indent=2))
                
                if 'events_received' in result['response'] and result['response']['events_received'] > 0:
                    print("\n✅ Evento enviado com sucesso!")
                else:
                    print("\n❌ Falha no envio do evento.")
            
            if 'error' in result:
                print(f"\n❌ Erro: {result['error']}")
    
    # Salvar FBclid para uso futuro
    save_fbclid = input("\nDeseja salvar este FBclid para uso futuro? (s/n): ")
    
    if save_fbclid.lower() == 's':
        file_name = "test_fbclid.json"
        
        with open(file_name, "w") as f:
            json.dump(fbclid_data, f, indent=2)
        
        print(f"\nFBclid salvo em {file_name}")
    
    print("\nProcesso concluído!")

if __name__ == "__main__":
    main()
