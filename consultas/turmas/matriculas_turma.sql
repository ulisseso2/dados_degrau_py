SELECT o.id as order_id, 
CASE WHEN o.school_id = 1 THEN "Degrau" ELSE "Central" end as empresa, 
o.paid_at as data_pagamento, 
oi.classroom_id as turma_id, 
os.name as status_pagamento,
CASE WHEN o.total_refund > 0 THEN (o.total-o.total_refund) ELSE o.total END as valor,
o.total as valor_pago,
o.total_refund as valor_devolvido

FROM seducar.orders o
left join seducar.order_items oi on o.id = oi.order_id
left join seducar.order_status os on o.order_status_id = os.id
WHERE os.id in (2,3,14,15,19)
AND oi.product_category_id in (1,3,4,7)