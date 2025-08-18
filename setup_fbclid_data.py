#!/usr/bin/env python3
"""
Script para inicializar o banco de dados de FBclids com dados
de exemplo ou migrar dados existentes de outras fontes.
"""

import sqlite3
import pandas as pd
import os
from datetime import datetime
import json
import argparse

DB_FILE = "fbclid_cache.db"
BACKUP_DIR = "backup"

def backup_db():
    """Cria um backup do banco de dados atual"""
    if not os.path.exists(DB_FILE):
        print("Nenhum banco de dados existente para backup.")
        return
    
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"{DB_FILE}.{timestamp}")
    
    import shutil
    shutil.copy2(DB_FILE, backup_path)
    print(f"Backup criado em: {backup_path}")

def initialize_db():
    """Inicializa o banco de dados com a estrutura correta"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Cria a tabela principal
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
    
    # Cria índices para melhorar a performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_fbclid_cache_empresa ON fbclid_cache(empresa)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_fbclid_cache_campaign ON fbclid_cache(campaign_name)")
    
    conn.commit()
    conn.close()
    print("Banco de dados inicializado com sucesso.")

def import_from_json(json_file, empresa="degrau"):
    """Importa dados de um arquivo JSON para o banco de dados"""
    if not os.path.exists(json_file):
        print(f"Arquivo {json_file} não encontrado.")
        return
    
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    count = 0
    for fbclid, campaign_data in data.items():
        if isinstance(campaign_data, str):
            # Formato simples: fbclid -> nome_campanha
            cursor.execute("""
            INSERT OR REPLACE INTO fbclid_cache 
            (fbclid, campaign_name, empresa, last_updated)
            VALUES (?, ?, ?, ?)
            """, (fbclid, campaign_data, empresa, datetime.now().isoformat()))
        elif isinstance(campaign_data, dict):
            # Formato completo: fbclid -> {dados da campanha}
            cursor.execute("""
            INSERT OR REPLACE INTO fbclid_cache 
            (fbclid, campaign_name, campaign_id, adset_name, ad_name, empresa, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                fbclid, 
                campaign_data.get('campaign_name'),
                campaign_data.get('campaign_id'),
                campaign_data.get('adset_name'),
                campaign_data.get('ad_name'),
                empresa, 
                datetime.now().isoformat()
            ))
        count += 1
    
    conn.commit()
    conn.close()
    print(f"Importados {count} registros do arquivo JSON.")

def import_from_csv(csv_file, empresa="degrau"):
    """Importa dados de um arquivo CSV para o banco de dados"""
    if not os.path.exists(csv_file):
        print(f"Arquivo {csv_file} não encontrado.")
        return
    
    df = pd.read_csv(csv_file)
    required_columns = ['fbclid']
    
    for col in required_columns:
        if col not in df.columns:
            print(f"Coluna obrigatória '{col}' não encontrada no CSV.")
            return
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    count = 0
    for _, row in df.iterrows():
        fbclid = row['fbclid']
        if pd.isna(fbclid) or fbclid == '':
            continue
        
        campaign_name = row.get('campaign_name', 'Não consultado')
        campaign_id = row.get('campaign_id')
        adset_name = row.get('adset_name')
        ad_name = row.get('ad_name')
        
        cursor.execute("""
        INSERT OR REPLACE INTO fbclid_cache 
        (fbclid, campaign_name, campaign_id, adset_name, ad_name, empresa, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            fbclid, 
            campaign_name,
            campaign_id,
            adset_name,
            ad_name,
            empresa, 
            datetime.now().isoformat()
        ))
        count += 1
    
    conn.commit()
    conn.close()
    print(f"Importados {count} registros do arquivo CSV.")

def add_sample_data():
    """Adiciona alguns dados de exemplo ao banco de dados"""
    sample_data = {
        "fb.sample123456": "Campanha de Teste 1",
        "fb.sample789012": "Campanha de Teste 2",
        "IwAR1234567890": "Campanha de Teste 3",
    }
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    for fbclid, campaign_name in sample_data.items():
        cursor.execute("""
        INSERT OR REPLACE INTO fbclid_cache 
        (fbclid, campaign_name, empresa, last_updated)
        VALUES (?, ?, ?, ?)
        """, (fbclid, campaign_name, "degrau", datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    print(f"Adicionados {len(sample_data)} registros de exemplo.")

def list_entries(limit=10, empresa="degrau"):
    """Lista as entradas no banco de dados"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT fbclid, campaign_name, campaign_id, last_updated
    FROM fbclid_cache
    WHERE empresa = ?
    LIMIT ?
    """, (empresa, limit))
    
    rows = cursor.fetchall()
    
    if not rows:
        print(f"Nenhum registro encontrado para a empresa '{empresa}'.")
    else:
        print(f"\nPrimeiros {len(rows)} registros para a empresa '{empresa}':")
        print("-" * 80)
        for row in rows:
            print(f"FBCLID: {row[0]}")
            print(f"Campanha: {row[1]}")
            print(f"ID da Campanha: {row[2] or 'N/A'}")
            print(f"Última Atualização: {row[3]}")
            print("-" * 80)
    
    cursor.execute("SELECT COUNT(*) FROM fbclid_cache WHERE empresa = ?", (empresa,))
    total = cursor.fetchone()[0]
    print(f"Total de registros para a empresa '{empresa}': {total}")
    
    conn.close()

def main():
    parser = argparse.ArgumentParser(description="Utilitário para gerenciar o banco de dados de FBclids")
    parser.add_argument("--json", help="Importar dados de um arquivo JSON")
    parser.add_argument("--csv", help="Importar dados de um arquivo CSV")
    parser.add_argument("--empresa", default="degrau", help="Nome da empresa para os registros (padrão: degrau)")
    parser.add_argument("--list", action="store_true", help="Listar entradas do banco de dados")
    parser.add_argument("--sample", action="store_true", help="Adicionar dados de exemplo")
    parser.add_argument("--limit", type=int, default=10, help="Limite de registros para listar (padrão: 10)")
    
    args = parser.parse_args()
    
    # Faz backup do banco existente
    backup_db()
    
    # Inicializa o banco
    initialize_db()
    
    # Processa as opções
    if args.json:
        import_from_json(args.json, args.empresa)
    
    if args.csv:
        import_from_csv(args.csv, args.empresa)
    
    if args.sample:
        add_sample_data()
    
    if args.list or not (args.json or args.csv or args.sample):
        # Lista as entradas se solicitado ou se nenhuma ação foi especificada
        list_entries(args.limit, args.empresa)

if __name__ == "__main__":
    main()
