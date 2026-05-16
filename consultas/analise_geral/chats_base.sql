SELECT
    COALESCE(io.id, ic.id) AS oportunidade_id,
    COALESCE(io.customer_id, ic.customer_id) AS cliente_id,
    CASE
        WHEN COALESCE(io.school_id, ic.school_id) = 1 THEN 1
        WHEN COALESCE(io.school_id, ic.school_id) = 2 THEN 2
        WHEN c.octa_origin LIKE '%2139701015%' OR c.octa_origin LIKE '%Degrau%' THEN 1
        WHEN c.octa_origin LIKE '%1130178800%' OR c.octa_origin LIKE '%Central%' THEN 2
        ELSE NULL
    END AS school_id,
    CASE
        WHEN COALESCE(io.school_id, ic.school_id) = 1 THEN 'Degrau'
        WHEN COALESCE(io.school_id, ic.school_id) = 2 THEN 'Central'
        WHEN c.octa_origin LIKE '%2139701015%' OR c.octa_origin LIKE '%Degrau%' THEN 'Degrau'
        WHEN c.octa_origin LIKE '%1130178800%' OR c.octa_origin LIKE '%Central%' THEN 'Central'
        ELSE 'Indefinida'
    END AS empresa,
    c.chat_id AS chat_id,
    c.octa_created_at AS data_chat,
    c.created_at AS data_criacao_avaliacao,
    COALESCE(c.octa_agent, uo.full_name, uc.full_name) AS agente,
    COALESCE(oo.name, oc.name) AS origem,
    CASE WHEN c.ai_evaluation IS NOT NULL AND c.ai_evaluation != '' THEN 1 ELSE 0 END AS avaliada,
    CASE WHEN c.classification = 'venda' THEN 1 ELSE 0 END AS avaliavel,
    c.vendor_score AS evaluation_ia,
    c.lead_score AS lead_score,
    c.main_product AS produto_recomendado,
    c.classification AS classificacao_triagem,
    c.classification_reason AS motivo_triagem,
    c.transcript AS transcript,
    c.ai_evaluation AS ai_evaluation,
    c.vendedor_disclaimer AS vendedor_disclaimer,
    c.lead_disclaimer AS lead_disclaimer,
    c.octa_origin AS octa_origin,
    c.octa_group AS octa_group,
    c.octa_status AS octa_status,
    c.octa_contact_name AS octa_contact_name,
    c.octa_contact_phone AS octa_contact_phone
FROM seducar.chat_ai_evaluations c
LEFT JOIN seducar.interesteds io ON c.opportunity_id = io.id
LEFT JOIN seducar.users uo ON io.owner_id = uo.id
LEFT JOIN seducar.opportunity_origins oo ON io.opportunity_origin_id = oo.id
LEFT JOIN seducar.interesteds ic ON c.opportunity_id IS NULL AND c.chat_id = ic.chat_id
LEFT JOIN seducar.users uc ON ic.owner_id = uc.id
LEFT JOIN seducar.opportunity_origins oc ON ic.opportunity_origin_id = oc.id
WHERE c.octa_created_at >= '{data_inicio}'
  AND c.octa_created_at < DATE_ADD('{data_fim}', INTERVAL 1 DAY)
  AND CASE
        WHEN COALESCE(io.school_id, ic.school_id) = 1 THEN 1
        WHEN COALESCE(io.school_id, ic.school_id) = 2 THEN 2
        WHEN c.octa_origin LIKE '%2139701015%' OR c.octa_origin LIKE '%Degrau%' THEN 1
        WHEN c.octa_origin LIKE '%1130178800%' OR c.octa_origin LIKE '%Central%' THEN 2
        ELSE NULL
      END IN ({school_ids})
  AND COALESCE(TRIM(c.vendedor_disclaimer), '') != ''
  {where_extra}
ORDER BY c.octa_created_at DESC, c.chat_id DESC;