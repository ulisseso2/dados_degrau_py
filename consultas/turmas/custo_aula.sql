SELECT
    c.id AS turma_id,
    c.name AS turma_nome,
	if(c.school_id = 1, "Degrau", "Central") As empresa,
    cu.title AS curso,
    cs.name AS curso_venda,
	un.name AS unidade,
    gl.id AS aula_id,
    gl.date AS data_aula,
    ROUND((TIME_TO_SEC(gl.workload) - TIME_TO_SEC('00:15:00')) / 3600, 2) AS carga_horaria_decimal,
    ROUND(
        ((TIME_TO_SEC(gl.workload) - TIME_TO_SEC('00:15:00')) / 3600 * 
        CASE 
            WHEN MAX(CASE 
                        WHEN cu.scholarity_id IN (5, 7, 10, 13, 18, 19) THEN 1
                        ELSE 0
                     END) = 1 THEN p.value_higher
            ELSE p.value_lower
        END) / GREATEST(gxl_count.turmas_compartilhadas, 1), 
        2
    ) AS valor_rateio_aula,
    gxl_count.turmas_compartilhadas,
    p.full_name AS professor,
    p.value_higher AS aula_superior,
    p.value_lower AS aula_medio,
    gls.name AS status_aula,
    glc.name AS categoria_aula,
    CASE 
        WHEN MAX(CASE 
                    WHEN cu.scholarity_id IN (5, 7, 10, 13, 18, 19) THEN 1
                    ELSE 0
                 END) = 1 THEN 'Superior'
        ELSE 'Médio'
    END AS escolaridade,
    CASE 
        WHEN g.id IS NOT NULL THEN 'Sim'
        ELSE 'Não'
    END AS possui_grade
FROM seducar.classrooms c
LEFT JOIN seducar.courses cu ON c.course_id = cu.id
LEFT JOIN seducar.course_sales cs ON cu.course_sale_id = cs.id
LEFT JOIN seducar.units un ON c.unit_id = un.id
LEFT JOIN seducar.grids g ON g.classroom_id = c.id
LEFT JOIN seducar.grid_x_lessons gxl ON gxl.grid_id = g.id
LEFT JOIN seducar.grid_lessons gl ON gxl.grid_lesson_id = gl.id
LEFT JOIN (
    SELECT grid_lesson_id, COUNT(id) AS turmas_compartilhadas
    FROM seducar.grid_x_lessons
    GROUP BY grid_lesson_id
) gxl_count ON gxl_count.grid_lesson_id = gl.id
LEFT JOIN seducar.teachers p ON gl.teacher_id = p.id
LEFT JOIN seducar.grid_lesson_status gls ON gl.grid_lesson_status_id = gls.id
LEFT JOIN seducar.grid_lesson_categories glc ON gl.grid_lesson_category_id = glc.id
GROUP BY c.id, c.name, cu.title, cs.name, gl.id, gl.date, gl.workload, gxl_count.turmas_compartilhadas, p.full_name, p.value_higher, p.value_lower, gls.name, glc.name, g.id
ORDER BY gxl_count.turmas_compartilhadas DESC, c.name;
