SELECT
  oi.id,
  oi.plots,
  oi.amount,
  oi.date,
  oi.paid_at,
  oi.order_id,
  c.full_name,
  c.cpf,
  c.email,
  ca.cep,
  ca.address,
  ca.city,
  ca.neighborhood,
  ca.number,
  ca.complement,
  ca.uf,
  oi.nfe_id,
  oi.nfse_id,
  o.total,
  pm.name,
  CASE WHEN oi.nfse_id IS NULL THEN "Vista Site" WHEN o.total = oi.amount THEN "Vista" ELSE "Parcela" END as parcelamento
FROM
  order_installments oi
  LEFT JOIN orders o ON oi.order_id = o.id
  LEFT JOIN payment_methods pm ON o.payment_method_id = pm.id
  LEFT JOIN customers c ON o.customer_id = c.id
  LEFT JOIN customer_addresses ca ON c.id = ca.customer_id
  WHERE (oi.nfe_id IS NOT NULL OR oi.nfse_id IS NOT NULL)
  AND o.school_id = 1