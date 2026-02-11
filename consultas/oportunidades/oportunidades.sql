SELECT i.id as oportunidade,
c.id as id_cliente,
i.page_title as pagina, 
i.page_type as tipo_pagina, 
i.first_name as name, 
i.phone as telefone, 
i.email as email, 
CASE WHEN i.school_id = 1 THEN 'Degrau' ELSE 'Central' END as empresa, 
i.created_at as criacao, 
i.customer_id as cliente_id, 
i.utm_source as utm_source,
i.utm_medium as utm_medium,
i.utm_campaign as utm_campaign,
i.tiktok as tiktok,
i.gclid as gclid,
i.fbclid as fbclid,
i.email_marketing as email_marketing,
s.id as id_etapa,
s.name as etapa, 
s.sort as ordem_etapas,
d.full_name as dono, 
a.name as area,
o.name as origem, 
f.name as concurso, 
l.name as unidade_original,
m.name as modalidade_original, 
t.name as turno, 
u.full_name as criador,
h.name as h_ligar,
-- Unidade tratada com regras de negócio
CASE 
    WHEN (l.name IS NULL OR l.name = '') AND i.opportunity_modality_id IN (2, 5) THEN 'EAD'
    WHEN (l.name IS NULL OR l.name = '') AND i.opportunity_modality_id IN (3, 6) THEN 'LIVE'
    WHEN (l.name IS NULL OR l.name = '') AND i.opportunity_modality_id IN (1, 4) THEN 'Presencial/Indefinido'
    WHEN (l.name IS NULL OR l.name = '') AND i.opportunity_modality_id IS NULL THEN 'Indefinida'
    ELSE l.name
END as unidade,
-- Modalidade tratada com regras de negócio
CASE 
    WHEN (m.name IS NULL OR m.name = '') AND i.unit_id IN (22, 24) THEN 'Live'
    WHEN (m.name IS NULL OR m.name = '') AND i.unit_id IN (23, 26) THEN 'Online'
    WHEN (m.name IS NULL OR m.name = '') AND i.unit_id BETWEEN 1 AND 21 THEN 'Presencial'
    WHEN (m.name IS NULL OR m.name = '') AND i.unit_id IN (26, 27) THEN 'Smart'
    WHEN (m.name IS NULL OR m.name = '') AND i.unit_id IS NULL THEN 'Indefinida'
    ELSE m.name
END as modalidade
FROM seducar.interesteds i
left join seducar.opportunity_steps s on i.opportunity_step_id = s.id
left join seducar.users d on i.owner_id = d.id
left join seducar.areas a on i.area_id = a.id
left join seducar.opportunity_origins o on i.opportunity_origin_id = o.id
left join seducar.sales_force f on i.sales_force_id = f.id
left join seducar.opportunity_modalities m on i.opportunity_modality_id = m.id
left join seducar.shifts t on i.shift_id = t.id
left join seducar.units l on i.unit_id = l.id
left join seducar.users u on i.user_id = u.id
left join seducar.time_to_calls h on i.time_to_call_id = h.id
left join seducar.customers c on i.customer_id = c.id