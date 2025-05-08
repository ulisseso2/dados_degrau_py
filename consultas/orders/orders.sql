SELECT 
    o.id AS ordem_id, 
    o.created_at AS criacao_pedido,
    o.paid_at AS data_pagamento,
    o.total AS total_pedido,
    o.total_discount AS desconto_ordem,
    o.total_refund AS estorno_cancelamento,
    o.request_date as solicitacao_cancelamento,
    oct.name AS tipo_cancelamento,
    ont.description AS descricacao,
    ont.title AS titulo_cancelamento,
    os.name AS status,
    os.id AS status_id,
    IF(o.school_id = 1, 'Degrau', 'Central') AS empresa, 
    o.customer_id AS cliente_id,
    c.cpf AS cpf,
    c.full_name as nome_cliente,
    c.email as email_cliente,
    c.cellphone as celular_cliente,

    COALESCE(o.request_date, o.paid_at) AS data_referencia,

    COALESCE(
        v.full_name,
        NULLIF(JSON_UNQUOTE(JSON_EXTRACT(o.json_consys, '$.seller')), '') 
    ) AS vendedor,

    pm.name AS metodo_pagamento,

    GROUP_CONCAT(DISTINCT t.name ORDER BY t.id SEPARATOR ', ') AS turma,
	GROUP_CONCAT(DISTINCT t.id ORDER BY t.id SEPARATOR ', ') AS turma_id,
    GROUP_CONCAT(DISTINCT 
        CASE 
            WHEN cu.title IS NULL AND oi.product_category_id = 7 THEN 'Passaporte'
            ELSE cu.title
        END 
        ORDER BY cu.title SEPARATOR ', '
    ) AS curso,
	GROUP_CONCAT(DISTINCT 
        CASE 
            WHEN cu.id IS NULL AND oi.product_category_id = 7 THEN 'Passaporte'
            ELSE cu.id
        END 
        ORDER BY cu.id SEPARATOR ', '
    ) AS curso_id,
    GROUP_CONCAT(DISTINCT 
        CASE 
            WHEN cs.name IS NULL AND oi.product_category_id = 7 THEN 'Passaporte'
            ELSE cs.name
        END 
        ORDER BY cs.name SEPARATOR ', '
    ) AS curso_venda,
    
        GROUP_CONCAT(DISTINCT 
        CASE 
            WHEN cs.id IS NULL AND oi.product_category_id = 7 THEN 'Passaporte'
            ELSE cs.id
        END 
        ORDER BY cs.id SEPARATOR ', '
    ) AS curso_venda_id,

    GROUP_CONCAT(DISTINCT oi.id ORDER BY oi.id SEPARATOR ', ') AS item_id,
	GROUP_CONCAT(DISTINCT pc.name ORDER BY pc.name SEPARATOR ', ') AS categoria,

    COALESCE(
        u.name,
        CASE 
            WHEN pc.id = 3 THEN 'Live'
            WHEN pc.id = 7 AND o.unit_id IS NOT NULL THEN 
                (SELECT name FROM seducar.units WHERE id = o.unit_id)
            ELSE u2.name
        END
    ) AS unidade

FROM seducar.orders o
LEFT JOIN seducar.order_status os ON os.id = o.order_status_id
LEFT JOIN seducar.payment_methods pm ON pm.id = o.payment_method_id
LEFT JOIN seducar.customers c ON c.id = o.customer_id
LEFT JOIN seducar.users v ON v.id = o.user_id
LEFT JOIN seducar.units u2 
    ON u2.id_old = SUBSTRING_INDEX(JSON_UNQUOTE(JSON_EXTRACT(o.json_consys, '$.code')), '-', 1)

LEFT JOIN seducar.order_items oi ON oi.order_id = o.id
LEFT JOIN seducar.product_categories pc ON pc.id = oi.product_category_id
LEFT JOIN seducar.classrooms t ON t.id = oi.classroom_id
LEFT JOIN seducar.units u ON u.id = t.unit_id
LEFT JOIN seducar.courses cu ON cu.id = t.course_id
LEFT JOIN seducar.course_sales cs ON cs.id = cu.course_sale_id
LEFT JOIN seducar.order_cancelation_types oct ON o.cancelation_type_id = oct.id
LEFT JOIN seducar.order_notes ont ON o.id = ont.order_id

WHERE o.created_at >= '2023-01-01'

GROUP BY o.id;
