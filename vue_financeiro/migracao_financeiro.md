# Migração da página `_pages/financeiro.py` (Streamlit) → Vue.js

Foco deste documento: **tabelas** e **exportação**, que são as partes mais delicadas.
Os gráficos (Plotly) seguem o mesmo padrão já descrito para a página de Oportunidades
(ECharts/Chart.js) e estão resumidos no final.

---

## 0. A notícia mais importante: o `st_aggrid` usava recursos PAGOS

O `st_aggrid` **não é uma tecnologia do Streamlit** — é apenas um _wrapper_ Python em volta do
**AG Grid**, uma biblioteca JavaScript. O detalhe que importa para o orçamento: o código atual
usa `enable_enterprise_modules=True` e depende de recursos **exclusivos do AG Grid Enterprise
(licença paga)**:

| Recurso usado hoje | No AG Grid |
|---|---|
| `rowGroup=True` (agrupar por centro_custo / categoria) | **Enterprise (pago)** |
| `aggFunc="sum"` + `autoGroupColumnDef` + `agGroupCellRenderer` | **Enterprise (pago)** |
| `groupIncludeFooter` / `groupIncludeTotalFooter` (subtotais/total) | **Enterprise (pago)** |
| Ordenar / filtrar / CSV / cell renderers / pinned rows | Community (grátis) |

Ou seja, **o agrupamento em linha com subtotais é a única coisa que era paga.** E ela NÃO
precisa do AG Grid — várias libs Vue gratuitas (MIT) fazem isso nativamente.

### ✅ Solução sem custo (recomendada)

**Não use o AG Grid.** Para a tabela hierárquica de despesas, use uma destas libs gratuitas:

| Opção grátis (MIT) | Agrupamento + subtotais | Esforço | Observação |
|---|---|---|---|
| **PrimeVue `TreeTable`** | ✅ nativo (hierárquico) | **Baixo** | Feito para dados em árvore centro→categoria→item |
| **PrimeVue `DataTable`** (rowGroup subheader + expansível + column footer) | ✅ nativo | Baixo | Subtotais no footer do grupo; expandir/recolher pronto |
| **TanStack Table (Vue)** | ✅ `getGroupedRowModel` + aggregation | Médio | *Headless*: você monta o HTML/estilo da tabela |

**Recomendação: PrimeVue** (`TreeTable` ou `DataTable`). É a rota gratuita mais próxima do
resultado atual com menos código — já traz agrupamento, subtotais por grupo, total geral no
footer, expand/collapse e export CSV embutidos. TanStack fica como alternativa se quiserem
controle total do markup. Ver §2.

> **Importante:** só o *agrupamento* era pago. **CSV e Excel multi-aba continuam grátis**
> (`xlsx`/SheetJS, §5) em qualquer cenário. As demais tabelas da página (§1.2–1.4) são planas e
> rodam em qualquer tabela gratuita, inclusive `<table>` puro.

---

## 1. Inventário das tabelas da página

A página tem **4 tabelas**, com complexidades bem diferentes:

### 1.1. Tabela hierárquica de Despesas — a mais complexa
- **Origem:** `tabela_agrupada` = groupby de `centro_custo, categoria_pedido_compra,
  descricao_pedido_compra, data_vencimento, data_pagamento` somando `valor_corrigido`.
- **Recursos:** 2 níveis de agrupamento em linha, subtotais por grupo, total geral no rodapé,
  valor formatado em R$, datas dd/MM/yyyy.
- **Migração:** PrimeVue `TreeTable`/`DataTable` (grátis, ver §2). Era o único ponto que dependia
  de recurso pago no AG Grid; com PrimeVue deixa de haver custo.

### 1.2. Tabela "Detalhamento das Contas a Pagar" (`st.dataframe` + column_config)
- Tabela simples, plana, ordenada por vencimento, com formatação de moeda e data por coluna.
- **Migração:** qualquer tabela gratuita (PrimeVue `DataTable` ou até `<table>` puro). Sem grouping.

