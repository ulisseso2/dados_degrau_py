"""
Script para migrar GCLIDs da Central do banco original para o banco específico da Central.
Este script deve ser executado uma única vez durante a configuração.
"""
import sqlite3
import pandas as pd
from datetime import datetime

# Configurações
ORIGEM_DB = "gclid_cache.db"
DESTINO_DB = "gclid_cache_central.db"

def migrar_gclids_central():
    print(f"Iniciando migração de GCLIDs da Central do {ORIGEM_DB} para {DESTINO_DB}...")
    
    # Conectar aos bancos
    origem_conn = sqlite3.connect(ORIGEM_DB)
    destino_conn = sqlite3.connect(DESTINO_DB)
    
    try:
        # Criar tabela no banco de destino
        destino_conn.execute("""
        CREATE TABLE IF NOT EXISTS gclid_cache (
            gclid TEXT PRIMARY KEY,
            campaign_name TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Ler os dados do banco de origem
        df = pd.read_sql_query("SELECT * FROM gclid_cache", origem_conn)
        
        # Filtrar apenas para campanhas da Central (se puder identificar)
        # Se não houver como identificar, você pode ajustar esta lógica ou remover o filtro
        # Exemplo de filtro:
        # df_central = df[df['campaign_name'].str.contains('Central', case=False, na=False)]
        
        # Por enquanto, vamos assumir que não há como identificar e copiar todos
        df_central = df
        
        # Verificar se há dados para migrar
        if df_central.empty:
            print("Nenhum GCLID encontrado para migração.")
            return
            
        # Inserir no banco de destino
        for _, row in df_central.iterrows():
            destino_conn.execute("""
            INSERT OR REPLACE INTO gclid_cache (gclid, campaign_name, last_updated)
            VALUES (?, ?, ?)
            """, (row['gclid'], row['campaign_name'], row['last_updated'] or datetime.now().isoformat()))
        
        destino_conn.commit()
        print(f"Migração concluída! {len(df_central)} GCLIDs migrados.")
        
    except Exception as e:
        print(f"Erro durante a migração: {e}")
    
    finally:
        origem_conn.close()
        destino_conn.close()

if __name__ == "__main__":
    migrar_gclids_central()
