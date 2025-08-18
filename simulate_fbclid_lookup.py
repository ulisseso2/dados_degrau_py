#!/usr/bin/env python3
# simulate_fbclid_lookup.py
# Script para simular a consulta de FBclids no Facebook e preencher o banco de dados com dados realistas

import sqlite3
import pandas as pd
import os
from datetime import datetime
from utils.sql_loader import carregar_dados
import random

# Configurações
DB_FILE = "fbclid_cache.db"
TIMEZONE = 'America/Sao_Paulo'

# Lista de possíveis nomes de campanhas do Facebook
CAMPAIGN_TEMPLATES = [
    "FB_CONV_MATRICULA_{curso}",
    "META_CONVERSAO_{curso}_LEAD",
    "FB_REMARKETING_{curso}",
    "INSTA_CONVERSAO_{curso}",
    "META_TRAFICO_{curso}",
    "FB_LEAD_{curso}",
    "META_ENGAJAMENTO_{curso}",
    "FB_VENDAS_{curso}",
    "FB_CONTEUDO_{curso}"
]

# Lista de cursos possíveis (extraídos do contexto do usuário)
CURSOS = [
    "POLICIA_CIVIL",
    "POLICIA_MILITAR",
    "BOMBEIROS",
    "CONCURSOS",
    "MEDICINA",
    "DIREITO",
    "PRE_ENEM",
    "PEDAGOGIA",
    "ENFERMAGEM",
    "TEC_INFORMATICA"
]

# Lista de conjuntos de anúncios (adsets)
ADSET_TEMPLATES = [
    "18-24_INTERESSE_{segmento}",
    "25-35_INTERESSE_{segmento}",
    "36-50_INTERESSE_{segmento}",
    "REMARKETING_30D_{segmento}",
    "LOOKALIKE_1PCT_{segmento}",
    "AMPLO_{segmento}",
    "CONVERSOES_ANTERIORES_{segmento}"
]

# Lista de segmentos de público
SEGMENTOS = [
    "ESTUDANTES",
    "CONCURSEIROS",
    "PROFISSIONAIS",
    "GERAL",
    "ALTA_RENDA",
    "ZONA_SUL",
    "ZONA_NORTE",
    "BAIXADA"
]

# Lista de templates de anúncios
AD_TEMPLATES = [
    "CARROSSEL_{tema}",
    "VIDEO_{tema}",
    "IMAGEM_{tema}",
    "COLECAO_{tema}",
    "LEAD_FORM_{tema}",
    "DEPOIMENTO_{tema}"
]

# Temas dos anúncios
TEMAS = [
    "DEPOIMENTO_ALUNOS",
    "PROMOCAO",
    "ULTIMAS_VAGAS",
    "APROVADOS",
    "ESTRUTURA",
    "PROFESSORES",
    "METODO",
    "GARANTIA"
]

def get_random_campaign(curso=None):
    """Gera um nome de campanha aleatório baseado em templates reais"""
    if not curso:
        curso = random.choice(CURSOS)
    
    template = random.choice(CAMPAIGN_TEMPLATES)
    return template.replace("{curso}", curso)

def get_random_adset(segmento=None):
    """Gera um nome de conjunto de anúncios aleatório"""
    if not segmento:
        segmento = random.choice(SEGMENTOS)
    
    template = random.choice(ADSET_TEMPLATES)
    return template.replace("{segmento}", segmento)

def get_random_ad(tema=None):
    """Gera um nome de anúncio aleatório"""
    if not tema:
        tema = random.choice(TEMAS)
    
    template = random.choice(AD_TEMPLATES)
    return template.replace("{tema}", tema)

def generate_campaign_id():
    """Gera um ID de campanha aleatório no formato usado pelo Facebook"""
    return str(random.randint(10000000000, 99999999999))

def get_fbclids_from_crm(start_date=None, end_date=None):
    """Carrega FBclids do CRM"""
    try:
        # Carrega os dados do banco de dados
        df_oportunidades = carregar_dados("consultas/oportunidades/oportunidades.sql")
        
        # Converte coluna de data
        df_oportunidades['criacao'] = pd.to_datetime(df_oportunidades['criacao']).dt.tz_localize(TIMEZONE, ambiguous='infer')
        
        # Filtra por data se necessário
        if start_date and end_date:
            start_date_aware = pd.Timestamp(start_date, tz=TIMEZONE)
            end_date_aware = pd.Timestamp(end_date, tz=TIMEZONE) + pd.Timedelta(days=1)
            
            df_oportunidades = df_oportunidades[
                (df_oportunidades['criacao'] >= start_date_aware) &
                (df_oportunidades['criacao'] < end_date_aware)
            ]
        
        # Filtra apenas registros com FBclid
        df_fbclids = df_oportunidades[
            (df_oportunidades['fbclid'].notnull()) & 
            (df_oportunidades['fbclid'] != '')
        ]
        
        # Extrai informações relevantes
        fbclid_data = []
        for _, row in df_fbclids.iterrows():
            fbclid_data.append({
                'fbclid': row['fbclid'],
                'criacao': row['criacao'],
                'concurso': row['concurso'],
                'origem': row['origem']
            })
        
        return fbclid_data
    
    except Exception as e:
        print(f"Erro ao carregar FBclids do CRM: {e}")
        return []

