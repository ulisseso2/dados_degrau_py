# gclid_db_central.py
import sqlite3
from pathlib import Path
from datetime import datetime
import streamlit as st

DB_FILE = "gclid_cache_central.db"  # Arquivo separado para a Central

def init_db():
    """Inicializa o banco de dados SQLite para a Central"""
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
    """Carrega todo o cache de GCLIDs do banco de dados da Central"""
    init_db()
    cache = {}
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT gclid, campaign_name FROM gclid_cache")
            for gclid, campaign_name in cursor.fetchall():
                cache[gclid] = campaign_name
    except Exception as e:
        st.warning(f"Erro ao carregar cache do banco de dados da Central: {e}")
    return cache

def save_gclid_cache_batch(gclid_campaign_map):
    """Salva um lote de GCLIDs no banco de dados da Central"""
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
        print(f"Erro ao salvar lote na Central: {e}")
        conn.rollback()
    finally:
        conn.close()

def update_gclid(gclid, campaign_name):
    """Atualiza um GCLID específico na Central"""
    save_gclid_cache_batch({gclid: campaign_name})

def get_campaign_for_gclid(gclid):
    """Obtém a campanha com prioridade para registros válidos na Central"""
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

def get_not_found_gclids():
    """Retorna todos os GCLIDs marcados como 'Não encontrado' na Central"""
    init_db()
    not_found_gclids = []
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT gclid, last_updated 
                FROM gclid_cache 
                WHERE campaign_name = 'Não encontrado'
                ORDER BY last_updated DESC
            """)
            not_found_gclids = cursor.fetchall()
    except Exception as e:
        print(f"Erro ao buscar GCLIDs não encontrados na Central: {e}")
    return not_found_gclids

def get_gclids_by_date_range(start_date, end_date):
    """Retorna GCLIDs não encontrados dentro de um período específico na Central"""
    init_db()
    gclids = []
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT gclid, last_updated 
                FROM gclid_cache 
                WHERE campaign_name = 'Não encontrado'
                AND date(last_updated) BETWEEN ? AND ?
                ORDER BY last_updated DESC
            """, (start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')))
            gclids = cursor.fetchall()
    except Exception as e:
        print(f"Erro ao buscar GCLIDs por período na Central: {e}")
    return gclids

def count_not_found_gclids():
    """Conta quantos GCLIDs estão marcados como 'Não encontrado' na Central"""
    init_db()
    count = 0
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM gclid_cache WHERE campaign_name = 'Não encontrado'")
            count = cursor.fetchone()[0]
    except Exception as e:
        print(f"Erro ao contar GCLIDs não encontrados na Central: {e}")
    return count

def has_valid_campaign_history(gclid):
    """
    Verifica se o GCLID já teve alguma campanha válida registrada no histórico (Central).
    Retorna a campanha válida mais recente, ou None se nunca foi encontrado.
    """
    init_db()
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            # Busca qualquer registro com campanha diferente de 'Não encontrado'
            cursor.execute("""
                SELECT campaign_name, last_updated 
                FROM gclid_cache 
                WHERE gclid = ? AND campaign_name != 'Não encontrado'
                ORDER BY last_updated DESC
                LIMIT 1
            """, (gclid,))
            result = cursor.fetchone()
            return result[0] if result else None
    except Exception as e:
        print(f"Erro ao buscar histórico do GCLID {gclid} na Central: {e}")
        return None

def restore_valid_gclids():
    """
    Restaura GCLIDs que foram encontrados anteriormente mas estão marcados como 'Não encontrado' (Central).
    Retorna um dicionário com os GCLIDs restaurados.
    """
    init_db()
    restored = {}
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            # Busca todos os GCLIDs marcados como 'Não encontrado'
            cursor.execute("""
                SELECT DISTINCT gclid 
                FROM gclid_cache 
                WHERE campaign_name = 'Não encontrado'
            """)
            not_found_gclids = [row[0] for row in cursor.fetchall()]
            
            # Para cada um, verifica se já teve campanha válida
            for gclid in not_found_gclids:
                valid_campaign = has_valid_campaign_history(gclid)
                if valid_campaign:
                    # Atualiza para a campanha válida
                    cursor.execute("""
                        UPDATE gclid_cache 
                        SET campaign_name = ?, last_updated = ?
                        WHERE gclid = ?
                    """, (valid_campaign, datetime.now().isoformat(), gclid))
                    restored[gclid] = valid_campaign
            
            conn.commit()
            if restored:
                print(f"✅ {len(restored)} GCLIDs restaurados com campanhas válidas (Central)")
    except Exception as e:
        print(f"Erro ao restaurar GCLIDs na Central: {e}")
    return restored
