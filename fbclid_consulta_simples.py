#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Teste simples de consulta de FBclid na API do Facebook
"""

import os
import time
import requests
import random
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()
load_dotenv('.facebook_credentials.env')

# Obtém o token de acesso
ACCESS_TOKEN = os.getenv('FB_ACCESS_TOKEN')

def consultar_fbclid(fbclid):
    """Consulta um FBclid diretamente na API do Facebook"""
    
    # Formata o FBclid se necessário
    if not fbclid.startswith('fb.'):
        timestamp = int(time.time()) + random.randint(1, 100)
        fbclid = f"fb.1.{timestamp}.{fbclid}"
    
    print(f"FBclid formatado: {fbclid}")
    
    # Consulta a API
    graph_url = "https://graph.facebook.com/v18.0/search"
    params = {
        'access_token': ACCESS_TOKEN,
        'type': 'adcampaign',
        'q': fbclid,
        'fields': 'name,id,adsets{name,id,ads{name,id}}'
    }
    
    response = requests.get(graph_url, params=params)
    return response.json()

# Solicita o FBclid ao usuário
fbclid = input("Digite o FBclid para consultar: ")

# Consulta a API
print("\nConsultando API do Facebook...")
resultado = consultar_fbclid(fbclid)

# Exibe o resultado completo
print("\nResultado da consulta:")
print(resultado)

# Extrai informações relevantes, se disponíveis
if 'data' in resultado and len(resultado['data']) > 0:
    campanha = resultado['data'][0]
    print("\nCampanha encontrada:")
    print(f"Nome: {campanha.get('name')}")
    print(f"ID: {campanha.get('id')}")
    
    # Verifica se tem conjuntos de anúncios
    if 'adsets' in campanha and 'data' in campanha['adsets'] and len(campanha['adsets']['data']) > 0:
        adset = campanha['adsets']['data'][0]
        print(f"\nConjunto de anúncios principal:")
        print(f"Nome: {adset.get('name')}")
        print(f"ID: {adset.get('id')}")
        
        # Verifica se tem anúncios
        if 'ads' in adset and 'data' in adset['ads'] and len(adset['ads']['data']) > 0:
            ad = adset['ads']['data'][0]
            print(f"\nAnúncio principal:")
            print(f"Nome: {ad.get('name')}")
            print(f"ID: {ad.get('id')}")
else:
    print("\nNenhuma campanha encontrada para este FBclid.")
