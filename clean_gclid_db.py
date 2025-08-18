# clean_gclid_db.py
import sqlite3

def clean_duplicate_gclids():
    """Remove duplicados, mantendo registros com campanha encontrada"""
    conn = sqlite3.connect('gclid_cache.db')
    cursor = conn.cursor()
    
    # 1. Identificar GCLIDs duplicados
    cursor.execute("""
    SELECT gclid, COUNT(*) as count 
    FROM gclid_cache 
    GROUP BY gclid 
    HAVING count > 1
    """)
    duplicates = cursor.fetchall()
    
    if not duplicates:
        print("Nenhum GCLID duplicado encontrado.")
        return
    
    print(f"Encontrados {len(duplicates)} GCLIDs duplicados")
    
    # 2. Para cada duplicado, manter o registro com campanha válida
    for gclid, count in duplicates:
        # Encontra o registro preferido (com campanha válida)
        cursor.execute("""
        SELECT rowid 
        FROM gclid_cache 
        WHERE gclid = ? AND campaign_name != 'Não encontrado'
        LIMIT 1
        """, (gclid,))
        
        valid_row = cursor.fetchone()
        
        if valid_row:
            # Mantém este registro e deleta os outros
            cursor.execute("""
            DELETE FROM gclid_cache 
            WHERE gclid = ? AND rowid != ?
            """, (gclid, valid_row[0]))
        else:
            # Se não houver campanha válida, mantém apenas o mais recente
            cursor.execute("""
            DELETE FROM gclid_cache 
            WHERE gclid = ? AND rowid NOT IN (
                SELECT rowid 
                FROM gclid_cache 
                WHERE gclid = ? 
                ORDER BY last_updated DESC 
                LIMIT 1
            )
            """, (gclid, gclid))
        
        conn.commit()
    
    print("Limpeza de duplicados concluída com sucesso!")
    conn.close()

if __name__ == "__main__":
    clean_duplicate_gclids()