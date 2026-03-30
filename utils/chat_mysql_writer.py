from typing import Optional, Tuple
from sqlalchemy import text
import json
from conexao.mysql_connector import conectar_mysql_writer

_migration_nullable_done = False

def _ensure_opportunity_id_nullable(engine) -> None:
    """Garante que opportunity_id aceita NULL (executa apenas uma vez por processo)."""
    global _migration_nullable_done
    if _migration_nullable_done:
        return
    _migration_nullable_done = True  # Marcar antes para não repetir mesmo em falha
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE seducar.chat_ai_evaluations "
                "MODIFY COLUMN opportunity_id INT NULL"
            ))
    except Exception:
        pass  # Já nullable ou tabela ainda não existe

def salvar_avaliacao_chat(
    opportunity_id: Optional[int],
    chat_id: str,
    classification: str,
    classification_reason: str,
    ai_evaluation: dict,
    transcript: Optional[str] = None,
    lead_score: Optional[int] = None,
    vendor_score: Optional[int] = None,
    main_product: Optional[str] = None,
    # --- NOVAS COLUNAS OCTADESK ---
    octa_agent: Optional[str] = None,
    octa_channel: Optional[str] = None,
    octa_status: Optional[str] = None,
    octa_tags: Optional[str] = None,
    octa_group: Optional[str] = None,
    octa_origin: Optional[str] = None,
    octa_contact_name: Optional[str] = None,
    octa_contact_phone: Optional[str] = None,
    octa_bot_name: Optional[str] = None,
    octa_created_at: Optional[str] = None,
    octa_closed_at: Optional[str] = None,
    octa_survey_response: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Salva ou atualiza a avaliação de um chat na tabela chat_ai_evaluations, 
    junto com os metadados do Octadesk e o texto do chat original.
    """
    if not chat_id:
        return False, "chat_id ausente"

    # Sanitiza tipos numéricos
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

    lead_score = _sanitize(lead_score)
    vendor_score = _sanitize(vendor_score)

    engine = conectar_mysql_writer()
    if engine is None:
        return False, "engine MySQL não inicializado"

    _ensure_opportunity_id_nullable(engine)

    try:
        ai_evaluation_json = json.dumps(ai_evaluation, ensure_ascii=False) if ai_evaluation else None
    except Exception:
        ai_evaluation_json = None

    import uuid
    chat_uuid = str(uuid.uuid4())

    query = text(
        """
        INSERT INTO seducar.chat_ai_evaluations (
            uuid,
            opportunity_id,
            chat_id,
            classification,
            classification_reason,
            ai_evaluation,
            transcript,
            lead_score,
            vendor_score,
            main_product,
            octa_agent,
            octa_channel,
            octa_status,
            octa_tags,
            octa_group,
            octa_origin,
            octa_contact_name,
            octa_contact_phone,
            octa_bot_name,
            octa_created_at,
            octa_closed_at,
            octa_survey_response,
            created_at,
            updated_at
        ) VALUES (
            :uuid,
            :opportunity_id,
            :chat_id,
            :classification,
            :classification_reason,
            :ai_evaluation,
            :transcript,
            :lead_score,
            :vendor_score,
            :main_product,
            :octa_agent,
            :octa_channel,
            :octa_status,
            :octa_tags,
            :octa_group,
            :octa_origin,
            :octa_contact_name,
            :octa_contact_phone,
            :octa_bot_name,
            :octa_created_at,
            :octa_closed_at,
            :octa_survey_response,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        ON DUPLICATE KEY UPDATE
            opportunity_id = COALESCE(VALUES(opportunity_id), opportunity_id),
            classification = VALUES(classification),
            classification_reason = VALUES(classification_reason),
            ai_evaluation = VALUES(ai_evaluation),
            transcript = VALUES(transcript),
            lead_score = VALUES(lead_score),
            vendor_score = VALUES(vendor_score),
            main_product = VALUES(main_product),
            octa_agent = VALUES(octa_agent),
            octa_channel = VALUES(octa_channel),
            octa_status = VALUES(octa_status),
            octa_tags = VALUES(octa_tags),
            octa_group = VALUES(octa_group),
            octa_origin = VALUES(octa_origin),
            octa_contact_name = VALUES(octa_contact_name),
            octa_contact_phone = VALUES(octa_contact_phone),
            octa_bot_name = VALUES(octa_bot_name),
            octa_created_at = VALUES(octa_created_at),
            octa_closed_at = VALUES(octa_closed_at),
            octa_survey_response = VALUES(octa_survey_response),
            updated_at = CURRENT_TIMESTAMP
        """
    )
    
    try:
        with engine.begin() as conn:
            conn.execute(
                query,
                {
                    "uuid": chat_uuid,
                    "opportunity_id": opportunity_id,
                    "chat_id": chat_id,
                    "classification": classification,
                    "classification_reason": classification_reason,
                    "ai_evaluation": ai_evaluation_json,
                    "transcript": transcript,
                    "lead_score": lead_score,
                    "vendor_score": vendor_score,
                    "main_product": main_product,
                    "octa_agent": octa_agent,
                    "octa_channel": octa_channel,
                    "octa_status": octa_status,
                    "octa_tags": octa_tags,
                    "octa_group": octa_group,
                    "octa_origin": octa_origin,
                    "octa_contact_name": octa_contact_name,
                    "octa_contact_phone": octa_contact_phone,
                    "octa_bot_name": octa_bot_name,
                    "octa_created_at": octa_created_at,
                    "octa_closed_at": octa_closed_at,
                    "octa_survey_response": octa_survey_response
                }
            )
        return True, None
    except Exception as e:
        return False, str(e)
