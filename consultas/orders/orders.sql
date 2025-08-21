SELECT 
    o.id AS ordem_id, 
    o.created_at AS criacao_pedido,
    o.paid_at AS data_pagamento,
    o.total AS total_pedido,
    o.total_discount AS desconto_ordem,
    o.total_refund AS estorno_cancelamento,
    o.request_date AS solicitacao_cancelamento,
    COALESCE(o.request_date, o.paid_at) AS data_referencia,
    oct.name AS tipo_cancelamento,
    ont.description AS descricao,
    ont.title AS titulo_cancelamento,
    p.title AS produto,
    os.name AS status,
    os.id AS status_id,
    CASE WHEN o.school_id = 1 THEN 'Degrau' ELSE 'Central' END as empresa, 
    o.customer_id AS cliente_id,
    c.cpf AS cpf,
    c.full_name AS nome_cliente,
    c.email AS email_cliente,
    c.cellphone AS celular_cliente,
    ca.cep AS cep_cliente,
    ca.address AS endereco_cliente,
    ca.neighborhood AS bairro_cliente,
    ca.city AS cidade_cliente,
    IFNULL(v.full_name, 'Indefinido') AS vendedor,
    pm.name AS metodo_pagamento,
    GROUP_CONCAT(DISTINCT t.name SEPARATOR ', ') AS turma,
    GROUP_CONCAT(DISTINCT t.id SEPARATOR ', ') AS turma_id,
    GROUP_CONCAT(DISTINCT s.name SEPARATOR ', ') AS turno,
    GROUP_CONCAT(DISTINCT 
        CASE 
            WHEN cu.title IS NULL AND oi.product_category_id = 7 THEN 'Passaporte'
            WHEN cu.title IS NULL AND oi.product_category_id = 10 THEN 'Degrau Smart'
            ELSE cu.title
        END SEPARATOR ', '
    ) AS curso,
    GROUP_CONCAT(DISTINCT 
        CASE 
            WHEN cs.name IS NULL AND oi.product_category_id = 7 THEN 'Passaporte'
            WHEN cs.name IS NULL AND oi.product_category_id = 10 THEN 'Degrau Smart'
            ELSE cs.name
        END SEPARATOR ', '
    ) AS curso_venda,
    GROUP_CONCAT(DISTINCT oi.id SEPARATOR ', ') AS item_id,
    GROUP_CONCAT(DISTINCT pc.name SEPARATOR ', ') AS categoria,
    IFNULL(u.name,
        CASE 
            WHEN pc.id = 3 THEN 'Live'
            WHEN pc.id = 10 THEN 'Degrau Smart'
            WHEN pc.id = 2 THEN 'EAD'
            WHEN pc.id = 7 AND o.unit_id IS NOT NULL THEN COALESCE(u3.name, 'Indefinido')
            ELSE 'Indefinido'
        END
    ) AS unidade
FROM seducar.orders o
LEFT JOIN seducar.order_status os ON os.id = o.order_status_id
LEFT JOIN seducar.payment_methods pm ON pm.id = o.payment_method_id
LEFT JOIN seducar.customers c ON c.id = o.customer_id
LEFT JOIN seducar.customer_addresses ca ON ca.customer_id = c.id
LEFT JOIN seducar.users v ON v.id = o.user_id
LEFT JOIN seducar.order_items oi ON oi.order_id = o.id
LEFT JOIN seducar.product_categories pc ON pc.id = oi.product_category_id
LEFT JOIN seducar.classrooms t ON t.id = oi.classroom_id
LEFT JOIN seducar.products p ON p.id = oi.product_id
LEFT JOIN seducar.shifts s ON s.id = t.shift_id
LEFT JOIN seducar.units u ON u.id = t.unit_id
LEFT JOIN seducar.units u3 ON u3.id = o.unit_id
LEFT JOIN seducar.courses cu ON cu.id = t.course_id
LEFT JOIN seducar.course_sales cs ON cs.id = cu.course_sale_id
LEFT JOIN seducar.order_cancelation_types oct ON o.cancelation_type_id = oct.id
LEFT JOIN seducar.order_notes ont ON o.id = ont.order_id
where o.updated_at >= '2023-01-01'
GROUP BY o.id;
