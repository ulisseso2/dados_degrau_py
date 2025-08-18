import sqlite3
from datetime import datetime

# Adiciona alguns dados de exemplo para testes
DB_FILE = "fbclid_cache.db"
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# Criar a tabela se não existir
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

# Adicionar alguns dados de exemplo
sample_data = [
    ("fb.example12345", "Campanha de Teste 1", "123456789", "Conjunto 1", "Anúncio 1", "degrau", datetime.now().isoformat()),
    ("fb.example67890", "Campanha de Teste 2", "987654321", "Conjunto 2", "Anúncio 2", "degrau", datetime.now().isoformat()),
    ("IwAR123456789", "Campanha de Teste 3", "5678901234", "Conjunto 3", "Anúncio 3", "degrau", datetime.now().isoformat())
]

cursor.executemany("""
INSERT OR REPLACE INTO fbclid_cache 
(fbclid, campaign_name, campaign_id, adset_name, ad_name, empresa, last_updated)
VALUES (?, ?, ?, ?, ?, ?, ?)
""", sample_data)

conn.commit()

# Verificar os dados
cursor.execute("SELECT COUNT(*) FROM fbclid_cache")
count = cursor.fetchone()[0]
print(f"Total de registros no banco: {count}")

cursor.execute("SELECT fbclid, campaign_name, campaign_id FROM fbclid_cache LIMIT 10")
rows = cursor.fetchall()
print("\nRegistros de exemplo:")
for row in rows:
    print(f"FBCLID: {row[0]} - Campanha: {row[1]} - ID da Campanha: {row[2]}")

conn.close()
print("\nDados de exemplo adicionados com sucesso ao banco fbclid_cache.db!")
