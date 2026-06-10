SELECT
    i.id AS oportunidade_id,
    i.customer_id AS cliente_id,
    i.school_id AS school_id,
    CASE WHEN i.school_id = 1 THEN 'Degrau' ELSE 'Central' END as empresa, 
    i.created_at AS criacao,
    i.first_name AS nome_lead,
    i.phone AS telefone,
    i.email AS email,
    i.chat_id AS chat_id,
    i.utm_source AS utm_source,
    i.utm_medium AS utm_medium,
    i.utm_campaign AS utm_campaign,
    i.tiktok AS tiktok,
    i.gclid AS gclid,
    i.fbclid AS fbclid,
    i.email_marketing AS email_marketing,
    s.id AS id_etapa,
    s.name AS etapa,
    s.sort AS ordem_etapa,
    d.full_name AS dono,
    a.name AS area,
    o.name AS origem,
    i.sales_force_id AS sales_force_id,
    f.name AS sales_force,
    f.name AS concurso,
    l.name AS unidade_original,
    m.name AS modalidade_original,
    t.name AS turno,
    u.full_name AS criador,
    h.name AS h_ligar,
    CASE
        WHEN (l.name IS NULL OR l.name = '') AND i.opportunity_modality_id IN (2, 5) THEN 'EAD'
        WHEN (l.name IS NULL OR l.name = '') AND i.opportunity_modality_id IN (3, 6) THEN 'LIVE'
        WHEN (l.name IS NULL OR l.name = '') AND i.opportunity_modality_id IN (1, 4) THEN 'Presencial/Indefinido'
        WHEN (l.name IS NULL OR l.name = '') AND i.opportunity_modality_id IS NULL THEN 'Indefinida'
        ELSE l.name
    END AS unidade,
    CASE
        WHEN (m.name IS NULL OR m.name = '') AND i.unit_id IN (22, 24) THEN 'Live'
        WHEN (m.name IS NULL OR m.name = '') AND i.unit_id IN (23, 26) THEN 'Online'
        WHEN (m.name IS NULL OR m.name = '') AND i.unit_id BETWEEN 1 AND 21 THEN 'Presencial'
        WHEN (m.name IS NULL OR m.name = '') AND i.unit_id IN (26, 27) THEN 'Smart'
        WHEN (m.name IS NULL OR m.name = '') AND i.unit_id IS NULL THEN 'Indefinida'
        ELSE m.name
    END AS modalidade
FROM seducar.interesteds i
LEFT JOIN seducar.opportunity_steps s ON i.opportunity_step_id = s.id
LEFT JOIN seducar.users d ON i.owner_id = d.id
LEFT JOIN seducar.areas a ON i.area_id = a.id
LEFT JOIN seducar.opportunity_origins o ON i.opportunity_origin_id = o.id
LEFT JOIN seducar.sales_force f ON i.sales_force_id = f.id
LEFT JOIN seducar.opportunity_modalities m ON i.opportunity_modality_id = m.id
LEFT JOIN seducar.shifts t ON i.shift_id = t.id
LEFT JOIN seducar.units l ON i.unit_id = l.id
LEFT JOIN seducar.users u ON i.user_id = u.id
LEFT JOIN seducar.time_to_calls h ON i.time_to_call_id = h.id
WHERE i.origin != 'upsell'
    AND i.created_at >= '2024-06-01'