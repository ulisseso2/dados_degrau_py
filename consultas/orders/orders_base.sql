-- Dados escalares de pedidos: todos os JOINs são many-to-one ou subqueries únicas.
-- Sem GROUP BY no resultado final → muito mais rápido que orders.sql.
-- As tabelas one-to-many (order_items, order_notes, order_refunds, customer_addresses)
-- são pré-agregadas em subqueries antes do JOIN principal.

SELECT
    o.id                                                                    AS ordem_id,
    o.uuid                                                                  AS uuid,
    o.created_at                                                            AS criacao_pedido,
    o.paid_at                                                               AS data_pagamento,
    o.total                                                                 AS total_pedido,
    o.total_discount                                                        AS desconto_ordem,
    o.total_refund                                                          AS estorno_cancelamento,
    o.request_date                                                          AS solicitacao_cancelamento,
    o.geolocation                                                           AS dados_aceite,
    o.date_acceptance                                                       AS data_aceite,
    COALESCE(o.request_date, o.paid_at)                                     AS data_referencia,
    oct.name                                                                AS tipo_cancelamento,
    ont.descricao,
    ont.titulo_cancelamento,
    orf.data_devolucao,
    rmc.name                                                                AS metodo_devolucao,
    os.name                                                                 AS status,
    os.id                                                                   AS status_id,
    c.birth                                                                 AS data_nascimento,
    COALESCE(CAST(TIMESTAMPDIFF(YEAR, c.birth, CURDATE()) AS CHAR), 'S/DN') AS idade_atual,
    COALESCE(CAST(TIMESTAMPDIFF(YEAR, c.birth, o.paid_at) AS CHAR), 'S/DN') AS idade_momento_compra,
    CASE WHEN o.school_id = 1 THEN 'Degrau' ELSE 'Central' END             AS empresa,
    o.customer_id                                                           AS cliente_id,
    c.cpf,
    c.full_name                                                             AS nome_cliente,
    c.email                                                                 AS email_cliente,
    c.cellphone                                                             AS celular_cliente,
    ca.cep                                                                  AS cep_cliente,
    ca.address                                                              AS endereco_cliente,
    ca.neighborhood                                                         AS bairro_cliente,
    ca.city                                                                 AS cidade_cliente,
    IFNULL(v.full_name, 'Indefinido')                                       AS vendedor,
    IFNULL(ow.full_name, v.full_name)                                       AS dono,
    IFNULL(o.owner_id, o.user_id)                                           AS owner_id,
    CASE WHEN o.owner_id IS NULL THEN 'Site' ELSE 'Time' END               AS canal_venda,
    pm.name                                                                 AS metodo_pagamento

FROM seducar.orders o

LEFT JOIN seducar.order_status              os  ON os.id  = o.order_status_id
LEFT JOIN seducar.payment_methods           pm  ON pm.id  = o.payment_method_id
LEFT JOIN seducar.customers                 c   ON c.id   = o.customer_id
LEFT JOIN seducar.users                     v   ON v.id   = o.user_id
LEFT JOIN seducar.users                     ow  ON ow.id  = o.owner_id
LEFT JOIN seducar.order_cancelation_types   oct ON oct.id = o.cancelation_type_id
LEFT JOIN seducar.return_methods            rmc ON rmc.id = o.return_method_id

-- Endereço: uma linha por cliente (evita multiplicação)
LEFT JOIN (
    SELECT customer_id, cep, address, neighborhood, city
    FROM seducar.customer_addresses
    GROUP BY customer_id
) ca ON ca.customer_id = c.id

-- Nota do pedido: uma linha por pedido
LEFT JOIN (
    SELECT order_id,
           description  AS descricao,
           title        AS titulo_cancelamento
    FROM seducar.order_notes
    GROUP BY order_id
) ont ON ont.order_id = o.id

-- Estorno: uma linha por pedido (o mais recente)
LEFT JOIN (
    SELECT order_id,
           MAX(refund_date) AS data_devolucao
    FROM seducar.order_refunds
    GROUP BY order_id
) orf ON orf.order_id = o.id

WHERE o.updated_at >= '2024-01-01';
