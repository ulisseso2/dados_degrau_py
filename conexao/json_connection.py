import os
import json
import logging
from typing import List, Dict, Any, Optional
import streamlit as st
from pathlib import Path

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class JsonDataConnection:
    """Classe para gerenciar acesso aos dados JSON locais"""
    
    def __init__(self):
        # Caminho para o arquivo JSON
        self.json_file_path = "/home/ulisses/dados_degrau_py/consultas/eduqc.subjectXtopics_total.json"
        self._data = None
        
    def load_data(self) -> bool:
        """Carrega os dados do arquivo JSON"""
        try:
            if not os.path.exists(self.json_file_path):
                logger.error(f"Arquivo JSON não encontrado: {self.json_file_path}")
                return False
                
            with open(self.json_file_path, 'r', encoding='utf-8') as file:
                self._data = json.load(file)
                
            logger.info(f"Dados carregados com sucesso: {len(self._data)} subjects")
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"Erro ao decodificar JSON: {e}")
            return False
        except Exception as e:
            logger.error(f"Erro inesperado ao carregar dados: {e}")
            return False
    
    def get_subjects_total(self) -> List[Dict[str, Any]]:
        """Busca todos os subjects do arquivo JSON (compatibilidade)"""
        try:
            if self._data is None:
                if not self.load_data():
                    return []
            
            # Retorna apenas nome e total para listagem
            subjects = []
            for item in self._data:
                subjects.append({
                    "name": item.get("name", ""),
                    "total": item.get("total", 0)
                })
            
            logger.info(f"Encontrados {len(subjects)} subjects")
            return subjects
            
        except Exception as e:
            logger.error(f"Erro ao buscar subjects: {e}")
            return []
    
    def get_subject_details(self, subject_name: str) -> Dict[str, Any]:
        """Busca detalhes de um subject específico"""
        try:
            if self._data is None:
                if not self.load_data():
                    return {}
            
            # Procura o subject específico
            for item in self._data:
                if item.get("name") == subject_name:
                    logger.info(f"Detalhes encontrados para subject: {subject_name}")
                    return item
            
            logger.warning(f"Subject não encontrado: {subject_name}")
            return {}
                
        except Exception as e:
            logger.error(f"Erro ao buscar detalhes do subject {subject_name}: {e}")
            return {}
    
    def get_all_subjects_with_topics(self) -> List[Dict[str, Any]]:
        """Busca todos os subjects com seus topics"""
        try:
            if self._data is None:
                if not self.load_data():
                    return []
            
            logger.info(f"Encontrados {len(self._data)} subjects com topics")
            return self._data
            
        except Exception as e:
            logger.error(f"Erro ao buscar subjects com topics: {e}")
            return []
    
    def health_check(self) -> Dict[str, Any]:
        """Verifica o status dos dados"""
        try:
            if not os.path.exists(self.json_file_path):
                return {"status": "error", "message": "Arquivo JSON não encontrado"}
            
            if self._data is None:
                if not self.load_data():
                    return {"status": "error", "message": "Falha ao carregar dados"}
            
            return {
                "status": "healthy",
                "data_source": "JSON Local",
                "document_count": len(self._data),
                "file_path": self.json_file_path
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def close(self):
        """Método de compatibilidade - não há conexão para fechar"""
        logger.info("Dados JSON - não há conexão para fechar")


# Funções com cache do Streamlit (mantendo compatibilidade)
@st.cache_data(ttl=600)  # Cache por 10 minutos
def get_cached_subjects():
    """Função cached para buscar subjects"""
    json_conn = JsonDataConnection()
    return json_conn.get_subjects_total()

@st.cache_data(ttl=600)  # Cache por 10 minutos  
def get_cached_subject_details(subject_name: str):
    """Função cached para buscar detalhes de um subject"""
    json_conn = JsonDataConnection()
    return json_conn.get_subject_details(subject_name)

@st.cache_data(ttl=600)  # Cache por 10 minutos
def get_cached_all_subjects_with_topics():
    """Função cached para buscar todos os subjects com topics"""
    json_conn = JsonDataConnection()
    return json_conn.get_all_subjects_with_topics()

# Funções de compatibilidade para manter interface consistente
def get_streamlit_cached_subjects():
    return get_cached_subjects()

def get_streamlit_cached_subject_details(subject_name: str):
    return get_cached_subject_details(subject_name)

def get_streamlit_cached_all_subjects_with_topics():
    return get_cached_all_subjects_with_topics()

def clear_cache():
    """Limpa o cache do Streamlit"""
    st.cache_data.clear()
    logger.info("Cache Streamlit limpo")

def get_mongodb_health():
    """Health check simples (compatibilidade)"""
    try:
        json_conn = JsonDataConnection()
        health = json_conn.health_check()
        
        return {
            'status': health.get('status', 'error'),
            'ping_time_ms': 'N/A (JSON Local)',
            'document_count': health.get('document_count', 0)
        }
    except Exception as e:
        return {
            'status': 'unhealthy',
            'error': str(e),
            'ping_time_ms': None,
            'document_count': 0
        }

def get_cache_stats():
    """Estatísticas do cache"""
    return {
        'cache_size': 'Gerenciado pelo Streamlit',
        'keys': ['subjects', 'subject_details', 'all_subjects'],
        'timestamps': {}
    }

def get_system_stats():
    """Estatísticas do sistema"""
    health = get_mongodb_health()
    return {
        'cache': {'cache_size': 'Streamlit', 'type': 'managed'},
        'data_source': health,
        'timestamp': 'Agora'
    }
