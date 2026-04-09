SELECT
    ot.id                   AS transcricao_id,
    ot.transcript           AS transcricao,
    JSON_UNQUOTE(JSON_EXTRACT(ot.original_transcript, '$.agente'))   AS agente,
    JSON_UNQUOTE(JSON_EXTRACT(ot.original_transcript, '$.duracao'))  AS duracao,
    JSON_UNQUOTE(JSON_EXTRACT(ot.original_transcript, '$.telefone')) AS telefone,
    JSON_UNQUOTE(JSON_EXTRACT(ot.original_transcript, '$.tipo'))     AS tipo,
    tais.ai_insight         AS insight_ia,
    tais.vendedor_disclaimer AS vendedor_disclaimer,
    tais.lead_disclaimer     AS lead_disclaimer

FROM seducar.opportunity_transcripts ot
LEFT JOIN seducar.transcription_ai_summaries tais ON ot.id = tais.transcription_id

WHERE ot.id IN ({ids})
