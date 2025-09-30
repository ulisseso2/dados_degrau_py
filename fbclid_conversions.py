#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Ferramenta para envio de FBclids para a API de Conversões da Meta
e exibição de estatísticas sobre as conversões.

Este script permite:
1. Extrair FBclids do banco de dados SQLite
2. Enviar eventos com FBclids para a API de Conversões da Meta
3. Exibir estatísticas sobre o envio
"""

import os
import time
import json
import sqlite3
import requests
from datetime import datetime, timedelta
import pandas as pd
from dotenv import load_dotenv
import argparse
import logging

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("fbclid_conversions.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("fbclid_conversions")

# Carregar variáveis de ambiente do arquivo principal e depois do arquivo específico do Facebook
load_dotenv()
load_dotenv('.facebook_credentials.env')  # Carrega as credenciais específicas do Facebook

# Configurações da API do Facebook
FB_ACCESS_TOKEN = os.getenv('FB_ACCESS_TOKEN')
PIXEL_ID = os.getenv('FB_PIXEL_ID')

# Verificar se as credenciais estão configuradas
if not FB_ACCESS_TOKEN or not PIXEL_ID:
    logger.error("Credenciais não encontradas. Configure FB_ACCESS_TOKEN e FB_PIXEL_ID no arquivo .env")
    exit(1)

# Funções para manipulação de FBclids
def format_fbclid(fbclid, created_at=None):
    """
    Garante que o FBclid esteja no formato correto (fb.1.timestamp.fbclid)
    
    Args:
        fbclid: O valor do FBclid
        created_at: Data de criação para usar como timestamp (opcional)
    """
    if fbclid is None or fbclid == "":
        return None

    # Verifica se já está no formato correto (fb.número.timestamp.valor)
    if fbclid.startswith('fb.') and len(fbclid.split('.')) >= 4:
        logger.debug(f"FBclid já está no formato correto: {fbclid}")
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
            logger.debug(f"Usando timestamp da data de criação: {timestamp}")
        except Exception as e:
            logger.warning(f"Erro ao converter data de criação, usando timestamp atual: {str(e)}")
            timestamp = int(time.time())
    else:
        # Usa o timestamp atual com um pequeno incremento aleatório para garantir unicidade
        import random
        timestamp = int(time.time()) + random.randint(1, 100)
        logger.debug(f"Usando timestamp atual com incremento: {timestamp}")
    
    # Formata o FBclid
    formatted = f"fb.1.{timestamp}.{fbclid}"
    logger.debug(f"FBclid formatado de '{fbclid}' para '{formatted}'")
    return formatted

def get_fbclids_from_db(db_path='gclid_cache.db', days_ago=30, limit=1000):
    """
    Extrai FBclids do banco de dados SQLite
    
    Args:
        db_path: Caminho para o banco de dados SQLite
        days_ago: Número de dias para trás a considerar
        limit: Limite de registros a retornar
        
    Returns:
        Lista de dicionários com FBclids e dados relacionados
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Verifica se a tabela existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [table[0] for table in cursor.fetchall()]
        logger.info(f"Tabelas encontradas no banco de dados: {tables}")
        
        # Determina qual tabela usar (gclid_cache ou ad_clicks)
        table_name = None
        if 'ad_clicks' in tables:
            table_name = 'ad_clicks'
        elif 'gclid_cache' in tables:
            table_name = 'gclid_cache'
        else:
            logger.error(f"Nenhuma tabela relevante encontrada no banco de dados {db_path}")
            return []
        
        # Verifica a estrutura da tabela selecionada
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [column[1] for column in cursor.fetchall()]
        logger.info(f"Colunas encontradas na tabela {table_name}: {columns}")
        
        # Verifica se a coluna fbclid existe
        fbclid_column = None
        if 'fbclid' in columns:
            fbclid_column = 'fbclid'
        elif 'fb_clid' in columns:
            fbclid_column = 'fb_clid'
        
        if not fbclid_column:
            logger.error(f"Coluna para FBclids não encontrada na tabela {table_name}")
            return []
        
        # Determina a coluna de data
        date_column = None
        for col in ['created_at', 'date', 'timestamp', 'created_date']:
            if col in columns:
                date_column = col
                break
        
        if not date_column:
            logger.warning(f"Coluna de data não encontrada na tabela {table_name}, usando todas as entradas")
            
            # Consulta sem filtro de data
            query = f"""
            SELECT {fbclid_column}
            FROM {table_name}
            WHERE {fbclid_column} IS NOT NULL AND {fbclid_column} != ''
            LIMIT ?
            """
            cursor.execute(query, (limit,))
        else:
            # Calcula a data de corte
            cutoff_date = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m-%d')
            
            # Consulta com filtro de data
            query = f"""
            SELECT {fbclid_column}, {date_column}
            FROM {table_name}
            WHERE {fbclid_column} IS NOT NULL AND {fbclid_column} != ''
            AND {date_column} >= ?
            ORDER BY {date_column} DESC
            LIMIT ?
            """
            cursor.execute(query, (cutoff_date, limit))
        
        results = cursor.fetchall()
        logger.info(f"Encontrados {len(results)} registros com FBclids")
        
        # Formata os resultados
        fbclids_data = []
        for row in results:
            if date_column:
                fbclid, created_at = row
                fbclids_data.append({
                    'fbclid': fbclid,
                    'formatted_fbclid': format_fbclid(fbclid, created_at),
                    'created_at': created_at
                })
            else:
                fbclid = row[0]
                fbclids_data.append({
                    'fbclid': fbclid,
                    'formatted_fbclid': format_fbclid(fbclid)
                })
            
        conn.close()
        logger.info(f"Extraídos {len(fbclids_data)} FBclids do banco de dados")
        return fbclids_data
    
    except Exception as e:
        logger.error(f"Erro ao extrair FBclids do banco de dados: {str(e)}")
        return []

