from typing import Optional, Tuple
from sqlalchemy import text
import json
from uuid import uuid4
from conexao.mysql_connector import conectar_mysql_writer


def atualizar_avaliacao_transcricao(
    transcricao_id: Optional[int],
    insight_ia: str,
    evaluation_ia: Optional[int],
    uuid: Optional[str] = None,
    created_at: Optional[str] = None,  # mantido por compatibilidade, não utilizado
    agent: Optional[str] = None,
    duration: Optional[str] = None,
    phone: Optional[str] = None,
    type_: Optional[str] = None,
    vendedor_disclaimer: Optional[str] = None,
    lead_disclaimer: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    if not transcricao_id:
        return False, "transcricao_id ausente"

    # Sanitiza tipos numpy/pandas: NaN e inf viram None
    import math
    def _sanitize(v):
        if v is None:
            return None
        try:
            if math.isnan(float(v)) or math.isinf(float(v)):
                return None
        except (TypeError, ValueError):
            pass
        return v

    duration = _sanitize(duration)
    evaluation_ia = _sanitize(evaluation_ia)

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
        _produto_raw = recomendacao.get('produto_principal')
        if isinstance(_produto_raw, dict):
            produto_principal = _produto_raw.get('produto')
        elif isinstance(_produto_raw, str) and _produto_raw:
            produto_principal = _produto_raw
        else:
            produto_principal = None

        strengths_raw = avaliacao_vendedor.get('pontos_fortes', [])
        improvements_raw = avaliacao_vendedor.get('melhorias', [])

        def _formatar_item_forte(item):
            if not isinstance(item, dict):
                return None
            cat = item.get('categoria', '')
            ponto = item.get('ponto', '').strip()
            return f"[{cat}] {ponto}" if cat else ponto

        def _formatar_item_melhoria(item):
            if not isinstance(item, dict):
                return None
            cat = item.get('categoria', '')
            melhoria = item.get('melhoria', '').strip()
            return f"[{cat}] {melhoria}" if cat else melhoria

        strengths = [s for s in (_formatar_item_forte(i) for i in strengths_raw) if s]
        improvements = [s for s in (_formatar_item_melhoria(i) for i in improvements_raw) if s]

        erro_mais_caro = avaliacao_vendedor.get('erro_mais_caro', {}) or {}
        cat_erro = erro_mais_caro.get('categoria', '')
        desc_erro = (erro_mais_caro.get('descricao', '') or '').strip()
        most_expensive_mistake = f"[{cat_erro}] {desc_erro}" if (cat_erro and desc_erro) else desc_erro or None

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

    # 1) Upsert em transcription_ai_summaries
    # created_at e updated_at sempre refletem o momento da avaliação (CURRENT_TIMESTAMP),
    # não a data da transcrição original.
    query_summary = text(
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
            main_product,
            vendedor_disclaimer,
            lead_disclaimer
        ) VALUES (
            :transcricao_id,
            :uuid,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP,
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
            :main_product,
            :vendedor_disclaimer,
            :lead_disclaimer
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
            vendedor_disclaimer = VALUES(vendedor_disclaimer),
            lead_disclaimer = VALUES(lead_disclaimer),
            updated_at = CURRENT_TIMESTAMP
        """
    )

    # 2) Atualiza colunas de avaliação na tabela principal de transcrições
    query_transcricao = text(
        """
        UPDATE seducar.opportunity_transcripts
        SET
            insight_ia    = :ai_insight,
            evaluation_ia = :ai_evaluation,
            agent         = COALESCE(:agent, agent),
            duration      = COALESCE(:duration, duration),
            phone         = COALESCE(:phone, phone),
            type          = COALESCE(:type_, type)
        WHERE id = :transcricao_id
        """
    )

    try:
        with engine.begin() as conn:
            conn.execute(
                query_summary,
                {
                    "ai_insight": insight_ia,
                    "ai_evaluation": evaluation_ia,
                    "transcricao_id": transcricao_id,
                    "uuid": uuid,
                    **campos,
                    "vendedor_disclaimer": vendedor_disclaimer,
                    "lead_disclaimer": lead_disclaimer,
                },
            )
            conn.execute(
                query_transcricao,
                {
                    "ai_insight": insight_ia,
                    "ai_evaluation": evaluation_ia,
                    "transcricao_id": transcricao_id,
                    "agent": agent,
                    "duration": duration,
                    "phone": phone,
                    "type_": type_,
                },
            )
        return True, None
    except Exception as e:
        return False, str(e)
