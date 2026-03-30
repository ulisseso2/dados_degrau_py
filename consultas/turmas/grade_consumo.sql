SELECT DISTINCT
    c.id AS turma_id,
    gl.id AS aula_id,
    gl.date AS data_aula,
    ROUND((TIME_TO_SEC(gl.workload) - TIME_TO_SEC('00:15:00')) / 3600, 2) AS carga_horaria_decimal
FROM seducar.classrooms c
INNER JOIN seducar.grids g ON g.classroom_id = c.id
INNER JOIN seducar.grid_x_lessons gxl ON gxl.grid_id = g.id
INNER JOIN seducar.grid_lessons gl ON gxl.grid_lesson_id = gl.id
WHERE c.id IS NOT NULL AND gl.id IS NOT NULL;
