SELECT
  pi.id AS id_parcela,
  po.id AS pedido_compra_id,
  if(po.school_id = 1, "Degrau", "Central") AS empresa,

  -- Dados financeiros e temporais
  pi.total_final AS total_parcela,
  pi.date AS data_vencimento_parcela,
  pi.installment AS parcela,
  po.installments AS total_de_parcelas,
  CONCAT(pi.installment, '/', po.installments) AS parcelas_de,
  pi.completed AS data_pagamento_parcela,
  COALESCE(pi.total_final, 0) * COALESCE(bxs.percent, 0) / 100 AS valor_corrigido,
  
  CASE
    WHEN pi.completed IS NULL AND pi.date < CURDATE() THEN 'Em Atraso'
    WHEN pi.completed IS NOT NULL AND pi.completed > pi.date THEN 'Pago Atrasado'
    WHEN pi.completed IS NOT NULL AND pi.completed <= pi.date THEN 'Pago em dia'
    ELSE 'A Vencer'
  END AS situacao,
  
  -- Status e identificação
  ps.name AS status_parcela,
  ps.id AS status_id,
  po.order_type AS tipo_pedido_compra,
  po.description AS descricao_pedido_compra,
  pi.purchase_order_id AS compra_id,
  pos.id AS pos_id,

  -- Relacionamentos contábeis
  pc.name AS categoria_pedido_compra,
  dt.name AS tipo_documento,
  op.name AS plano_contas,
  cc.name AS centro_custo,
  ba.name AS conta_bancaria,
  s.company_name AS fornecedor,

  -- Rateio
  bxs.id AS id_bxs,
  bxs.percent AS percentual,
  bu.company_name AS unidade_negocio,
  su.company_name AS unidade_estrategica

FROM seducar.purchase_order_installments pi
JOIN seducar.purchase_orders po ON pi.purchase_order_id = po.id
JOIN seducar.purchase_order_strategic_units pos ON po.id = pos.purchase_order_id
JOIN seducar.business_x_strategics bxs ON bxs.po_strategic_unit_id = pos.id
JOIN seducar.business_units bu ON bxs.business_unit_id = bu.id
JOIN seducar.strategic_units su ON bxs.strategic_unit_id = su.id

-- JOINs auxiliares
LEFT JOIN seducar.bank_accounts ba ON pi.bank_account_id = ba.id
LEFT JOIN seducar.purchase_order_installment_status ps ON pi.purchase_order_installment_status_id = ps.id
LEFT JOIN seducar.purchase_order_categories pc ON po.purchase_order_category_id = pc.id
LEFT JOIN seducar.order_document_types dt ON po.order_document_type_id = dt.id
LEFT JOIN seducar.order_plans op ON po.order_plan_id = op.id
LEFT JOIN seducar.cost_centers cc ON op.cost_center_id = cc.id
LEFT JOIN seducar.suppliers s ON po.supplier_id = s.id
