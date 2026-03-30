SELECT 
    i.id as oportunidade_id,
    i.chat_id,
    i.created_at as data_chat,
    c.octa_created_at as data_octa,
    i.created_at as data_criacao_sistema,
    CASE WHEN i.school_id = 1 THEN 'Degrau' ELSE 'Central' END as empresa,
    COALESCE(c.octa_agent, u.full_name) as agente,
    o.name as origem,
    CASE WHEN c.uuid IS NOT NULL THEN 1 ELSE 0 END as avaliada,
    1 as avaliavel,
    c.vendor_score as evaluation_ia,
    c.lead_score,
    c.main_product as produto_recomendado,
    c.classification as classificacao_triagem,
    c.classification_reason as motivo_triagem,
    c.transcript,
    c.ai_evaluation,
    c.octa_origin,
    c.octa_group,
    c.octa_status,
    c.octa_contact_name,
    c.octa_contact_phone
FROM seducar.interesteds i
LEFT JOIN seducar.chat_ai_evaluations c ON i.chat_id = c.chat_id
LEFT JOIN seducar.users u ON i.owner_id = u.id
LEFT JOIN seducar.opportunity_origins o ON i.opportunity_origin_id = o.id
WHERE i.chat_id IS NOT NULL 
  AND i.chat_id != ''
ORDER BY i.created_at DESC
