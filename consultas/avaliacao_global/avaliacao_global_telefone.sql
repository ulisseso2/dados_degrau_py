SELECT
    s.transcription_id,
    s.ai_insight AS ai_evaluation,
    s.ai_evaluation AS evaluation_ia,
    s.lead_score,
    s.lead_classification,
    s.strengths,
    s.improvements,
    s.most_expensive_mistake,
    s.contest_area,
    s.main_product,
    s.vendedor_disclaimer,
    s.lead_disclaimer,
    t.agent AS agente,
    t.date AS data_avaliacao,
    CASE
        WHEN t.school_id = 1 THEN 'Degrau'
        ELSE 'Central'
    END AS empresa,
    'Telefone' AS canal
FROM seducar.transcription_ai_summaries s
JOIN seducar.opportunity_transcripts t ON s.transcription_id = t.id
WHERE s.ai_evaluation IS NOT NULL
  AND s.ai_evaluation > 0
