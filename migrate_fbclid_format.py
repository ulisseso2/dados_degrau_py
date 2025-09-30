#!/usr/bin/env python3
# migrate_fbclid_format.py
# Script para migrar FBclids existentes para o novo formato da Meta

import sqlite3
import time
import re
from datetime import datetime
from pathlib import Path
import os

DB_FILE = "fbclid_cache.db"
BACKUP_DIR = "backup"

def format_fbclid(fbclid_raw):
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
            return fbclid_raw
        
        # Se o FBclid começar com IwAR, é provável que seja apenas a parte final
        if fbclid_raw.startswith('IwAR') or fbclid_raw.startswith('fb'):
            # Formata no padrão correto
            timestamp = int(time.time() * 1000)  # Timestamp atual em milissegundos
            return f"fb.1.{timestamp}.{fbclid_raw}"
    
    return fbclid_raw

def backup_database():
    """Cria um backup do banco de dados atual"""
    # Garante que o diretório de backup existe
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    
    # Nome do arquivo de backup com timestamp
    backup_file = os.path.join(BACKUP_DIR, f"fbclid_cache_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
    
    # Copia o banco de dados atual para o backup
    if os.path.exists(DB_FILE):
        # Cria uma conexão de backup
        source = sqlite3.connect(DB_FILE)
        backup = sqlite3.connect(backup_file)
        
        source.backup(backup)
        
        # Fecha as conexões
        source.close()
        backup.close()
        
        print(f"Backup criado em: {backup_file}")
        return True
    else:
        print("Banco de dados original não encontrado. Nenhum backup criado.")
        return False

def add_formatted_column():
    """Adiciona a coluna formatted_fbclid se ela não existir"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        # Verifica se a coluna já existe
        cursor.execute("PRAGMA table_info(fbclid_cache)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if "formatted_fbclid" not in columns:
            # Adiciona a coluna
            cursor.execute("ALTER TABLE fbclid_cache ADD COLUMN formatted_fbclid TEXT")
            conn.commit()
            print("Coluna formatted_fbclid adicionada com sucesso.")
        else:
            print("Coluna formatted_fbclid já existe.")
    
    except Exception as e:
        print(f"Erro ao adicionar coluna: {e}")
    
    finally:
        conn.close()

def migrate_fbclids():
    """Migra os FBclids existentes para o novo formato"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        # Busca todos os FBclids
        cursor.execute("SELECT fbclid FROM fbclid_cache")
        rows = cursor.fetchall()
        
        if not rows:
            print("Nenhum FBclid encontrado no banco de dados.")
            return
        
        print(f"Migrando {len(rows)} FBclids...")
        
        # Atualiza cada FBclid
        for i, (fbclid,) in enumerate(rows):
            # Formata o FBclid
            formatted_fbclid = format_fbclid(fbclid)
            
            # Atualiza o banco de dados
            cursor.execute(
                "UPDATE fbclid_cache SET formatted_fbclid = ? WHERE fbclid = ?",
                (formatted_fbclid, fbclid)
            )
            
            # A cada 100 registros, faz commit
            if (i + 1) % 100 == 0:
                conn.commit()
                print(f"Processados {i + 1}/{len(rows)} FBclids...")
        
        # Commit final
        conn.commit()
        print(f"Migração concluída. {len(rows)} FBclids foram migrados para o novo formato.")
    
    except Exception as e:
        print(f"Erro durante a migração: {e}")
        conn.rollback()
    
    finally:
        conn.close()

def verify_migration():
    """Verifica o resultado da migração"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        # Conta quantos registros foram migrados
        cursor.execute("SELECT COUNT(*) FROM fbclid_cache WHERE formatted_fbclid IS NOT NULL")
        migrated_count = cursor.fetchone()[0]
        
        # Conta o total de registros
        cursor.execute("SELECT COUNT(*) FROM fbclid_cache")
        total_count = cursor.fetchone()[0]
        
        print(f"\nResultado da migração:")
        print(f"- Total de registros: {total_count}")
        print(f"- Registros migrados: {migrated_count}")
        print(f"- Porcentagem: {migrated_count / total_count * 100:.2f}% concluída")
        
        # Mostra alguns exemplos
        cursor.execute("""
        SELECT fbclid, formatted_fbclid FROM fbclid_cache 
        WHERE formatted_fbclid IS NOT NULL 
        LIMIT 5
        """)
        
        examples = cursor.fetchall()
        
        if examples:
            print("\nExemplos de registros migrados:")
            for fbclid, formatted_fbclid in examples:
                print(f"Original: {fbclid}")
                print(f"Formatado: {formatted_fbclid}")
                print("-" * 50)
    
    except Exception as e:
        print(f"Erro ao verificar migração: {e}")
    
    finally:
        conn.close()

def main():
    print("=== Migração de FBclids para o Formato da Meta ===")
    
    # Verifica se o banco de dados existe
    if not os.path.exists(DB_FILE):
        print(f"Banco de dados {DB_FILE} não encontrado.")
        return
    
    # Faz backup do banco de dados
    print("\n1. Criando backup do banco de dados...")
    backup_database()
    
    # Adiciona a coluna formatted_fbclid
    print("\n2. Adicionando coluna formatted_fbclid...")
    add_formatted_column()
    
    # Migra os FBclids
    print("\n3. Migrando FBclids para o novo formato...")
    migrate_fbclids()
    
    # Verifica a migração
    print("\n4. Verificando resultado da migração...")
    verify_migration()
    
    print("\nProcesso de migração concluído!")
    print("""
Próximos passos:
1. Execute o script clean_fbclid_db.py para limpar dados de teste
2. Configure o Pixel ID nas variáveis de ambiente ou Streamlit Secrets
3. Teste a consulta de campanhas reais na dashboard
""")

if __name__ == "__main__":
    main()
