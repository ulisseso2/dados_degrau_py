#!/usr/bin/env python3
"""
Script para reprocessar GCLIDs não encontrados na Central

Este script permite executar o reprocessamento de GCLIDs não encontrados 
de forma independente do dashboard Streamlit para a versão Central.

Uso:
    python reprocess_gclids_central.py --period 30  # Reprocessa últimos 30 dias
    python reprocess_gclids_central.py --all        # Reprocessa todos os GCLIDs não encontrados
    python reprocess_gclids_central.py --count      # Apenas mostra quantos não foram encontrados
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Adiciona o diretório raiz ao path para importar módulos
sys.path.append(str(Path(__file__).parent))

from gclid_db_central import (
    get_not_found_gclids,
    get_gclids_by_date_range,
    count_not_found_gclids,
    save_gclid_cache_batch,
    load_gclid_cache
)

def get_google_ads_client():
    """Configuração do cliente Google Ads para a Central"""
    try:
        from google.ads.googleads.client import GoogleAdsClient
        from dotenv import load_dotenv
        import yaml
        import os
        
        load_dotenv()
        
        # Carrega configurações do Google Ads específicas da Central
        with open("google-ads_central.yaml", "r") as f:
            config = yaml.safe_load(f)
        
        client = GoogleAdsClient.load_from_storage(path="google-ads_central.yaml")
        customer_id = config.get("customer_id")
        
        return client, customer_id
    except Exception as e:
        print(f"Erro ao configurar cliente Google Ads (Central): {e}")
        return None, None

def reprocess_gclids_batch(client, customer_id, gclid_list):
    """Reprocessa um lote de GCLIDs na Central"""
    from google.ads.googleads.errors import GoogleAdsException
    import time
    
    # Cria dicionário de GCLIDs para consulta
    today = datetime.now().date()
    gclid_date_dict = {gclid: today for gclid, _ in gclid_list}
    
    if not gclid_date_dict:
        return {}
    
    ga_service = client.get_service("GoogleAdsService")
    found_campaigns = {}
    
    # Agrupa por lotes para evitar sobrecarga da API
    batch_size = 100
    gclids_list = list(gclid_date_dict.keys())
    
    for i in range(0, len(gclids_list), batch_size):
        batch_gclids = gclids_list[i:i + batch_size]
        
        # Tenta diferentes períodos para maximizar chances de encontrar
        date_ranges = [
            today.strftime('%Y-%m-%d'),
            (today - timedelta(days=7)).strftime('%Y-%m-%d'),
            (today - timedelta(days=30)).strftime('%Y-%m-%d'),
            (today - timedelta(days=90)).strftime('%Y-%m-%d'),
        ]
        
        for date_str in date_ranges:
            query = f"""
                SELECT 
                    campaign.name, 
                    click_view.gclid
                FROM click_view
                WHERE click_view.gclid IN ('{"','".join(batch_gclids)}')
                AND segments.date = '{date_str}'
                LIMIT {len(batch_gclids)}
            """
            
            try:
                stream = ga_service.search_stream(
                    customer_id=customer_id, 
                    query=query
                )
                
                for response in stream:
                    for row in response.results:
                        gclid = row.click_view.gclid
                        campaign_name = row.campaign.name
                        if gclid and campaign_name and gclid not in found_campaigns:
                            found_campaigns[gclid] = campaign_name
                
                time.sleep(0.5)  # Rate limiting
                
            except GoogleAdsException as ex:
                print(f"Erro na consulta para {date_str} (Central): {ex}")
                continue
        
        # Remove os GCLIDs já encontrados do próximo lote
        batch_gclids = [g for g in batch_gclids if g not in found_campaigns]
        if not batch_gclids:
            break
    
    return found_campaigns

def main():
    parser = argparse.ArgumentParser(description="Reprocessa GCLIDs não encontrados na Central")
    parser.add_argument("--period", type=int, help="Reprocessa GCLIDs dos últimos N dias")
    parser.add_argument("--all", action="store_true", help="Reprocessa todos os GCLIDs não encontrados")
    parser.add_argument("--count", action="store_true", help="Apenas conta GCLIDs não encontrados")
    parser.add_argument("--batch-size", type=int, default=500, help="Tamanho do lote para processamento")
    
    args = parser.parse_args()
    
    if args.count:
        total = count_not_found_gclids()
        print(f"Total de GCLIDs não encontrados na Central: {total}")
        return
    
    if not (args.period or args.all):
        parser.print_help()
        return
    
    # Obtém lista de GCLIDs para reprocessar
    if args.all:
        gclid_list = get_not_found_gclids()
        print(f"Reprocessando {len(gclid_list)} GCLIDs não encontrados na Central...")
    else:
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=args.period)
        gclid_list = get_gclids_by_date_range(start_date, end_date)
        print(f"Reprocessando {len(gclid_list)} GCLIDs não encontrados dos últimos {args.period} dias na Central...")
    
    if not gclid_list:
        print("Nenhum GCLID não encontrado para reprocessar na Central!")
        return
    
    # Configura cliente Google Ads
    client, customer_id = get_google_ads_client()
    if not client or not customer_id:
        print("Erro: Não foi possível configurar o cliente Google Ads (Central)")
        return
    
    # Processa em lotes
    total_found = 0
    batch_size = args.batch_size
    
    for i in range(0, len(gclid_list), batch_size):
        batch = gclid_list[i:i + batch_size]
        print(f"Processando lote {i//batch_size + 1} ({len(batch)} GCLIDs) na Central...")
        
        found_campaigns = reprocess_gclids_batch(client, customer_id, batch)
        
        if found_campaigns:
            # Salva no banco de dados
            save_gclid_cache_batch(found_campaigns)
            total_found += len(found_campaigns)
            print(f"  ✅ Encontrados {len(found_campaigns)} campanhas neste lote")
        else:
            print(f"  ❌ Nenhuma campanha encontrada neste lote")
    
    print(f"\n🎉 Reprocessamento da Central concluído!")
    print(f"📊 Total de GCLIDs encontrados: {total_found}")
    print(f"📊 GCLIDs ainda não encontrados: {len(gclid_list) - total_found}")

if __name__ == "__main__":
    main()