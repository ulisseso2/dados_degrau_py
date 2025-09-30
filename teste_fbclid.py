#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script simples para consultar a campanha associada a um FBclid.
Uso:
    python teste_fbclid.py <fbclid>
    
Exemplo:
    python teste_fbclid.py KLWJ829SJDLAK
"""

import os
import sys
import sqlite3
import requests
import time
from dotenv import load_dotenv
import re
from datetime import datetime

# Carrega variáveis de ambiente
load_dotenv()
load_dotenv('.facebook_credentials.env')  # Carrega as credenciais específicas do Facebook

# Configurações
DB_FILE = "fbclid_cache.db"
FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN")

def format_fbclid(fbclid, created_at=None):
    """
    Formata o FBclid conforme especificação da Meta:
    fb.subdomainIndex.creationTime.fbclid
    """
    # Verifica se já está no formato correto (fb.1.timestamp.fbclid)
    if fbclid and isinstance(fbclid, str):
        if re.match(r'^fb\.\d+\.\d+\.', fbclid):
            return fbclid
        
        # Determina o timestamp a usar
        if created_at:
            try:
                if isinstance(created_at, str):
                    dt = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                else:
                    dt = created_at
                timestamp = int(dt.timestamp())
            except Exception as e:
                print(f"Erro ao converter data de criação, usando timestamp atual: {str(e)}")
                timestamp = int(time.time())
        else:
            # Timestamp atual com pequeno incremento aleatório
            import random
            timestamp = int(time.time()) + random.randint(1, 100)
        
        # Formata o FBclid
        formatted = f"fb.1.{timestamp}.{fbclid}"
        return formatted
    
    return fbclid

def ensure_db_structure():
    """Garante que o banco de dados e a tabela existam"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Cria a tabela se não existir
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS fbclid_cache (
        fbclid TEXT PRIMARY KEY,
        campaign_name TEXT,
        campaign_id TEXT,
        adset_name TEXT,
        ad_name TEXT,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.commit()
    conn.close()

def get_campaign_from_db(fbclid):
    """Busca a campanha associada ao FBclid no banco de dados"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Primeiro verifica se a tabela existe
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fbclid_cache'")
    if not cursor.fetchone():
        conn.close()
        return None
    
    # Busca o FBclid
    cursor.execute("""
    SELECT fbclid, campaign_name, campaign_id, adset_name, ad_name 
    FROM fbclid_cache 
    WHERE fbclid = ?
    """, (fbclid,))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            'fbclid': result[0],
            'campaign_name': result[1],
            'campaign_id': result[2],
            'adset_name': result[3],
            'ad_name': result[4]
        }
    
    return None

def lookup_campaign_api(fbclid):
    """Consulta a campanha na API do Facebook"""
    if not FB_ACCESS_TOKEN:
        print("Erro: Token de acesso do Facebook não configurado.")
        return None
    
    # Formata o FBclid
    formatted_fbclid = format_fbclid(fbclid)
    
    # Tenta consultar a API Graph
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
        
        # Verifica se encontrou alguma campanha
        if 'data' in data and len(data['data']) > 0:
            campaign = data['data'][0]  # Pega a primeira campanha encontrada
            
            # Informações da campanha
            campaign_info = {
                'campaign_name': campaign.get('name'),
                'campaign_id': campaign.get('id'),
                'adset_name': None,
                'ad_name': None
            }
            
            # Tenta obter informações de conjunto de anúncios e anúncios
            if 'adsets' in campaign and 'data' in campaign['adsets'] and len(campaign['adsets']['data']) > 0:
                adset = campaign['adsets']['data'][0]
                campaign_info['adset_name'] = adset.get('name')
                
                if 'ads' in adset and 'data' in adset['ads'] and len(adset['ads']['data']) > 0:
                    ad = adset['ads']['data'][0]
                    campaign_info['ad_name'] = ad.get('name')
            
            # Salva no banco de dados para cache
            save_to_db(fbclid, campaign_info)
            
            return campaign_info
        
        return None
    
    except Exception as e:
        print(f"Erro ao consultar API: {e}")
        return None

def save_to_db(fbclid, campaign_info):
    """Salva informações da campanha no banco de dados"""
    ensure_db_structure()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
    INSERT OR REPLACE INTO fbclid_cache 
    (fbclid, campaign_name, campaign_id, adset_name, ad_name, last_updated)
    VALUES (?, ?, ?, ?, ?, datetime('now'))
    """, (
        fbclid,
        campaign_info.get('campaign_name'),
        campaign_info.get('campaign_id'),
        campaign_info.get('adset_name'),
        campaign_info.get('ad_name')
    ))
    
    conn.commit()
    conn.close()

def consultar_fbclid(fbclid):
    """Função principal para consultar um FBclid"""
    print(f"\nConsultando FBclid: {fbclid}")
    
    # 1. Primeiro procura no banco de dados local
    print("\nBuscando no banco de dados local...")
    resultado_db = get_campaign_from_db(fbclid)
    
    if resultado_db:
        print("✓ Encontrado no banco de dados local!")
        return resultado_db
    
    print("✗ Não encontrado no banco de dados local.")
    
    # 2. Se não encontrar, consulta a API
    print("\nConsultando a API do Facebook...")
    resultado_api = lookup_campaign_api(fbclid)
    
    if resultado_api:
        print("✓ Encontrado via API do Facebook!")
        return resultado_api
    
    print("✗ Não encontrado via API do Facebook.")
    
    # 3. Se não encontrado, salva como "Não encontrado"
    not_found = {
        'fbclid': fbclid,
        'campaign_name': 'Não encontrado',
        'campaign_id': None,
        'adset_name': None,
        'ad_name': None
    }
    
    save_to_db(fbclid, not_found)
    return not_found

def main():
    """Função principal do script"""
    print("=" * 60)
    print(" CONSULTA DE CAMPANHA POR FBCLID")
    print("=" * 60)
    
    # Verifica se o token do Facebook está configurado
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
    
    # Consulta o FBclid
    resultado = consultar_fbclid(fbclid)
    
    # Exibe o resultado
    print("\n" + "=" * 60)
    print(" RESULTADO DA CONSULTA")
    print("=" * 60)
    
    print(f"FBclid: {resultado['fbclid']}")
    print(f"Campanha: {resultado['campaign_name']}")
    
    if resultado['campaign_id']:
        print(f"ID da Campanha: {resultado['campaign_id']}")
    
    if resultado['adset_name']:
        print(f"Conjunto de Anúncios: {resultado['adset_name']}")
    
    if resultado['ad_name']:
        print(f"Anúncio: {resultado['ad_name']}")
    
    print("\nConsulta concluída!")

if __name__ == "__main__":
    main()
