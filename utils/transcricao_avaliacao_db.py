"""
Gerenciamento de banco SQLite local para avaliações de transcrições
"""
import sqlite3
import os
import hashlib
from datetime import datetime
from typing import Optional, Dict, List
import pandas as pd

class TranscricaoAvaliacaoDB:
    def __init__(self, db_path: str = "transcricoes_avaliacoes.db"):
        """Inicializa conexão com SQLite"""
        self.db_path = db_path
        self._criar_tabela()
    
    def _criar_tabela(self):
        """Cria tabela de avaliações se não existir"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS avaliacoes_transcricoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                oportunidade_id INTEGER,
                transcricao_hash TEXT,
                transcricao TEXT,
                ramal TEXT,
                origem_ramal TEXT,
                nome_lead TEXT,
                telefone_lead TEXT,
                
                -- Avaliação completa (JSON estruturado)
                avaliacao_completa TEXT,
                
                -- Scores principais
                nota_vendedor INTEGER,
                lead_score INTEGER,
                lead_classificacao TEXT,
                concurso_area TEXT,
                produto_recomendado TEXT,
                
                -- Controle
                comentarios_usuario TEXT,
                avaliado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TIMESTAMP,
                status TEXT DEFAULT 'pendente',
                sincronizado INTEGER DEFAULT 0,
                tokens_usados INTEGER,
                
                UNIQUE(transcricao_hash)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def salvar_avaliacao(self, avaliacao: Dict) -> bool:
        """
        Salva ou atualiza avaliação
        
        Args:
            avaliacao: Dicionário com dados da avaliação
            
        Returns:
            True se sucesso, False caso contrário
        """
        try:
            # Gera hash da transcrição como identificador único alternativo
            transcricao = avaliacao.get('transcricao', '')
            if not transcricao:
                print("Erro: Transcrição vazia")
                return False
            
            transcricao_hash = hashlib.md5(transcricao.encode()).hexdigest()
            avaliacao['transcricao_hash'] = transcricao_hash
            
            # oportunidade_id é opcional agora
            oportunidade_id = avaliacao.get('oportunidade_id')
            if oportunidade_id is not None and pd.notna(oportunidade_id):
                oportunidade_id = int(oportunidade_id)
            else:
                oportunidade_id = None
            
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()
            
            # Verifica se já existe (por hash da transcrição)
            cursor.execute(
                "SELECT id FROM avaliacoes_transcricoes WHERE transcricao_hash = ?",
                (transcricao_hash,)
            )
            
            existe = cursor.fetchone()
            
            # Debug
            print(f"Salvando avaliação - Hash: {transcricao_hash}, Já existe: {existe is not None}")
            
            if existe:
                # Atualiza
                cursor.execute("""
                    UPDATE avaliacoes_transcricoes 
                    SET 
                        oportunidade_id = ?,
                        avaliacao_completa = ?,
                        nota_vendedor = ?,
                        lead_score = ?,
                        lead_classificacao = ?,
                        concurso_area = ?,
                        produto_recomendado = ?,
                        tokens_usados = ?,
                        comentarios_usuario = ?,
                        atualizado_em = CURRENT_TIMESTAMP,
                        status = ?
                    WHERE transcricao_hash = ?
                """, (
                    oportunidade_id,
                    avaliacao.get('avaliacao_completa'),
                    avaliacao.get('nota_vendedor'),
                    avaliacao.get('lead_score'),
                    avaliacao.get('lead_classificacao'),
                    avaliacao.get('concurso_area'),
                    avaliacao.get('produto_recomendado'),
                    avaliacao.get('tokens_usados'),
                    avaliacao.get('comentarios_usuario'),
                    avaliacao.get('status', 'avaliado'),
                    transcricao_hash
                ))
            else:
                # Insere
                cursor.execute("""
                    INSERT INTO avaliacoes_transcricoes (
                        oportunidade_id, transcricao_hash, transcricao, ramal, origem_ramal,
                        nome_lead, telefone_lead,
                        avaliacao_completa, nota_vendedor, lead_score,
                        lead_classificacao, concurso_area, produto_recomendado,
                        tokens_usados, comentarios_usuario, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    oportunidade_id,
                    transcricao_hash,
                    avaliacao.get('transcricao'),
                    avaliacao.get('ramal'),
                    avaliacao.get('origem_ramal'),
                    avaliacao.get('nome_lead'),
                    avaliacao.get('telefone_lead'),
                    avaliacao.get('avaliacao_completa'),
                    avaliacao.get('nota_vendedor'),
                    avaliacao.get('lead_score'),
                    avaliacao.get('lead_classificacao'),
                    avaliacao.get('concurso_area'),
                    avaliacao.get('produto_recomendado'),
                    avaliacao.get('tokens_usados'),
                    avaliacao.get('comentarios_usuario'),
                    avaliacao.get('status', 'avaliado')
                ))
            
            conn.commit()
            print(f"✓ Avaliação salva com sucesso - Hash: {transcricao_hash}")
            conn.close()
            return True
            
        except Exception as e:
            print(f"Erro ao salvar avaliação: {e}")
            return False
    
    def buscar_avaliacao(self, oportunidade_id: int) -> Optional[Dict]:
        """Busca avaliação por ID da oportunidade"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM avaliacoes_transcricoes 
                WHERE oportunidade_id = ?
            """, (oportunidade_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                colunas = [desc[0] for desc in cursor.description]
                return dict(zip(colunas, row))
            
            return None
            
        except Exception as e:
            print(f"Erro ao buscar avaliação: {e}")
            return None
    
    def listar_avaliacoes(self, status: Optional[str] = None) -> pd.DataFrame:
        """Lista todas avaliações, opcionalmente filtradas por status"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            
            if status:
                query = "SELECT * FROM avaliacoes_transcricoes WHERE status = ? ORDER BY avaliado_em DESC"
                df = pd.read_sql_query(query, conn, params=(status,))
            else:
                query = "SELECT * FROM avaliacoes_transcricoes ORDER BY avaliado_em DESC"
                df = pd.read_sql_query(query, conn)
            
            conn.close()
            return df
            
        except Exception as e:
            print(f"Erro ao listar avaliações: {e}")
            return pd.DataFrame()
    
    def marcar_sincronizado(self, oportunidade_id: int) -> bool:
        """Marca avaliação como sincronizada com banco principal"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE avaliacoes_transcricoes 
                SET sincronizado = 1 
                WHERE oportunidade_id = ?
            """, (oportunidade_id,))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"Erro ao marcar como sincronizado: {e}")
            return False
    
    def exportar_nao_sincronizados(self) -> pd.DataFrame:
        """Exporta registros não sincronizados para envio ao banco principal"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            query = """
                SELECT oportunidade_id, classificacao_ligacao, qualidade_atendimento,
                       pontos_positivos, pontos_melhoria, notas_ia,
                       spin_situacao, spin_problema, spin_implicacao, spin_necessidade
                FROM avaliacoes_transcricoes 
                WHERE sincronizado = 0 AND status = 'avaliado'
            """
            df = pd.read_sql_query(query, conn)
            conn.close()
            return df
            
        except Exception as e:
            print(f"Erro ao exportar não sincronizados: {e}")
            return pd.DataFrame()
    
    def estatisticas(self) -> Dict:
        """Retorna estatísticas das avaliações"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()
            
            stats = {}
            
            # Total
            cursor.execute("SELECT COUNT(*) FROM avaliacoes_transcricoes")
            stats['total'] = cursor.fetchone()[0]
            
            # Por status
            cursor.execute("""
                SELECT status, COUNT(*) 
                FROM avaliacoes_transcricoes 
                GROUP BY status
            """)
            stats['por_status'] = dict(cursor.fetchall())
            
            # Sincronizados
            cursor.execute("SELECT COUNT(*) FROM avaliacoes_transcricoes WHERE sincronizado = 1")
            stats['sincronizados'] = cursor.fetchone()[0]
            
            # Pendentes
            cursor.execute("SELECT COUNT(*) FROM avaliacoes_transcricoes WHERE sincronizado = 0")
            stats['pendentes_sincronizacao'] = cursor.fetchone()[0]
            
            conn.close()
            return stats
            
        except Exception as e:
            print(f"Erro ao obter estatísticas: {e}")
            return {}