def simular_campanha_para_fbclid(fbclid_info):
    """Simula a resposta da API do Facebook com dados realistas baseados nas informações do CRM"""
    # Tenta extrair o curso do campo 'concurso'
    curso = None
    if fbclid_info.get('concurso'):
        # Converte o nome do concurso em um formato compatível com os templates
        curso_raw = fbclid_info['concurso'].upper()
        # Simplifica e remove caracteres especiais
        curso = curso_raw.replace(' ', '_').replace('-', '_')
        # Se o curso for muito longo, pega apenas as primeiras palavras
        if len(curso) > 20:
            curso = '_'.join(curso.split('_')[:2])
    
    # Determina um segmento com base na origem
    segmento = None
    if fbclid_info.get('origem'):
        origem = fbclid_info['origem'].upper()
        if 'FACEBOOK' in origem or 'META' in origem:
            segmento = 'GERAL'
        elif 'INSTAGRAM' in origem:
            segmento = 'GERAL'
        elif 'GOOGLE' in origem:
            segmento = 'CONCURSEIROS'
    
    # Gera informações da campanha
    campaign_name = get_random_campaign(curso)
    campaign_id = generate_campaign_id()
    adset_name = get_random_adset(segmento)
    ad_name = get_random_ad()
    
    return {
        'fbclid': fbclid_info['fbclid'],
        'campaign_name': campaign_name,
        'campaign_id': campaign_id,
        'adset_name': adset_name,
        'ad_name': ad_name,
        'empresa': 'degrau',
        'last_updated': datetime.now().isoformat()
    }

def salvar_campanhas_simuladas(fbclid_campaigns):
    """Salva as campanhas simuladas no banco de dados"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Cria a tabela se não existir
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS fbclid_cache (
        fbclid TEXT PRIMARY KEY,
        campaign_name TEXT,
        campaign_id TEXT,
        adset_name TEXT,
        ad_name TEXT,
        empresa TEXT DEFAULT 'degrau',
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Prepara os dados para inserção
    records = [
        (
            campaign['fbclid'],
            campaign['campaign_name'],
            campaign['campaign_id'],
            campaign['adset_name'],
            campaign['ad_name'],
            campaign['empresa'],
            campaign['last_updated']
        )
        for campaign in fbclid_campaigns
    ]
    
    # Insere ou atualiza os registros
    cursor.executemany("""
    INSERT OR REPLACE INTO fbclid_cache 
    (fbclid, campaign_name, campaign_id, adset_name, ad_name, empresa, last_updated)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, records)
    
    conn.commit()
    conn.close()

def verificar_banco_dados():
    """Verifica o conteúdo atual do banco de dados"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM fbclid_cache")
    count = cursor.fetchone()[0]
    print(f"Total de registros no banco de dados: {count}")
    
    cursor.execute("SELECT fbclid, campaign_name, campaign_id, adset_name, ad_name FROM fbclid_cache LIMIT 10")
    rows = cursor.fetchall()
    
    print("\nPrimeiros 10 registros:")
    for row in rows:
        print(f"FBCLID: {row[0]}")
        print(f"  Campanha: {row[1]}")
        print(f"  ID da Campanha: {row[2]}")
        print(f"  Conjunto de Anúncios: {row[3]}")
        print(f"  Anúncio: {row[4]}")
        print("-" * 50)
    
    conn.close()

def main():
    print("=== Simulação de Consulta de FBclids no Facebook ===")
    print("Esse script simula a consulta à API do Facebook e preenche o banco de dados com informações realistas")
    
    # Carrega FBclids do CRM
    print("\n1. Carregando FBclids do CRM...")
    fbclid_infos = get_fbclids_from_crm()
    
    if not fbclid_infos:
        print("Nenhum FBclid encontrado no CRM. Adicionando exemplos para teste...")
        # Adiciona alguns exemplos para teste
        fbclid_infos = [
            {'fbclid': f"fb.test{i}", 'concurso': random.choice(CURSOS), 'origem': 'Facebook Ads'}
            for i in range(1, 11)
        ]
    
    print(f"Total de FBclids encontrados: {len(fbclid_infos)}")
    
    # Simula consulta ao Facebook
    print("\n2. Simulando consulta à API do Facebook...")
    fbclid_campaigns = []
    for fbclid_info in fbclid_infos:
        campaign = simular_campanha_para_fbclid(fbclid_info)
        fbclid_campaigns.append(campaign)
        print(f"Simulação para FBCLID {fbclid_info['fbclid']} concluída.")
    
    # Salva no banco de dados
    print("\n3. Salvando resultados no banco de dados...")
    salvar_campanhas_simuladas(fbclid_campaigns)
    print("Dados salvos com sucesso!")
    
    # Verifica o conteúdo do banco de dados
    print("\n4. Verificando o banco de dados após a atualização:")
    verificar_banco_dados()
    
    print("\nPronto! Agora você pode testar a consulta de campanhas do Facebook na dashboard.")

if __name__ == "__main__":
    main()
