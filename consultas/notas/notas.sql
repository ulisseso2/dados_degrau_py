SELECT
    nf.id,
    nf.tipo,
    nf.school_id,
    CASE nf.school_id
        WHEN 1 THEN 'Degrau'
        WHEN 2 THEN 'Central'
        ELSE CONCAT('School ', nf.school_id)
    END AS empresa,
    nf.numero,
    nf.rps,
    nf.protocolo,
    nf.data_emissao,

    -- Destinatário / Tomador (cliente)
    CASE
        WHEN nf.tipo = 'NFe' THEN ExtractValue(nf.xml_nfe, '//dest/CPF')
        ELSE COALESCE(
            NULLIF(ExtractValue(nf.xml_resposta, '//toma/CPF'), ''),
            NULLIF(ExtractValue(nf.xml_resposta, '//toma/CNPJ'), '')
        )
    END AS cpf,
    CASE
        WHEN nf.tipo = 'NFe' THEN ExtractValue(nf.xml_nfe, '//dest/xNome')
        ELSE ExtractValue(nf.xml_resposta, '//toma/xNome')
    END AS xNome,
    CASE
        WHEN nf.tipo = 'NFe' THEN ExtractValue(nf.xml_nfe, '//dest/email')
        ELSE ExtractValue(nf.xml_resposta, '//toma/email')
    END AS email,

    -- Produtos (NFe) ou descrição do serviço (NFSe)
    CASE
        WHEN nf.tipo = 'NFe' THEN CONCAT_WS(' | ',
            NULLIF(ExtractValue(nf.xml_nfe, '//det[1]/prod/xProd'), ''),
            NULLIF(ExtractValue(nf.xml_nfe, '//det[2]/prod/xProd'), ''),
            NULLIF(ExtractValue(nf.xml_nfe, '//det[3]/prod/xProd'), ''),
            NULLIF(ExtractValue(nf.xml_nfe, '//det[4]/prod/xProd'), ''),
            NULLIF(ExtractValue(nf.xml_nfe, '//det[5]/prod/xProd'), '')
        )
        ELSE COALESCE(
            NULLIF(ExtractValue(nf.xml_resposta, '//serv/xDescServ'), ''),
            NULLIF(ExtractValue(nf.xml_resposta, '//xTribNac'), ''),
            ''
        )
    END AS produtos,

    -- Valor total da nota (NFe: vNF | NFSe-SP: ValorTotalServicos | NFSe-Nacional: vLiq/vServ)
    CASE
        WHEN nf.tipo = 'NFe' THEN ExtractValue(nf.xml_nfe, '//total/ICMSTot/vNF')
        ELSE COALESCE(
            NULLIF(ExtractValue(nf.xml_resposta, '//ValorTotalServicos'), ''),
            NULLIF(ExtractValue(nf.xml_resposta, '//vLiq'), ''),
            NULLIF(ExtractValue(nf.xml_resposta, '//vServ'), ''),
            '0'
        )
    END AS valor_total_nota,

    nf.pdf_path AS link_nota,
    nf.chave_acesso,
    nf.resultado_json,
    nf.xml_resposta
FROM (
    -- Subquery para extrair o XML da NFe (que fica dentro do resultado_json) uma única vez
    SELECT *, JSON_UNQUOTE(JSON_EXTRACT(resultado_json, '$.xmlProc')) AS xml_nfe
    FROM seducar.notas_fiscais
) nf
WHERE nf.id NOT IN (6, 115, 116, 117)
