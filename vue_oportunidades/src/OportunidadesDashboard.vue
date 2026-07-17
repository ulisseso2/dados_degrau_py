<script setup>
/**
 * Dashboard de Oportunidades — porte do _pages/oportunidades.py (Streamlit) para Vue 3.
 *
 * Usa a MESMA query (via GET /api/oportunidades, que lê consultas/oportunidades/oportunidades.sql).
 * A filtragem e as agregações que o pandas fazia agora rodam no cliente, em JS.
 *
 * Dependências: vue, echarts, vue-echarts
 *   npm i echarts vue-echarts
 */
import { ref, computed, onMounted } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart, BarChart, FunnelChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, GridComponent, LegendComponent } from 'echarts/components'

use([CanvasRenderer, PieChart, BarChart, FunnelChart,
     TitleComponent, TooltipComponent, GridComponent, LegendComponent])

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// ---------- estado ----------
const rows = ref([])
const loading = ref(true)
const erro = ref('')

// filtros (equivalentes à sidebar do Streamlit)
const empresa = ref('Degrau')
const dataInicio = ref(hoje())
const dataFim = ref(hoje())
const unidadesSel = ref([])
const etapasSel = ref([])
const modalidadesSel = ref([])
const incluirPrelead = ref(false)
const contatosUnicos = ref(false)
const filtroScore = ref('Todos') // Todos | Com score | Sem score

function hoje() {
  return new Date().toISOString().slice(0, 10)
}

// ---------- carga ----------
onMounted(async () => {
  try {
    const res = await fetch(`${API}/api/oportunidades`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const json = await res.json()
    rows.value = json.data
    // defaults: seleciona tudo, como os multiselect com default=todos
    unidadesSel.value = uniq(rowsEmpresa.value.map(r => r.unidade))
    etapasSel.value = uniq(rowsEmpresa.value.map(r => r.etapa))
    modalidadesSel.value = uniq(rowsEmpresa.value.map(r => r.modalidade))
  } catch (e) {
    erro.value = `Falha ao carregar dados: ${e.message}`
  } finally {
    loading.value = false
  }
})

// ---------- helpers ----------
function uniq(arr) {
  return [...new Set(arr.filter(v => v != null))].sort()
}
function countBy(arr, key) {
  const m = new Map()
  for (const r of arr) {
    const k = r[key] ?? 'Indefinida'
    m.set(k, (m.get(k) ?? 0) + 1)
  }
  return [...m.entries()].map(([name, value]) => ({ name, value }))
}

// opções derivadas
const empresas = computed(() => uniq(rows.value.map(r => r.empresa)))
const rowsEmpresa = computed(() => rows.value.filter(r => r.empresa === empresa.value))
const unidadesOpts = computed(() => uniq(rowsEmpresa.value.map(r => r.unidade)))
const etapasOpts = computed(() => uniq(rowsEmpresa.value.map(r => r.etapa)))
const modalidadesOpts = computed(() => uniq(rowsEmpresa.value.map(r => r.modalidade)))

// ---------- aplicação dos filtros (espelha df_filtrado do Python) ----------
const dadosFiltrados = computed(() => {
  const ini = new Date(dataInicio.value + 'T00:00:00')
  const fim = new Date(dataFim.value + 'T00:00:00')
  fim.setDate(fim.getDate() + 1) // < data_fim + 1 dia, como no Python

  let out = rowsEmpresa.value.filter(r => {
    const c = new Date(r.criacao)
    return c >= ini && c < fim
  })

  const inclNulo = (val, sel) => sel.length === 0 || val == null || sel.includes(val)
  out = out.filter(r => inclNulo(r.unidade, unidadesSel.value))
  out = out.filter(r => inclNulo(r.etapa, etapasSel.value))
  out = out.filter(r => inclNulo(r.modalidade, modalidadesSel.value))

  if (!incluirPrelead.value) out = out.filter(r => r.prelead !== true && r.prelead !== 1)

  if (filtroScore.value === 'Com score') out = out.filter(r => r.total_score != null)
  else if (filtroScore.value === 'Sem score') out = out.filter(r => r.total_score == null)

  if (contatosUnicos.value) {
    out = [...out].sort((a, b) => new Date(b.criacao) - new Date(a.criacao))
    const vistos = new Set()
    out = out.filter(r => (vistos.has(r.email) ? false : vistos.add(r.email)))
  }
  return out
})

// ---------- métricas ----------
const total = computed(() => dadosFiltrados.value.length)
const online = computed(() => dadosFiltrados.value.filter(r => r.modalidade === 'Online').length)
const live = computed(() => dadosFiltrados.value.filter(r => r.modalidade === 'Live').length)
const presencial = computed(() => dadosFiltrados.value.filter(r => r.modalidade === 'Presencial').length)

// ---------- gráficos ----------
const pieModalidade = computed(() => pie('Oportunidades por Modalidade', countBy(dadosFiltrados.value, 'modalidade')))
const pieUnidade = computed(() => pie('Oportunidades por Unidade', countBy(dadosFiltrados.value, 'unidade')))
const pieOrigem = computed(() => pie('Oportunidades por Origem', countBy(dadosFiltrados.value, 'origem')))

const barDia = computed(() => {
  const m = new Map()
  for (const r of dadosFiltrados.value) {
    const d = new Date(r.criacao).toISOString().slice(0, 10)
    m.set(d, (m.get(d) ?? 0) + 1)
  }
  const dados = [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  return {
    title: { text: 'Oportunidades por dia', left: 'center' },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: dados.map(d => d[0]) },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: dados.map(d => d[1]), label: { show: true, position: 'top' } }],
  }
})

