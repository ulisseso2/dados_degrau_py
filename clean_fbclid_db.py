import sqlite3
import os
import shutil
from datetime import datetime

# Configurações
DB_FILE = "fbclid_cache.db"
BACKUP_DIR = "backup"

# Cria o diretório de backup se não existir
if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)
    print(f"Diretório de backup '{BACKUP_DIR}' criado.")

# Faz backup do banco de dados atual antes de apagá-lo
if os.path.exists(DB_FILE):
    backup_file = os.path.join(BACKUP_DIR, f"{DB_FILE}.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(DB_FILE, backup_file)
    print(f"Backup do banco de dados realizado: {backup_file}")
    
    # Remove o banco de dados atual
    os.remove(DB_FILE)
    print(f"Banco de dados '{DB_FILE}' removido.")

# Cria um novo banco de dados com a estrutura correta
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# Cria a tabela
cursor.execute("""
CREATE TABLE IF NOT EXISTS fbclid_cache (
    fbclid TEXT PRIMARY KEY,
    formatted_fbclid TEXT,
    campaign_name TEXT,
    campaign_id TEXT,
    adset_name TEXT,
    ad_name TEXT,
    empresa TEXT DEFAULT 'degrau',
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# Cria índices para otimização
cursor.execute("CREATE INDEX IF NOT EXISTS idx_fbclid_cache_empresa ON fbclid_cache(empresa)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_fbclid_cache_campaign ON fbclid_cache(campaign_name)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_fbclid_cache_formatted ON fbclid_cache(formatted_fbclid)")

conn.commit()
conn.close()

print(f"Novo banco de dados '{DB_FILE}' criado com sucesso!")
print("O banco de dados agora está limpo e pronto para receber novos dados.")
print("Para preencher com dados reais, use o botão 'Consultar Campanhas no Facebook' na página de análise do Facebook.")