# Funções para interação com a API do Facebook
def send_conversion_event(fbclid, event_name="PageView", event_time=None, event_id=None):
    """
    Envia um evento para a API de Conversões do Facebook
    
    Args:
        fbclid: FBclid formatado para envio
        event_name: Nome do evento (default: PageView)
        event_time: Timestamp do evento (default: agora)
        event_id: ID único do evento (optional)
        
    Returns:
        Resposta da API de Conversões
    """
    if not fbclid:
        return {"error": "FBclid não fornecido"}
    
    # Usa a data de criação para o timestamp, ou o tempo atual
    if not event_time:
        event_time = int(time.time())
    
    # Gera um event_id único se não fornecido
    if not event_id:
        import uuid
        event_id = str(uuid.uuid4())
    
    # Usa a função de formatação melhorada
    # Se fbclid já for um dicionário com created_at, extrai os valores
    if isinstance(fbclid, dict) and 'fbclid' in fbclid:
        created_at = fbclid.get('created_at')
        fbclid_value = fbclid.get('fbclid')
        formatted_fbclid = format_fbclid(fbclid_value, created_at)
    else:
        # Se for uma string, usa como está
        formatted_fbclid = format_fbclid(fbclid)
    
    # Log detalhado do FBclid sendo enviado
    logger.debug(f"Enviando evento com FBclid: {formatted_fbclid}, event_time: {event_time}, event_id: {event_id}")
    
    # Prepara o payload do evento
    event_data = {
        "data": [
            {
                "event_name": event_name,
                "event_time": event_time,
                "event_id": event_id,
                "action_source": "website",
                "event_source_url": "https://degrauculturalidiomas.com.br/",
                "user_data": {
                    "fbc": formatted_fbclid,
                    # Adiciona valores padrão para campos obrigatórios
                    "client_ip_address": "127.0.0.1",
                    "client_user_agent": "Mozilla/5.0"
                }
            }
        ]
    }
    
    # URL da API de Conversões
    url = f"https://graph.facebook.com/v17.0/{PIXEL_ID}/events"
    
    # Parâmetros da requisição
    params = {
        "access_token": FB_ACCESS_TOKEN
    }
    
    try:
        # Envia o evento para a API
        response = requests.post(url, params=params, json=event_data)
        result = response.json()
        
        # Log da resposta
        logger.debug(f"Resposta da API para FBclid {formatted_fbclid}: {result}")
        
        return result
    
    except Exception as e:
        logger.error(f"Erro ao enviar evento para API de Conversões: {str(e)}")
        return {"error": str(e)}

