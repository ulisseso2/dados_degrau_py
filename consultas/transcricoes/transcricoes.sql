SELECT
ot.id as transcricao_id,
ot.created_at as data_trancricao,
ot.transcript as transcricao,
ot.opportunity_id as oportunidade,
ot.original_transcript as json_completo,
ot.insight_ia as insight_ia,
ot.evaluation_ia as evaluation_ia,
ot.date as data_ligacao,
c.full_name as nome_lead,
c.cellphone as telefone_lead,
c.cpf as cpf_lead,
os.name as etapa,
oo.name as origem,
om.name as modalidade,

CASE
	WHEN ot.school_id = 1 THEN 'Degrau' 
    ELSE 'Central' 
END as empresa,
ot.time as hora_ligacao

FROM seducar.opportunity_transcripts ot

LEFT JOIN seducar.interesteds i on ot.opportunity_id = i.id
LEFT JOIN seducar.customers c on i.customer_id = c.id
LEFT join seducar.opportunity_steps os on i.opportunity_step_id = os.id
LEFT join seducar.opportunity_modalities om on i.opportunity_modality_id = om.id
LEFT JOIN seducar.opportunity_origins oo on i.opportunity_origin_id = oo.id
