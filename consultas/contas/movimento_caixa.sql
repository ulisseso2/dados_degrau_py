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
COALESCE(
        STR_TO_DATE(REGEXP_SUBSTR(bl.description, '[0-9]{2}/[0-9]{2}/[0-9]{4}'), '%d/%m/%Y'),
        DATE(bl.created_at)
    ) as data,
    CAST(CASE WHEN bl.operation_type = "transfer" THEN 'Transferência' ELSE 'Manual' END AS CHAR(20)) as tipo,
    CAST(CASE WHEN bl.school_id = 1 THEN 'Degrau' ELSE 'Central' END AS CHAR(20)) as empresa,
    CAST(bl.amount AS DECIMAL(15,2)) as valor,
    CAST(bl.description AS CHAR(255)) as descricao,
    CAST(CASE WHEN bl.operation_type = "transfer" THEN "Transferência entre contas" ELSE 'Ajuste manual' END AS CHAR(255)) as fornecedor,
    CAST(b2.name AS CHAR(255)) as conta_bancaria
FROM seducar.bank_account_logs bl
INNER JOIN seducar.bank_accounts b2 ON bl.bank_account_id = b2.id
where
    (bl.operation_type = 'transfer' AND bl.created_at <= '2025-12-25 23:59:59')
    OR 
    (bl.operation_type = 'manual_adjustment'))

UNION ALL

(SELECT 
	CAST(DATE(poi.completed) AS CHAR) as data,
    CAST('Pagamento' AS CHAR(20)) as tipo,
    CAST(CASE WHEN po.school_id = 1 THEN "Degral" ELSE "Central" END AS CHAR(20)) as empresa,
    CAST((poi.total_final * -1) AS DECIMAL(15,2)) as valor,
    CAST(CASE WHEN poi.comment is null THEN po.description ELSE poi.comment END AS CHAR(255)) as descricao,
    CAST(f.company_name as CHAR(255)) as fornecedor,
    CAST(b.name AS CHAR(255)) as conta_bancaria
FROM seducar.purchase_order_installments poi
INNER JOIN seducar.purchase_orders po on poi.purchase_order_id = po.id
INNER JOIN seducar.suppliers f on po.supplier_id = f.id
INNER JOIN seducar.bank_accounts b on poi.bank_account_id = b.id
WHERE poi.completed is not null
)

UNION ALL

(SELECT 
    CAST(DATE(tf.date) AS CHAR) as data,
    CAST('Transferência' AS CHAR(20)) as tipo,
    CAST(CASE WHEN tf.school_id = 1 THEN 'Degrau' ELSE 'Central' END AS CHAR(20)) as empresa,
    CAST(-tf.amount AS DECIMAL(15,2)) as valor,
    CAST(CONCAT(tf.notes, ' | Enviado para: ', be.name) AS CHAR(255)) as descricao,
    CAST('Transferência Saída' AS CHAR(255)) as fornecedor,
    CAST(bs.name AS CHAR(255)) as conta_bancaria
FROM seducar.transfers tf
INNER JOIN seducar.bank_accounts bs ON tf.from_bank_account_id = bs.id
INNER JOIN seducar.bank_accounts be ON tf.to_bank_account_id = be.id
)

UNION ALL

(SELECT 
    CAST(DATE(tf.date) AS CHAR) as data,
    CAST('Transferência' AS CHAR(20)) as tipo,
    CAST(CASE WHEN tf.school_id = 1 THEN 'Degrau' ELSE 'Central' END AS CHAR(20)) as empresa,
    CAST(tf.amount AS DECIMAL(15,2)) as valor,
    CAST(CONCAT('Recebido de: ', bs.name,' | Descrição: ', tf.notes) AS CHAR(255)) as descricao,
    CAST('Transferência Entrada' AS CHAR(255)) as fornecedor,
    CAST(be.name AS CHAR(255)) as conta_bancaria
FROM seducar.transfers tf
INNER JOIN seducar.bank_accounts be ON tf.to_bank_account_id = be.id
INNER JOIN seducar.bank_accounts bs ON tf.from_bank_account_id = bs.id
)