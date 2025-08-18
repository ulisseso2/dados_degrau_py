# check_fbclid_migration.py
"""
Este script verifica e atualiza a estrutura do banco de dados de FBclids.
Útil para migrações e verificações de integridade do banco.
"""

import sqlite3
import os
import shutil
from datetime import datetime

DB_FILE = "fbclid_cache.db"
BACKUP_FOLDER = "backup"

def backup_database():
    """Cria um backup do banco de dados atual"""
    # Garante que a pasta de backup existe
    if not os.path.exists(BACKUP_FOLDER):
        os.makedirs(BACKUP_FOLDER)
        
    # Nome do arquivo de backup com timestamp
    backup_file = os.path.join(BACKUP_FOLDER, f"{DB_FILE}.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    
    # Copia o arquivo apenas se ele existir
    if os.path.exists(DB_FILE):
        shutil.copy2(DB_FILE, backup_file)
        print(f"Backup criado: {backup_file}")
    else:
        print(f"Nenhum arquivo de banco de dados existente para backup.")

def check_table_structure():
    """Verifica se a tabela tem a estrutura correta e atualiza se necessário"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Verifica se a tabela fbclid_cache existe
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fbclid_cache'")
    table_exists = cursor.fetchone()
    
    if not table_exists:
        # Cria a tabela com a estrutura atual
        cursor.execute("""
        CREATE TABLE fbclid_cache (
            fbclid TEXT PRIMARY KEY,
            campaign_name TEXT,
            campaign_id TEXT,
            adset_name TEXT,
            ad_name TEXT,
            empresa TEXT DEFAULT 'degrau',
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        print("Tabela fbclid_cache criada com sucesso.")
    else:
        # Verifica se todas as colunas necessárias existem
        cursor.execute("PRAGMA table_info(fbclid_cache)")
        columns = {row[1] for row in cursor.fetchall()}
        
        required_columns = {
            'fbclid', 'campaign_name', 'campaign_id', 'adset_name', 
            'ad_name', 'empresa', 'last_updated'
        }
        
        missing_columns = required_columns - columns
        
        if missing_columns:
            print(f"Colunas ausentes na tabela: {missing_columns}")
            
            # Adiciona as colunas ausentes
            for column in missing_columns:
                if column == 'empresa':
                    cursor.execute(f"ALTER TABLE fbclid_cache ADD COLUMN {column} TEXT DEFAULT 'degrau'")
                elif column == 'last_updated':
                    cursor.execute(f"ALTER TABLE fbclid_cache ADD COLUMN {column} TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                else:
                    cursor.execute(f"ALTER TABLE fbclid_cache ADD COLUMN {column} TEXT")
                    
            print("Tabela atualizada com as colunas necessárias.")
        else:
            print("A estrutura da tabela está atualizada.")
    
    conn.commit()
    conn.close()

def verify_indexes():
    """Verifica e cria índices para melhorar a performance das consultas"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Verifica índices existentes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='fbclid_cache'")
    existing_indexes = {row[0] for row in cursor.fetchall()}
    
    # Define os índices necessários
    required_indexes = {
        'idx_fbclid_cache_empresa': 'CREATE INDEX idx_fbclid_cache_empresa ON fbclid_cache(empresa)',
        'idx_fbclid_cache_campaign': 'CREATE INDEX idx_fbclid_cache_campaign ON fbclid_cache(campaign_name)',
    }
    
    # Cria os índices ausentes
    for index_name, create_stmt in required_indexes.items():
        if index_name not in existing_indexes:
            cursor.execute(create_stmt)
            print(f"Índice {index_name} criado.")
    
    conn.commit()
    conn.close()

def main():
    print("Iniciando verificação do banco de dados de FBclids...")
    
    # Faz backup do banco existente (se houver)
    backup_database()
    
    # Verifica e atualiza a estrutura da tabela
    check_table_structure()
    
    # Verifica e cria os índices necessários
    verify_indexes()
    
    print("Verificação concluída com sucesso!")

if __name__ == "__main__":
    main()
