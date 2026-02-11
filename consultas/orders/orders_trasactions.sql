SELECT 
    t.uuid as transacao,
    CASE WHEN o.school_id = 1 THEN 'Degrau' ELSE 'Central' END as empresa,
    o.id as pedido, 
    o.total as valor, 
    t.created_at as data_transacao, 
    os.name as status,
    oi.product_category_id as categoria_id,
    c.cpf as cpf
FROM seducar.transactions t
LEFT JOIN seducar.orders o on t.order_id = o.id
LEFT JOIN seducar.order_status os on o.order_status_id = os.id
LEFT JOIN seducar.order_items oi on o.id = oi.order_id
LEFT JOIN seducar.customers c on o.customer_id = c.id
WHERE t.created_at >= '2024-01-01'