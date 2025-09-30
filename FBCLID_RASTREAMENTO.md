# Rastreamento de Campanhas do Facebook com FBclids

Este documento explica como utilizar o sistema de rastreamento de FBclids (Facebook Click IDs) para identificar as campanhas que geraram cliques e conversões no seu site.

## Como funciona o rastreamento de FBclids

O Facebook/Meta adiciona um parâmetro chamado `fbclid` às URLs quando um usuário clica em um anúncio. Este parâmetro pode ser capturado no seu site e usado para identificar qual campanha gerou o clique.

### Formato do FBclid segundo a Meta

De acordo com a [documentação oficial da Meta](https://developers.facebook.com/docs/marketing-api/conversions-api/parameters/fbp-and-fbc/), o FBclid deve ser formatado no seguinte padrão para uso com a API de Conversões:

fb.subdomainIndex.creationTime.fbclid

Onde:

- `fb` é sempre o prefixo
- `subdomainIndex` indica em qual domínio o cookie está definido ("com" = 0, "example.com" = 1, "www.example.com" = 2)
- `creationTime` é o timestamp em milissegundos de quando o FBclid foi capturado
- `fbclid` é o valor original do parâmetro

## Arquivos do Sistema de Rastreamento

O sistema de rastreamento de FBclids consiste nos seguintes arquivos:

1. `fbclid_db.py` - Gerencia o banco de dados SQLite para armazenar FBclids e informações de campanha
2. `facebook_api_utils.py` - Contém funções para interagir com a API do Facebook/Meta
3. `migrate_fbclid_format.py` - Script para migrar FBclids existentes para o formato da Meta
4. `configure_pixel_id.py` - Script para configurar o Pixel ID do Facebook
5. `clean_fbclid_db.py` - Script para limpar o banco de dados de FBclids (manter backups)

## Configuração do Sistema

Para configurar o sistema de rastreamento de FBclids, siga os passos abaixo:

### 1. Configure o Pixel ID do Facebook

O Pixel ID é necessário para consultar informações de campanhas a partir de FBclids.

```bash
python configure_pixel_id.py
```

### 2. Migre os FBclids existentes para o formato da Meta

```bash
python migrate_fbclid_format.py
```

### 3. Limpe o banco de dados de FBclids de teste (opcional)

Se você tiver dados de teste no banco de dados, pode limpá-los antes de usar em produção:

```bash
python clean_fbclid_db.py
```

## Usando o Dashboard para Consultar Campanhas

Após configurar o sistema, você pode usar o dashboard para consultar campanhas do Facebook:

1. Acesse a página "Análise de Campanhas - Meta (Facebook Ads)"
2. Na seção "Auditoria de Conversões com FBCLID", clique no botão "Consultar Campanhas no Facebook"
3. O sistema consultará a API do Facebook/Meta para obter informações de campanhas para cada FBclid

### Usando o Botão "Converter FBclids para Formato Meta"

Se você tiver FBclids que não estão no formato correto, pode usar o botão "Converter FBclids para Formato Meta" para convertê-los:

1. Acesse a página "Análise de Campanhas - Meta (Facebook Ads)"
2. Na seção "Auditoria de Conversões com FBCLID", clique no botão "Converter FBclids para Formato Meta"
3. O sistema converterá todos os FBclids para o formato da Meta

## Limitações Técnicas

- A API do Facebook/Meta não fornece uma forma direta de consultar informações de campanha a partir de FBclids
- A implementação atual usa a API de Conversões da Meta para tentar identificar as campanhas com base nos FBclids
- A taxa de sucesso depende da configuração correta do Pixel do Facebook e da implementação da API de Conversões

## Melhores Práticas

1. **Utilize o Pixel do Facebook**: Instale o Pixel do Facebook no seu site para melhorar o rastreamento de conversões
2. **Adicione parâmetros UTM**: Utilize parâmetros UTM em seus links para facilitar o rastreamento de campanhas
3. **Implemente a API de Conversões**: Para um rastreamento mais completo, implemente a API de Conversões da Meta no seu site

## Referências

- [Documentação da API de Conversões da Meta](https://developers.facebook.com/docs/marketing-api/conversions-api/)
- [Parâmetros FBP e FBC](https://developers.facebook.com/docs/marketing-api/conversions-api/parameters/fbp-and-fbc/)
- [Configurações de cookies para o Pixel da Meta](https://www.facebook.com/business/help/471978536642445)
