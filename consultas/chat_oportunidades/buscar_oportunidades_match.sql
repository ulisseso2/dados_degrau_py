-- Busca oportunidades recentes para matching com chats do Octadesk
-- Usado pela página octadesk.py para vincular chat_id → oportunidade
SELECT 
    i.id as oportunidade_id,
    i.chat_id,
    LOWER(TRIM(i.email)) as email,
    i.phone as telefone,
    i.first_name as nome,
    i.created_at as criacao,
    CASE WHEN i.school_id = 1 THEN 'Degrau' ELSE 'Central' END as empresa,
    s.name as etapa,
    d.full_name as dono
FROM seducar.interesteds i
LEFT JOIN seducar.opportunity_steps s ON i.opportunity_step_id = s.id
LEFT JOIN seducar.users d ON i.owner_id = d.id
WHERE i.created_at >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
ORDER BY i.created_at DESC
