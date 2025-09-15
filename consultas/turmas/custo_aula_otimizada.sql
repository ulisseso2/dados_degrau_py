-- Query otimizada para custo de aulas com correções de boas práticas SQL
SELECT
    c.id AS turma_id,
    c.name AS turma_nome,
    CASE 
        WHEN c.school_id = 1 THEN 'Degrau' 
        ELSE 'Central' 
    END AS empresa,
    COALESCE(cu.title, 'Curso não informado') AS curso,
    COALESCE(cs.name, 'Venda não informada') AS curso_venda,
    COALESCE(un.name, 'Unidade não informada') AS unidade,
    gl.id AS aula_id,
    gl.date AS data_aula,
    -- Calcula carga horária com validação de dados nulos
    CASE 
        WHEN gl.workload IS NOT NULL THEN
            ROUND(
                GREATEST(
                    (TIME_TO_SEC(gl.workload) - TIME_TO_SEC('00:15:00')) / 3600, 
                    0
                ), 
                2
            )
        ELSE 0
    END AS carga_horaria_decimal,
    -- Calcula valor do rateio com validações
    CASE 
        WHEN gl.workload IS NOT NULL 
             AND p.value_higher IS NOT NULL 
             AND p.value_lower IS NOT NULL THEN
            ROUND(
                (
                    GREATEST(
                        (TIME_TO_SEC(gl.workload) - TIME_TO_SEC('00:15:00')) / 3600, 
                        0
                    ) * 
                    CASE 
                        WHEN cu.scholarity_id IN (5, 7, 10, 13, 18, 19) THEN p.value_higher
                        ELSE p.value_lower
                    END
                ) / GREATEST(COALESCE(gxl_count.turmas_compartilhadas, 1), 1), 
                2
            )
        ELSE 0
    END AS valor_rateio_aula,
    COALESCE(gxl_count.turmas_compartilhadas, 1) AS turmas_compartilhadas,
    COALESCE(p.full_name, 'Professor não informado') AS professor,
    COALESCE(p.value_higher, 0) AS aula_superior,
    COALESCE(p.value_lower, 0) AS aula_medio,
    COALESCE(gls.name, 'Status não informado') AS status_aula,
    COALESCE(glc.name, 'Categoria não informada') AS categoria_aula,
    CASE 
        WHEN cu.scholarity_id IN (5, 7, 10, 13, 18, 19) THEN 'Superior'
        ELSE 'Médio'
    END AS escolaridade,
    CASE 
        WHEN g.id IS NOT NULL THEN 'Sim'
        ELSE 'Não'
    END AS possui_grade,
    -- Campos adicionais para análise
    c.created_at AS data_criacao_turma,
    gl.created_at AS data_criacao_aula,
    gl.updated_at AS data_atualizacao_aula
FROM seducar.classrooms c
LEFT JOIN seducar.courses cu ON cu.id = c.course_id
LEFT JOIN seducar.course_sales cs ON cs.id = cu.course_sale_id
LEFT JOIN seducar.units un ON un.id = c.unit_id
LEFT JOIN seducar.grids g ON g.classroom_id = c.id
LEFT JOIN seducar.grid_x_lessons gxl ON gxl.grid_id = g.id
LEFT JOIN seducar.grid_lessons gl ON gl.id = gxl.grid_lesson_id
LEFT JOIN seducar.teachers p ON p.id = gl.teacher_id
LEFT JOIN seducar.grid_lesson_status gls ON gls.id = gl.grid_lesson_status_id
LEFT JOIN seducar.grid_lesson_categories glc ON glc.id = gl.grid_lesson_category_id
-- Subquery otimizada para contar turmas compartilhadas
LEFT JOIN (
    SELECT 
        gxl_inner.grid_lesson_id, 
        COUNT(DISTINCT gxl_inner.grid_id) AS turmas_compartilhadas
    FROM seducar.grid_x_lessons gxl_inner
    GROUP BY gxl_inner.grid_lesson_id
) gxl_count ON gxl_count.grid_lesson_id = gl.id
WHERE 
    c.id IS NOT NULL
    -- Adiciona filtros para dados válidos
    AND c.name IS NOT NULL
    AND c.name != ''
    -- Opcional: filtrar apenas turmas ativas ou com aulas
    -- AND (g.id IS NOT NULL OR gl.id IS NOT NULL)
ORDER BY 
    COALESCE(gxl_count.turmas_compartilhadas, 1) DESC, 
    c.name ASC,
    gl.date ASC;
