# Roteiro de Implementação — Pipeline Automatizado de Relatórios com Claude

> **Projeto:** Relatórios diários/semanais automatizados de Tráfego Pago + Orgânico  
> **Marcas:** Central de Concursos e Degrau Cultural  
> **Data:** Março 2026  
> **Baseado em:** `documents/arquitetura_pipeline_trafego_pago.pdf` e `documents/arquitetura_pipeline_organico.pdf`

---

## 📋 Inventário: O que Já Existe no Projeto

### ✅ Google Ads — Integração COMPLETA
| Item | Status | Arquivo |
|------|--------|---------|
| SDK `google-ads` instalado (v27.0.0) | ✅ | `requirements.txt` |
| Credenciais **Degrau** (customer_id `4934481887`) | ✅ | `google-ads.yaml` |
| Credenciais **Central** (customer_id `1646681121`) | ✅ | `google-ads_central.yaml` |
| Query GAQL por campanha (custo, impressões, cliques, CTR, CPC, conversões, CPA) | ✅ | `_pages/gads_face_combinado.py` |
| Inicialização híbrida (Secrets + YAML) | ✅ | `_pages/gads_face_combinado.py` |
| Rastreamento GCLID + SQLite | ✅ | `gclid_db.py`, `gclid_db_central.py` |

### ✅ Meta Ads — Integração COMPLETA
| Item | Status | Arquivo |
|------|--------|---------|
| SDK `facebook-business` instalado (v23.0.0) | ✅ | `requirements.txt` |
| Credenciais (App ID, Secret, Token, Ad Account ID) | ✅ | `.facebook_credentials.env` |
| Query de insights por campanha (spend, impressões, cliques, CTR, CPC, conversões, CPA) | ✅ | `_pages/gads_face_combinado.py` |
| Inicialização híbrida (Secrets + .env) | ✅ | `_pages/gads_face_combinado.py` |
| Rastreamento FBCLID + SQLite | ✅ | `fbclid_db.py`, `fbclid_utils.py` |

### ✅ Google Analytics — Credenciais Configuradas
| Item | Status | Arquivo |
|------|--------|---------|
| SDK `google-analytics-data` instalado (v0.18.19) | ✅ | `requirements.txt` |
| Service Account **Degrau** | ✅ | `gcp_credentials.json` |
| Service Account **Central** | ✅ | `gcp_credentials_central.json` |

### ❌ O que NÃO Existe Ainda
| Item | Prioridade |
|------|-----------|
| Integração com Claude API (Anthropic) | 🔴 Alta |
| Collector de criativos (imagens/textos) do Google Ads e Meta | 🟡 Média |
| Collector Instagram Graph API (orgânico) | 🟡 Média |
| Collector YouTube Data API | 🟡 Média |
| Collector TikTok | 🟢 Baixa |
| Collector Google Search Console | 🟡 Média |
| Collector GA4 (blog) | 🟡 Média |
| Sistema de entrega (e-mail/Slack/WhatsApp) | 🟡 Média |
| CRON/agendamento automatizado | 🟡 Média |
| Histórico de relatórios (JSON/SQLite) | 🟢 Baixa |
| Página Streamlit para visualizar relatórios IA | 🔴 Alta |

---

## 🗺️ Fases de Implementação

### FASE 1 — Pipeline de Tráfego Pago (Prioridade Máxima)
> **Objetivo:** Relatório diário automatizado das campanhas Google Ads + Meta Ads analisado pelo Claude  
> **Prazo sugerido:** Semana 1-2

#### 1.1 Instalar dependência do Claude
```bash
pip install anthropic>=0.40.0
```
Adicionar ao `requirements.txt` e `requirements_production.txt`.

#### 1.2 Criar módulo `collectors/google_ads_collector.py`
**Reutilizar** as funções que já existem em `_pages/gads_face_combinado.py`:
- `init_google_ads_client()` — já pronta
- `get_google_ads_campaign_data()` — já pronta
- **Adicionar:** coleta para **ambas as contas** (Degrau + Central) em uma única execução
- **Adicionar:** métricas adicionais do PDF: `search_impression_share`, `conversion_rate`
- **Adicionar:** breakdown por grupo de anúncio e palavra-chave (para análise mais profunda)

```python
# Ações:
# 1. Extrair funções de gads_face_combinado.py para módulo compartilhado
# 2. Adicionar query para Central (google-ads_central.yaml) 
# 3. Adicionar métricas extras no SELECT da GAQL
# 4. Formatar output como texto tabular para o Claude
```

#### 1.3 Criar módulo `collectors/meta_ads_collector.py`
**Reutilizar** as funções de `_pages/gads_face_combinado.py`:
- `init_facebook_api()` — já pronta
- `get_facebook_campaign_insights()` — já pronta
- **Adicionar:** métricas extras do PDF: `reach`, `frequency`, `cpm`, `video_p25_watched_actions`
- **Adicionar:** coleta de **ambas as contas** (Central + Degrau) se houver contas separadas