### 1.3. Tabela "Saldos Atuais das Contas" (`st.dataframe`)
- Duas colunas, valores já formatados. Trivial.

### 1.4. Extrato Detalhado (`st.dataframe` com linha TOTAL)
- Plana, mas com **duas particularidades**:
  - **Saldo corrente** = `saldo_anterior + valor.cumsum()` → precisa reproduzir o `cumsum` em JS.
  - **Linha de TOTAL** ao final → use o slot `#footer` do PrimeVue `DataTable` (§4), não concatene no array.

---

## 2. Tabela hierárquica de despesas com PrimeVue (grátis)

Instalação:
```bash
npm i primevue
```

Há duas abordagens equivalentes ao que o AG Grid fazia. Escolha uma:

### Opção A — `TreeTable` (dados em árvore)
Melhor quando você quer a hierarquia centro→categoria→item explícita, com expandir/recolher por nó.
O backend (ou um transform em JS) monta os dados no formato de árvore que o PrimeVue espera:

```js
// cada nó: { key, data: {...colunas...}, children: [...] }
// nível 1 = centro_custo, nível 2 = categoria, folhas = itens.
// Os subtotais são calculados ao montar a árvore (soma dos filhos) e ficam em node.data.valor_total.
```
```html
<TreeTable :value="arvore" :expandedKeys="expandidos">
  <Column field="rotulo" header="Centro de Custo / Categoria" expander />
  <Column field="descricao_pedido_compra" header="Histórico" />
  <Column field="data_vencimento_parcela" header="Vencimento">
    <template #body="{ node }">{{ formatarData(node.data.data_vencimento_parcela) }}</template>
  </Column>
  <Column field="valor_total" header="Valor">
    <template #body="{ node }">{{ formatarReais(node.data.valor_total) }}</template>
  </Column>
</TreeTable>
```

### Opção B — `DataTable` com `rowGroup="subheader"` + footer de grupo
Mais próxima do visual "groupRows" do AG Grid: linhas de subcabeçalho por grupo, subtotal no
`groupfooter` e total geral no `footer`. Bom para agrupamento por **um** nível (ex.: centro de
custo); para o segundo nível (categoria) dá para aninhar ou concatenar a chave.

```html
<DataTable :value="linhas" rowGroupMode="subheader" groupRowsBy="centro_custo"
           sortMode="single" sortField="centro_custo" :expandableRowGroups="true"
           v-model:expandedRowGroups="expandidos">
  <template #groupheader="{ data }"><strong>{{ data.centro_custo }}</strong></template>

  <Column field="categoria_pedido_compra" header="Categoria" />
  <Column field="descricao_pedido_compra" header="Histórico" />
  <Column field="data_vencimento_parcela" header="Vencimento">
    <template #body="{ data }">{{ formatarData(data.data_vencimento_parcela) }}</template>
  </Column>
  <Column field="valor_total" header="Valor">
    <template #body="{ data }">{{ formatarReais(data.valor_total) }}</template>
  </Column>

  <template #groupfooter="{ data }">
    Subtotal {{ data.centro_custo }}: {{ formatarReais(subtotalPorCentro[data.centro_custo]) }}
  </template>
</DataTable>
```

Notas de equivalência com o código Streamlit:
- `valueFormatter` do AG Grid (o antigo `JsCode`) → `<template #body>` da coluna (acima) ou uma
  função de formatação. Sem `allow_unsafe_jscode`, sem string de JS.
- `groupIncludeFooter` (subtotal por grupo) → `#groupfooter` (Opção B) ou o valor agregado no nó
  pai (Opção A). Os subtotais você calcula em JS com um `groupby` (um `Map` somando `valor_total`).
- `groupIncludeTotalFooter` (total geral) → slot `#footer` da tabela / do `<Column>`.
- `groupDefaultExpanded=0` (recolhido) → `expandedKeys`/`expandedRowGroups` começando vazio.

