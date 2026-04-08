SELECT 
    i.id as oportunidade_id,
    c.chat_id,
    c.octa_created_at as data_chat,
    c.created_at as data_criacao_sistema,
    CASE 
        WHEN i.school_id = 1 THEN 'Degrau' 
        WHEN i.school_id IS NOT NULL THEN 'Central'
        ELSE 'Degrau'
    END as empresa,
    COALESCE(c.octa_agent, u.full_name) as agente,
    o.name as origem,
    CASE WHEN c.ai_evaluation IS NOT NULL AND c.ai_evaluation != '' THEN 1 ELSE 0 END as avaliada,
    CASE WHEN c.classification = 'venda' THEN 1 ELSE 0 END as avaliavel,
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
FROM seducar.chat_ai_evaluations c
LEFT JOIN seducar.interesteds i ON c.chat_id = i.chat_id
LEFT JOIN seducar.users u ON i.owner_id = u.id
LEFT JOIN seducar.opportunity_origins o ON i.opportunity_origin_id = o.id
ORDER BY c.octa_created_at DESC
