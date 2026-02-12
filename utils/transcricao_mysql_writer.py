from typing import Optional, Tuple
from sqlalchemy import text
import json
import pandas as pd
from uuid import uuid4
from conexao.mysql_connector import conectar_mysql_writer


def atualizar_avaliacao_transcricao(
    transcricao_id: Optional[int],
    insight_ia: str,
    evaluation_ia: Optional[int],
    uuid: Optional[str] = None,
    created_at: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    if not transcricao_id:
        return False, "transcricao_id ausente"

    engine = conectar_mysql_writer()
    if engine is None:
        return False, "engine MySQL não inicializado"

    def _join_lista(valores):
        if not isinstance(valores, list):
            return None
        itens = [str(v).strip() for v in valores if v and str(v).strip()]
        return "; ".join(itens) if itens else None

    def _extrair_campos(insight_json_str: str) -> dict:
        try:
            data = json.loads(insight_json_str) if insight_json_str else {}
        except (TypeError, json.JSONDecodeError):
            data = {}

        avaliacao_vendedor = data.get('avaliacao_vendedor', {}) or {}
        avaliacao_lead = data.get('avaliacao_lead', {}) or {}
        extracao = data.get('extracao', {}) or {}
        recomendacao = data.get('recomendacao_final', {}) or {}
        produto_principal = (recomendacao.get('produto_principal', {}) or {}).get('produto')

        strengths = [pf.get('ponto') for pf in avaliacao_vendedor.get('pontos_fortes', []) if isinstance(pf, dict)]
        improvements = [mf.get('melhoria') for mf in avaliacao_vendedor.get('melhorias', []) if isinstance(mf, dict)]
        most_expensive_mistake = (avaliacao_vendedor.get('erro_mais_caro', {}) or {}).get('descricao')

        return {
            "lead_score": avaliacao_lead.get('lead_score_0_100'),
            "lead_classification": avaliacao_lead.get('classificacao'),
            "strengths": _join_lista(strengths),
            "improvements": _join_lista(improvements),
            "most_expensive_mistake": most_expensive_mistake,
            "main_pain_points": _join_lista(extracao.get('dores_principais')),
            "restrictions": _join_lista(extracao.get('restricoes')),
            "contest_area": extracao.get('concurso_area'),
            "main_product": produto_principal,
        }

    campos = _extrair_campos(insight_ia)
    if not uuid:
        uuid = str(uuid4())
    if created_at is not None:
        try:
            created_at = pd.to_datetime(created_at).to_pydatetime()
        except Exception:
            created_at = None

    query = text(
        """
        INSERT INTO seducar.transcription_ai_summaries (
            transcription_id,
            uuid,
            created_at,
            updated_at,
            ai_insight,
            ai_evaluation,
            lead_score,
            lead_classification,
            strengths,
            improvements,
            most_expensive_mistake,
            main_pain_points,
            restrictions,
            contest_area,
            main_product
        ) VALUES (
            :transcricao_id,
            :uuid,
            COALESCE(:created_at, CURRENT_TIMESTAMP),
            COALESCE(:created_at, CURRENT_TIMESTAMP),
            :ai_insight,
            :ai_evaluation,
            :lead_score,
            :lead_classification,
            :strengths,
            :improvements,
            :most_expensive_mistake,
            :main_pain_points,
            :restrictions,
            :contest_area,
            :main_product
        )
        ON DUPLICATE KEY UPDATE
            ai_insight = VALUES(ai_insight),
            ai_evaluation = VALUES(ai_evaluation),
            lead_score = VALUES(lead_score),
            lead_classification = VALUES(lead_classification),
            strengths = VALUES(strengths),
            improvements = VALUES(improvements),
            most_expensive_mistake = VALUES(most_expensive_mistake),
            main_pain_points = VALUES(main_pain_points),
            restrictions = VALUES(restrictions),
            contest_area = VALUES(contest_area),
            main_product = VALUES(main_product),
            created_at = COALESCE(VALUES(created_at), created_at),
            updated_at = CURRENT_TIMESTAMP
        """
    )

    try:
        with engine.begin() as conn:
            result = conn.execute(
                query,
                {
                    "ai_insight": insight_ia,
                    "ai_evaluation": evaluation_ia,
                    "transcricao_id": transcricao_id,
                    "uuid": uuid,
                    "created_at": created_at,
                    **campos,
                },
            )
        if result.rowcount > 0:
            return True, None
        return False, "nenhuma linha atualizada"
    except Exception as e:
        return False, str(e)
