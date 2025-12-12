SELECT
m.CODIGO as codigo,
e.RAZAO as unidade_central,
m.MATRICULA as matricula,
t.NUM_TURMA as turma,
t.DESCRICAO as desc_curso,
m.ENDERECO as endereco, m.CIDADE as cidade, m.CEP as cep, 
m.CNPJ_CPF as cpf, m.TELEFONE as telefone, m.EMAIL as email, m.NOME_COBRANCA as nome,
m.DT_CADASTRO as data,
m.CARTA_CURSO as carta_usada, 
m.HORAS_CARTA_CURSO as horas_usadas_contratadas, 
m.VAlOR_ORIGINAL as valor_produto, 
m.DIFERENCA as desconto, 
m.TOTAL_PARCELAS as valor_pagamento,
(SELECT COUNT(*)
        FROM central3.MATRICULA_PARCELA mp 
        WHERE mp.MATRICULA = m.CODIGO
		AND mp.EMPRESA_ID = m.EMPRESA_ID
) as parcelas,
(
    SELECT JSON_ARRAYAGG(
        JSON_OBJECT(
            'num', mp.PARCELA, 
            'val', mp.VALOR, 
            'venc', mp.VENCIMENTO
        )
    )
    FROM central3.MATRICULA_PARCELA mp 
    WHERE mp.MATRICULA = m.CODIGO AND mp.EMPRESA_ID = m.EMPRESA_ID
) as json_parcelas,
m.SITUACAO as status,
fd.DESCRICAO as forma,
m.MOTIVO_DIF as motivo_desconto
FROM central3.MATRICULA m
left join central3.TURMA t on m.TURMA = t.CODIGO AND m.UNIDADE = t.EMPRESA_ID
left join central3.EMPRESA e on m.EMPRESA_ID = e.CODIGO
left join central3.FORMA_PAGAMENTO f on m.FORMA_PAGTO_CURSO = f.FORMA_PAGAMENTO_ID
left join central3.FORMA_PAGAMENTO_DESCRICAO fd on fd.ID = f.DESCRICAO_ID
where m.DT_CADASTRO > "2019-01-01"

