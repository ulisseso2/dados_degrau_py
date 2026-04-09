SELECT
    ot.id                   AS transcricao_id,
    ot.created_at           AS data_trancricao,
    ot.date                 AS data_ligacao,
    ot.time                 AS hora_ligacao,
    ot.opportunity_id       AS oportunidade,
    ot.transcript           AS transcricao,
    CASE WHEN ot.school_id = 1 THEN 'Degrau' ELSE 'Central' END AS empresa,
    c.full_name             AS nome_lead,
    c.cellphone             AS telefone_lead,
    os.name                 AS etapa,
    om.name                 AS modalidade,
    oo.name                 AS origem,
    tais.ai_evaluation      AS evaluation_ia,
    tais.lead_score         AS lead_score,
    tais.lead_classification AS lead_classification,
    tais.strengths          AS strengths,
    tais.improvements       AS improvements,
    tais.most_expensive_mistake AS most_expensive_mistake,
    tais.contest_area       AS concurso_area,
    tais.main_product       AS produto_recomendado,
    tais.main_pain_points   AS principais_dores,
    tais.ai_insight         AS insight_ia,
    tais.vendedor_disclaimer AS vendedor_disclaimer,
    tais.lead_disclaimer     AS lead_disclaimer,
    JSON_UNQUOTE(JSON_EXTRACT(tais.ai_insight, '$.classificacao_ligacao'))  AS tipo_classificacao_ia,
    CAST(JSON_EXTRACT(tais.ai_insight, '$.confianca_classificacao') AS DECIMAL(4,2)) AS confianca_classificacao,
    COALESCE(ot.agent,    JSON_UNQUOTE(JSON_EXTRACT(ot.original_transcript, '$.agente')))   AS agente,
    COALESCE(ot.duration, JSON_UNQUOTE(JSON_EXTRACT(ot.original_transcript, '$.duracao'))) AS duracao,
    COALESCE(ot.type,     JSON_UNQUOTE(JSON_EXTRACT(ot.original_transcript, '$.tipo')))    AS tipo_ligacao,
    CASE
        WHEN ot.transcript IS NULL OR CHAR_LENGTH(ot.transcript) < 500 THEN 0
        ELSE 1
    END AS avaliavel

FROM seducar.opportunity_transcripts ot

LEFT JOIN seducar.interesteds i         ON ot.opportunity_id = i.id
LEFT JOIN seducar.customers c           ON i.customer_id = c.id
LEFT JOIN seducar.opportunity_steps os  ON i.opportunity_step_id = os.id
LEFT JOIN seducar.opportunity_modalities om ON i.opportunity_modality_id = om.id
LEFT JOIN seducar.opportunity_origins oo    ON i.opportunity_origin_id = oo.id
LEFT JOIN seducar.transcription_ai_summaries tais ON ot.id = tais.transcription_id