const barTopConcursos = computed(() => {
  const dados = countBy(dadosFiltrados.value, 'concurso').sort((a, b) => b.value - a.value)
  const TOP = 15
  let top = dados.slice(0, TOP)
  if (dados.length > TOP) {
    const outros = dados.slice(TOP).reduce((s, d) => s + d.value, 0)
    top = [...top, { name: 'Outros', value: outros }]
  }
  top.reverse()
  return {
    title: { text: `Top ${TOP} Concursos`, left: 'center' },
    tooltip: { trigger: 'axis' },
    grid: { left: 180 },
    xAxis: { type: 'value' },
    yAxis: { type: 'category', data: top.map(d => d.name) },
    series: [{ type: 'bar', data: top.map(d => d.value), label: { show: true, position: 'right' } }],
  }
})

const funil = computed(() => {
  const m = new Map()
  for (const r of dadosFiltrados.value) {
    if (r.etapa == null) continue
    const cur = m.get(r.etapa) ?? { qtd: 0, ordem: r.ordem_etapas }
    cur.qtd += 1
    m.set(r.etapa, cur)
  }
  const dados = [...m.entries()]
    .map(([name, v]) => ({ name, value: v.qtd, ordem: v.ordem }))
    .sort((a, b) => a.ordem - b.ordem)
  return {
    title: { text: 'Funil de Oportunidades por Etapa', left: 'center' },
    tooltip: { trigger: 'item' },
    series: [{
      type: 'funnel', sort: 'none', label: { show: true, formatter: '{b}: {c}' },
      data: dados.map(d => ({ name: d.name, value: d.value })),
    }],
  }
})

const barDono = computed(() => {
  const dados = countBy(dadosFiltrados.value, 'dono').sort((a, b) => b.value - a.value)
  return {
    title: { text: 'Oportunidades por Dono', left: 'center' },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: dados.map(d => d.name), axisLabel: { rotate: 45 } },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: dados.map(d => d.value), label: { show: true, position: 'top' } }],
  }
})

function pie(titulo, dados) {
  return {
    title: { text: titulo, left: 'center' },
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, type: 'scroll' },
    series: [{ type: 'pie', radius: '60%', data: dados, label: { formatter: '{c} ({d}%)' } }],
  }
}

// ---------- tabela pivô concurso x modalidade ----------
const pivotConcursoModalidade = computed(() => {
  const modalidades = uniq(dadosFiltrados.value.map(r => r.modalidade))
  const porConcurso = new Map()
  for (const r of dadosFiltrados.value) {
    const c = r.concurso ?? 'Indefinido'
    if (!porConcurso.has(c)) porConcurso.set(c, {})
    const linha = porConcurso.get(c)
    linha[r.modalidade] = (linha[r.modalidade] ?? 0) + 1
  }
  const linhas = [...porConcurso.entries()].map(([concurso, vals]) => {
    const total = modalidades.reduce((s, m) => s + (vals[m] ?? 0), 0)
    return { concurso, vals, total }
  }).sort((a, b) => b.total - a.total)
  return { modalidades, linhas }
})