```python
# Ações:
# 1. Extrair funções de gads_face_combinado.py para módulo compartilhado
# 2. Adicionar campos: reach, frequency, cpm
# 3. Adicionar level="ad" para granularidade maior
# 4. Formatar output como texto tabular para o Claude
```

#### 1.4 Criar módulo `analysis/claude_client.py`
Integração com a API do Claude conforme o PDF.

```python
# Conteúdo:
# 1. Inicialização do client Anthropic (API key via .env ou Secrets)
# 2. System prompt de analista de tráfego pago (copiar do PDF)
# 3. Função analisar_campanhas(dados_consolidados) → str
# 4. Função para formatar/consolidar dados de ambas plataformas
```

**System prompt:** usar exatamente o do PDF (seção 4.2) — analista sênior de tráfego pago, estrutura de 6 seções (Resumo Executivo, Alertas, Top 5, Bottom 5, Recomendações, Comparação).

**Modelo:** `claude-sonnet-4-20250514`  
**Max tokens:** 4000  
**Custo estimado:** ~US$ 0,04/execução (~US$ 1,20/mês)

#### 1.5 Criar módulo `analysis/prompts.py`
Centralizar todos os prompts:
- `SYSTEM_PROMPT_TRAFEGO_PAGO` (do PDF)
- `SYSTEM_PROMPT_CRIATIVOS` (do PDF, seção 11.3)
- Templates de formatação dos dados

#### 1.6 Criar `pipeline_trafego_pago.py` (orquestrador)
```python
# Fluxo:
# 1. Coletar dados Google Ads (Degrau + Central)
# 2. Coletar dados Meta Ads (Degrau + Central)
# 3. Consolidar em formato tabular 
# 4. Enviar para Claude API
# 5. Receber análise
# 6. Salvar relatório (JSON/txt em data/historico/)
# 7. Entregar via e-mail (ou outro canal)
```

#### 1.7 Criar sistema de entrega
Escolher **um canal** para começar (recomendação: e-mail via SendGrid):
- `delivery/email_sender.py` — SendGrid (mais profissional)
- **Alternativa:** Slack webhook (mais simples, sem custo)
- **Alternativa:** WhatsApp via Twilio

**Credenciais necessárias:**
| Canal | Credencial | Como obter |
|-------|-----------|-----------|
| SendGrid | API Key | app.sendgrid.com |
| Slack | Webhook URL | api.slack.com/apps → Incoming Webhooks |
| WhatsApp | Twilio SID + Token | console.twilio.com |

#### 1.8 Configurar agendamento CRON
```bash
# Executar todo dia às 06:00 BRT
0 6 * * * cd /home/ulisses/dados_degrau_py && python pipeline_trafego_pago.py >> logs/pipeline_$(date +\%F).log 2>&1
```

---

### FASE 2 — Análise de Criativos com Vision (Semana 3)

#### 2.1 Coletar criativos Meta Ads
- Puxar `image_url`, `thumbnail_url`, `body`, `title` dos ads ativos
- Converter imagens para base64
- Vincular aos KPIs do ad

#### 2.2 Coletar criativos Google Ads
- Responsive Search Ads: headlines + descriptions
- Performance Max: imagens via `asset_group_asset`
- Vincular ao performance label

#### 2.3 Enviar para Claude Vision
- Analisar **apenas Top 5 + Bottom 5** por CPA (economia de custo)
- System prompt específico para análise de criativos (seção 11.3 do PDF)
- Custo adicional: ~US$ 0,05/dia

---

### FASE 3 — Pipeline Orgânico: Redes Sociais (Semana 4-5)

#### 3.1 Collector Instagram (`collectors/instagram.py`)
**Pré-requisitos:**
- Token do Business Manager (já existe para Meta Ads — mesmo token!)
- IG Business Account ID (vincular no Business Manager)
- Permissões: `instagram_basic`, `instagram_manage_insights`, `pages_read_engagement`

**Métricas:** alcance, impressões, seguidores, engajamento, saves por post

#### 3.2 Collector Facebook Pages (`collectors/facebook_pages.py`)
**Pré-requisitos:**
- Mesmo token do Business Manager
- Page ID das páginas da Central e Degrau

**Métricas:** page_impressions, page_engaged_users, page_fans, reações/comentários por post

#### 3.3 Collector YouTube (`collectors/youtube.py`)
**Pré-requisitos:**
- OAuth2 (mesmo projeto Google Cloud do Google Ads — reaproveitar)
- Habilitar YouTube Data API v3 + YouTube Analytics API
- Channel IDs dos canais

