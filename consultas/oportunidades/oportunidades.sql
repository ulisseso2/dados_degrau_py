SELECT i.id as oportunidade, 
i.page_title as pagina, 
i.page_type as tipo_pagina, 
i.first_name as name, 
i.phone, 
i.email, 
if(i.school_id = 1, "Degrau", "Central") as empresa, 
i.created_at as criacao, 
i.customer_id as cliente_id, 
i.utm_source as utm, 
i.utm_campaign as campanha, 
s.name as etapa, 
s.sort as ordem_etapas,
d.full_name as dono, 
a.name as area,
o.name as origem, 
f.name as concurso, 
m.name as modalidade, 
t.name as turno, 
l.name as unidade, 
c.full_name as criador,
h.name as h_ligar
FROM seducar.interesteds i
left join seducar.opportunity_steps s on i.opportunity_step_id = s.id
left join seducar.users d on i.owner_id = d.id
left join seducar.areas a on i.area_id = a.id
left join seducar.opportunity_origins o on i.opportunity_origin_id = o.id
left join seducar.sales_force f on i.sales_force_id = f.id
left join seducar.opportunity_modalities m on i.opportunity_modality_id = m.id
left join seducar.shifts t on i.shift_id = t.id
left join seducar.units l on i.unit_id = l.id
left join seducar.users c on i.user_id = c.id
left join seducar.time_to_calls h on i.time_to_call_id = h.id