// ---------- export CSV (equivale ao download Excel) ----------
function baixarCsv() {
  const cols = ['oportunidade', 'concurso', 'unidade', 'modalidade', 'etapa', 'dono',
    'criacao', 'origem', 'utm_campaign', 'name', 'email', 'telefone', 'total_score']
  const esc = v => `"${String(v ?? '').replace(/"/g, '""')}"`
  const linhas = [cols.join(',')]
  for (const r of dadosFiltrados.value) linhas.push(cols.map(c => esc(r[c])).join(','))
  const blob = new Blob([linhas.join('\n')], { type: 'text/csv;charset=utf-8;' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = 'lista_oportunidades.csv'
  a.click()
}
</script>

<template>
  <div class="dash">
    <h1>🎯 Dashboard Oportunidades</h1>

    <p v-if="loading">Carregando…</p>
    <p v-else-if="erro" class="erro">{{ erro }}</p>

    <div v-else class="layout">
      <!-- Sidebar de filtros -->
      <aside class="sidebar">
        <label>Empresa</label>
        <select v-model="empresa">
          <option v-for="e in empresas" :key="e" :value="e">{{ e }}</option>
        </select>

        <label>Início</label>
        <input type="date" v-model="dataInicio" />
        <label>Fim</label>
        <input type="date" v-model="dataFim" />

        <label>Unidade</label>
        <select multiple v-model="unidadesSel" size="5">
          <option v-for="u in unidadesOpts" :key="u" :value="u">{{ u }}</option>
        </select>

        <label>Etapa</label>
        <select multiple v-model="etapasSel" size="5">
          <option v-for="e in etapasOpts" :key="e" :value="e">{{ e }}</option>
        </select>

        <label>Modalidade</label>
        <select multiple v-model="modalidadesSel" size="4">
          <option v-for="m in modalidadesOpts" :key="m" :value="m">{{ m }}</option>
        </select>

        <label><input type="checkbox" v-model="incluirPrelead" /> Incluir Preleads</label>
        <label><input type="checkbox" v-model="contatosUnicos" /> Contatos únicos</label>

        <label>Total Score</label>
        <select v-model="filtroScore">
          <option>Todos</option><option>Com score</option><option>Sem score</option>
        </select>
      </aside>

      <!-- Conteúdo -->
      <main class="content">
        <div class="metrics">
          <div class="metric"><span>Total</span><strong>{{ total }}</strong></div>
          <div class="metric"><span>Online</span><strong>{{ online }}</strong></div>
          <div class="metric"><span>Live</span><strong>{{ live }}</strong></div>
          <div class="metric"><span>Presencial</span><strong>{{ presencial }}</strong></div>
        </div>

        <section class="grid2">
          <v-chart class="chart" :option="pieModalidade" autoresize />
          <v-chart class="chart" :option="barDia" autoresize />
          <v-chart class="chart" :option="pieUnidade" autoresize />
          <v-chart class="chart" :option="funil" autoresize />
          <v-chart class="chart" :option="barTopConcursos" autoresize />
          <v-chart class="chart" :option="pieOrigem" autoresize />
          <v-chart class="chart" :option="barDono" autoresize />
        </section>

        <h3>Oportunidades por Concurso / Modalidade</h3>
        <table class="pivot">
          <thead>
            <tr>
              <th>Concurso</th>
              <th v-for="m in pivotConcursoModalidade.modalidades" :key="m">{{ m }}</th>
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="l in pivotConcursoModalidade.linhas" :key="l.concurso">
              <td>{{ l.concurso }}</td>
              <td v-for="m in pivotConcursoModalidade.modalidades" :key="m">{{ l.vals[m] ?? 0 }}</td>
              <td><strong>{{ l.total }}</strong></td>
            </tr>
          </tbody>
        </table>

        <button class="download" @click="baixarCsv">📥 Baixar Lista Detalhada (CSV)</button>
      </main>
    </div>
  </div>
</template>

<style scoped>
.dash { font-family: system-ui, sans-serif; padding: 1rem; }
.layout { display: flex; gap: 1.5rem; }
.sidebar { width: 240px; display: flex; flex-direction: column; gap: .4rem; flex-shrink: 0; }
.sidebar label { font-size: .85rem; font-weight: 600; margin-top: .5rem; }
.sidebar select, .sidebar input[type="date"] { width: 100%; }
.content { flex: 1; min-width: 0; }
.metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 1rem; }
.metric { background: #f1f5f9; border-radius: 8px; padding: 1rem; display: flex; flex-direction: column; }
.metric span { font-size: .8rem; color: #64748b; }
.metric strong { font-size: 1.8rem; }
.grid2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem; }
.chart { height: 340px; width: 100%; }
.pivot { width: 100%; border-collapse: collapse; margin: .5rem 0 1rem; font-size: .85rem; }
.pivot th, .pivot td { border: 1px solid #e2e8f0; padding: 4px 8px; text-align: right; }
.pivot th:first-child, .pivot td:first-child { text-align: left; }
.download { padding: .6rem 1rem; background: #457B9D; color: #fff; border: 0; border-radius: 6px; cursor: pointer; }
.erro { color: #b91c1c; }
</style>
