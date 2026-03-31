-- Agregações de itens por pedido.
-- Parte do conjunto de queries que substitui orders.sql.
-- Faz JOIN de volta a orders apenas para school_id e unit_id (necessários nos CASEs).
-- Resultado: uma linha por order_id, para ser mergeado com orders_base.sql em Python.

SELECT
    oi.order_id AS ordem_id,

    GROUP_CONCAT(DISTINCT p.title  SEPARATOR ', ') AS produto,
    GROUP_CONCAT(DISTINCT t.name   SEPARATOR ', ') AS turma,
    GROUP_CONCAT(DISTINCT t.id     SEPARATOR ', ') AS turma_id,
    GROUP_CONCAT(DISTINCT s.name   SEPARATOR ', ') AS turno,
    GROUP_CONCAT(DISTINCT pc.name  SEPARATOR ', ') AS categoria,
    GROUP_CONCAT(DISTINCT oi.id    SEPARATOR ', ') AS item_id,

    GROUP_CONCAT(DISTINCT
        CASE
            WHEN cu.title IS NULL AND oi.product_category_id = 7  THEN 'Passaporte'
            WHEN cu.title IS NULL AND oi.product_category_id = 10 AND o.school_id = 1 THEN 'Degrau Smart'
            WHEN cu.title IS NULL AND oi.product_category_id = 10 AND o.school_id = 2 THEN 'Central Smart'
            ELSE cu.title
        END SEPARATOR ', '
    ) AS curso,

    GROUP_CONCAT(DISTINCT
        CASE
            WHEN cs.name  IS NULL AND oi.product_category_id = 7  THEN 'Passaporte'
            WHEN cu.title IS NULL AND oi.product_category_id = 10 AND o.school_id = 1 THEN 'Degrau Smart'
            WHEN cu.title IS NULL AND oi.product_category_id = 10 AND o.school_id = 2 THEN 'Central Smart'
            ELSE cs.name
        END SEPARATOR ', '
    ) AS curso_venda,

    -- Unidade: prefere a unidade da turma; cai em derivação por categoria ou unidade do pedido
    COALESCE(
        MAX(u.name),
        CASE
            WHEN MAX(pc.id) = 3  THEN 'Live'
            WHEN MAX(pc.id) = 10 THEN 'Smart'
            WHEN MAX(pc.id) = 2  THEN 'EAD'
            WHEN MAX(pc.id) = 7  THEN COALESCE(MAX(u3.name), 'Indefinido')
            ELSE 'Indefinido'
        END
    ) AS unidade

FROM seducar.order_items oi

-- INNER JOIN: filtra só os pedidos dentro do período
JOIN  seducar.orders            o   ON o.id   = oi.order_id AND o.updated_at >= '2024-01-01'

LEFT JOIN seducar.product_categories  pc  ON pc.id  = oi.product_category_id
LEFT JOIN seducar.classrooms          t   ON t.id   = oi.classroom_id
LEFT JOIN seducar.products            p   ON p.id   = oi.product_id
LEFT JOIN seducar.shifts              s   ON s.id   = t.shift_id
LEFT JOIN seducar.units               u   ON u.id   = t.unit_id
LEFT JOIN seducar.courses             cu  ON cu.id  = t.course_id
LEFT JOIN seducar.course_sales        cs  ON cs.id  = cu.course_sale_id
-- Unidade do pedido (fallback para categoria Passaporte)
LEFT JOIN seducar.units               u3  ON u3.id  = o.unit_id

GROUP BY oi.order_id;
