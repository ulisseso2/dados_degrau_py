SELECT
    c.chat_id,
    c.classification,
    c.ai_evaluation,
    c.lead_score,
    c.vendor_score AS evaluation_ia,
    c.main_product,
    c.vendedor_disclaimer,
    c.lead_disclaimer,
    c.octa_agent AS agente,
    c.octa_created_at AS data_avaliacao,
    c.octa_group AS grupo,
    CASE
        WHEN c.octa_origin LIKE '%Degrau%' THEN 'Degrau'
        WHEN c.octa_origin LIKE '%Central%' THEN 'Central'
        ELSE 'Outros'
    END AS empresa,
    'WhatsApp' AS canal
FROM seducar.chat_ai_evaluations c
WHERE c.classification = 'venda'
  AND c.vendor_score IS NOT NULL
  AND c.vendor_score > 0
