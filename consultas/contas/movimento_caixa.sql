(SELECT
    CAST(DATE(cf.date) AS CHAR) as data,
    CAST('Entrada' AS CHAR(20)) as tipo,
    CAST(CASE WHEN cf.school_id = 1 THEN 'Degrau' ELSE 'Central' END AS CHAR(20)) as empresa, 
    CAST(cf.value AS DECIMAL(15,2)) as valor, 
    CAST(cf.observation AS CHAR(255)) as descricao,
    CAST(f.company_name AS CHAR(255)) as fornecedor,
    CAST(b.name AS CHAR(255)) as conta_bancaria
FROM seducar.cash_flows cf
INNER JOIN seducar.suppliers f ON cf.supplier_id = f.id
INNER JOIN seducar.bank_accounts b ON cf.bank_account_id = b.id)

UNION ALL

(SELECT 
    CAST(DATE(bl.created_at) AS CHAR) as data,
    CAST('Transferência' AS CHAR(20)) as tipo,
    CAST(CASE WHEN bl.school_id = 1 THEN 'Degrau' ELSE 'Central' END AS CHAR(20)) as empresa,
    CAST(bl.amount AS DECIMAL(15,2)) as valor,
    CAST(bl.description AS CHAR(255)) as descricao,
    CAST('Transferencia Entre Contas' AS CHAR(255)) as fornecedor,
    CAST(b2.name AS CHAR(255)) as conta_bancaria
FROM seducar.bank_account_logs bl
INNER JOIN seducar.bank_accounts b2 ON bl.bank_account_id = b2.id
where bl.operation_type = 'transfer')

UNION ALL

(SELECT 
	CAST(DATE(poi.completed) AS CHAR) as data,
    CAST('Pagamento' AS CHAR(20)) as tipo,
    CAST(CASE WHEN po.school_id = 1 THEN "Degral" ELSE "Central" END AS CHAR(20)) as empresa,
    CAST((poi.total_final * -1) AS DECIMAL(15,2)) as valor,
    CAST(po.description AS CHAR(255)) as descricao,
    CAST(f.company_name as CHAR(255)) as fornecedor,
    CAST(b.name AS CHAR(255)) as conta_bancaria
FROM seducar.purchase_order_installments poi
INNER JOIN seducar.purchase_orders po on poi.purchase_order_id = po.id
INNER JOIN seducar.suppliers f on po.supplier_id = f.id
INNER JOIN seducar.bank_accounts b on poi.bank_account_id = b.id
WHERE poi.completed is not null
)