> **Alternativa headless:** se preferir controle total do HTML, **TanStack Table** (`npm i
> @tanstack/vue-table`) faz o mesmo com `getGroupedRowModel()` + `aggregationFn: 'sum'`, mas você
> escreve o markup da tabela à mão.

---

## 3. Formatação de moeda e data (substitui `formatar_reais`)

`formatar_reais` (Python) vira uma função JS reutilizável (ex.: em um `utils.js`):

```js
const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })
export const formatarReais = v => (v == null ? '' : brl.format(v))

export const formatarData = v => {
  if (!v) return ''
  const d = new Date(v)
  return d.toLocaleDateString('pt-BR')   // dd/mm/yyyy
}
```

> **Fuso horário:** o Python faz `tz_localize('America/Sao_Paulo')`. Prefira que o **backend
> devolva as datas já como string ISO** (ou só `YYYY-MM-DD` quando a hora não importa, como nas
> parcelas). Assim você evita o deslocamento de fuso que o `new Date()` do browser aplicaria.

---

## 4. Linha de TOTAL do Extrato (saldo corrente + pinned row)

O extrato calcula saldo acumulado e adiciona uma linha "TOTAL". Em JS:

```js
// saldo corrente (equivale a saldo_anterior + valor.cumsum())
let acc = saldoAnterior
const linhas = movimentos
  .slice().sort((a, b) => new Date(a.data) - new Date(b.data))
  .map(m => {
    acc += m.valor
    return {
      ...m,
      entrada: m.valor > 0 ? m.valor : null,
      saida:   m.valor < 0 ? Math.abs(m.valor) : null,
      saldo:   acc,
    }
  })

// linha de total NÃO vai no array de linhas — vai no rodapé da tabela:
const totais = {
  entrada: linhas.reduce((s, l) => s + (l.entrada ?? 0), 0),
  saida:   linhas.reduce((s, l) => s + (l.saida   ?? 0), 0),
  saldo:   linhas.at(-1)?.saldo ?? saldoAnterior,
}
// PrimeVue DataTable: <template #footer> TOTAL ... {{ formatarReais(totais.saldo) }} </template>
// (em <ColumnGroup>/<Row>/<Column> para alinhar por coluna, se quiser)
```

Em uma `<table>` simples, o mesmo cai em um `<tfoot>`. O importante é **calcular os totais a
partir dos valores numéricos ANTES de formatar** (o Python faz exatamente isso: soma primeiro,
formata depois — linhas 772-786 do original).

---

## 5. Exportação

### 5.1. Excel com múltiplas abas (substitui `xlsxwriter`)

O Python gera um `.xlsx` com 3 abas (Despesas Detalhadas / Totais por Centro Custo / Totais por
Categoria). No front, use **SheetJS (`xlsx`)** — grátis e suporta múltiplas abas:

```bash
npm i xlsx
```
```js
import * as XLSX from 'xlsx'

function exportarExcel(detalhado, totaisCC, totaisCat, nomeArquivo) {
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(detalhado), 'Despesas Detalhadas')
  XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(totaisCC),  'Totais por Centro Custo')
  XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(totaisCat), 'Totais por Categoria')
  XLSX.writeFile(wb, nomeArquivo)   // dispara o download no browser
}
```
Os `totaisCC` / `totaisCat` você monta com um `groupby` em JS (um `Map` somando `valor_total`),
igual às linhas 299-312 do Python. Como a exportação é feita com SheetJS (e não pela tabela),
ela funciona igual independentemente da lib de tabela escolhida.

### 5.2. CSV

O PrimeVue `DataTable` já traz export CSV embutido (`ref` + `exportCSV()`), grátis. Se a tabela
não tiver, o mesmo SheetJS gera CSV (`XLSX.writeFile(wb, 'arquivo.csv')`).

### 5.3. PDF (substitui `reportlab`) — recomendação diferente

