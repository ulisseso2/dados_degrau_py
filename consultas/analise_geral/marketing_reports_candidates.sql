SELECT
    id,
    uuid,
    reference_date,
    type,
    generated_at,
    raw_data,
    ai_analysis
FROM ai_reports
WHERE type IN ('completo_ads', 'alerta')
  AND generated_at >= DATE_SUB('{data_inicio}', INTERVAL 90 DAY)
  AND generated_at < DATE_ADD('{data_fim}', INTERVAL 7 DAY)
ORDER BY generated_at DESC
LIMIT 200;