# 🔄 Reprocessamento de GCLIDs

Esta funcionalidade permite reprocessar GCLIDs que foram marcados como "Não encontrado" no banco de dados, tentando encontrá-los novamente na API do Google Ads.

## 📋 Contexto

Quando o sistema processa GCLIDs, alguns podem não ser encontrados na primeira tentativa por diversos motivos:
- **Delay de disponibilidade**: Dados podem não estar imediatamente disponíveis na API
- **Período de consulta**: GCLID pode ter sido consultado em uma data diferente da real
- **Problemas temporários**: Issues temporários na API do Google Ads
- **Rate limiting**: Limites de consulta podem ter impedido o processamento completo

## 🎯 Como Funciona

### 1. **Identificação**
O sistema identifica todos os GCLIDs marcados como "Não encontrado" no banco de dados SQLite (`gclid_cache.db`).

### 2. **Reprocessamento**
- Remove temporariamente os GCLIDs do cache em memória
- Executa nova consulta na API do Google Ads
- Tenta múltiplas datas para maximizar chances de encontrar
- Salva os resultados encontrados no banco de dados

### 3. **Atualização**
- Substitui "Não encontrado" pelos nomes de campanhas reais
- Atualiza cache em memória e banco de dados
- Mantém histórico com timestamp da última atualização

## 🚀 Como Usar

### No Dashboard Streamlit

1. Acesse a página "Análise de Performance Digital (GA4)"
2. Localize a seção "🔄 Reprocessamento de GCLIDs"
3. Veja as estatísticas de GCLIDs não encontrados
4. Escolha uma das opções:
   - **"Reprocessar Período Atual"**: Apenas GCLIDs do período selecionado
   - **"Reprocessar Todos"**: Todos os GCLIDs não encontrados (pode demorar)

### Via Linha de Comando

#### Script Python:
```bash
# Contar GCLIDs não encontrados
python reprocess_gclids.py --count

# Reprocessar últimos 30 dias
python reprocess_gclids.py --period 30

# Reprocessar últimos 7 dias
python reprocess_gclids.py --period 7

# Reprocessar todos (cuidado - pode demorar muito)
python reprocess_gclids.py --all

# Usar lote personalizado
python reprocess_gclids.py --all --batch-size 200
```

#### Script Bash (mais fácil):
```bash
# Contar GCLIDs não encontrados
./reprocess_gclids.sh count

# Reprocessar últimos 30 dias (padrão)
./reprocess_gclids.sh period

# Reprocessar últimos 7 dias
./reprocess_gclids.sh period 7

# Reprocessar todos (com confirmação)
./reprocess_gclids.sh all
```

## 📊 Monitoramento

### Métricas Disponíveis
- **Total de GCLIDs Não Encontrados**: Quantidade total no banco
- **Não Encontrados no Período**: Quantidade no período selecionado
- **Taxa de Sucesso**: Percentual de GCLIDs encontrados após reprocessamento

### Logs
- Todas as operações são logadas
- Progresso é mostrado em tempo real
- Resultados são reportados ao final

## ⚠️ Considerações Importantes

### Performance
- **Rate Limiting**: Sistema respeita limites da API do Google Ads
- **Batch Processing**: Processa em lotes para evitar sobrecarga
- **Múltiplas Datas**: Tenta diferentes períodos para maximizar sucesso

### Dados
- **Backup Automático**: Dados originais são preservados
- **Rollback**: Em caso de erro, cache original é restaurado
- **Versionamento**: Timestamps mantêm histórico de atualizações

### Recomendações
- **Execute periodicamente**: Especialmente após campanhas novas
- **Monitore logs**: Verifique resultados para identificar padrões
- **Use períodos**: Prefira reprocessar períodos específicos primeiro

## 🔧 Configuração

### Pré-requisitos
- Credenciais válidas do Google Ads (`google-ads.yaml`)
- Arquivo de ambiente configurado (`.env`)
- Cliente Google Ads com permissões adequadas

### Dependências
```python
google-ads
streamlit
pandas
sqlite3
pyyaml
python-dotenv
```

## 📈 Resultados Esperados

Após o reprocessamento, você deve ver:
- ✅ Redução de GCLIDs "Não encontrado"
- 📊 Dados mais precisos nos relatórios
- 🎯 Melhor atribuição de campanhas
- 📈 Relatórios mais completos

## 🐛 Troubleshooting

### Problemas Comuns

**"Cliente Google Ads não disponível"**
- Verifique arquivo `google-ads.yaml`
- Confirme credenciais no `.env`
- Teste conexão com API

**"Nenhum GCLID encontrado"**
- Normal se dados já foram processados
- Verifique se há GCLIDs no período
- Confirme configuração de datas

**"Erro durante reprocessamento"**
- Verifique logs para detalhes
- Cache original é restaurado automaticamente
- Tente novamente com lote menor

### Debug
```bash
# Verificar quantidade de GCLIDs não encontrados
./reprocess_gclids.sh count

# Testar com período pequeno primeiro
./reprocess_gclids.sh period 1

# Verificar logs de erro
tail -f logs/gclid_processing.log
```

## 📝 Notas Técnicas

- **Atomicidade**: Operações são atômicas - ou tudo funciona ou nada muda
- **Idempotência**: Seguro executar múltiplas vezes
- **Escalabilidade**: Suporta milhares de GCLIDs com rate limiting
- **Compatibilidade**: Funciona com estrutura existente sem breaking changes