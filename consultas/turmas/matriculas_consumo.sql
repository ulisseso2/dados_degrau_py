SELECT
    o.id AS order_id,
    o.paid_at AS data_pagamento,
    oi.classroom_id AS turma_id,
    t.name AS turma_nome,
    CASE WHEN o.school_id = 1 THEN 'Degrau' ELSE 'Central' END AS empresa,
    os.name AS status,
    os.id AS status_id,
    CASE WHEN o.total_refund > 0 THEN (o.total - o.total_refund) ELSE o.total END AS total_pedido,
    c.full_name AS nome_cliente,
    c.cpf AS cpf,
    c.email AS email_cliente,
    c.cellphone AS celular_cliente,
    ca.cep AS cep_cliente,
    ca.address AS endereco_cliente,
    ca.neighborhood AS bairro_cliente,
    ca.city AS cidade_cliente,
    IFNULL(v.full_name, 'Indefinido') AS vendedor,
    pm.name AS metodo_pagamento,
    s.name AS turno,
    cs.name AS curso_venda,
    cu.title AS curso,
    IFNULL(un.name, 'Indefinido') AS unidade,
    pc.name AS categoria,
    COALESCE(CAST(TIMESTAMPDIFF(YEAR, c.birth, o.paid_at) AS CHAR), 'S/DN') AS idade_momento_compra
FROM seducar.orders o
LEFT JOIN seducar.order_status os ON os.id = o.order_status_id
LEFT JOIN seducar.payment_methods pm ON pm.id = o.payment_method_id
LEFT JOIN seducar.customers c ON c.id = o.customer_id
LEFT JOIN (
    SELECT customer_id,
           MAX(cep) AS cep,
           MAX(address) AS address,
           MAX(neighborhood) AS neighborhood,
           MAX(city) AS city
    FROM seducar.customer_addresses
    GROUP BY customer_id
) ca ON ca.customer_id = c.id
LEFT JOIN seducar.users v ON v.id = o.user_id
LEFT JOIN seducar.order_items oi ON oi.order_id = o.id
LEFT JOIN seducar.product_categories pc ON pc.id = oi.product_category_id
LEFT JOIN seducar.classrooms t ON t.id = oi.classroom_id
LEFT JOIN seducar.shifts s ON s.id = t.shift_id
LEFT JOIN seducar.units un ON un.id = t.unit_id
LEFT JOIN seducar.courses cu ON cu.id = t.course_id
LEFT JOIN seducar.course_sales cs ON cs.id = cu.course_sale_id
WHERE oi.product_category_id IN (1, 3, 4)
AND oi.classroom_id IS NOT NULL
AND o.updated_at >= '2024-01-01'
GROUP BY
    o.id, oi.classroom_id;
