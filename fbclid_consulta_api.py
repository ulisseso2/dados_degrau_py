#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script simples para consultar campanhas do Facebook a partir de um FBclid.
Este script consulta diretamente a API do Facebook sem utilizar banco de dados local.

Uso:
    python fbclid_consulta_api.py <fbclid>
    
Exemplo:
    python fbclid_consulta_api.py KLW9284JASDF
"""

import os
import sys
import time
import re
import requests
from datetime import datetime
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()
load_dotenv('.facebook_credentials.env')  # Carrega as credenciais específicas do Facebook

# Configurações da API do Facebook
FB_ACCESS_TOKEN = os.getenv('FB_ACCESS_TOKEN')

def format_fbclid(fbclid, created_at=None):
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
    if fbclid and isinstance(fbclid, str):
        if re.match(r'^fb\.\d+\.\d+\.', fbclid):
            return fbclid
        
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
            except Exception as e:
                print(f"Erro ao converter data de criação, usando timestamp atual: {str(e)}")
                timestamp = int(time.time())
        else:
            # Usa o timestamp atual com um pequeno incremento aleatório para garantir unicidade
            import random
            timestamp = int(time.time()) + random.randint(1, 100)
        
        # Formata o FBclid
        formatted = f"fb.1.{timestamp}.{fbclid}"
        return formatted
    
    return fbclid

def consultar_campanha_api(fbclid):
    """
    Consulta diretamente a API do Facebook para obter informações 
    da campanha associada ao FBclid
    
    Args:
        fbclid: O fbclid a ser consultado (pode ser formatado ou não)
        
    Returns:
        Um dicionário com as informações da campanha ou None se não encontrada
    """
    if not FB_ACCESS_TOKEN:
        print("Erro: Token de acesso do Facebook não configurado.")
        print("Configure a variável FB_ACCESS_TOKEN no arquivo .facebook_credentials.env")
        return None
    
    # Formata o FBclid se necessário
    formatted_fbclid = format_fbclid(fbclid)
    print(f"FBclid formatado: {formatted_fbclid}")
    
    # Consulta a API Graph do Facebook
    graph_url = "https://graph.facebook.com/v18.0/search"
    params = {
        'access_token': FB_ACCESS_TOKEN,
        'type': 'adcampaign',
        'q': formatted_fbclid,
        'fields': 'name,id,adsets{name,id,ads{name,id}}'
    }
    
    try:
        print("\nConsultando API do Facebook...")
        response = requests.get(graph_url, params=params)
        data = response.json()
        
        # Verifica se houve erro na consulta
        if 'error' in data:
            print(f"\nErro na API: {data['error'].get('message')}")
            return None
        
        # Verifica se encontrou alguma campanha
        if 'data' in data and len(data['data']) > 0:
            print(f"\nEncontradas {len(data['data'])} campanhas!")
            
            campaigns = []
            for campaign in data['data']:
                campaign_info = {
                    'campaign_name': campaign.get('name'),
                    'campaign_id': campaign.get('id'),
                    'adsets': []
                }
                
                # Verifica se tem conjuntos de anúncios
                if 'adsets' in campaign and 'data' in campaign['adsets']:
                    for adset in campaign['adsets']['data']:
                        adset_info = {
                            'adset_name': adset.get('name'),
                            'adset_id': adset.get('id'),
                            'ads': []
                        }
                        
                        # Verifica se tem anúncios
                        if 'ads' in adset and 'data' in adset['ads']:
                            for ad in adset['ads']['data']:
                                ad_info = {
                                    'ad_name': ad.get('name'),
                                    'ad_id': ad.get('id')
                                }
                                adset_info['ads'].append(ad_info)
                        
                        campaign_info['adsets'].append(adset_info)
                
                campaigns.append(campaign_info)
            
            return campaigns
        else:
            print("\nNenhuma campanha encontrada para este FBclid.")
            return None
    
    except Exception as e:
        print(f"\nErro ao consultar API: {e}")
        return None

def main():
    """Função principal do script"""
    print("=" * 70)
    print(" CONSULTA DE CAMPANHA POR FBCLID (DIRETO NA API)")
    print("=" * 70)
    
    # Verifica se um FBclid foi fornecido como argumento
    if len(sys.argv) > 1:
        fbclid = sys.argv[1]
    else:
        # Se não houver argumento, solicita ao usuário
        fbclid = input("\nDigite o FBclid para consultar: ")
    
    if not fbclid:
        print("Nenhum FBclid fornecido. Saindo.")
        return
    
    # Consulta o FBclid na API
    print(f"\nConsultando FBclid: {fbclid}")
    
    campaigns = consultar_campanha_api(fbclid)
    
    if campaigns:
        print("\n" + "=" * 70)
        print(" RESULTADOS DA CONSULTA")
        print("=" * 70)
        
        for i, campaign in enumerate(campaigns):
            print(f"\n[Campanha {i+1}]")
            print(f"Nome: {campaign['campaign_name']}")
            print(f"ID: {campaign['campaign_id']}")
            
            if campaign['adsets']:
                for j, adset in enumerate(campaign['adsets']):
                    print(f"\n  [Conjunto de Anúncios {j+1}]")
                    print(f"  Nome: {adset['adset_name']}")
                    print(f"  ID: {adset['adset_id']}")
                    
                    if adset['ads']:
                        for k, ad in enumerate(adset['ads']):
                            print(f"\n    [Anúncio {k+1}]")
                            print(f"    Nome: {ad['ad_name']}")
                            print(f"    ID: {ad['ad_id']}")
    else:
        print("\nNenhuma informação de campanha encontrada para este FBclid.")
    
    print("\nConsulta concluída!")

if __name__ == "__main__":
    main()