def send_fbclids_batch(fbclids_data, batch_size=50):
    """
    Envia FBclids em lotes para a API de Conversões
    
    Args:
        fbclids_data: Lista de dicionários com dados de FBclids
        batch_size: Tamanho do lote para envio
        
    Returns:
        Resultados do envio
    """
    import uuid
    
    results = {
        'total': len(fbclids_data),
        'success': 0,
        'failed': 0,
        'responses': []
    }
    
    # Processa em lotes
    for i in range(0, len(fbclids_data), batch_size):
        batch = fbclids_data[i:i+batch_size]
        logger.info(f"Processando lote {i//batch_size + 1}/{(len(fbclids_data) + batch_size - 1) // batch_size}")
        
        for item in batch:
            # Gera um ID de evento único
            event_id = str(uuid.uuid4())
            
            # Obtém o FBclid já formatado, ou o original para formatação
            fbclid = item.get('formatted_fbclid') or item.get('fbclid')
            
            # Log do FBclid sendo processado
            logger.info(f"Processando FBclid: {fbclid[:30]}...")
            
            # Tenta extrair a data de criação para o event_time
            event_time = None
            try:
                if 'created_at' in item and item['created_at']:
                    created_date = datetime.strptime(item['created_at'], '%Y-%m-%d %H:%M:%S')
                    event_time = int(created_date.timestamp())
                    logger.debug(f"Usando data de criação como event_time: {event_time}")
            except Exception as e:
                logger.warning(f"Erro ao converter data de criação: {str(e)}")
                # Se falhar, usa o tempo atual
                pass
            
            # Envia o evento com o ID único
            response = send_conversion_event(fbclid, event_time=event_time, event_id=event_id)
            
            # Registra o resultado
            item['response'] = response
            results['responses'].append({
                'fbclid': fbclid,
                'event_id': event_id,
                'event_time': event_time,
                'response': response
            })
            
            if response.get('events_received', 0) > 0:
                results['success'] += 1
                logger.info(f"Evento enviado com sucesso: event_id={event_id}")
            else:
                results['failed'] += 1
                logger.warning(f"Falha ao enviar evento: {response}")
            
            # Pequena pausa para não sobrecarregar a API
            time.sleep(0.5)
    
    logger.info(f"Processamento concluído: {results['success']} eventos enviados com sucesso, {results['failed']} falhas")
    return results

# Função principal
def main():
    """Função principal"""
    parser = argparse.ArgumentParser(description='Ferramenta para envio de FBclids para a API de Conversões da Meta')
    parser.add_argument('--days', type=int, default=30, help='Número de dias para trás a considerar')
    parser.add_argument('--limit', type=int, default=1000, help='Limite de FBclids a processar')
    parser.add_argument('--batch', type=int, default=50, help='Tamanho do lote para envio')
    parser.add_argument('--db', type=str, default='gclid_cache.db', help='Caminho para o banco de dados SQLite')
    parser.add_argument('--output', type=str, help='Arquivo para salvar os resultados (JSON)')
    
    args = parser.parse_args()
    
    logger.info("Iniciando processamento de FBclids")
    
    # Extrai FBclids do banco de dados
    fbclids_data = get_fbclids_from_db(db_path=args.db, days_ago=args.days, limit=args.limit)
    
    if not fbclids_data:
        logger.warning("Nenhum FBclid encontrado para processar")
        return
    
    # Envia FBclids para a API de Conversões
    results = send_fbclids_batch(fbclids_data, batch_size=args.batch)
    
    # Exibe estatísticas
    print("\n" + "="*80)
    print(" ESTATÍSTICAS DE ENVIO DE FBCLIDS")
    print("="*80)
    print(f"Total de FBclids: {results['total']}")
    print(f"Eventos enviados com sucesso: {results['success']}")
    print(f"Eventos com falha: {results['failed']}")
    print(f"Taxa de sucesso: {results['success']/results['total']*100:.2f}%")
    print("="*80 + "\n")
    
    # Salva os resultados em arquivo JSON se solicitado
    if args.output:
        try:
            with open(args.output, 'w') as f:
                json.dump(results, f, indent=2)
            logger.info(f"Resultados salvos em {args.output}")
        except Exception as e:
            logger.error(f"Erro ao salvar resultados: {str(e)}")
    
    logger.info("Processamento concluído")

if __name__ == "__main__":
    main()
