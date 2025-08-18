# fbclid_utils.py
"""
Utilitários para trabalhar com FBclids, incluindo funcionalidades
para validação, formatação e manipulação de dados.
"""

import re
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from fbclid_db import load_fbclid_cache, save_fbclid_cache_batch

def is_valid_fbclid(fbclid):
    """
    Verifica se um FBCLID está em um formato válido.
    Os FBclids do Facebook geralmente seguem um padrão específico.
    """
    if not isinstance(fbclid, str):
        return False
    
    # FBclids geralmente começam com 'fb.' ou 'IwAR'
    fbclid_pattern = r'^(fb\.|IwAR)[A-Za-z0-9_-]+$'
    return bool(re.match(fbclid_pattern, fbclid))

def extract_fbclids_from_url(url):
    """
    Extrai FBclids de uma URL.
    """
    if not url:
        return None
    
    # Padrão para extrair fbclid de URLs
    fbclid_pattern = r'fbclid=([^&]+)'
    match = re.search(fbclid_pattern, url)
    
    if match:
        return match.group(1)
    return None

def format_fbclid_display(fbclid, max_length=20):
    """
    Formata FBclids para exibição na interface, truncando se necessário.
    """
    if not fbclid or not isinstance(fbclid, str):
        return "N/A"
    
    if len(fbclid) > max_length:
        return f"{fbclid[:max_length]}..."
    return fbclid

def enrich_data_with_fbclid_info(df, fbclid_column='fbclid', empresa='degrau'):
    """
    Enriquece um DataFrame com informações de campanha para FBclids.
    
    Args:
        df: DataFrame com os dados
        fbclid_column: Nome da coluna que contém os FBclids
        empresa: Nome da empresa para filtrar os dados
        
    Returns:
        DataFrame enriquecido com informações de campanha
    """
    if fbclid_column not in df.columns or df.empty:
        return df
    
    # Carrega o cache de FBclids
    fbclid_cache = load_fbclid_cache(empresa)
    
    # Função para buscar dados da campanha do cache
    def get_campaign_info(fbclid):
        if not fbclid or pd.isna(fbclid):
            return "Sem FBCLID"
        return fbclid_cache.get(fbclid, "Não consultado")
    
    # Adiciona coluna com informações da campanha
    df['campanha_facebook'] = df[fbclid_column].apply(get_campaign_info)
    
    return df

def create_fbclid_dashboard(df, fbclid_column='fbclid', empresa='degrau'):
    """
    Cria um dashboard para análise de FBclids.
    
    Args:
        df: DataFrame com os dados
        fbclid_column: Nome da coluna que contém os FBclids
        empresa: Nome da empresa para filtrar os dados
    """
    st.subheader("Análise de FBclids")
    
    if df.empty or fbclid_column not in df.columns:
        st.warning("Não há dados de FBclids para análise.")
        return
    
    # Filtra apenas registros com FBclid
    df_fbclid = df[df[fbclid_column].notna() & (df[fbclid_column] != '')].copy()
    
    if df_fbclid.empty:
        st.info("Não foram encontrados FBclids no conjunto de dados.")
        return
    
    # Estatísticas básicas
    total_registros = len(df)
    registros_com_fbclid = len(df_fbclid)
    porcentagem = (registros_com_fbclid / total_registros) * 100 if total_registros > 0 else 0
    
    col1, col2 = st.columns(2)
    col1.metric("Total de Registros", f"{total_registros:,}".replace(",", "."))
    col2.metric("Registros com FBCLID", f"{registros_com_fbclid:,} ({porcentagem:.1f}%)".replace(",", "."))
    
    # Enriquece os dados com informações de campanha
    df_enriquecido = enrich_data_with_fbclid_info(df_fbclid, fbclid_column, empresa)
    
    # Mostra tabela de FBclids
    st.dataframe(df_enriquecido, use_container_width=True)
    
    return df_enriquecido
