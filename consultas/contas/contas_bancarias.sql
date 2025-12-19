SELECT 
b.id as conta_id,
CASE WHEN b.school_id = 1 THEN 'Degrau' ELSE 'Central' END AS empresa, 
b.name as conta_bancaria, 
b.saldo as saldo_atual  
FROM seducar.bank_accounts b