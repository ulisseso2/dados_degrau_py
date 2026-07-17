# -*- coding: utf-8 -*-
"""
crm_sync_writer.py — Retorno de interações ao CRM (Seducar)
===========================================================
Envia ao CRM a TRANSCRIÇÃO da interação (WhatsApp ou ligação) e a inteligência
sobre o LEAD, vinculadas à oportunidade, para que o próximo contato comercial
tenha o histórico completo.

POLÍTICA DE DADOS (decisão de negócio + jurídica — NÃO ALTERAR sem aprovação
da diretoria):
    ✔ VAI para o CRM: transcrição, canal, data do evento, agente (fato
      operacional), lead_score, classificação A-D, lead_disclaimer,
      recomendação de próximo passo e mensagem pronta.
    ✘ NUNCA vai para o CRM: nota do vendedor, vendedor_disclaimer, notas por
      categoria, pontos fortes/melhorias, erro mais caro, alertas de
      compliance. Avaliação de desempenho de colaborador é material de gestão
      interna; expô-la no CRM (visível a toda a operação) cria risco
      trabalhista. A whitelist abaixo é o mecanismo técnico dessa política:
      mesmo que o chamador passe o dict inteiro da avaliação, só os campos
      permitidos são gravados.

TABELA (DDL proposto — Gabriel/Ulisses ajustam nome/schema se necessário):

    CREATE TABLE IF NOT EXISTS crm_lead_interacoes (
        id              BIGINT AUTO_INCREMENT PRIMARY KEY,
        opportunity_id  BIGINT NOT NULL,
        school_id       TINYINT NULL,               -- 1=Degrau, 2=Central
        canal           VARCHAR(16) NOT NULL,       -- 'whatsapp' | 'ligacao'
        origem_id       VARCHAR(64) NOT NULL,       -- chat_id ou transcricao_id
        data_evento     DATETIME NULL,              -- data REAL da interação
        agente          VARCHAR(128) NULL,
        transcript      MEDIUMTEXT NULL,
        lead_score      TINYINT UNSIGNED NULL,
        lead_class      CHAR(1) NULL,               -- A|B|C|D
        lead_disclaimer TEXT NULL,
        proximo_passo   TEXT NULL,
        mensagem_pronta VARCHAR(512) NULL,
        regua_versao    VARCHAR(16) NULL,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_origem (canal, origem_id),
        KEY idx_opp (opportunity_id),
        KEY idx_data (data_evento)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

Ativação: env CRM_SYNC_ENABLED=1 (default desligado até o Gabriel expor a
timeline no Seducar). O writer usa a mesma conexão MySQL do projeto.
"""

import logging
import os
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Campos que PODEM ir ao CRM. Whitelist HARD-CODED — defesa em profundidade.
_WHITELIST_CAMPOS = (
    'opportunity_id', 'school_id', 'canal', 'origem_id', 'data_evento',
    'agente', 'transcript', 'lead_score', 'lead_class', 'lead_disclaimer',
    'proximo_passo', 'mensagem_pronta', 'regua_versao',
)

# Campos que JAMAIS podem ser gravados, mesmo se enviados por engano.
_BLACKLIST_HARD = (
    'vendor_score', 'nota_vendedor', 'evaluation_ia', 'vendedor_disclaimer',
    'notas_por_categoria', 'pontos_fortes', 'melhorias', 'erro_mais_caro',
    'alertas', 'avaliacao_vendedor',
)

_TABELA = os.getenv("CRM_SYNC_TABLE", "crm_lead_interacoes")


def crm_sync_habilitado() -> bool:
    return os.getenv("CRM_SYNC_ENABLED", "0").strip() in ("1", "true", "True")


def _get_conn():
    """
    Obtém conexão MySQL reutilizando a infra do projeto.
    Tenta utils.sql_loader.get_connection(); fallback para mysql.connector
    com as envs padrão do projeto (MYSQL_HOST/USER/PASSWORD/DATABASE).
    """
    try:
        from utils.sql_loader import get_connection  # type: ignore
        return get_connection()
    except Exception:
        pass
    import mysql.connector  # type: ignore
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        user=os.getenv("MYSQL_USER", ""),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", ""),
    )


