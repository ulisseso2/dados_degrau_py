SELECT 
    c.id AS turma_id, 
    c.start_type AS tipo_turma, 
    CASE 
        WHEN c.start_type = 'mother' THEN cu.mother_value
        WHEN c.start_type = 'cyclical' THEN cu.cyclical_value 
        ELSE NULL 
    END AS valor_iniciar
FROM seducar.classrooms c
LEFT JOIN seducar.courses cu ON c.course_id = cu.id;