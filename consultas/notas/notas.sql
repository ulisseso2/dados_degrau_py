SELECT 
    nf.id,
    nf.numero,
    nf.rps,
    nf.protocolo,
    nf.data_emissao,
    -- Extração do Destinatário
    ExtractValue(nf.xml_limpo, '//dest/CPF') AS cpf,
    ExtractValue(nf.xml_limpo, '//dest/xNome') AS xNome,
    ExtractValue(nf.xml_limpo, '//dest/email') AS email,
    
    -- Extração de Itens (Concatenando até 5 itens individualmente para evitar erro de XPath dinâmico)
    CONCAT_WS(' | ',
        NULLIF(ExtractValue(nf.xml_limpo, '//det[1]/prod/xProd'), ''),
        NULLIF(ExtractValue(nf.xml_limpo, '//det[2]/prod/xProd'), ''),
        NULLIF(ExtractValue(nf.xml_limpo, '//det[3]/prod/xProd'), ''),
        NULLIF(ExtractValue(nf.xml_limpo, '//det[4]/prod/xProd'), ''),
        NULLIF(ExtractValue(nf.xml_limpo, '//det[5]/prod/xProd'), '')
    ) AS produtos,

    -- Valor Total da Nota
    ExtractValue(nf.xml_limpo, '//total/ICMSTot/vNF') AS valor_total_nota,
    nf.pdf_path AS link_nota,
    nf.chave_acesso,
    nf.resultado_json
FROM (
    -- Subquery para limpar o XML uma única vez e evitar repetição de código
    SELECT *, JSON_UNQUOTE(JSON_EXTRACT(resultado_json, '$.xmlProc')) as xml_limpo
    FROM seducar.notas_fiscais
) nf
   where nf.tipo = "NFe"
   and nf.id not in (6,115,116,117 )