def montar_payload_crm(
    opportunity_id: int,
    canal: str,
    origem_id: str,
    transcript: str,
    ai_evaluation: Optional[Dict] = None,
    data_evento: Optional[str] = None,
    agente: Optional[str] = None,
    school_id: Optional[int] = None,
) -> Dict:
    """
    Extrai da avaliação SOMENTE o que a política permite e monta o payload.
    ai_evaluation: JSON completo da avaliação (dict) — a extração aqui dentro
    garante que nada da avaliação do vendedor escape.
    """
    lead_score = None
    lead_class = None
    lead_disclaimer = None
    proximo_passo = None
    mensagem_pronta = None
    regua = None

    if isinstance(ai_evaluation, dict):
        al = ai_evaluation.get('avaliacao_lead') or {}
        if isinstance(al, dict):
            try:
                ls = al.get('lead_score_0_100')
                lead_score = int(ls) if ls is not None else None
            except (TypeError, ValueError):
                lead_score = None
            lc = al.get('classificacao')
            lead_class = lc if lc in ('A', 'B', 'C', 'D') else None
        ld = ai_evaluation.get('lead_disclaimer')
        lead_disclaimer = str(ld).strip() if ld else None
        rec = ai_evaluation.get('recomendacao_final') or {}
        if isinstance(rec, dict):
            pp = rec.get('melhor_proximo_passo') or rec.get('proximo_passo')
            proximo_passo = str(pp).strip() if pp else None
            mp = rec.get('mensagem_pronta') or rec.get('mensagem_pronta_para_enviar_agora')
            mensagem_pronta = str(mp).strip()[:512] if mp else None
        regua = ai_evaluation.get('regua_versao')

    return {
        'opportunity_id': int(opportunity_id),
        'school_id': school_id,
        'canal': canal,
        'origem_id': str(origem_id),
        'data_evento': data_evento,
        'agente': agente,
        'transcript': transcript,
        'lead_score': lead_score,
        'lead_class': lead_class,
        'lead_disclaimer': lead_disclaimer,
        'proximo_passo': proximo_passo,
        'mensagem_pronta': mensagem_pronta,
        'regua_versao': regua,
    }


def sincronizar_interacao_crm(payload: Dict) -> Tuple[bool, str]:
    """
    Grava a interação no CRM. Idempotente por (canal, origem_id):
    reenvio atualiza em vez de duplicar (ON DUPLICATE KEY UPDATE).
    Retorna (ok, mensagem).
    """
    if not crm_sync_habilitado():
        return False, 'CRM sync desabilitado (CRM_SYNC_ENABLED != 1)'

    if not payload.get('opportunity_id'):
        return False, 'Sem opportunity_id — interação não vinculável ao CRM'
    if payload.get('canal') not in ('whatsapp', 'ligacao'):
        return False, f"Canal inválido: {payload.get('canal')}"
    if not payload.get('origem_id'):
        return False, 'Sem origem_id'

    # Defesa em profundidade: derruba qualquer campo proibido ou desconhecido.
    for proibido in _BLACKLIST_HARD:
        payload.pop(proibido, None)
    limpo = {k: payload.get(k) for k in _WHITELIST_CAMPOS}

    cols = ', '.join(limpo.keys())
    marks = ', '.join(['%s'] * len(limpo))
    updates = ', '.join(
        f"{c}=VALUES({c})" for c in limpo.keys()
        if c not in ('canal', 'origem_id')
    )
    sql = (
        f"INSERT INTO {_TABELA} ({cols}) VALUES ({marks}) "
        f"ON DUPLICATE KEY UPDATE {updates}"
    )

    conn = None
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(sql, tuple(limpo.values()))
        conn.commit()
        cur.close()
        return True, 'ok'
    except Exception as e:
        logger.error("CRM sync falhou (%s/%s): %s",
                     payload.get('canal'), payload.get('origem_id'), e)
        return False, str(e)
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass
