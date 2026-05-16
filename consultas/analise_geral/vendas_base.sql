SELECT
    o.id AS ordem_id,
    o.uuid AS uuid,
    o.school_id AS school_id,
    CASE
        WHEN o.school_id = 1 THEN 'Degrau'
        WHEN o.school_id = 2 THEN 'Central'
        ELSE 'Indefinida'
    END AS empresa,
    o.customer_id AS cliente_id,
    o.created_at AS criacao_pedido,
    o.paid_at AS data_pagamento,
    o.total AS total_pedido,
    o.total_discount AS desconto_ordem,
    o.total_refund AS estorno_cancelamento,
    o.request_date AS solicitacao_cancelamento,
    o.date_acceptance AS data_aceite,
    COALESCE(o.request_date, o.paid_at) AS data_referencia,
    os.name AS status,
    os.id AS status_id,
    IFNULL(v.full_name, 'Indefinido') AS vendedor,
    IFNULL(ow.full_name, v.full_name) AS dono,
    IFNULL(o.owner_id, o.user_id) AS owner_id,
    pm.name AS metodo_pagamento,
    GROUP_CONCAT(DISTINCT p.title SEPARATOR ', ') AS produto,
    GROUP_CONCAT(DISTINCT pc.name SEPARATOR ', ') AS categoria,
    GROUP_CONCAT(DISTINCT
        CASE
            WHEN cs.name IS NULL AND oi.product_category_id = 7 THEN 'Passaporte'
            WHEN cu.title IS NULL AND oi.product_category_id = 10 AND o.school_id = 1 THEN 'Degrau Smart'
            WHEN cu.title IS NULL AND oi.product_category_id = 10 AND o.school_id = 2 THEN 'Central Smart'
            ELSE cs.name
        END SEPARATOR ', '
    ) AS curso_venda,
    IFNULL(
        u.name,
        CASE
            WHEN pc.id = 3 THEN 'Live'
            WHEN pc.id = 10 THEN 'Smart'
            WHEN pc.id = 2 THEN 'EAD'
            WHEN pc.id = 7 AND o.unit_id IS NOT NULL THEN COALESCE(u3.name, 'Indefinido')
            ELSE 'Indefinido'
        END
    ) AS unidade
FROM seducar.orders o
LEFT JOIN seducar.order_status os ON os.id = o.order_status_id
LEFT JOIN seducar.payment_methods pm ON pm.id = o.payment_method_id
LEFT JOIN seducar.users v ON v.id = o.user_id
LEFT JOIN seducar.users ow ON o.owner_id = ow.id
LEFT JOIN seducar.order_items oi ON oi.order_id = o.id
LEFT JOIN seducar.product_categories pc ON pc.id = oi.product_category_id
LEFT JOIN seducar.classrooms t ON t.id = oi.classroom_id
LEFT JOIN seducar.products p ON p.id = oi.product_id
LEFT JOIN seducar.units u ON u.id = t.unit_id
LEFT JOIN seducar.units u3 ON u3.id = o.unit_id
LEFT JOIN seducar.courses cu ON cu.id = t.course_id
LEFT JOIN seducar.course_sales cs ON cs.id = cu.course_sale_id
WHERE o.school_id IN ({school_ids})
  AND o.paid_at >= '{data_inicio}'
  AND o.paid_at < DATE_ADD('{data_fim}', INTERVAL 1 DAY)
  AND o.total != 0
  AND o.payment_method_id NOT IN (5, 8, 13)
  {where_extra}
GROUP BY o.id
ORDER BY o.paid_at DESC, o.id DESC;