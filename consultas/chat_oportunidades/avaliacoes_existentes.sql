-- Retorna todos os chat_ids já avaliados via IA em chat_ai_evaluations
-- Usado pela página octadesk.py para marcar chats já processados
SELECT DISTINCT
    chat_id,
    classification,
    vendor_score,
    lead_score,
    updated_at
FROM seducar.chat_ai_evaluations
ORDER BY updated_at DESC
