# Dashboard Oportunidades — versão Vue.js

Porte da página Streamlit `_pages/oportunidades.py` para Vue 3, **reaproveitando a mesma query**
(`consultas/oportunidades/oportunidades.sql`).

## Arquitetura

O Streamlit é backend + frontend no mesmo processo Python. O Vue é só frontend, então dividimos:

- **`api.py`** — backend FastAPI. Roda o mesmo `.sql`, devolve JSON. Cache de 10 min (igual ao `@st.cache_data`).
- **`src/OportunidadesDashboard.vue`** — a página. Filtros, KPIs, gráficos (ECharts) e tabela/export.
  A filtragem/agregação que o pandas fazia agora roda em JS no navegador.

## Rodar

Backend:
```bash
pip install fastapi uvicorn sqlalchemy mysql-connector-python python-dotenv
uvicorn vue_oportunidades.api:app --reload --port 8000   # lê o .env da raiz
```

Frontend (dentro de um projeto Vite + Vue já existente):
```bash
npm i echarts vue-echarts
# copie src/OportunidadesDashboard.vue e registre-o numa rota
```

## O que foi portado

KPIs (total/online/live/presencial), filtros de empresa, período, unidade, etapa, modalidade,
preleads, contatos únicos e score; gráficos de pizza (modalidade/unidade/origem), barras
(por dia, top concursos, por dono), funil por etapa, tabela pivô concurso×modalidade e export CSV.

Não portados (extras da versão Streamlit, fáceis de replicar seguindo o mesmo padrão):
drill-down dinâmico, seção de pontuação P1/P2, facetas por unidade, tabela concurso×etapa/origem.
