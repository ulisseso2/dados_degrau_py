import sqlite3
from datetime import datetime

# Atualiza alguns dados existentes com informações de campanha
DB_FILE = "fbclid_cache.db"
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# Pegar alguns FBCLIDs existentes
cursor.execute("SELECT fbclid FROM fbclid_cache LIMIT 5")
fbclids = [row[0] for row in cursor.fetchall()]

# Dados de campanha para atualização
campaign_data = [
    ("Campanha Facebook Test 1", "123456", "Conjunto de Anúncios 1", "Anúncio Criativo 1"),
    ("Campanha Facebook Test 2", "234567", "Conjunto de Anúncios 2", "Anúncio Criativo 2"),
    ("Campanha Facebook Test 3", "345678", "Conjunto de Anúncios 3", "Anúncio Criativo 3"),
    ("Campanha Facebook Test 4", "456789", "Conjunto de Anúncios 4", "Anúncio Criativo 4"),
    ("Campanha Facebook Test 5", "567890", "Conjunto de Anúncios 5", "Anúncio Criativo 5")
]

# Atualizar os registros
for i, fbclid in enumerate(fbclids):
    cursor.execute("""
    UPDATE fbclid_cache 
    SET campaign_name = ?, campaign_id = ?, adset_name = ?, ad_name = ?, last_updated = ?
    WHERE fbclid = ?
    """, (campaign_data[i][0], campaign_data[i][1], campaign_data[i][2], campaign_data[i][3], datetime.now().isoformat(), fbclid))

conn.commit()

# Verificar os dados atualizados
cursor.execute("SELECT fbclid, campaign_name, campaign_id FROM fbclid_cache WHERE campaign_name != 'Não encontrado' LIMIT 10")
rows = cursor.fetchall()
print("\nRegistros atualizados:")
for row in rows:
    print(f"FBCLID: {row[0]} - Campanha: {row[1]} - ID da Campanha: {row[2]}")

conn.close()
print("\nDados atualizados com sucesso!")
