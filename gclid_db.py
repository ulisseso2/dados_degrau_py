# gclid_db.py
import sqlite3
from pathlib import Path
from datetime import datetime
import streamlit as st

DB_FILE = "gclid_cache.db"

def init_db():
    """Inicializa o banco de dados SQLite"""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS gclid_cache (
            gclid TEXT PRIMARY KEY,
            campaign_name TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.commit()

def load_gclid_cache():
    """Carrega todo o cache de GCLIDs do banco de dados"""
    init_db()
    cache = {}
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT gclid, campaign_name FROM gclid_cache")
            for gclid, campaign_name in cursor.fetchall():
                cache[gclid] = campaign_name
    except Exception as e:
        st.warning(f"Erro ao carregar cache do banco de dados: {e}")
    return cache

def save_gclid_cache_batch(gclid_campaign_map):
    """Salva um lote de GCLIDs no banco de dados"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        for gclid, campaign_name in gclid_campaign_map.items():
            cursor.execute("""
            INSERT OR REPLACE INTO gclid_cache (gclid, campaign_name, last_updated)
            VALUES (?, ?, ?)
            """, (gclid, campaign_name, datetime.now().isoformat()))
        conn.commit()
    except Exception as e:
        print(f"Erro ao salvar lote: {e}")
        conn.rollback()
    finally:
        conn.close()

def update_gclid(gclid, campaign_name):
    """Atualiza um GCLID específico"""
    save_gclid_cache_batch({gclid: campaign_name})

def get_campaign_for_gclid(gclid):
    """Obtém a campanha com prioridade para registros válidos"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Primeiro tenta encontrar um registro com campanha válida
    cursor.execute("""
    SELECT campaign_name 
    FROM gclid_cache 
    WHERE gclid = ? AND campaign_name != 'Não encontrado'
    LIMIT 1
    """, (gclid,))
    
    result = cursor.fetchone()
    
    if not result:
        # Se não encontrar, pega qualquer registro (incluindo 'Não encontrado')
        cursor.execute("""
        SELECT campaign_name 
        FROM gclid_cache 
        WHERE gclid = ?
        LIMIT 1
        """, (gclid,))
        result = cursor.fetchone()
    
    conn.close()
    return result[0] if result else None