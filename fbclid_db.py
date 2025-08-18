# fbclid_db.py
import sqlite3
from pathlib import Path
from datetime import datetime
import streamlit as st

DB_FILE = "fbclid_cache.db"

def init_db():
    """Inicializa o banco de dados SQLite para FBclids"""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
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
        conn.commit()

def load_fbclid_cache(empresa="degrau"):
    """Carrega todo o cache de FBclids do banco de dados para uma empresa específica"""
    init_db()
    cache = {}
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT fbclid, campaign_name FROM fbclid_cache WHERE empresa = ?", (empresa.lower(),))
            for fbclid, campaign_name in cursor.fetchall():
                cache[fbclid] = campaign_name
    except Exception as e:
        st.warning(f"Erro ao carregar cache de FBclids do banco de dados: {e}")
    return cache

def save_fbclid_cache_batch(fbclid_campaign_map, empresa="degrau"):
    """Salva um lote de FBclids no banco de dados"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        for fbclid, campaign_data in fbclid_campaign_map.items():
            # Se campaign_data for uma string, é apenas o nome da campanha
            if isinstance(campaign_data, str):
                campaign_name = campaign_data
                campaign_id = None
                adset_name = None
                ad_name = None
            # Se for um dicionário, contém informações detalhadas
            elif isinstance(campaign_data, dict):
                campaign_name = campaign_data.get('campaign_name')
                campaign_id = campaign_data.get('campaign_id')
                adset_name = campaign_data.get('adset_name')
                ad_name = campaign_data.get('ad_name')
            else:
                continue
            
            cursor.execute("""
            INSERT OR REPLACE INTO fbclid_cache 
            (fbclid, campaign_name, campaign_id, adset_name, ad_name, empresa, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (fbclid, campaign_name, campaign_id, adset_name, ad_name, empresa.lower(), datetime.now().isoformat()))
        conn.commit()
    except Exception as e:
        print(f"Erro ao salvar lote de FBclids: {e}")
        conn.rollback()
    finally:
        conn.close()

def update_fbclid(fbclid, campaign_data, empresa="degrau"):
    """Atualiza um FBCLID específico"""
    save_fbclid_cache_batch({fbclid: campaign_data}, empresa)

def get_campaign_for_fbclid(fbclid, empresa="degrau"):
    """Obtém a campanha com prioridade para registros válidos"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Primeiro tenta encontrar um registro com campanha válida
    cursor.execute("""
    SELECT campaign_name, campaign_id, adset_name, ad_name
    FROM fbclid_cache 
    WHERE fbclid = ? AND empresa = ? AND campaign_name != 'Não encontrado'
    LIMIT 1
    """, (fbclid, empresa.lower()))
    
    result = cursor.fetchone()
    
    if not result:
        # Se não encontrar, pega qualquer registro (incluindo 'Não encontrado')
        cursor.execute("""
        SELECT campaign_name, campaign_id, adset_name, ad_name
        FROM fbclid_cache 
        WHERE fbclid = ? AND empresa = ?
        LIMIT 1
        """, (fbclid, empresa.lower()))
        result = cursor.fetchone()
    
    conn.close()
    
    if result:
        return {
            'campaign_name': result[0],
            'campaign_id': result[1],
            'adset_name': result[2],
            'ad_name': result[3]
        }
    return None

def get_all_fbclid_data(empresa="degrau"):
    """Retorna todos os dados de FBclids para uma empresa"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT fbclid, campaign_name, campaign_id, adset_name, ad_name, last_updated
    FROM fbclid_cache 
    WHERE empresa = ?
    """, (empresa.lower(),))
    
    result = cursor.fetchall()
    conn.close()
    
    return [{
        'fbclid': row[0],
        'campaign_name': row[1],
        'campaign_id': row[2],
        'adset_name': row[3],
        'ad_name': row[4],
        'last_updated': row[5]
    } for row in result]
