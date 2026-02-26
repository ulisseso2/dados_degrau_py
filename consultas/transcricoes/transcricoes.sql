SELECT
    ot.id                   AS transcricao_id,
    ot.created_at           AS data_trancricao,
    ot.date                 AS data_ligacao,
    ot.time                 AS hora_ligacao,
    ot.opportunity_id       AS oportunidade,
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
    ot.agent                AS agente,
    ot.duration             AS duracao,
    ot.type                 AS tipo_ligacao,
    CASE
        WHEN ot.transcript IS NULL OR CHAR_LENGTH(ot.transcript) <= 255 THEN 0
        ELSE 1
    END AS avaliavel

FROM seducar.opportunity_transcripts ot

LEFT JOIN seducar.interesteds i         ON ot.opportunity_id = i.id
LEFT JOIN seducar.customers c           ON i.customer_id = c.id
LEFT JOIN seducar.opportunity_steps os  ON i.opportunity_step_id = os.id
LEFT JOIN seducar.opportunity_modalities om ON i.opportunity_modality_id = om.id
LEFT JOIN seducar.opportunity_origins oo    ON i.opportunity_origin_id = oo.id
LEFT JOIN seducar.transcription_ai_summaries tais ON ot.id = tais.transcription_id