O PDF do extrato (linhas 863-1015) é elaborado: cabeçalho estilizado, tabela de resumo, tabela
detalhada com quebra de linha, cores, linha de total. Reproduzir isso em `jsPDF + jspdf-autotable`
é possível, porém trabalhoso e com menos controle tipográfico.

**Recomendação:** **mantenha a geração do PDF no backend**, reaproveitando o código `reportlab`
que já existe e já está testado. Exponha um endpoint que recebe os filtros (ou os dados já
filtrados) e devolve o PDF:

```
POST /api/financeiro/extrato/pdf   ->  application/pdf
```
No Vue, é só um `fetch` que baixa o blob:
```js
const res = await fetch(`${API}/api/financeiro/extrato/pdf`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ empresa, periodo, contas }),
})
const blob = await res.blob()
const a = document.createElement('a')
a.href = URL.createObjectURL(blob); a.download = 'extrato.pdf'; a.click()
```
Vantagens: fidelidade total ao PDF atual, zero reescrita, e o cálculo de saldos/totais fica em
um só lugar. Se você **precisar** que o PDF seja 100% client-side (sem backend), aí sim vá de
`jsPDF + jspdf-autotable` — a estrutura `table_data` que o Python monta (linha 953) mapeia bem
para o formato que o `autotable` espera.

---

## 6. Filtros em cascata

A sidebar tem filtros dependentes: Unidade Estratégica → Unidade de Negócio → Centro de Custo →
Categoria → Conta Bancária (cada nível filtra as opções do próximo, linhas 88-131). Em Vue isso
é uma cadeia de `computed`:

```js
const opcoesUN = computed(() =>
  uniq(base.value.filter(r => ueSel.value.includes(r.unidade_estrategica))
                 .map(r => r.unidade_negocio)))
// ...e assim por diante, cada nível dependendo da seleção anterior.
```
Há ainda **dois conjuntos independentes de filtros** (a análise principal por _pagamento_ e a
análise "Contas a Pagar" por _vencimento_, que só respeita o filtro de empresa) — mantenha-os
como dois blocos de estado separados, exatamente como o Python faz com `df_filtrado` vs
`df_apagar_filtrado`.

---

## 7. Gráficos (resumo)

Todos são Plotly (`px.pie`, `px.bar`) → ECharts/Chart.js, mesmo padrão da página de Oportunidades:

| Gráfico Python | Equivalente |
|---|---|
| Pizza "Situação das Parcelas" com `color_discrete_map` | ECharts pie + `itemStyle.color` pelo mapa de cores |
| Barras horizontais por Centro de Custo / Conta / Unidade | ECharts bar `type:'bar'` horizontal |
| Pizza "rosca" Tipo de Movimento (`hole=0.3`) | ECharts pie com `radius: ['30%','60%']` |
| Barras empilhadas Conta × Tipo (`barmode='stack'`) | ECharts bar com `stack: 'total'` |

O `mapa_cores` (linha 164) passa direto: em ECharts use `data: [{name, value, itemStyle:{color}}]`.

---

## 8. Estimativa de esforço

| Bloco | Complexidade | Observação |
|---|---|---|
| Tabelas simples (contas a pagar, saldos, extrato) | Baixa | PrimeVue `DataTable` ou `<table>` |
| Tabela hierárquica de despesas | **Média** | PrimeVue `TreeTable`/`DataTable` (grátis) |
| Export Excel multi-aba | Baixa | SheetJS resolve |
| Export PDF | Baixa (se manter no backend) / Alta (se client-side) | **Recomendo manter no backend** |
| Filtros em cascata + estado duplo | Média | `computed` chains |
| Gráficos | Baixa | Padrão já conhecido |

**Custo de licença: zero.** A única parte que era paga (agrupamento em linha do AG Grid) é
coberta pelo PrimeVue (MIT) sem custo. Toda a stack sugerida — PrimeVue, ECharts/Chart.js,
SheetJS — é gratuita/open source.