**Métricas:** views, watch time, CTR thumbnail, inscritos, retenção

#### 3.4 Collector TikTok (OPCIONAL)
**Recomendação:** começar com export manual de CSV do TikTok Analytics.  
Migrar para TikAPI (~US$ 30/mês) ou API oficial quando justificar.

#### 3.5 Prompts para Social (`analysis/prompts_social.py`)
Usar `SYSTEM_PROMPT_SOCIAL` do PDF orgânico (seção 5.1) — análise cross-platform.

---

### FASE 4 — Pipeline Orgânico: Blog + SEO (Semana 5-6)

#### 4.1 Collector GA4 (`collectors/google_analytics.py`)
**Pré-requisitos:**
- Service Account já existe (`gcp_credentials.json` / `gcp_credentials_central.json`)  
- **Ação:** verificar se tem permissão de Viewer na propriedade GA4
- Habilitar Google Analytics Data API no Google Cloud (se ainda não)

**Métricas:** sessões, usuários, pageviews, duração média, bounce rate, conversões por página

#### 4.2 Collector Search Console (`collectors/search_console.py`)
**Pré-requisitos:**
- Propriedade verificada no Google Search Console  
- Service Account com permissão na propriedade
- Habilitar Search Console API no Google Cloud

**Métricas:** cliques, impressões, CTR, posição média, queries, páginas
> ⚠️ Dados do Search Console têm delay de 2-3 dias — buscar `d-3`

#### 4.3 Prompts para SEO (`analysis/prompts_seo.py`)
Usar `SYSTEM_PROMPT_SEO` do PDF orgânico (seção 5.2) — quick wins, canibalização, oportunidades.

#### 4.4 Orquestrador orgânico
```python
# pipeline_organico.py
# Frequência: semanal (segunda-feira 07h)
# Fluxo: 6 APIs em paralelo → consolidar → Claude → entregar
```

---

### FASE 5 — Página Streamlit para Relatórios IA (Semana 3, em paralelo)

#### 5.1 Criar `_pages/relatorios_ia.py`
Nova página no dashboard para:
- **Visualizar relatórios gerados** pelo Claude (histórico)
- **Gerar relatório sob demanda** (botão "Analisar agora")
- **Filtrar por data, plataforma** (Google Ads, Meta, Orgânico)
- **Exibir análise formatada** (Markdown renderizado via `st.markdown`)
- **Comparação dia anterior** (side-by-side)

#### 5.2 Registrar no `main.py`
Adicionar a nova página ao dicionário `PAGES` e ao import.

---

### FASE 6 — Consolidação e Relatório Mensal (Semana 7)

#### 6.1 Relatório mensal cruzado
O Claude recebe dados de **todos os pipelines** (Ads + Orgânico) e gera análise cruzada:
- Correlação tráfego orgânico × CPA dos ads
- Posts orgânicos com alto engajamento → candidatos a criativos de ads
- Queries do Search Console → oportunidades de campanhas Search
- Temas de Reels com alta retenção → LPs de ads

#### 6.2 Agendamento completo
| Execução | Frequência | CRON (UTC) |
|----------|-----------|------------|
| Relatório Ads (diário) | Seg-Sex 06h BRT | `0 9 * * 1-5` |
| Alertas orgânico (diário) | Seg-Sex 07h BRT | `0 10 * * 1-5` |
| Relatório Social (semanal) | Segunda 07h BRT | `0 10 * * 1` |
| Relatório SEO (semanal) | Quarta 07h BRT | `0 10 * * 3` |
| Relatório Mensal Consolidado | 1º dia útil 07h | `0 10 1 * *` |

---

## 📂 Estrutura de Arquivos a Criar

```
dados_degrau_py/
├── collectors/                      # NOVO — Módulos de coleta
│   ├── __init__.py
│   ├── google_ads_collector.py      # Reutiliza código de gads_face_combinado.py
│   ├── meta_ads_collector.py        # Reutiliza código de gads_face_combinado.py
│   ├── instagram.py                 # FASE 3
│   ├── facebook_pages.py            # FASE 3
│   ├── youtube.py                   # FASE 3
│   ├── tiktok.py                    # FASE 3 (opcional)
│   ├── google_analytics.py          # FASE 4
│   └── search_console.py            # FASE 4
├── analysis/                        # NOVO — Módulos de análise IA
│   ├── __init__.py
│   ├── claude_client.py             # Client Anthropic + função de análise
│   ├── prompts.py                   # Prompt tráfego pago
│   ├── prompts_social.py            # Prompt redes sociais (FASE 3)
│   └── prompts_seo.py              # Prompt SEO/blog (FASE 4)
├── delivery/                        # NOVO — Módulos de entrega
│   ├── __init__.py
│   ├── email_sender.py              # SendGrid
│   ├── slack_sender.py              # Slack webhook
│   └── whatsapp_sender.py           # Twilio (opcional)
├── data/
│   └── historico/                   # NOVO — Relatórios salvos
├── logs/                            # NOVO — Logs de execução
├── pipeline_trafego_pago.py         # NOVO — Orquestrador diário (ads)
├── pipeline_organico.py             # NOVO — Orquestrador semanal (orgânico)
├── _pages/
│   └── relatorios_ia.py             # NOVO — Página Streamlit
├── (arquivos existentes mantidos)
└── ...
```

