#!/usr/bin/env python3
# test_fbclid_api.py
# Script simples para testar envio de FBclids formatados para a API da Meta

import os
import time
import sqlite3
import re
import pandas as pd
from datetime import datetime
import requests
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo principal e depois do arquivo específico do Facebook
load_dotenv()
load_dotenv('.facebook_credentials.env')  # Carrega as credenciais específicas do Facebook

# Configurações
DB_FILE = "fbclid_cache.db"
TIMEZONE = 'America/Sao_Paulo'

def format_fbclid(fbclid_raw, created_at=None):
    """
    Formata o FBclid conforme especificação da Meta:
    fb.subdomainIndex.creationTime.fbclid
    
    Onde:
    - fb é sempre o prefixo
    - subdomainIndex é 1 (para domínio principal)
    - creationTime é o timestamp em ms
    - fbclid é o valor original do parâmetro
    
    Se o FBclid já estiver formatado, retorna-o como está.
    """
    # Verifica se já está no formato correto (fb.1.timestamp.fbclid)
    if fbclid_raw and isinstance(fbclid_raw, str):
        # Regex para verificar se já está no formato fb.1.timestamp.fbclid
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

def get_fbclids_from_db():
    """Carrega FBclids do banco de dados SQLite"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Verifica se a tabela existe
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fbclid_cache'")
    if not cursor.fetchone():
        print("Tabela fbclid_cache não encontrada. O banco de dados está vazio.")
        return []
    
    # Busca os FBclids
    cursor.execute("SELECT fbclid FROM fbclid_cache")
    fbclids = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    return fbclids

def get_fbclids_from_crm():
    """Carrega FBclids do CRM usando o script SQL"""
    try:
        from utils.sql_loader import carregar_dados
        
        # Carrega os dados do banco de dados
        df_oportunidades = carregar_dados("consultas/oportunidades/oportunidades.sql")
        
        # Converte coluna de data
        df_oportunidades['criacao'] = pd.to_datetime(df_oportunidades['criacao']).dt.tz_localize(TIMEZONE, ambiguous='infer')
        
        # Filtra apenas registros com FBclid
        df_fbclids = df_oportunidades[
            (df_oportunidades['fbclid'].notnull()) & 
            (df_oportunidades['fbclid'] != '')
        ]
        
        # Extrai os FBclids
        fbclids = df_fbclids['fbclid'].tolist()
        
        print(f"Encontrados {len(fbclids)} FBclids no CRM.")
        return fbclids
    
    except Exception as e:
        print(f"Erro ao carregar FBclids do CRM: {e}")
        return []

def test_facebook_graph_api(fbclid, access_token):
    """Testa a API Graph do Facebook com um FBclid formatado"""
    try:
        # Formata o FBclid
        formatted_fbclid = format_fbclid(fbclid)
        
        print(f"FBclid original: {fbclid}")
        print(f"FBclid formatado: {formatted_fbclid}")
        
        # Tenta consultar a API Graph
        graph_url = "https://graph.facebook.com/v18.0/search"
        params = {
            'access_token': access_token,
            'type': 'adcampaign',
            'q': formatted_fbclid,
            'fields': 'name,id,adsets{name,id,ads{name,id}}'
        }
        
        print("\nConsultando API Graph do Facebook...")
        response = requests.get(graph_url, params=params)
        data = response.json()
        
        print("\nResposta da API Graph:")
        print(data)
        
        # Verifica se encontrou alguma campanha
        if 'data' in data and len(data['data']) > 0:
            print(f"\nEncontradas {len(data['data'])} campanhas!")
            for i, campaign in enumerate(data['data']):
                print(f"\nCampanha {i+1}:")
                print(f"  Nome: {campaign.get('name')}")
                print(f"  ID: {campaign.get('id')}")
                
                # Verifica se tem conjuntos de anúncios
                if 'adsets' in campaign and 'data' in campaign['adsets'] and len(campaign['adsets']['data']) > 0:
                    print(f"  Conjuntos de anúncios: {len(campaign['adsets']['data'])}")
                    for adset in campaign['adsets']['data']:
                        print(f"    - {adset.get('name')} (ID: {adset.get('id')})")
        else:
            print("\nNenhuma campanha encontrada para este FBclid.")
        
        return data
    
    except Exception as e:
        print(f"\nErro ao consultar API Graph: {e}")
        return None

def test_conversions_api(fbclid, access_token, pixel_id):
    """Testa a API de Conversões do Facebook com um FBclid formatado"""
    try:
        # Gera um ID de evento único
        import uuid
        event_id = str(uuid.uuid4())
        
        # Formata o FBclid
        formatted_fbclid = format_fbclid(fbclid)
        
        print(f"FBclid original: {fbclid}")
        print(f"FBclid formatado: {formatted_fbclid}")
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
                "event_source_url": "https://degrauculturalidiomas.com.br/teste",
                "user_data": {
                    "fbc": formatted_fbclid,
                    "client_ip_address": "127.0.0.1",
                    "client_user_agent": "Mozilla/5.0"
                }
            }]
            # Removido test_event_code para usar o modo de produção
        }
        
        # URL da API de Conversões
        url = f"https://graph.facebook.com/v18.0/{pixel_id}/events"
        
        print("\nEnviando evento para a API de Conversões...")
        print("Dados do evento:")
        import json
        print(json.dumps(event_data, indent=2))
        
        response = requests.post(
            url, 
            params={'access_token': access_token},
            json=event_data
        )
        
        data = response.json()
        print("\nResposta da API de Conversões:")
        print(json.dumps(data, indent=2))
        
        # Verifica sucesso
        if 'events_received' in data and data['events_received'] > 0:
            print(f"\n✅ SUCESSO! Evento recebido: {data['events_received']}")
        else:
            error_msg = data.get('error', {}).get('message', 'Erro desconhecido')
            print(f"\n❌ ERRO: {error_msg}")
        
        return data
    
    except Exception as e:
        print(f"\n❌ Erro ao usar a API de Conversões: {e}")
        return None

def main():
    print("=" * 80)
    print(" TESTE DE FBCLIDS COM A API DA META")
    print("=" * 80)
    
    # Verifica credenciais
    access_token = os.getenv("FB_ACCESS_TOKEN")
    if not access_token:
        print("Erro: Access Token do Facebook não encontrado. Configure FB_ACCESS_TOKEN no arquivo .env")
        return
    
    pixel_id = os.getenv("FB_PIXEL_ID")
    if not pixel_id:
        print("Erro: Pixel ID não encontrado. Configure FB_PIXEL_ID no arquivo .env")
        return
    
    print(f"Access Token: {access_token[:10]}...{access_token[-4:]}")
    print(f"Pixel ID: {pixel_id}")
    
    # Escolhe a fonte de FBclids
    print("\nEscolha a fonte dos FBclids:")
    print("1. Banco de dados SQLite")
    print("2. CRM (consulta SQL)")
    print("3. Informar FBclid manualmente")
    
    choice = input("\nDigite sua escolha (1-3): ")
    
    fbclids = []
    if choice == "1":
        fbclids = get_fbclids_from_db()
    elif choice == "2":
        fbclids = get_fbclids_from_crm()
    elif choice == "3":
        fbclid = input("\nDigite o FBclid para testar: ")
        if fbclid:
            fbclids = [fbclid]
    else:
        print("Opção inválida.")
        return
    
    if not fbclids:
        print("Nenhum FBclid encontrado para teste.")
        return
    
    # Limita o número de FBclids para teste
    if len(fbclids) > 5:
        print(f"Limitando a 5 FBclids dos {len(fbclids)} encontrados.")
        fbclids = fbclids[:5]
    
    # Pergunta qual API testar
    print("\nQual API você deseja testar?")
    print("1. API Graph (busca)")
    print("2. API de Conversões (envio de eventos)")
    print("3. Ambas")
    
    api_choice = input("\nDigite sua escolha (1-3): ")
    
    # Testa cada FBclid
    for i, fbclid in enumerate(fbclids):
        print("\n" + "=" * 80)
        print(f"Testando FBclid {i+1}/{len(fbclids)}: {fbclid}")
        print("=" * 80)
        
        if api_choice in ("1", "3"):
            print("\n[TESTE DA API GRAPH]\n")
            test_facebook_graph_api(fbclid, access_token)
        
        if api_choice in ("2", "3"):
            print("\n[TESTE DA API DE CONVERSÕES]\n")
            test_conversions_api(fbclid, access_token, pixel_id)
        
        # Pausa entre requisições para evitar rate limiting
        if i < len(fbclids) - 1:
            print("\nAguardando 3 segundos antes do próximo teste...")
            time.sleep(3)
    
    print("\nTestes concluídos!")

if __name__ == "__main__":
    main()
