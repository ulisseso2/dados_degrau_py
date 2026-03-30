SELECT 
    i.id as oportunidade_id,
    i.first_name as nome,
    i.phone as telefone,
    i.email as email,
    i.chat_id as chat_id,
    i.created_at as criacao,
    CASE WHEN i.school_id = 1 THEN 'Degrau' ELSE 'Central' END as empresa,
    s.name as etapa,
    d.full_name as dono,
    a.name as area,
    o.name as origem,
    'Não' as analisado,
    NULL as classificacao_ia,
    NULL as score_ia
FROM seducar.interesteds i
LEFT JOIN seducar.opportunity_steps s ON i.opportunity_step_id = s.id
LEFT JOIN seducar.users d ON i.owner_id = d.id
LEFT JOIN seducar.areas a ON i.area_id = a.id
LEFT JOIN seducar.opportunity_origins o ON i.opportunity_origin_id = o.id
WHERE i.chat_id IS NOT NULL 
  AND i.chat_id != ''
ORDER BY i.created_at DESC