---

## 🔑 Credenciais Necessárias (Checklist)

| Serviço | Credencial | Status | Ação |
|---------|-----------|--------|------|
| Google Ads (Degrau) | Developer Token + OAuth2 | ✅ Já tem | Nenhuma |
| Google Ads (Central) | Developer Token + OAuth2 | ✅ Já tem | Nenhuma |
| Meta Ads | App ID + Secret + Token | ✅ Já tem | Verificar se token está válido |
| **Claude API** | API Key (Anthropic) | ❌ Falta | Criar em console.anthropic.com |
| **SendGrid** (ou Slack) | API Key | ❌ Falta | Criar em app.sendgrid.com |
| Instagram | Token Business Manager | 🟡 Parcial | Mesmo token Meta, verificar permissões IG |
| YouTube | OAuth2 | 🟡 Parcial | Mesmo projeto GCP, habilitar API |
| GA4 | Service Account | ✅ Já tem | Verificar permissão na propriedade |
| Search Console | Service Account | 🟡 Parcial | Mesmo SA, verificar acesso à propriedade |
| TikTok | TikAPI key | ❌ Falta | tikapi.io (opcional, ~US$ 30/mês) |

---

## 📦 Dependências a Adicionar

```txt
# requirements.txt — adicionar:
anthropic>=0.40.0              # Claude API
sendgrid>=6.11.0               # E-mail (se usar)
twilio>=9.0.0                  # WhatsApp (se usar)
google-api-python-client>=2.130.0  # YouTube + Search Console (já pode ter)
```

---

## 💰 Custo Estimado Mensal

| Pipeline | Frequência | Custo/mês |
|----------|-----------|-----------|
| Ads (KPIs) | Diário | ~US$ 1,20 |
| Ads (Criativos/Vision) | Diário | ~US$ 1,50 |
| Social orgânico | Semanal + alertas | ~US$ 1,50 |
| Blog + SEO | Semanal | ~US$ 0,40 |
| **TOTAL Claude API** | | **~US$ 4,60/mês** |
| SendGrid (e-mail) | Até 100/dia grátis | US$ 0 |
| TikAPI (opcional) | Mensal | ~US$ 30 |

---

## ⚡ Ordem de Execução Recomendada

```
SEMANA 1:
  [1] Obter API Key do Claude (console.anthropic.com)
  [2] Criar módulo analysis/claude_client.py + prompts.py
  [3] Extrair collectors do gads_face_combinado.py para módulos reutilizáveis
  [4] Criar pipeline_trafego_pago.py (orquestrador)
  [5] Testar: execução manual → análise gerada pelo Claude

SEMANA 2:
  [6] Criar delivery/email_sender.py (ou slack_sender.py)
  [7] Configurar CRON para execução diária às 06h
  [8] Criar _pages/relatorios_ia.py (página Streamlit)
  [9] Registrar página no main.py
  [10] Criar diretório data/historico/ para salvar relatórios

SEMANA 3:
  [11] Adicionar coleta de criativos (Meta + Google)
  [12] Integrar análise de criativos via Claude Vision
  [13] Testar pipeline completo ponta a ponta

SEMANA 4-5:
  [14] Implementar collectors Instagram + Facebook Pages
  [15] Implementar collector YouTube
  [16] Criar prompts_social.py + pipeline parcial

SEMANA 5-6:
  [17] Implementar collector GA4 (blog)
  [18] Implementar collector Search Console
  [19] Criar prompts_seo.py + pipeline orgânico completo

SEMANA 7:
  [20] Relatório mensal consolidado (Ads + Orgânico cruzado)
  [21] Ajustes finos nos prompts baseado em feedback
  [22] Documentação final
```

---

## 🔗 Referências

- Documento tráfego pago: `documents/arquitetura_pipeline_trafego_pago.pdf`
- Documento orgânico: `documents/arquitetura_pipeline_organico.pdf`
- Código existente de referência: `_pages/gads_face_combinado.py`
- Credenciais Google Ads: `google-ads.yaml`, `google-ads_central.yaml`
- Credenciais Meta: `.facebook_credentials.env`
- Credenciais GA: `gcp_credentials.json`, `gcp_credentials_central.json`
