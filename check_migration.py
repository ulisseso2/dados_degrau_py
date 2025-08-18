# check_migration.py
import sqlite3

DB_FILE = "gclid_cache.db"

def check_database():
    """Verifica os dados no banco SQLite"""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        
        # Conta o total de registros
        cursor.execute("SELECT COUNT(*) FROM gclid_cache")
        total = cursor.fetchone()[0]
        print(f"Total de registros no banco: {total}")
        
        # Conta campanhas encontradas vs não encontradas
        cursor.execute("""
        SELECT 
            SUM(CASE WHEN campaign_name = 'Não encontrado' THEN 1 ELSE 0 END) as not_found,
            SUM(CASE WHEN campaign_name != 'Não encontrado' THEN 1 ELSE 0 END) as found
        FROM gclid_cache
        """)
        not_found, found = cursor.fetchone()
        print(f"GCLIDs com campanha encontrada: {found}")
        print(f"GCLIDs não encontrados: {not_found}")
        
        # Mostra alguns exemplos
        print("\nAlguns exemplos de registros:")
        cursor.execute("SELECT gclid, campaign_name FROM gclid_cache LIMIT 5")
        for row in cursor.fetchall():
            print(f"GCLID: {row[0][:15]}... | Campanha: {row[1][:30]}...")

if __name__ == "__main__":
    check_database()