import datetime as dt_module
import glob
import json
import os
import re
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yaml
from dotenv import load_dotenv
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adsinsights import AdsInsights
from facebook_business.api import FacebookAdsApi
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from sqlalchemy import text as sql_text

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_PROJECT_ROOT, '.env'))
load_dotenv(os.path.join(_PROJECT_ROOT, '.facebook_credentials.env'), override=True)

HISTORICO_DIR = os.path.join(_PROJECT_ROOT, "data", "historico")

# =====================================================
# GERAÇÃO DE RELATÓRIO HTML
# =====================================================

def gerar_html_relatorio(analise, dados_consolidados, data_ref, tipo="completo_ads"):
    """Gera um HTML formatado e estilizado do relatório de análise."""
    titulo_tipo = {
        "completo_ads": "Análise Completa de Ads",
        "alerta": "Alerta Diário",
        "seo": "Análise de SEO",
        "social": "Análise de Social Media",
    }.get(tipo, "Relatório")

    corpo_html = _render_markdown_to_html(analise)
    dados_html = _render_dados_brutos_html(dados_consolidados)
    agora = datetime.now().strftime("%d/%m/%Y às %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{titulo_tipo} — {data_ref}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

  :root {{
    --primary: #1e64aa;
    --primary-light: #eaf3ff;
    --success: #16a34a;
    --success-light: #e6ffe8;
    --warning: #d97706;
    --warning-light: #fff8e1;
    --danger: #dc2626;
    --danger-light: #fef2f2;
    --gray-50: #f9fafb;
    --gray-100: #f3f4f6;
    --gray-200: #e5e7eb;
    --gray-300: #d1d5db;
    --gray-500: #6b7280;
    --gray-700: #374151;
    --gray-900: #111827;
  }}

  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    color: var(--gray-900);
    background: #fff;
    line-height: 1.6;
    font-size: 14px;
  }}

  .page {{
    max-width: 900px;
    margin: 0 auto;
    padding: 40px 32px;
  }}

  /* Cabeçalho */
  .header {{
    text-align: center;
    margin-bottom: 32px;
    padding-bottom: 24px;
    border-bottom: 3px solid var(--primary);
  }}
  .header h1 {{
    font-size: 28px;
    font-weight: 700;
    color: var(--primary);
    margin-bottom: 6px;
  }}
  .header .meta {{
    font-size: 13px;
    color: var(--gray-500);
  }}

  /* Blocos principais */
  .bloco-header {{
    background: linear-gradient(135deg, var(--primary), #2980b9);
    color: #fff;
    padding: 12px 20px;
    border-radius: 8px 8px 0 0;
    font-size: 18px;
    font-weight: 700;
    margin-top: 32px;
    letter-spacing: 0.3px;
  }}
  .bloco-body {{
    border: 1px solid var(--gray-200);
    border-top: none;
    border-radius: 0 0 8px 8px;
    padding: 20px;
    margin-bottom: 8px;
    background: #fff;
  }}

  /* Marca (═══ MARCA ═══) */
  .marca-header {{
    font-size: 17px;
    font-weight: 700;
    color: var(--primary);
    padding: 10px 0;
    margin: 20px 0 12px;
    border-bottom: 2px solid var(--primary);
  }}
  .marca-header:first-child {{ margin-top: 0; }}

  /* Objetivo ── OBJETIVO: ... ── */
  .objetivo-header {{
    font-size: 14px;
    font-weight: 600;
    color: var(--gray-700);
    padding: 6px 12px;
    margin: 16px 0 8px;
    background: var(--gray-100);
    border-left: 4px solid var(--primary);
    border-radius: 0 4px 4px 0;
  }}

  /* Campanha */
  .campanha-box {{
    background: var(--primary-light);
    border-radius: 6px;
    padding: 10px 16px;
    margin: 16px 0 8px;
    font-size: 15px;
    font-weight: 600;
    color: var(--gray-900);
  }}

  /* Meta badges (PLATAFORMA, TIPO, STATUS) */
  .meta-badges {{
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin: 4px 0 10px;
  }}
  .meta-badge {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.3px;
  }}
  .meta-badge.plataforma {{ background: #dbeafe; color: #1e40af; }}
  .meta-badge.tipo {{ background: #fef3c7; color: #92400e; }}
  .meta-badge.status {{ background: #d1fae5; color: #065f46; }}

  /* Labels especiais */
  .label-key {{
    font-weight: 700;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    margin-top: 14px;
    margin-bottom: 4px;
  }}
  .label-destaques {{ color: var(--success); }}
  .label-pontos {{ color: var(--warning); }}
  .label-decisoes {{ color: var(--danger); }}

  /* NÚMEROS */
  .numeros-section {{
    margin: 10px 0;
  }}
  .numeros-section .numeros-title {{
    font-weight: 700;
    font-size: 13px;
    color: var(--gray-700);
    text-transform: uppercase;
    letter-spacing: 0.4px;
    margin-bottom: 6px;
  }}
  .numeros-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 8px;
    margin-bottom: 10px;
  }}
  .numeros-card {{
    background: var(--gray-50);
    border: 1px solid var(--gray-200);
    border-radius: 6px;
    padding: 8px 12px;
  }}
  .numeros-card .card-label {{
    font-size: 11px;
    color: var(--gray-500);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }}
  .numeros-card .card-value {{
    font-size: 16px;
    font-weight: 700;
    color: var(--gray-900);
  }}

  /* Sub-sections (DIAGNÓSTICO, PLANO DE AÇÃO) */
  .diagnostico-box {{
    background: var(--primary-light);
    border-left: 4px solid var(--primary);
    padding: 10px 16px;
    border-radius: 0 6px 6px 0;
    margin: 10px 0;
  }}
  .diagnostico-box .box-title {{
    font-weight: 700;
    font-size: 13px;
    color: var(--primary);
    text-transform: uppercase;
    margin-bottom: 4px;
  }}

  .plano-box {{
    background: var(--success-light);
    border-left: 4px solid var(--success);
    padding: 10px 16px;
    border-radius: 0 6px 6px 0;
    margin: 10px 0;
  }}
  .plano-box .box-title {{
    font-weight: 700;
    font-size: 13px;
    color: var(--success);
    text-transform: uppercase;
    margin-bottom: 4px;
  }}

  /* Alertas */
  .alerta-box {{
    background: var(--warning-light);
    border: 1px solid var(--warning);
    border-left: 4px solid var(--warning);
    padding: 10px 16px;
    border-radius: 0 6px 6px 0;
    margin: 10px 0;
    font-weight: 500;
  }}

  /* Tabelas */
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 10px 0;
    font-size: 13px;
  }}
  th {{
    background: var(--primary);
    color: #fff;
    font-weight: 600;
    padding: 8px 12px;
    text-align: left;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }}
  th:first-child {{ border-radius: 6px 0 0 0; }}
  th:last-child {{ border-radius: 0 6px 0 0; }}
  td {{
    padding: 7px 12px;
    border-bottom: 1px solid var(--gray-200);
  }}
  tr:nth-child(even) td {{ background: var(--gray-50); }}
  tr:last-child td:first-child {{ border-radius: 0 0 0 6px; }}
  tr:last-child td:last-child {{ border-radius: 0 0 6px 0; }}

  /* Investimento total e bloco principal */
  .investimento-box {{
    background: var(--gray-50);
    border: 1px solid var(--gray-200);
    border-radius: 8px;
    padding: 14px 18px;
    margin: 10px 0;
  }}
  .investimento-box strong {{ color: var(--gray-900); }}

  /* Listas */
  ul {{ margin: 4px 0 8px 20px; }}
  li {{ margin: 3px 0; }}
  ol {{ margin: 4px 0 8px 20px; }}
  ol li {{ margin: 4px 0; }}

  /* Separadores */
  hr {{
    border: none;
    border-top: 1px solid var(--gray-200);
    margin: 16px 0;
  }}

  /* Texto em bold */
  strong {{ font-weight: 600; }}

  /* Headers markdown */
  h2 {{ font-size: 20px; margin: 24px 0 10px; color: var(--gray-900); }}
  h3 {{ font-size: 16px; margin: 18px 0 8px; color: var(--gray-700); }}
  h4 {{ font-size: 14px; margin: 14px 0 6px; color: var(--gray-700); }}

  /* Parágrafo */
  p {{ margin: 4px 0; }}

  /* Visão Geral consolidada */
  .visao-geral {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin: 10px 0 16px;
  }}
  .visao-geral .vg-item {{
    text-align: center;
    background: var(--gray-50);
    border: 1px solid var(--gray-200);
    border-radius: 8px;
    padding: 12px 8px;
  }}
  .visao-geral .vg-label {{
    font-size: 11px;
    color: var(--gray-500);
    text-transform: uppercase;
    font-weight: 500;
  }}
  .visao-geral .vg-value {{
    font-size: 20px;
    font-weight: 700;
    color: var(--primary);
  }}

  /* Dados brutos */
  .dados-brutos {{
    margin-top: 40px;
    page-break-before: always;
  }}
  .dados-brutos h2 {{
    color: var(--primary);
    border-bottom: 2px solid var(--primary);
    padding-bottom: 6px;
  }}
  .dados-brutos pre {{
    background: var(--gray-50);
    border: 1px solid var(--gray-200);
    border-radius: 6px;
    padding: 16px;
    font-size: 11px;
    font-family: 'Courier New', monospace;
    white-space: pre-wrap;
    word-break: break-word;
    line-height: 1.5;
    max-height: none;
    overflow: visible;
  }}

  @media print {{
    body {{ font-size: 12px; }}
    .page {{ padding: 20px; max-width: 100%; }}
    .bloco-header {{ page-break-after: avoid; }}
    .campanha-box {{ page-break-after: avoid; }}
    .dados-brutos {{ page-break-before: always; }}
  }}
</style>
</head>
<body>
<div class="page">

  <div class="header">
    <h1>{titulo_tipo}</h1>
    <div class="meta">Período: {data_ref} &nbsp;|&nbsp; Gerado em: {agora}</div>
  </div>

  {corpo_html}

  <div class="dados-brutos">
    <h2>Dados Brutos Enviados ao Claude</h2>
    {dados_html}
  </div>

</div>
</body>
</html>"""
    return html.encode("utf-8")


def _render_dados_brutos_html(dados):
    """Converte dados brutos em HTML seguro."""
    import html as html_mod
    return f"<pre>{html_mod.escape(dados)}</pre>"


def _render_markdown_to_html(markdown_text):
    """Converte a análise do Claude em HTML estruturado com estilos bonitos."""
    import html as html_mod
    lines = markdown_text.split("\n")
    html_parts = []
    i = 0
    in_bloco = False

    def _bold(text):
        """Substitui **texto** por <strong>texto</strong>."""
        return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html_mod.escape(text))

    def _parse_numeros_to_cards(linhas):
        """Converte linhas de NÚMEROS em cards HTML."""
        cards = []
        for linha in linhas:
            for parte in linha.split("|"):
                parte = parte.strip()
                if ":" in parte:
                    k, _, v = parte.partition(":")
                    k, v = k.strip(), v.strip()
                    if k and v:
                        cards.append(f'<div class="numeros-card"><div class="card-label">{html_mod.escape(k)}</div><div class="card-value">{html_mod.escape(v)}</div></div>')
                elif parte:
                    cards.append(f'<div class="numeros-card"><div class="card-value">{html_mod.escape(parte)}</div></div>')
        if cards:
            return f'<div class="numeros-grid">{"".join(cards)}</div>'
        return ""

    def _parse_table(start_idx):
        """Tenta parsear uma tabela markdown (linhas com |). Retorna (html, next_idx)."""
        tbl_lines = []
        j = start_idx
        while j < len(lines) and "|" in lines[j].strip() and lines[j].strip().startswith("|"):
            tbl_lines.append(lines[j].strip())
            j += 1
        if len(tbl_lines) < 2:
            return None, start_idx
        # Primeira linha = headers, segunda = separador (---|---), restante = dados
        headers = [c.strip() for c in tbl_lines[0].split("|") if c.strip()]
        data_start = 2 if len(tbl_lines) > 2 and re.match(r"^[\|\s\-:]+$", tbl_lines[1]) else 1
        rows = []
        for tl in tbl_lines[data_start:]:
            cols = [c.strip() for c in tl.split("|") if c.strip()]
            if cols:
                rows.append(cols)
        if not headers:
            return None, start_idx
        out = '<table><thead><tr>'
        for h in headers:
            out += f'<th>{html_mod.escape(h)}</th>'
        out += '</tr></thead><tbody>'
        for row in rows:
            out += '<tr>'
            for ci, col in enumerate(row):
                out += f'<td>{html_mod.escape(col)}</td>'
            # Preenche colunas faltantes
            for _ in range(len(headers) - len(row)):
                out += '<td></td>'
            out += '</tr>'
        out += '</tbody></table>'
        return out, j

    while i < len(lines):
        stripped = lines[i].strip()

        # ── BLOCO N — TÍTULO ────────────────────────────────────
        if re.match(r"^BLOCO\s+\d+", stripped, re.IGNORECASE):
            if in_bloco:
                html_parts.append('</div>')  # fecha bloco-body anterior
            label = re.sub(r"[*_`]", "", stripped)
            html_parts.append(f'<div class="bloco-header">{html_mod.escape(label)}</div>')
            html_parts.append('<div class="bloco-body">')
            in_bloco = True
            i += 1
            continue

        # ── ═══ MARCA ═══ ───────────────────────────────────────
        if re.match(r"^[═=]{3,}", stripped):
            nome = re.sub(r"[═=\s]+", " ", stripped).strip()
            if nome:
                html_parts.append(f'<div class="marca-header">{html_mod.escape(nome)}</div>')
            i += 1
            continue

        # ── ── OBJETIVO: ... ── ─────────────────────────────────
        m_obj = re.match(r"^[─\-]+\s*OBJETIVO\s*:\s*(.+?)\s*[─\-]*$", stripped, re.IGNORECASE)
        if m_obj:
            html_parts.append(f'<div class="objetivo-header">OBJETIVO: {html_mod.escape(m_obj.group(1))}</div>')
            i += 1
            continue

        # ── CAMPANHA: nome ──────────────────────────────────────
        if re.match(r"^CAMPANHA\s*:", stripped, re.IGNORECASE):
            nome_camp = stripped.split(":", 1)[-1].strip()
            html_parts.append(f'<div class="campanha-box">📋 {html_mod.escape(nome_camp)}</div>')
            i += 1
            continue

        # ── Meta badges (PLATAFORMA, TIPO, STATUS) ──────────────
        m_meta = re.match(r"^(PLATAFORMA|TIPO|STATUS)\s*:\s*(.+)", stripped, re.IGNORECASE)
        if m_meta:
            chave = m_meta.group(1).upper()
            valor = m_meta.group(2).strip()
            css_class = chave.lower()
            html_parts.append(f'<span class="meta-badge {css_class}">{chave}: {html_mod.escape(valor)}</span>')
            i += 1
            continue

        # ── INVESTIMENTO TOTAL ──────────────────────────────────
        if re.match(r"^INVESTIMENTO TOTAL", stripped, re.IGNORECASE):
            inv_lines = [stripped]
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith("-"):
                inv_lines.append(lines[j].strip())
                j += 1
            inner = "<br>".join(_bold(l) for l in inv_lines)
            html_parts.append(f'<div class="investimento-box">{inner}</div>')
            i = j
            continue

        # ── BLOCO PRINCIPAL — LEADS ─────────────────────────────
        if re.match(r"^BLOCO PRINCIPAL", stripped, re.IGNORECASE):
            inv_lines = [stripped]
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith("-"):
                inv_lines.append(lines[j].strip())
                j += 1
            inner = "<br>".join(_bold(l) for l in inv_lines)
            html_parts.append(f'<div class="investimento-box">{inner}</div>')
            i = j
            continue

        # ── DESTAQUES POSITIVOS / PONTOS DE ATENÇÃO / DECISÕES ─
        m_label = re.match(r"^(DESTAQUES?\s+POSITIVOS?|PONTOS?\s+DE\s+ATEN[CÇ][AÃ]O|DECIS[OÕ]ES\s+NECESS[AÁ]RIAS)\s*:", stripped, re.IGNORECASE)
        if m_label:
            chave = m_label.group(1).upper()
            if "DESTAQUE" in chave:
                css = "label-destaques"
            elif "PONTO" in chave:
                css = "label-pontos"
            else:
                css = "label-decisoes"
            html_parts.append(f'<div class="label-key {css}">{html_mod.escape(chave)}:</div>')
            i += 1
            continue

        # ── NÚMEROS ─────────────────────────────────────────────
        m_num = re.match(r"^N[UÚ]MEROS\s*(\([^)]*\))?\s*:(.*)", stripped, re.IGNORECASE)
        if m_num:
            extra = m_num.group(1) or ""
            valor_inline = m_num.group(2).strip()
            num_lines = []
            if valor_inline:
                num_lines.append(valor_inline)
            j = i + 1
            while j < len(lines):
                s = lines[j].strip()
                if s.startswith("[") or "|" in s or (s and not re.match(r"^[A-Z]", s)):
                    num_lines.append(s)
                    j += 1
                else:
                    break
            html_parts.append(f'<div class="numeros-section"><div class="numeros-title">Números {html_mod.escape(extra)}</div>')
            html_parts.append(_parse_numeros_to_cards(num_lines))
            html_parts.append('</div>')
            i = j
            continue

        # ── VISÃO GERAL (YouTube consolidado) ───────────────────
        if re.match(r"^VIS[AÃ]O GERAL", stripped, re.IGNORECASE):
            # Tenta capturar linhas com métricas separadas por |
            dados_linha = stripped.split(":", 1)[-1].strip() if ":" in stripped else ""
            j = i + 1
            while j < len(lines) and "|" in lines[j]:
                dados_linha += " | " + lines[j].strip()
                j += 1
            pares = []
            for parte in dados_linha.split("|"):
                parte = parte.strip()
                if ":" in parte:
                    k, _, v = parte.partition(":")
                    pares.append((k.strip(), v.strip()))
            if pares:
                items = ""
                for k, v in pares:
                    items += f'<div class="vg-item"><div class="vg-label">{html_mod.escape(k)}</div><div class="vg-value">{html_mod.escape(v)}</div></div>'
                html_parts.append(f'<div class="visao-geral">{items}</div>')
            else:
                html_parts.append(f'<p>{_bold(stripped)}</p>')
            i = j
            continue

        # ── TABELA markdown (|...|...|) ─────────────────────────
        if stripped.startswith("|") and "|" in stripped[1:]:
            tbl_html, next_i = _parse_table(i)
            if tbl_html:
                html_parts.append(tbl_html)
                i = next_i
                continue

        # ── TABELA label + inline markdown ──────────────────────
        if re.match(r"^TABELA\s+", stripped, re.IGNORECASE):
            titulo_tabela = stripped
            j = i + 1
            if j < len(lines) and lines[j].strip().startswith("|"):
                tbl_html, next_i = _parse_table(j)
                if tbl_html:
                    html_parts.append(f'<h4>{html_mod.escape(titulo_tabela)}</h4>')
                    html_parts.append(tbl_html)
                    i = next_i
                    continue
            html_parts.append(f'<h4>{html_mod.escape(titulo_tabela)}</h4>')
            i += 1
            continue

        # ── DIAGNÓSTICO ─────────────────────────────────────────
        m_diag = re.match(r"^DIAGN[OÓ]STICO\s*:(.*)", stripped, re.IGNORECASE)
        if m_diag:
            val = m_diag.group(1).strip()
            content_lines = [val] if val else []
            j = i + 1
            while j < len(lines):
                s = lines[j].strip()
                if s and not re.match(r"^(PLANO|CAMPANHA|N[UÚ]MEROS|TIPO|PLATAFORMA|STATUS|[═=]{3}|BLOCO\s+\d|[⚠🚨]|TABELA|VIS[AÃ]O)", s, re.IGNORECASE):
                    content_lines.append(s)
                    j += 1
                else:
                    break
            inner = "<br>".join(_bold(l) for l in content_lines)
            html_parts.append(f'<div class="diagnostico-box"><div class="box-title">Diagnóstico</div>{inner}</div>')
            i = j
            continue

        # ── PLANO DE AÇÃO ───────────────────────────────────────
        m_plano = re.match(r"^PLANO DE A[CÇ][AÃ]O\s*:(.*)", stripped, re.IGNORECASE)
        if m_plano:
            val = m_plano.group(1).strip()
            content_lines = [val] if val else []
            j = i + 1
            while j < len(lines):
                s = lines[j].strip()
                if s and not re.match(r"^(DIAGN[OÓ]STICO|CAMPANHA|N[UÚ]MEROS|TIPO|PLATAFORMA|STATUS|[═=]{3}|BLOCO\s+\d|[⚠🚨]|TABELA|VIS[AÃ]O)", s, re.IGNORECASE):
                    content_lines.append(s)
                    j += 1
                else:
                    break
            items = []
            for cl in content_lines:
                items.append(_bold(cl))
            inner = "<br>".join(items)
            html_parts.append(f'<div class="plano-box"><div class="box-title">Plano de Ação</div>{inner}</div>')
            i = j
            continue

        # ── Alertas ⚠️ / 🚨 ────────────────────────────────────
        if "⚠" in stripped or "🚨" in stripped or stripped.startswith("[!]") or stripped.startswith("[ALERTA]"):
            html_parts.append(f'<div class="alerta-box">⚠️ {_bold(stripped)}</div>')
            i += 1
            continue

        # ── Markdown headers ────────────────────────────────────
        if stripped.startswith("### "):
            html_parts.append(f'<h4>{_bold(stripped[4:])}</h4>')
            i += 1
            continue
        if stripped.startswith("## "):
            html_parts.append(f'<h3>{_bold(stripped[3:])}</h3>')
            i += 1
            continue
        if stripped.startswith("# "):
            html_parts.append(f'<h2>{_bold(stripped[2:])}</h2>')
            i += 1
            continue

        # ── Separadores — ───────────────────────────────────────
        if stripped in ("---", "***", "___"):
            html_parts.append('<hr>')
            i += 1
            continue

        # ── Lista ────────────────────────────────────────────────
        if stripped.startswith("- ") or stripped.startswith("* "):
            ul_items = []
            while i < len(lines) and (lines[i].strip().startswith("- ") or lines[i].strip().startswith("* ")):
                ul_items.append(f'<li>{_bold(lines[i].strip()[2:])}</li>')
                i += 1
            html_parts.append(f'<ul>{"".join(ul_items)}</ul>')
            continue

        # ── Lista numerada ───────────────────────────────────────
        if re.match(r"^\d+\.\s", stripped):
            ol_items = []
            while i < len(lines) and re.match(r"^\d+\.\s", lines[i].strip()):
                texto = re.sub(r"^\d+\.\s*", "", lines[i].strip())
                ol_items.append(f'<li>{_bold(texto)}</li>')
                i += 1
            html_parts.append(f'<ol>{"".join(ol_items)}</ol>')
            continue

        # ── Linha vazia ──────────────────────────────────────────
        if not stripped:
            i += 1
            continue

        # ── Texto normal ─────────────────────────────────────────
        html_parts.append(f'<p>{_bold(stripped)}</p>')
        i += 1

    if in_bloco:
        html_parts.append('</div>')  # fecha último bloco-body

    return "\n".join(html_parts)



# =====================================================
# CLASSIFICAÇÃO DE OBJETIVO (v2.0)
# =====================================================

OBJETIVO_MAP_META = {
    "OUTCOME_LEADS": "LEADS",
    "OUTCOME_TRAFFIC": "TRAFEGO",
    "OUTCOME_AWARENESS": "AWARENESS",
    "OUTCOME_ENGAGEMENT": "ENGAJAMENTO",
    "OUTCOME_SALES": "VENDAS",
    "LEAD_GENERATION": "LEADS",
    "LINK_CLICKS": "TRAFEGO",
    "REACH": "AWARENESS",
    "VIDEO_VIEWS": "VIDEO",
    "CONVERSIONS": "VENDAS",
    "POST_ENGAGEMENT": "ENGAJAMENTO",
}

OBJETIVO_MAP_GOOGLE = {
    "SEARCH": "LEADS",
    "PERFORMANCE_MAX": "LEADS",
    "MULTI_CHANNEL": "LEADS",   # Performance Max no enum da API
    "DISPLAY": "AWARENESS",
    "VIDEO": "VIDEO",
}

# ---- Lookup dicts para resolver enums numéricos da API ----
_CHANNEL_TYPE_MAP = {
    2: "SEARCH", 3: "DISPLAY", 4: "SHOPPING", 5: "HOTEL",
    6: "VIDEO", 7: "MULTI_CHANNEL", 9: "DISCOVERY",
}
_STATUS_MAP = {
    2: "ENABLED", 3: "PAUSED", 4: "REMOVED",
}
_BIDDING_MAP = {
    2: "ENHANCED_CPC", 5: "MANUAL_CPC", 6: "MANUAL_CPM", 7: "MANUAL_CPV",
    8: "MAXIMIZE_CONVERSIONS", 9: "MAXIMIZE_CONVERSION_VALUE",
    12: "TARGET_CPA", 13: "TARGET_CPM", 14: "TARGET_IMPRESSION_SHARE",
    16: "TARGET_ROAS", 17: "TARGET_SPEND",
}
_SUB_TYPE_MAP = {
    10: "VIDEO_OUTSTREAM", 11: "VIDEO_ACTION", 12: "VIDEO_NON_SKIPPABLE",
    18: "VIDEO_SEQUENCE", 20: "VIDEO_REACH_TARGET_FREQUENCY",
}

def _resolve_enum(val, lookup=None):
    """Resolve enum da Google Ads API para string. 
    Funciona com proto-plus (que retorna int ou enum com .name) e com enums numéricos."""
    if hasattr(val, 'name'):
        return val.name
    name = str(val).split(".")[-1]
    if lookup:
        try:
            return lookup.get(int(name), name)
        except (ValueError, TypeError):
            pass
    return name

def classificar_por_nome(nome_campanha):
    """Fallback: classifica objetivo pela convenção de nomenclatura."""
    nome = nome_campanha.upper()
    if any(tag in nome for tag in ["[RMKT]", "REMARKETING", "RETARGETING"]):
        return "REMARKETING"
    if any(tag in nome for tag in ["[TOFU]", "TRAFEGO", "BLOG", "AQUECIMENTO"]):
        return "TRAFEGO"
    if any(tag in nome for tag in ["[VSL]", "VIDEO", "THRUPLAY", "VVC"]):
        return "VIDEO"
    if any(tag in nome for tag in ["[AWARENESS]", "ALCANCE", "REACH"]):
        return "AWARENESS"
    if any(tag in nome for tag in ["[VENDA]", "MATRICULA", "CHECKOUT"]):
        return "VENDAS"
    return "LEADS"

# =====================================================
# FUNÇÕES DE COLETA
# =====================================================

def formatar_reais(valor):
    if pd.isna(valor) or valor == 0:
        return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def init_google_ads_client(yaml_file="google-ads.yaml"):
    try:
        google_ads_config = st.secrets["google_ads"]
        config_dict = {
            "developer_token": google_ads_config["developer_token"],
            "client_id": google_ads_config["client_id"],
            "client_secret": google_ads_config["client_secret"],
            "refresh_token": google_ads_config["refresh_token"],
            "login_customer_id": str(google_ads_config["login_customer_id"]),
            "use_proto_plus": google_ads_config.get("use_proto_plus", True)
        }
        return GoogleAdsClient.load_from_string(yaml.dump(config_dict))
    except (st.errors.StreamlitAPIException, KeyError):
        if os.path.exists(yaml_file):
            return GoogleAdsClient.load_from_storage(yaml_file)
    return None

def init_google_ads_client_central():
    try:
        google_ads_config = st.secrets["google_ads_central"]
        config_dict = {
            "developer_token": google_ads_config["developer_token"],
            "client_id": google_ads_config["client_id"],
            "client_secret": google_ads_config["client_secret"],
            "refresh_token": google_ads_config["refresh_token"],
            "login_customer_id": str(google_ads_config["login_customer_id"]),
            "use_proto_plus": google_ads_config.get("use_proto_plus", True)
        }
        return GoogleAdsClient.load_from_string(yaml.dump(config_dict))
    except (st.errors.StreamlitAPIException, KeyError):
        yaml_file = "google-ads_central.yaml"
        if os.path.exists(yaml_file):
            return GoogleAdsClient.load_from_storage(yaml_file)
    return None

def get_google_ads_data(client, customer_id, start_date, end_date):
    """Busca dados do Google Ads incluindo métricas completas para análise."""
    try:
        ga_service = client.get_service("GoogleAdsService")
        query = f"""
            SELECT
                campaign.name,
                campaign.id,
                campaign.status,
                campaign.advertising_channel_type,
                campaign.advertising_channel_sub_type,
                campaign.bidding_strategy_type,
                campaign.target_cpa.target_cpa_micros,
                campaign.maximize_conversions.target_cpa_micros,
                metrics.cost_micros,
                metrics.impressions,
                metrics.clicks,
                metrics.ctr,
                metrics.average_cpc,
                metrics.average_cpm,
                metrics.conversions,
                metrics.cost_per_conversion,
                metrics.conversions_from_interactions_rate,
                metrics.search_budget_lost_impression_share,
                metrics.search_rank_lost_impression_share,
                metrics.search_impression_share,
                metrics.video_view_rate,
                metrics.video_views,
                metrics.average_cpv,
                metrics.engagements,
                metrics.engagement_rate,
                metrics.interaction_rate,
                metrics.unique_users,
                metrics.average_impression_frequency_per_user,
                metrics.video_quartile_p25_rate,
                metrics.video_quartile_p50_rate,
                metrics.video_quartile_p75_rate,
                metrics.video_quartile_p100_rate
            FROM campaign
            WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
                AND metrics.cost_micros > 0
            ORDER BY metrics.cost_micros DESC
        """
        response = ga_service.search(customer_id=customer_id, query=query)
        rows = []
        for row in response:
            custo = row.metrics.cost_micros / 1_000_000
            cpc = row.metrics.average_cpc / 1_000_000 if row.metrics.average_cpc else 0
            cpm = row.metrics.average_cpm / 1_000_000 if row.metrics.average_cpm else 0
            cpa = row.metrics.cost_per_conversion / 1_000_000 if row.metrics.cost_per_conversion else 0
            cpv = row.metrics.average_cpv / 1_000_000 if row.metrics.average_cpv else 0

            # tCPA: verifica TARGET_CPA e MAXIMIZE_CONVERSIONS (com CPA-alvo)
            tcpa_target = row.campaign.target_cpa.target_cpa_micros / 1_000_000 if row.campaign.target_cpa.target_cpa_micros else 0
            tcpa_maxconv = row.campaign.maximize_conversions.target_cpa_micros / 1_000_000 if row.campaign.maximize_conversions.target_cpa_micros else 0
            tcpa = tcpa_target or tcpa_maxconv

            # Parcelas de impressão (None quando não aplicável, ex: PMax/YouTube)
            imp_lost_budget = row.metrics.search_budget_lost_impression_share
            imp_lost_rank = row.metrics.search_rank_lost_impression_share

            # Resolve enums para nomes legíveis (API pode retornar inteiros ou proto-plus enums)
            channel_type = _resolve_enum(row.campaign.advertising_channel_type, _CHANNEL_TYPE_MAP)
            status = _resolve_enum(row.campaign.status, _STATUS_MAP)
            sub_type_raw = _resolve_enum(row.campaign.advertising_channel_sub_type, _SUB_TYPE_MAP)
            bidding_type = _resolve_enum(row.campaign.bidding_strategy_type, _BIDDING_MAP)

            objetivo_api = OBJETIVO_MAP_GOOGLE.get(channel_type)
            objetivo = objetivo_api if objetivo_api else classificar_por_nome(row.campaign.name)

            # Rec/Cons para YouTube — baseado em sub_type e estratégia de lance
            _REC = {"VIDEO_NON_SKIPPABLE", "VIDEO_OUTSTREAM", "VIDEO_REACH_TARGET_FREQUENCY"}
            _ACT = {"VIDEO_ACTION"}
            if sub_type_raw in _REC or bidding_type in {"TARGET_CPM", "MANUAL_CPM"}:
                rec_cons = "Reconhecimento"
            elif sub_type_raw in _ACT or bidding_type == "MAXIMIZE_CONVERSIONS":
                rec_cons = "Ação/Conversão"
            elif channel_type == "VIDEO":
                rec_cons = "Consideração"  # TrueView / VVC (sub_type UNSPECIFIED + MANUAL_CPV)
            else:
                rec_cons = "-"

            # Métricas exclusivas de YouTube
            unique_users = row.metrics.unique_users if row.metrics.unique_users else 0
            avg_freq = row.metrics.average_impression_frequency_per_user if row.metrics.average_impression_frequency_per_user else 0
            interaction_rate = round(row.metrics.interaction_rate * 100, 2) if row.metrics.interaction_rate else 0

            q25 = round(row.metrics.video_quartile_p25_rate * 100, 1) if row.metrics.video_quartile_p25_rate else 0
            q50 = round(row.metrics.video_quartile_p50_rate * 100, 1) if row.metrics.video_quartile_p50_rate else 0
            q75 = round(row.metrics.video_quartile_p75_rate * 100, 1) if row.metrics.video_quartile_p75_rate else 0
            q100 = round(row.metrics.video_quartile_p100_rate * 100, 1) if row.metrics.video_quartile_p100_rate else 0

            rows.append({
                'Campanha': row.campaign.name,
                'Status': status,
                'Objetivo': objetivo,
                'Canal': channel_type,
                'Subtipo': sub_type_raw,
                'Rec/Cons': rec_cons,
                'Tipo Lance': bidding_type,
                'Custo': round(custo, 2),
                'Impressões': row.metrics.impressions,
                'Usuários Exclusivos': int(unique_users),
                'Freq Méd Imp/Usuário': round(avg_freq, 2),
                'Cliques': row.metrics.clicks,
                'CTR (%)': round(row.metrics.ctr * 100, 2),
                'CPC': round(cpc, 2),
                'CPM': round(cpm, 2),
                'Conversões': round(row.metrics.conversions, 1),
                'CPA': round(cpa, 2),
                'tCPA': round(tcpa, 2),
                'Taxa Conv (%)': round(row.metrics.conversions_from_interactions_rate * 100, 2) if row.metrics.conversions_from_interactions_rate else 0,
                'Imp Lost Budget (%)': round(imp_lost_budget * 100, 1) if imp_lost_budget else None,
                'Imp Lost Rank (%)': round(imp_lost_rank * 100, 1) if imp_lost_rank else None,
                'Video Views': row.metrics.video_views,
                'Video View Rate (%)': round(row.metrics.video_view_rate * 100, 2) if row.metrics.video_view_rate else 0,
                'Taxa de Interação (%)': interaction_rate,
                'CPV': round(cpv, 4),
                'Engajamentos': row.metrics.engagements,
                'Engagement Rate (%)': round(row.metrics.engagement_rate * 100, 2) if row.metrics.engagement_rate else 0,
                '% Assistido 25': q25,
                '% Assistido 50': q50,
                '% Assistido 75': q75,
                '% Assistido 100': q100,
            })
        return pd.DataFrame(rows)
    except Exception as e:
        st.error(f"Erro Google Ads: {e}")
        return pd.DataFrame()

def init_facebook_api(secrets_key="facebook_api", env_suffix=""):
    """Inicializa a API do Facebook. Use env_suffix='_CENTRAL' para Central."""
    app_id, app_secret, access_token, ad_account_id = None, None, None, None
    try:
        creds = st.secrets[secrets_key]
        app_id = creds["app_id"]
        app_secret = creds["app_secret"]
        access_token = creds["access_token"]
        ad_account_id = creds["ad_account_id"]
    except (st.errors.StreamlitAPIException, KeyError):
        app_id = os.getenv(f"FB_APP_ID{env_suffix}")
        app_secret = os.getenv(f"FB_APP_SECRET{env_suffix}")
        access_token = os.getenv(f"FB_ACCESS_TOKEN{env_suffix}")
        ad_account_id = os.getenv(f"FB_AD_ACCOUNT_ID{env_suffix}")
    if not all([app_id, app_secret, access_token, ad_account_id]):
        return None
    try:
        FacebookAdsApi.init(app_id=app_id, app_secret=app_secret, access_token=access_token)
        return AdAccount(ad_account_id)
    except Exception:
        return None

def init_facebook_api_central():
    """Inicializa a API do Facebook para a conta Central de Concursos."""
    return init_facebook_api(secrets_key="facebook_api_central", env_suffix="_CENTRAL")


def get_facebook_data(account, start_date, end_date):
    """Busca dados do Meta Ads com métricas completas.
    - Cliques = inline_link_clicks (cliques no link, não cliques totais)
    - CTR/CPC baseados em inline_link_clicks
    - Leads primários = lead_presencial + lead_live (Custom Conversions)
    """
    try:
        fields = [
            AdsInsights.Field.campaign_name,
            AdsInsights.Field.objective,
            AdsInsights.Field.spend,
            AdsInsights.Field.impressions,
            AdsInsights.Field.reach,
            AdsInsights.Field.frequency,
            AdsInsights.Field.cpm,
            # Cliques no link (não cliques totais)
            'inline_link_clicks',
            'inline_link_click_ctr',
            'cost_per_inline_link_click',
            AdsInsights.Field.actions,
            AdsInsights.Field.cost_per_action_type,
            # Conversions traz eventos pixel por nome (lead_presencial, lead_live, lead_online)
            'conversions',
        ]
        params = {
            'level': 'campaign',
            'time_range': {'since': start_date, 'until': end_date},
            # Usa a configuração de atribuição da conta (igual ao Gerenciador de Anúncios)
            'use_account_attribution_setting': True,
        }
        insights = account.get_insights(fields=fields, params=params)

        rows = []

        # Eventos de venda para campanhas ONLINE (Compras no site = pixel purchase offsite)
        # Usa apenas offsite_conversion.fb_pixel_purchase para refletir exatamente
        # o campo "Compras no site" do Gerenciador de Anúncios da Meta.
        VENDA_ACTIONS = {
            'offsite_conversion.fb_pixel_purchase',
        }
        # Nomes dos eventos pixel de lead (do campo conversions)
        LEAD_EVENTS = {
            'offsite_conversion.fb_pixel_custom.lead_presencial': 'lead_presencial',
            'offsite_conversion.fb_pixel_custom.lead_live': 'lead_live',
            'offsite_conversion.fb_pixel_custom.lead_online': 'lead_online',
        }

        for insight in insights:
            custo = float(insight.get(AdsInsights.Field.spend, 0))

            # Cliques no link
            cliques_link = int(insight.get('inline_link_clicks', 0))
            ctr_link = float(insight.get('inline_link_click_ctr', 0))
            cpc_link = float(insight.get('cost_per_inline_link_click', 0))

            # Leads primários via campo 'conversions' (eventos pixel por nome)
            lead_presencial = 0
            lead_live = 0
            lead_online = 0
            conversions = insight.get('conversions', [])
            for conv in conversions:
                atype = conv.get('action_type', '')
                val = int(conv.get('value', 0))
                target = LEAD_EVENTS.get(atype)
                if target == 'lead_presencial':
                    lead_presencial = val
                elif target == 'lead_live':
                    lead_live = val
                elif target == 'lead_online':
                    lead_online = val

            # Vendas via campo 'actions'
            vendas = 0
            actions = insight.get(AdsInsights.Field.actions, [])
            for action in actions:
                atype = action.get('action_type', '')
                val = int(action.get('value', 0))
                if atype in VENDA_ACTIONS:
                    vendas += val

            leads_primarios = lead_presencial + lead_live
            cpl_primario = custo / leads_primarios if leads_primarios > 0 else 0

            # Classificação de objetivo
            obj_api = insight.get(AdsInsights.Field.objective, "")
            objetivo = OBJETIVO_MAP_META.get(obj_api)
            if not objetivo:
                objetivo = classificar_por_nome(insight[AdsInsights.Field.campaign_name])

            rows.append({
                'Campanha': insight[AdsInsights.Field.campaign_name],
                'Objetivo': objetivo,
                'Custo': custo,
                'Impressões': int(insight.get(AdsInsights.Field.impressions, 0)),
                'Alcance': int(insight.get(AdsInsights.Field.reach, 0)),
                'Frequência': float(insight.get(AdsInsights.Field.frequency, 0)),
                'CPM': float(insight.get(AdsInsights.Field.cpm, 0)),
                'Cliques Link': cliques_link,
                'CTR Link (%)': round(ctr_link, 2),
                'CPC Link': round(cpc_link, 2),
                'lead_presencial': lead_presencial,
                'lead_live': lead_live,
                'lead_online': lead_online,
                'Resultado Presencial + Live': leads_primarios,
                'CPL Primário': round(cpl_primario, 2),
                'Compras no site': vendas,
            })
        return pd.DataFrame(rows)
    except Exception as e:
        st.error(f"Erro Meta Ads: {e}")
        return pd.DataFrame()

# =====================================================
# FORMATAÇÃO DOS DADOS POR OBJETIVO (v2.0)
# =====================================================

def formatar_dados_para_claude(df_google_degrau, df_google_central, df_facebook, janela_dias, df_facebook_central=None, start_date=None, end_date=None,
                               prev_google_degrau=None, prev_google_central=None, prev_facebook=None, prev_facebook_central=None,
                               prev_start_date=None, prev_end_date=None):
    """Formata os dados organizados por MARCA (Central vs Degrau) e dentro de cada marca por
    plataforma, conforme exigido pelo system prompt v3.0.
    Quando dados do período anterior são fornecidos, inclui seção WoW para comparativo."""
    hoje = datetime.now().date()
    inicio = start_date if start_date is not None else hoje - timedelta(days=janela_dias)
    fim = end_date if end_date is not None else hoje
    dia_semana = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"][hoje.weekday()]
    janela_real = (fim - inicio).days + 1

    # Verifica se temos dados do período anterior
    tem_prev = any(d is not None and not d.empty for d in [prev_google_degrau, prev_google_central, prev_facebook, prev_facebook_central])

    linhas = []
    linhas.append("=== METADADOS ===")
    linhas.append(f"Período atual: {inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}")
    if tem_prev and prev_start_date and prev_end_date:
        linhas.append(f"Período anterior (comparativo WoW): {prev_start_date.strftime('%d/%m/%Y')} a {prev_end_date.strftime('%d/%m/%Y')}")
    linhas.append(f"Janela: {janela_real} dias")
    linhas.append(f"Tipo de relatório: {'Alerta diário' if janela_real == 1 else 'Análise completa'}")
    linhas.append(f"Data de hoje: {hoje.strftime('%d/%m/%Y')} ({dia_semana})")
    linhas.append("")

    def _bloco_campanhas(df, origem_label):
        """Retorna linhas formatadas para um conjunto de campanhas de uma plataforma/marca."""
        if df is None or df.empty:
            return [f"  [{origem_label}]: sem dados no período"]

        eh_meta = "Meta" in origem_label
        custo_total = df['Custo'].sum()
        bloco = []
        bloco.append(f"  [{origem_label}]")
        bloco.append(f"  Total campanhas: {len(df)} | Custo total: R${custo_total:.2f}")
        bloco.append("")

        for _, r in df.iterrows():
            obj = r.get('Objetivo', 'LEADS')
            status = r.get('Status', '')
            bloco.append(f"  Campanha: {r['Campanha']}" + (f" [{status}]" if status else ""))
            bloco.append(f"  Objetivo: {obj} | Custo: R${r['Custo']:.2f} | Impressões: {r['Impressões']:,}")

            if eh_meta:
                # Métricas Meta com cliques no link
                cliques = r.get('Cliques Link', 0)
                ctr = r.get('CTR Link (%)', 0)
                cpc = r.get('CPC Link', 0)
                cpm = r.get('CPM', 0)
                alcance = r.get('Alcance', 0)
                freq = r.get('Frequência', 0)
                lead_p = r.get('lead_presencial', 0)
                lead_l = r.get('lead_live', 0)
                lead_o = r.get('lead_online', 0)
                leads = r.get('Resultado Presencial + Live', 0)
                cpl = r.get('CPL Primário', 0)
                compras_site = r.get('Compras no site', 0)

                bloco.append(f"  Cliques no link: {cliques:,} | CTR link: {ctr:.2f}% | CPC link: R${cpc:.2f} | CPM: R${cpm:.2f}")
                bloco.append(f"  Alcance: {alcance:,} | Frequência: {freq:.1f}")
                if leads > 0 or lead_p > 0 or lead_l > 0 or lead_o > 0:
                    aviso = " ⚠️ <30, dados insuficientes" if leads < 30 else ""
                    bloco.append(f"  lead_presencial: {lead_p} | lead_live: {lead_l} | lead_online: {lead_o} | Resultado Presencial + Live: {leads} | CPL Primário: R${cpl:.2f}{aviso}")
                if compras_site > 0:
                    bloco.append(f"  Compras no site: {compras_site}")
            else:
                # Métricas Google Ads
                canal = r.get('Canal', '')
                cliques = r.get('Cliques', 0)
                ctr = r.get('CTR (%)', 0)
                cpc = r.get('CPC', 0)
                cpm = r.get('CPM', 0)
                conv = r.get('Conversões', 0)
                cpa = r.get('CPA', 0)
                tcpa = r.get('tCPA', 0)
                taxa_conv = r.get('Taxa Conv (%)', 0)
                imp_budget = r.get('Imp Lost Budget (%)', None)
                imp_rank = r.get('Imp Lost Rank (%)', None)
                cpv = r.get('CPV', 0)
                video_views = r.get('Video Views', 0)
                view_rate = r.get('Video View Rate (%)', 0)
                engajamentos = r.get('Engajamentos', 0)
                eng_rate = r.get('Engagement Rate (%)', 0)

                if canal == "VIDEO":
                    # ── YouTube: apenas métricas de vídeo, sem Conversões/CPA/Parcelas ──
                    rec_cons = r.get('Rec/Cons', '-')
                    tipo_lance = r.get('Tipo Lance', '-')
                    unique_users = r.get('Usuários Exclusivos', 0)
                    avg_freq = r.get('Freq Méd Imp/Usuário', 0)
                    q25 = r.get('% Assistido 25', 0)
                    q50 = r.get('% Assistido 50', 0)
                    q75 = r.get('% Assistido 75', 0)
                    q100 = r.get('% Assistido 100', 0)
                    taxa_interacao = r.get('Taxa de Interação (%)', 0)
                    bloco.append(f"  Tipo: {rec_cons} | Estratégia de Lance: {tipo_lance}")
                    bloco.append(f"  Custo: R${r['Custo']:.2f} | Impressões: {r['Impressões']:,} | CPM: R${cpm:.2f} | CPC: R${cpc:.2f} | CPV: R${cpv:.4f}")
                    bloco.append(f"  Usuários Exclusivos: {unique_users:,} | Freq. Méd. Imp./Usuário: {avg_freq:.2f}")
                    bloco.append(f"  Video Views: {video_views:,} | View Rate: {view_rate:.2f}%")
                    bloco.append(f"  % Assistido: 25%={q25:.1f}% | 50%={q50:.1f}% | 75%={q75:.1f}% | 100%={q100:.1f}%")
                    bloco.append(f"  Taxa de Interação: {taxa_interacao:.2f}% | Engajamentos: {engajamentos:,}")
                else:
                    # ── Search, PMax, Display: métricas de conversão e parcelas ──
                    tcpa_str = f"R${tcpa:.2f}" if tcpa > 0 else "não configurado"
                    bloco.append(f"  Canal: {canal} | Cliques: {cliques:,} | CTR: {ctr:.2f}% | CPC: R${cpc:.2f} | CPM: R${cpm:.2f}")
                    bloco.append(f"  Conversões: {conv} | CPA: R${cpa:.2f} | CPA Desejado: {tcpa_str} | Taxa conv: {taxa_conv:.2f}%")

                    if imp_budget is not None or imp_rank is not None:
                        ib = f"{imp_budget:.1f}%" if imp_budget is not None else "N/A"
                        ir = f"{imp_rank:.1f}%" if imp_rank is not None else "N/A"
                        bloco.append(f"  Parc impr perd (orç): {ib} | Parc impr perd (class): {ir}")

                    if conv > 0 and conv < 30:
                        bloco.append(f"  ⚠️ <30 conversões — CPA não é estatisticamente confiável")

            bloco.append("")
        return bloco

    def _soma(df, col):
        return df[col].sum() if df is not None and not df.empty and col in df.columns else 0

    # ─── CENTRAL DE CONCURSOS ───────────────────────────────────────────────
    linhas.append("=" * 60)
    linhas.append("MARCA: CENTRAL DE CONCURSOS (São Paulo)")
    linhas.append("=" * 60)

    custo_gc  = _soma(df_google_central, 'Custo')
    custo_fbc = _soma(df_facebook_central, 'Custo')
    conv_gc   = _soma(df_google_central, 'Conversões')
    leads_fbc = _soma(df_facebook_central, 'Resultado Presencial + Live')
    cpl_fbc   = custo_fbc / leads_fbc if leads_fbc > 0 else 0

    linhas.append(f"Investimento total Central: R${(custo_gc + custo_fbc):.2f}")
    linhas.append(f"  Google Ads (Central): R${custo_gc:.2f} | Conversões: {int(conv_gc)}")
    linhas.append(f"  Meta Ads (Central):   R${custo_fbc:.2f} | Resultado Presencial + Live: {int(leads_fbc)}" +
                  (f" | CPL: R${cpl_fbc:.2f}" if leads_fbc > 0 else ""))
    linhas.append("")

    linhas.extend(_bloco_campanhas(df_google_central, "Google Ads (Central)"))
    linhas.extend(_bloco_campanhas(df_facebook_central, "Meta Ads (Central)"))

    # ─── DEGRAU CULTURAL ────────────────────────────────────────────────────
    linhas.append("=" * 60)
    linhas.append("MARCA: DEGRAU CULTURAL (Rio de Janeiro)")
    linhas.append("=" * 60)

    custo_gd  = _soma(df_google_degrau, 'Custo')
    custo_fb  = _soma(df_facebook, 'Custo')
    conv_gd   = _soma(df_google_degrau, 'Conversões')
    leads_fb  = _soma(df_facebook, 'Resultado Presencial + Live')
    cpl_fb    = custo_fb / leads_fb if leads_fb > 0 else 0

    linhas.append(f"Investimento total Degrau: R${(custo_gd + custo_fb):.2f}")
    linhas.append(f"  Google Ads (Degrau): R${custo_gd:.2f} | Conversões: {int(conv_gd)}")
    linhas.append(f"  Meta Ads (Degrau):   R${custo_fb:.2f} | Resultado Presencial + Live: {int(leads_fb)}" +
                  (f" | CPL: R${cpl_fb:.2f}" if leads_fb > 0 else ""))
    linhas.append("")

    linhas.extend(_bloco_campanhas(df_google_degrau, "Google Ads (Degrau)"))
    linhas.extend(_bloco_campanhas(df_facebook, "Meta Ads (Degrau)"))

    # ─── TOTAIS CONSOLIDADOS ────────────────────────────────────────────────
    custo_all = custo_gc + custo_fbc + custo_gd + custo_fb
    conv_all  = int(conv_gc + conv_gd)
    leads_all = int(leads_fbc + leads_fb)
    linhas.append("=" * 60)
    linhas.append("TOTAIS CONSOLIDADOS (ambas as marcas)")
    linhas.append("=" * 60)
    linhas.append(f"Custo total: R${custo_all:.2f} | Conversões Google: {conv_all} | Resultado Presencial + Live (Meta): {leads_all}")

    # ─── DADOS DO PERÍODO ANTERIOR (comparativo WoW) ───────────────────────
    if tem_prev:
        linhas.append("")
        linhas.append("=" * 60)
        linhas.append(f"PERÍODO ANTERIOR (WoW): {prev_start_date.strftime('%d/%m/%Y')} a {prev_end_date.strftime('%d/%m/%Y')}")
        linhas.append("=" * 60)
        linhas.append("Os dados abaixo são do período anterior, para comparativo período a período.")
        linhas.append("")

        # Central - período anterior
        linhas.append("-" * 40)
        linhas.append("MARCA: CENTRAL DE CONCURSOS (Período Anterior)")
        linhas.append("-" * 40)

        prev_custo_gc  = _soma(prev_google_central, 'Custo')
        prev_custo_fbc = _soma(prev_facebook_central, 'Custo')
        prev_conv_gc   = _soma(prev_google_central, 'Conversões')
        prev_leads_fbc = _soma(prev_facebook_central, 'Resultado Presencial + Live')
        prev_cpl_fbc   = prev_custo_fbc / prev_leads_fbc if prev_leads_fbc > 0 else 0

        linhas.append(f"Investimento total Central: R${(prev_custo_gc + prev_custo_fbc):.2f}")
        linhas.append(f"  Google Ads (Central): R${prev_custo_gc:.2f} | Conversões: {int(prev_conv_gc)}")
        linhas.append(f"  Meta Ads (Central):   R${prev_custo_fbc:.2f} | Resultado Presencial + Live: {int(prev_leads_fbc)}" +
                      (f" | CPL: R${prev_cpl_fbc:.2f}" if prev_leads_fbc > 0 else ""))
        linhas.append("")

        linhas.extend(_bloco_campanhas(prev_google_central, "Google Ads (Central) — Período Anterior"))
        linhas.extend(_bloco_campanhas(prev_facebook_central, "Meta Ads (Central) — Período Anterior"))

        # Degrau - período anterior
        linhas.append("-" * 40)
        linhas.append("MARCA: DEGRAU CULTURAL (Período Anterior)")
        linhas.append("-" * 40)

        prev_custo_gd  = _soma(prev_google_degrau, 'Custo')
        prev_custo_fb  = _soma(prev_facebook, 'Custo')
        prev_conv_gd   = _soma(prev_google_degrau, 'Conversões')
        prev_leads_fb  = _soma(prev_facebook, 'Resultado Presencial + Live')
        prev_cpl_fb    = prev_custo_fb / prev_leads_fb if prev_leads_fb > 0 else 0

        linhas.append(f"Investimento total Degrau: R${(prev_custo_gd + prev_custo_fb):.2f}")
        linhas.append(f"  Google Ads (Degrau): R${prev_custo_gd:.2f} | Conversões: {int(prev_conv_gd)}")
        linhas.append(f"  Meta Ads (Degrau):   R${prev_custo_fb:.2f} | Resultado Presencial + Live: {int(prev_leads_fb)}" +
                      (f" | CPL: R${prev_cpl_fb:.2f}" if prev_leads_fb > 0 else ""))
        linhas.append("")

        linhas.extend(_bloco_campanhas(prev_google_degrau, "Google Ads (Degrau) — Período Anterior"))
        linhas.extend(_bloco_campanhas(prev_facebook, "Meta Ads (Degrau) — Período Anterior"))

    return "\n".join(linhas)

# =====================================================
# SYSTEM PROMPTS v4.0 (Março 2026)
# =====================================================

SYSTEM_PROMPT_ADS_V2 = """
SYSTEM PROMPT — SISTEMA DE INTELIGÊNCIA DE MARKETING
Degrau Cultural / Central de Concursos
Versão 2.5 — Abril 2026

Base: v2.4. Correções v2.5: hierarquia explícita de classificação (API > campo estruturado > naming),
travas flexíveis com override justificado, frequência por tipo de campanha, separação Meta Tráfego e
Meta Venda no resumo, camada operacional recuperada (micros, pausadas, zeradas), período parametrizável.

1. IDENTIDADE E PAPEL

Você é o analista sênior de tráfego pago da operação Degrau Cultural / Central de Concursos.

1. Resumo Diretoria: visão executiva, clara, objetiva e sem jargão técnico desnecessário, focada em
   investimento, eficiência, tendência e decisão.

2. Análise Completa para o Gestor de Tráfego: diagnóstico técnico campanha a campanha, com gargalos
   identificados, prioridade definida e plano de ação prático.

Idioma: português brasileiro. Tom: técnico, direto, sem enrolação. Pode ser coloquial, mas nunca
genérico. Toda recomendação deve responder: o que está acontecendo, por que isso importa e o que fazer agora.

2. CONTEXTO DO NEGÓCIO

Marcas: Central de Concursos (São Paulo, desde 1989) e Degrau Cultural (Rio de Janeiro, desde 1983).

Segmento: cursos preparatórios para concursos públicos no Brasil. Três modalidades: Presencial
(aulas em unidades físicas), Live (aulas ao vivo remotas com horário fixo) e Online (acesso assíncrono).

Modelo de funil:
- Presencial e Live: o site não vende diretamente. O papel principal das campanhas é gerar lead
  para atendimento consultivo.
- Online: em campanhas específicas de venda, o curso pode ser comprado direto no site. Tratar como e-commerce.
- PMax Google: leva para página do concurso com múltiplas modalidades. Pode gerar lead presencial/live
  e compra online indireta.

Concorrentes principais: Estratégia Concursos e Gran Cursos Online. Competem no mesmo leilão,
modelo mais orientado a venda direta online.

Concursos ativos mudam constantemente. O sistema identifica os concursos a partir dos nomes das
campanhas e dos campos estruturados recebidos.

3. REGRAS ESTRUTURAIS DE CLASSIFICAÇÃO

3.1 Hierarquia de classificação de campanhas

Fonte de verdade para classificar o tipo/objetivo de uma campanha, em ordem de precedência:

1. 1ª fonte — Campo objetivo da API: usar o campo 'objective' ou equivalente retornado pela API
   da plataforma (Google Ads API: campaign.advertising_channel_type + bidding_strategy; Meta
   Marketing API: campaign.objective). Esta é a fonte mais confiável.

2. 2ª fonte — Campo estruturado nos dados: quando a integração com o CRM envia campos explícitos
   como 'tipo_campanha', 'objetivo_campanha' ou equivalente, usar como segunda referência.

3. 3ª fonte — Naming convention (fallback): usar o marcador entre barras no nome da campanha
   (/LEADS/, /TRÁFEGO/, /VENDA/, /ONLINE/) apenas quando as fontes 1 e 2 estiverem ausentes ou
   inconsistentes. Se o naming contradizer a API, prevalece a API e o conflito deve ser sinalizado
   como problema de governança.

Quando houver inconsistência entre fontes (ex: API diz LEADS mas nome diz /TRÁFEGO/), sinalizar
explicitamente no relatório, classificar pela fonte de maior precedência e recomendar correção de
naming ao gestor.

3.2 Regras gerais de classificação

- Separar SEMPRE a análise por marca. Central e Degrau nunca misturadas no mesmo bloco.
- Campanhas Meta em três famílias: Lead, Tráfego, Venda Online.
- Campanhas YouTube em duas famílias: Conversão ou Reconhecimento/Consideração (VVC).
- Campanhas com prefixo z{} são topo de funil, institucional ou marca. Não servem de benchmark
  para campanhas de concurso específico.

4. MÉTRICAS OBRIGATÓRIAS POR TIPO DE CAMPANHA

4.1 Google Ads — Search
- Status, custo, impressões, cliques, CTR, CPC, conversões primárias, CPA real, CPA desejado/tCPA,
  CPM, taxa de conversão.
- Parcela de impressões perdida por orçamento e por classificação/rank.

4.2 Google Ads — Performance Max
- Custo, conversões primárias, CPA real, tCPA, taxa de conversão, impressões, cliques, CTR, CPC, CPM.
- Parcela perdida por orçamento e por classificação quando disponível.
- Se houver visão por canal/grupo de assets, usar como apoio. Se não houver, não inventar diagnóstico
  granular de canal.

4.3 Google Ads — YouTube VVC
- Alcance: impressões, usuários exclusivos, frequência média 7d, CPM.
- Retenção: View Rate e quartis 25%, 50%, 75%, 100%.
- Engajamento: CPV, interações, taxa de interação.
Campanhas VVC nunca devem ser avaliadas por CPA como métrica principal.

4.4 Meta Ads — Lead
- Valor usado, impressões, alcance, frequência, leads primários (lead_presencial + lead_live) e
  CPL primário.
- Lead online: métrica secundária de apoio. Reportar em linha separada (complementar, não entra no
  CPL primário).

4.4.1 Fórmula obrigatória de CPL primário médio Meta

CPL primário médio Meta = Σ(custo das campanhas com objetivo = LEAD) ÷ Σ(lead_presencial + lead_live
dessas mesmas campanhas).

Proibido incluir no numerador custo de campanhas TRÁFEGO, VENDA ou VVC. Proibido incluir no
denominador leads gerados por essas campanhas. Aplicar a fórmula literal.

4.5 Meta Ads — Venda Online
- ROAS, custo por compra, volume de compras, valor de conversão, ticket médio quando disponível.
- Sem receita/valor de conversão: não concluir lucratividade.

4.6 Meta Ads — Tráfego
- Valor usado, impressões, alcance, frequência, cliques no link, CTR de link, CPC de link.
- Nunca avaliar por CPA, CPL ou ROAS.
- Não chamar de 'qualificado' sem métrica downstream (sessão engajada, microconversão, conversão
  assistida). Sem downstream, descrever apenas eficiência de distribuição.

4.7 Fórmula obrigatória de CPA médio Google Ads no Resumo

Reportar Google Ads em três linhas separadas:
1. Concurso específico: R$ X.XXX | conversões: XXX | CPA médio: R$ XX,XX (exclui z{} e VVC).
2. Topo de funil z{}: R$ X.XXX | conversões: XXX | CPA estrutural: R$ XX,XX (referencial interno).
3. YouTube VVC: R$ X.XXX (investimento em awareness, sem denominador de conversão).

Proibido calcular CPA médio único consolidando z{}, concurso específico e VVC.

5. PRINCÍPIOS GERAIS DE ANÁLISE

1. Diagnosticar antes de prescrever. Sempre responder primeiro: qual é o principal gargalo aqui?
2. Separar fato, inferência e hipótese. Causa não comprovada: 'pode indicar', 'sugere', 'hipótese
   provável'. Nunca afirmar como certeza.
3. Não confundir eficiência com qualidade. CPA menor não significa lead melhor.
4. Dados ausentes não autorizam chute.
5. Comparar período atual com anterior sempre que disponível.
6. Hipóteses sazonais: citar o feriado específico e a data. Proibido 'pode ser pós-feriado' sem
   especificar qual e quando.

5.1 Normalização de variação por investimento

Antes de afirmar 'queda/crescimento de volume', comparar Δconversões% contra Δcusto%.

Três cenários:
1. Custo e conversões variaram em proporção similar (diferença < 10pp como regra padrão):
   eficiência estável. Descrever como 'investimento ajustado, CPA estável'. Investigar causa do
   corte/aumento antes de diagnosticar.
2. Custo caiu e conversões caíram menos ou cresceram: eficiência melhorou.
3. Conversões caíram bem mais que custo, OU custo subiu e conversões caíram: perda de eficiência
   real. Diagnosticar e agir.

A faixa de 10pp é referência padrão, não trava absoluta. Em campanhas com oscilação alta de volume
(orçamento < R$50/dia, concurso com demanda flutuante), usar julgamento contextual e sinalizar a
limitação.

6. REGRAS DE ANÁLISE — GOOGLE ADS

6.1 Search
- Ler primeiro: custo, conversões, CPA real, taxa de conversão, CPC e comparação com o tCPA.
- Perda por classificação alta: problema é relevância/leilão/lance/LP, não orçamento.
- Perda por orçamento alta: há espaço para discutir aumento de verba.
- Não usar 'Ad Strength' como explicação principal de rank em Search.

6.2 Lógica correta de tCPA
- Reduzir tCPA = mais seletivo, pode reduzir volume. Aumentar tCPA = mais competitivo, pode piorar
  eficiência.
Nunca recomendar redução de tCPA como caminho para ganhar volume.
- CPA acima do alvo: avaliar competição, estrutura, LP, relevância antes de recomendar aumento de tCPA.

tCPA não é meta de negócio. É parâmetro operacional do algoritmo. O gestor pode elevar tCPA para
competir no leilão sem que o novo valor represente o CPA desejado. Não usar 'dentro/fora do tCPA'
como critério principal de sucesso. Usar como contexto auxiliar da trajetória.

6.3 Performance Max
- Avaliar por CPA, volume e tendência.
- Não afirmar 'asset ruim' sem evidência além de classification loss.
- PMax com CPA menor que Search: apontar diferença como ponto de análise, não recomendar realocação
  sem dado de qualidade.

6.4 YouTube
- VVC = topo de funil. Julgar por alcance, retenção, engajamento.
- Melhora de View Rate não prova sozinha que criativo melhorou. Tratar como indicativo.

7. REGRAS DE ANÁLISE — META ADS

7.1 Lead
- Ler primeiro: valor investido, alcance, frequência, leads primários e CPL primário.
- CTR bom + CPL ruim: pode ser fricção de formulário, público desalinhado ou promessa inadequada.
  Não culpar LP sem sinal consistente.

7.2 Tráfego
- Julgar por cliques no link, CTR, CPC, alcance e frequência.
- Não chamar de 'qualificado' sem métrica downstream.

7.3 Venda Online
- Tratar como e-commerce.
- Sem receita: concluir apenas eficiência de compra, não rentabilidade.
- Lead gerado em campanha de venda: métrica secundária, não entra no bloco principal de leads.

7.4 Frequência — réguas por tipo de campanha

Frequência não tem uma régua única. O limiar de alerta depende do tipo de campanha e do tamanho
do público:
- Prospecção ampla (campanhas de lead com público aberto): frequência ≥ 2,5 = sinal de atenção.
  ≥ 3,0 = alerta de saturação.
- Retargeting (visitantes, engajamento, lookalike próximo): frequência até 4,0–5,0 pode ser normal.
  Alertar acima de 5,0.
- Venda online (público menor, intento comercial): frequência até 3,0–3,5 pode ser aceitável,
  especialmente com público pequeno. Alertar acima de 3,5.
- Tráfego/Awareness: frequência ≥ 2,5 = sinal de atenção. Manter abaixo de 2,0 idealmente.

Esses limiares são referência padrão, não lei absoluta. Se o gestor estiver operando público
deliberadamente pequeno com frequência mais alta, registrar o dado sem tratar como problema
automático. Sinalizar e deixar a decisão para o gestor.

8. REGRAS CRÍTICAS DE CONSISTÊNCIA E QUALIDADE

8.1 Validação matemática obrigatória

Direção numérica: Se número subiu, texto não pode dizer 'queda/caiu/redução'. Se caiu, não pode
dizer 'alta/crescimento/aumento'.

Polaridade de métricas:
- Menor = melhor: CPA, CPL, CPC, CPM, custo por compra. Aumento = PIORA, queda = MELHORA.
- Maior = melhor: conversões, leads primários, CTR, View Rate, ROAS, taxa de conversão. Aumento =
  MELHORA, queda = PIORA.
- Frequência: não tem polaridade única. Depende do tipo de campanha (ver seção 7.4). Não classificar
  automaticamente como 'quanto menor, melhor'.

Proibido chamar aumento de CPA/CPL/CPC de 'melhora' ou 'resultado positivo', ainda que dentro da
meta ou do tCPA.

8.2 Coerência entre blocos

Bloco 1 (Resumo Diretoria) não pode contradizer Bloco 2 (Análise Completa).

Mecanismo obrigatório: gerar Bloco 2 PRIMEIRO, depois derivar Bloco 1 a partir das conclusões do
Bloco 2. Na apresentação final: Bloco 1 no topo, Bloco 2 abaixo. Geração e visualização são
independentes.

8.3 Separação obrigatória de funis

Proibido misturar métricas de funis diferentes no mesmo indicador principal. Ver seções 4.4.1 e
4.7 para fórmulas.

8.4 Volume mínimo para conclusões

Com menos de 30 conversões primárias OU menos de 30 compras online no período:
- CPA/CPL/custo por compra não é estatisticamente confiável para conclusão forte.
- Proibido: 'tendência positiva/negativa', 'dobrou', 'triplicou', 'melhora consistente', 'queda
  sistemática'.
- Permitido: descrever valores absolutos e sinalizar 'volume insuficiente para conclusão estatística'.
- Campanhas com orçamento < R$100/dia podem ter < 30 conversões por natureza. A régua limita a
  força da conclusão, não a elegibilidade para análise ou destaque (ver 10.1.1).

8.5 Proibição de previsão numérica sem base

'+40 conversões', 'recuperar X leads' só com premissas explícitas. Senão, linguagem qualitativa.

8.6 Campanha com nome desatualizado

Sinalizar como problema de governança e possível fadiga de oferta. Nome não prova causa da piora.

9. COMPORTAMENTO QUANDO FALTAM METAS OU DADOS

- Sem CPA target: registrar 'meta não informada', analisar tendência e eficiência relativa sem
  julgamento binário.
- Sem search impression shares: apontar que não é possível separar gargalo de orçamento vs.
  classificação.
- Sem receita: não concluir ROAS ou rentabilidade.
- Sem semana anterior: analisar período atual e solicitar comparativo para próxima rodada.

10. FORMATO DE SAÍDA OBRIGATÓRIO

10.0 Período de análise

Período padrão: semanal, de domingo a sábado. Porém, o sistema deve aceitar qualquer janela
temporal que vier nos dados (quinzenal, mensal, custom). Extrair o período dos metadados recebidos.
Se o período não for semanal, adaptar a análise mantendo todas as regras (WoW vira período-a-período
com a janela correspondente).

Sempre que houver dados do período anterior, incluir comparativo.

ORDEM DE GERAÇÃO: gerar Bloco 2 primeiro, depois Bloco 1, depois Bloco 3. ORDEM DE APRESENTAÇÃO:
Bloco 1 no topo, Bloco 2 abaixo, Bloco 3 no final.

10.1 Bloco 1 — Resumo Diretoria

Separado por marca. Dentro de cada marca:

INVESTIMENTO E LEADS:
- Google Ads (concurso específico): R$ X.XXX | conversões: XXX | CPA médio: R$ XX,XX
- Google Ads (topo de funil z{}): R$ X.XXX | conversões: XXX | CPA estrutural: R$ XX,XX
- Google Ads (YouTube VVC): R$ X.XXX (awareness, sem denominador)
- Meta Ads (campanhas /LEADS/): R$ X.XXX | leads primários: XXX | CPL primário médio: R$ XX,XX
- Meta Ads (campanhas /TRÁFEGO/): R$ X.XXX | cliques: XXX | CPC médio: R$ XX,XX
- Meta Ads (campanhas /VENDA/ ou /ONLINE/): R$ X.XXX | compras: XX | custo por compra: R$ XX,XX

[Comparativo com período anterior quando disponível]

Subdivisão obrigatória por objetivo:

── OBJETIVO: /LEADS/ ──
DESTAQUES POSITIVOS:
PONTOS DE ATENÇÃO:
DECISÕES NECESSÁRIAS:

── OBJETIVO: YouTube — Reconhecimento e Consideração ──
DESTAQUES POSITIVOS:
PONTOS DE ATENÇÃO:
DECISÕES NECESSÁRIAS:

── OBJETIVO: /TRÁFEGO/ ──
DESTAQUES POSITIVOS:
PONTOS DE ATENÇÃO:
DECISÕES NECESSÁRIAS:

── OBJETIVO: /VENDA/ ou /ONLINE/ ──
DESTAQUES POSITIVOS:
PONTOS DE ATENÇÃO:
DECISÕES NECESSÁRIAS:

Tom: claro, executivo, sem jargão. Não usar z{} como destaque por CPA baixo.

10.1.1 Critério para Destaque Positivo

Campanha entra em Destaques Positivos quando demonstra melhora material ou estabilidade saudável.
Pelo menos UM dos seguintes sinais:
1. Melhora WoW: CPA/CPL caiu e volume se manteve ou cresceu.
2. Escala eficiente: volume cresceu em proporção maior que o custo.
3. Estabilidade saudável: CPA/CPL estável por 2+ semanas em patamar eficiente, sem sinais de alerta.

Bloqueios padrão (regra geral, com override justificado):
- CPA/CPL subiu mais de 10% WoW → vai para Pontos de Atenção.
- Queda de conversões > 15% WoW sem causa contextual (corte planejado de orçamento, fim de edital).
  Se queda de conversões for proporcional à queda de investimento (≤ 10pp), não é bloqueio.
- Frequência Meta acima do limiar do tipo de campanha (ver seção 7.4).
- < 30 conversões E sem comparativo WoW: não tratar como destaque, apenas descrever.

Override: qualquer bloqueio pode ser superado se houver justificativa explícita nos dados. Exemplo:
CPA subiu 12% WoW mas a campanha está escalando de R$50/dia para R$150/dia com volume triplicando —
a piora marginal de CPA pode ser aceitável no contexto. Nesse caso, listar como destaque COM a
ressalva da piora de CPA. O ponto é: o bloqueio é o padrão; o override exige justificativa escrita.

Sobre tCPA: não usar 'dentro/fora do tCPA' como critério principal. tCPA é parâmetro operacional.

Volume mínimo: campanhas com orçamento < R$100/dia podem ser destaque com < 30 conversões, desde
que trajetória WoW seja consistente por 2+ semanas.

10.2 Bloco 2 — Análise Completa para o Gestor de Tráfego

Separar por marca. Dentro de cada marca, quatro blocos: (1) /LEADS/, (2) YouTube VVC,
(3) /TRÁFEGO/, (4) /VENDA/ ou /ONLINE/.

Para campanhas YouTube VVC, apresentar os dados em FORMATO TABULAR ANTES do diagnóstico campanha
a campanha:

VISÃO GERAL (consolidado de todas as campanhas YouTube VVC da marca):
  Impressões: XX.XXX | Usuários únicos: XX.XXX | Custo total: R$ X.XXX,XX | CPM médio: R$ XX,XX

TABELA ALCANCE:
| Campanha | Orçam./dia | Impr. | Usuários Excl. | Freq. 7D | CPM Méd. |
| [nome]   | R$ XX,XX   | XX.XXX| XX.XXX          | X,X      | R$ XX,XX |

TABELA RETENÇÃO DE VÍDEO:
| Campanha | View Rate | 25% | 50% | 75% | 100% |
| [nome]   | XX,X%     | XX% | XX% | XX% | XX%  |

TABELA ENGAJAMENTO:
| Campanha | CPV Méd. | CPC Méd. | Interações | Taxa Inter. | Visualizações |
| [nome]   | R$ X,XX  | R$ X,XX  | XX.XXX     | X,XX%       | XX.XXX        |

Para cada campanha: números atual vs. anterior, diagnóstico (gargalo principal primeiro) e plano
de ação.

z{}: contextualizar CPA baixo como estrutural. PMax vs Search: apontar diferença sem recomendar
realocação. Orçamento: linguagem progressiva ('testar incremento de 10-20%').

10.3 Bloco 3 — Alocação de Budget

- Só incluir quando houver base real.
- Distinguir recomendações diretas de 'pontos para avaliação do gestor'.
- Não recomendar migração Search → PMax apenas por CPA menor.

11. PROCESSAMENTO DOS DADOS DAS PLATAFORMAS

11.1 Origem dos dados
Dados chegam das APIs (Google Ads API e Meta Marketing API) via integração com o CRM. Formato pode
variar: tabelas, objetos estruturados, dados brutos.

11.2 Regras de processamento
1. Conversão de micros: Se os dados vierem com valores em micros (ex: cost_micros), converter para
   reais dividindo por 1.000.000.
2. Classificação YouTube: se o nome contém 'VVC', 'view', 'visualização' ou 'engajamento', OU se o
   campo objetivo da API indica VIDEO/AWARENESS → tratar como VVC. Caso contrário → conversão. Em
   caso de dúvida, seguir hierarquia da seção 3.1.
3. Classificação Meta: se objetivo é VENDAS ou nome contém '/VENDA/', '/ONLINE/' → venda online.
   Se objetivo é TRAFEGO ou nome contém '/TRÁFEGO/' → tráfego. Demais → lead. Hierarquia da seção
   3.1 prevalece.
4. Campos ausentes ou zerados: sinalizar na análise, não inventar dados.
5. Adaptar leitura ao formato recebido. Extrair o máximo independentemente da estrutura.
6. Campanhas com gasto no período: incluir na análise TODA campanha que teve custo > 0 OU
   impressões > 0, mesmo que esteja atualmente pausada (pode ter sido pausada no meio da semana).
   Para campanhas pausadas com gasto, sinalizar: 'Campanha pausada durante o período. Custo
   registrado: R$ X,XX com X conversões antes da pausa.'
7. Campanhas zeradas: campanhas com custo = R$ 0,00 E impressões = 0 devem ser listadas no final
   da seção em bloco resumido ('Campanhas zeradas/pausadas'), com recomendação de verificar se são
   legados a limpar ou se há oportunidade perdida (edital aberto para aquele concurso).

12. CHECKLIST FINAL ANTES DE ENTREGAR

1.  Toda variação percentual bate com os números absolutos?
2.  Polaridade correta: CPA que subiu NÃO é 'melhora', conversões que caíram NÃO é 'resultado
    positivo'? Frequência avaliada pelo tipo de campanha (seção 7.4)?
3.  Bloco 1 foi derivado do Bloco 2 e nenhuma frase contradiz o detalhamento?
4.  Hipótese não foi tratada como fato?
5.  Recomendação de tCPA não está com lógica invertida?
6.  CPL médio Meta usa APENAS custo e leads de campanhas /LEADS/? CPA médio Google separado em
    três linhas? Meta separado em três linhas (lead/tráfego/venda)?
7.  Campanhas com < 30 conversões ou < 30 compras não receberam rótulo de 'tendência'?
8.  z{} não virou herói falso do relatório?
9.  Para cada campanha com Δcusto > 10%, variação de conversões normalizada pelo investimento?
10. Hipóteses sazonais citam feriado e data específicos?
11. Campanhas pausadas com gasto foram incluídas? Zeradas foram listadas no bloco de legados?
12. Classificação seguiu hierarquia 3.1 (API > campo estruturado > naming)? Inconsistências
    sinalizadas?

13. TIKTOK ADS (SECUNDÁRIO)

- Se dados chegarem, tratar como awareness/tráfego salvo indicação de conversão.
- Métricas: custo, impressões, cliques, CTR, CPC, visualizações de vídeo.
- Rastreamento incompleto: declarar limitação.

14. SAÍDA ESPERADA DO SISTEMA

O relatório final deve ser útil para decisão: rigor matemático, separação correta dos funis e
humildade analítica quando o dado não fecha o diagnóstico.

Resumo em uma linha: melhor um relatório ligeiramente menos brilhante e matematicamente sólido do
que um relatório bonito, confiante e errado.

Versão do prompt: 2.5 | Abril 2026
Base: v2.4. Correções v2.5: (1) Hierarquia explícita de classificação API > campo estruturado >
naming (3.1), (2) Travas flexíveis com override justificado (10.1.1), (3) Frequência por tipo de
campanha (7.4 + 8.1), (4) Meta Tráfego e Meta Venda separados no resumo (10.1), (5) Camada
operacional recuperada: micros, pausadas, zeradas (11.2), (6) Período parametrizável (10.0).
"""

SYSTEM_PROMPT_ALERTA_DIARIO = """
Você é um monitor de tráfego pago para Central de Concursos e Degrau Cultural.

REGRA FUNDAMENTAL: os alertas devem ser SEMPRE separados por marca. Jamais misture campanhas
da Central de Concursos com campanhas da Degrau Cultural.

Seu objetivo é APENAS identificar anomalias que exigem ação imediata. NÃO faça análise completa.

=== ALERTAR APENAS SE ===

ADS:
- Campanha ativa com 0 impressões (possível reprovação)
- Gasto diário >2x o gasto médio diário da campanha
- CPA diário >3x o CPA médio (só para LEADS/VENDAS com 30+ conversões no histórico)
- Campanha de REMARKETING/Meta com frequência >5 no dia
- Erro de pixel/tracking (conversões = 0 em todas as campanhas de uma marca)

ORGÂNICO:
- Post/vídeo viralizando (>5x média de views em 24h)
- Queda de sessões do blog >40% vs mesmo dia semana passada
- Comentários negativos em volume incomum

=== FORMATO DA RESPOSTA ===

Se NÃO houver anomalias:
"✅ Tudo normal. Nenhuma anomalia detectada."

Se houver anomalias, organizar por marca:

"═══ CENTRAL DE CONCURSOS ═══
🚨 ALERTA [TIPO]: [descrição curta]
Ação sugerida: [o que fazer agora]

═══ DEGRAU CULTURAL ═══
🚨 ALERTA [TIPO]: [descrição curta]
Ação sugerida: [o que fazer agora]"

Máximo 5 alertas por marca. Priorize por gravidade.
NÃO inclua análises, recomendações estratégicas ou comentários gerais. Só alertas acionáveis.
"""

SYSTEM_PROMPT_SOCIAL_V2 = """
Você é um analista sênior de social media especializado em
marketing educacional brasileiro para concursos públicos.
Você analisa Central de Concursos e Degrau Cultural.

=== PERIODICIDADE E CONTEXTO ===
Os dados que você recebe cobrem uma semana completa
(segunda a domingo). Compare SEMPRE com a semana anterior
quando dados estiverem disponíveis.

Ciclos naturais por plataforma:
- Instagram: post performa em 48-72h; Reels até 7 dias
- TikTok: 24h a 7 dias (redistribuição algorítmica)
- YouTube: 7-14 dias (algoritmo lento, long tail)
- Facebook: 48-72h (alcance orgânico decrescente)

Não compare vídeos de 2 dias com vídeos de 7 dias.
Ao listar performance de posts, SEMPRE inclua a idade
do post (quantos dias desde publicação) para contextualizar.

=== MÉTRICAS POR TIPO DE CONTEÚDO ===

REELS / TIKTOK (vídeo curto):
  - Métrica primordial: Completion Rate (% que assistiu até o fim)
  - Secundárias: shares (viralidade), saves (valor), views
  - Completion <30% = hook fraco
  - Completion >60% = conteúdo excelente
  - Shares alto + saves alto = conteúdo viral E útil

FEED / CARROSSEL:
  - Métrica primordial: Taxa de Salvamento (saves/alcance)
  - Secundárias: engajamento, comentários, shares
  - Para concursos, saves > likes em importância
    (salvar = "vou estudar isso depois")

STORIES:
  - Respostas e taps back (indicam interesse)
  - Exits e taps forward (indicam desinteresse)
  - Taxa de saída por story para identificar onde perde atenção

YOUTUBE (vídeo longo):
  - CTR de thumbnail (benchmark: >5% bom, >8% excelente)
  - Retenção média (benchmark: >40% bom, >50% excelente)
  - Watch time total (mais importante que views)
  - Inscritos ganhos por vídeo

=== ESTRUTURA DO RELATÓRIO ===

1. RESUMO EXECUTIVO
   - Visão cross-platform em 3-5 linhas
   - Destaque da semana (melhor conteúdo + por quê)
   - Crescimento de seguidores (todas as plataformas)

2. INSTAGRAM
   - Alcance e impressões (% vs semana anterior)
   - Top 3 posts por engajamento (com idade do post)
   - Taxa de salvamento média
   - Performance Reels vs Feed vs Carrossel vs Stories
   - Melhor horário de publicação (se dado disponível)

3. TIKTOK
   - Views totais e média por vídeo
   - Completion rate médio
   - Top 3 vídeos por share rate (viralidade)
   - Temas/formatos que mais performaram

4. YOUTUBE
   - Watch time total da semana
   - CTR média de thumbnails
   - Retenção média
   - Inscritos ganhos vs perdidos
   - ATENÇÃO: vídeos recentes (<7 dias) podem não ter
     dados maduros. Sinalize quando for o caso.

5. FACEBOOK
   - Alcance orgânico e engajamento
   - Comparação com semana anterior

6. ALERTAS
   - Post/vídeo viralizando (>3x média de views)
   - Queda de alcance >20% sem mudança de frequência
   - Vídeos com retenção <30% (hook fraco)
   - Engajamento negativo (comentários críticos em alta)

7. RECOMENDAÇÕES DE CONTEÚDO
   - Formatos para REPLICAR (com justificativa em dados)
   - Formatos para EVITAR (com justificativa em dados)
   - 3-5 sugestões de temas baseadas em:
     a) O que performou esta semana
     b) Concursos com editais próximos (se informado)
     c) Dores do público evidenciadas nos comentários/saves
   - Cross-posting: conteúdo do IG que pode ir pro TikTok
     e vice-versa (com adaptações)

=== REGRAS ===
- Nunca invente dados.
- Sempre contextualize a idade do post ao avaliar performance.
- Para concursos, conteúdo de VALOR (dicas, resumos, mapas
  mentais) tende a performar melhor que conteúdo motivacional
  genérico. Favoreça recomendações nessa direção.
- Recomendações devem ser específicas, não genéricas.
  Em vez de "poste mais Reels", diga "Reels de 15-20s
  com dicas rápidas de [tema X] tiveram 2x mais completion."
"""

SYSTEM_PROMPT_SEO_V2 = """
Você é um analista de SEO e conteúdo especializado em
marketing educacional brasileiro para concursos públicos.

=== PERIODICIDADE E CONTEXTO ===

Dados do Google Search Console têm delay de 2-3 dias.
Os dados que você recebe devem ser comparados com o período
equivalente anterior.

Regras de temporalidade:
- Mudanças de posição <2 posições em 1 semana = flutuação
  normal, NÃO sinalize como queda ou ganho
- Mudanças de posição >5 posições = tendência real, SINALIZE
- Mudanças de 2-5 posições = acompanhar na próxima semana
- CTR varia muito com sazonalidade de editais. Sempre
  considere se há edital recente influenciando buscas.

Para Blog (GA4): análise semanal é adequada.
Para SEO (GSC): análise quinzenal/mensal é ideal.
Se receber dados semanais de SEO, seja conservador nas
conclusões e sinalize quando a janela é curta demais.

=== CONTEXTO DO NICHO ===

Concursos públicos têm sazonalidade forte:
- Publicação de edital = pico de busca (dias)
- Próximo à prova = pico de busca (semanas antes)
- Pós-prova = pico de gabarito/resultado (1-2 dias)
- Entre editais = volume baixo, foco em evergreen

Tipos de conteúdo por intenção:
- TRANSACIONAL: "inscrição concurso X", "curso preparatorio X"
  -> Prioridade máxima, converter em lead/matrícula
- INFORMACIONAL-QUENTE: "edital concurso X", "vagas concurso X"
  -> Alta prioridade, público próximo da decisão
- INFORMACIONAL-FRIA: "o que faz um [cargo]", "como estudar para"
  -> Média prioridade, funil de topo
- NAVEGACIONAL: "central de concursos", "degrau cultural"
  -> Marca, monitorar mas não otimizar

=== ESTRUTURA DO RELATÓRIO ===

1. RESUMO DO BLOG (GA4)
   - Sessões totais, usuários, pageviews
   - Canal principal de aquisição (% por canal)
   - Mobile vs Desktop (% e diferenças de comportamento)
   - Taxa de conversão geral
   - Comparação vs período anterior (% variação)

2. TOP 10 PÁGINAS (por tráfego orgânico)
   - Cliques, impressões, CTR, posição média
   - Classificar por INTENÇÃO (transacional/informacional)
   - Sinalizar se há edital ativo influenciando

3. QUICK WINS DE SEO
   - Queries com posição 5-20 E >100 impressões/semana
   - Priorizar por INTENÇÃO: transacional > informacional-quente
     > informacional-fria
   - Para cada quick win, sugerir ação específica
   - NÍVEL DE CONFIANÇA: [ALTA] ou [MÉDIA]

4. PROBLEMAS DE CTR
   - Páginas com posição <5 e CTR <5%
   - Sugerir title tag e meta description otimizados
   - Usar gatilhos do nicho: vagas, salário, data da prova

5. CANIBALIZAÇÃO
   - Queries com 2+ páginas competindo
   - Só sinalize como canibalização se ambas estiverem
     na posição >5

6. OPORTUNIDADES DE CONTEÚDO
   - Queries com volume mas sem página dedicada
   - Artigos desatualizados (>6 meses sem update + queda)
   - Priorizar por potencial de conversão

7. COMPARAÇÃO COM PERÍODO ANTERIOR
   - Páginas que ganharam >5 posições (celebrar)
   - Páginas que perderam >5 posições (diagnosticar)
   - Flutuações de 1-2 posições: IGNORAR (ruído)

=== REGRAS ===
- Nunca invente dados ou posições.
- Priorize sempre conteúdo transacional sobre informacional.
- Considere sazonalidade de editais ao interpretar picos/quedas.
- Flutuações de 1-2 posições em 1 semana são NORMAIS.
- Se os dados cobrem <14 dias, sinalize que conclusões
  de SEO são PRELIMINARES.
- Sugestões de title/description devem ser específicas
  e prontas para implementar, não genéricas.
"""

# =====================================================
# LÓGICA DE PERIODICIDADE (v2.0)
# =====================================================

def selecionar_config_automatica():
    """Seleciona prompt e janela baseado no dia da semana."""
    hoje = datetime.now().date()
    dia_semana = hoje.weekday()  # 0=segunda

    configs = []

    # Alerta diário (seg a sex)
    if dia_semana in [0, 1, 2, 3, 4]:
        configs.append({
            "nome": "Alerta Diário (Ads)",
            "prompt": SYSTEM_PROMPT_ALERTA_DIARIO,
            "janela": 1,
            "tipo": "alerta",
        })

    # Segunda: relatório completo de ads (7 dias)
    if dia_semana == 0:
        configs.append({
            "nome": "Relatório Semanal de Ads",
            "prompt": SYSTEM_PROMPT_ADS_V2,
            "janela": 7,
            "tipo": "completo_ads",
        })

    # Quarta: relatório de SEO (14 dias)
    if dia_semana == 2:
        configs.append({
            "nome": "Relatório Quinzenal de SEO",
            "prompt": SYSTEM_PROMPT_SEO_V2,
            "janela": 14,
            "tipo": "seo",
        })

    # Se não caiu em nenhum especial (sábado/domingo), padrão = alerta
    if not configs:
        configs.append({
            "nome": "Alerta Diário (Ads)",
            "prompt": SYSTEM_PROMPT_ALERTA_DIARIO,
            "janela": 1,
            "tipo": "alerta",
        })

    return configs

# =====================================================
# RENDERIZAÇÃO VISUAL DA ANÁLISE DA IA
# =====================================================

def _renderizar_analise(analise: str, tipo: str = "completo_ads"):
    """Renderiza o texto de análise do Claude com formatação visual aprimorada.

    Estratégia:
    - Divide o texto nos blocos principais (BLOCO 1, BLOCO 2, BLOCO 3 / ALERTA).
    - Cada bloco é exibido num contêiner com estilo e cor próprios.
    - Dentro do BLOCO 2, cada campanha individual é exibida num expander.
    - Linhas com ⚠️ são destacadas como avisos (st.warning).
    - Linhas com 🚨 são destacadas como erros (st.error).
    - Restante é renderizado como markdown normal.
    """
    CSS = """
    <style>
    .bloco-card {
        background: #f8f9fa;
        border-left: 4px solid #1f77b4;
        border-radius: 6px;
        padding: 1rem 1.2rem;
        margin-bottom: 1rem;
    }
    .bloco-resumo { border-left-color: #2ca02c; }
    .bloco-completo { border-left-color: #1f77b4; }
    .bloco-budget { border-left-color: #ff7f0e; }
    .bloco-alerta { border-left-color: #d62728; }
    .marca-header {
        background: linear-gradient(90deg, #1f3c88 0%, #1565c0 100%);
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 4px;
        font-weight: 700;
        font-size: 1.05rem;
        margin: 0.8rem 0 0.4rem 0;
    }
    .campanha-nome {
        font-weight: 700;
        color: #0d47a1;
        font-size: 0.95rem;
    }
    </style>
    """
    st.markdown(CSS, unsafe_allow_html=True)

    # ── Divide nos três blocos principais ──────────────────────────────────
    def _split_blocos(texto):
        """Retorna lista de (titulo, conteudo) para cada bloco detectado."""
        # Padrões de abertura de bloco
        import re as _re
        pattern = _re.compile(
            r'(BLOCO\s+\d+\s*[—\-–]+[^\n]+|'
            r'═{3,}[^\n]*|'
            r'\*{2}BLOCO\s+\d+[^\*]+\*{2})',
            _re.IGNORECASE
        )
        parts = pattern.split(texto)
        blocos = []
        i = 0
        if parts and parts[0].strip():
            blocos.append(("INTRODUÇÃO", parts[0]))
        i = 1
        while i < len(parts) - 1:
            titulo = parts[i].strip()
            conteudo = parts[i + 1] if i + 1 < len(parts) else ""
            blocos.append((titulo, conteudo))
            i += 2
        return blocos

    def _cor_bloco(titulo: str):
        t = titulo.upper()
        if "RESUMO" in t or "BLOCO 1" in t or "BLOCO1" in t:
            return "bloco-resumo", "📊 RESUMO DIRETORIA"
        if "COMPLETA" in t or "GESTOR" in t or "BLOCO 2" in t or "BLOCO2" in t:
            return "bloco-completo", "🔍 ANÁLISE COMPLETA — GESTOR DE TRÁFEGO"
        if "BUDGET" in t or "ALOCAÇÃO" in t or "BLOCO 3" in t or "BLOCO3" in t:
            return "bloco-budget", "💰 ALOCAÇÃO DE BUDGET"
        if "ALERTA" in t:
            return "bloco-alerta", "🚨 ALERTAS"
        return "bloco-card", titulo

    def _render_conteudo(conteudo: str):
        """Renderiza o conteúdo de um bloco, tratando campanhas, alertas e marcas."""
        import re as _re
        linhas = conteudo.split("\n")
        buffer = []

        def _flush():
            txt = "\n".join(buffer).strip()
            if txt:
                # Detecta e converte tabelas ASCII simples em st.dataframe
                if _tentar_tabela(txt):
                    pass
                else:
                    st.markdown(txt)
            buffer.clear()

        def _tentar_tabela(txt):
            """Tenta converter bloco de texto com | em uma tabela visual."""
            linhas_t = [l for l in txt.split("\n") if l.strip()]
            linhas_pipe = [l for l in linhas_t if "|" in l]
            if len(linhas_pipe) < 2:
                return False
            # Separa cabeçalho e dados (ignora linhas de separação --)
            rows = []
            for l in linhas_pipe:
                if _re.match(r"^[\s\|\-\:]+$", l):
                    continue
                cells = [c.strip() for c in l.split("|") if c.strip()]
                if cells:
                    rows.append(cells)
            if len(rows) < 2:
                return False
            try:
                df_t = pd.DataFrame(rows[1:], columns=rows[0])
                st.dataframe(df_t, use_container_width=True, hide_index=True)
                return True
            except Exception:
                return False

        i = 0
        while i < len(linhas):
            linha = linhas[i]
            linha_strip = linha.strip()

            # Cabeçalho de marca (═══ xxxx ═══)
            if _re.match(r"^═{2,}.*═{2,}$", linha_strip) or (
                linha_strip.startswith("═") or linha_strip.endswith("═")
            ):
                _flush()
                st.markdown(
                    f'<div class="marca-header">{linha_strip.replace("═", "").strip()}</div>',
                    unsafe_allow_html=True,
                )
                i += 1
                continue

            # Linha de campanha individual dentro do Bloco 2
            if _re.match(r"^(CAMPANHA|CAMP\.?)\s*:", linha_strip, _re.IGNORECASE):
                _flush()
                nome_camp = linha_strip.split(":", 1)[-1].strip()
                # Acumula o bloco da campanha até a próxima campanha ou separador
                bloco_camp = [linha]
                j = i + 1
                while j < len(linhas):
                    prox = linhas[j].strip()
                    if _re.match(r"^(CAMPANHA|CAMP\.?)\s*:", prox, _re.IGNORECASE):
                        break
                    if _re.match(r"^═{3,}", prox):
                        break
                    bloco_camp.append(linhas[j])
                    j += 1
                camp_txt = "\n".join(bloco_camp).strip()
                _render_campanha_expander(nome_camp, camp_txt)
                i = j
                continue

            # Alertas ⚠️
            if "⚠️" in linha_strip and linha_strip:
                _flush()
                st.warning(linha_strip)
                i += 1
                continue

            # Alertas críticos 🚨
            if "🚨" in linha_strip and linha_strip:
                _flush()
                st.error(linha_strip)
                i += 1
                continue

            buffer.append(linha)
            i += 1

        _flush()

    def _render_campanha_expander(nome: str, conteudo: str):
        """Renderiza uma campanha individual dentro de um expander com ícone de status."""
        import re as _re

        # Detecta indicadores de status para colorir o ícone
        tem_alerta = "⚠️" in conteudo or "🚨" in conteudo
        icone = "🔴" if "🚨" in conteudo else ("🟡" if tem_alerta else "🟢")
        label = f"{icone} {nome}"

        linhas_diag = [l.strip() for l in conteudo.split("\n") if "DIAGNÓSTICO" in l.upper() or "maior problema" in l.lower()]
        subtitulo = linhas_diag[0].replace("DIAGNÓSTICO:", "").replace("DIAGNÓSTICO", "").strip() if linhas_diag else ""
        if subtitulo:
            label += f"  —  {subtitulo[:80]}"

        with st.expander(label, expanded=False):
            linhas = conteudo.split("\n")

            # Extrai metadados da campanha (PLATAFORMA, TIPO, STATUS)
            meta_info = {}
            SECOES = {
                "PLATAFORMA": "meta",
                "TIPO": "meta",
                "STATUS": "meta",
                "NÚMEROS": "numeros",
                "DIAGNÓSTICO": "diagnostico",
                "PLANO DE AÇÃO": "plano",
                "PLANO": "plano",
            }

            secao_atual = None
            buffer_secao = []

            def _flush_secao(secao, buf):
                txt = "\n".join(buf).strip()
                if not txt:
                    return
                if secao == "numeros":
                    _render_metricas_inline(txt)
                elif secao == "diagnostico":
                    st.info(f"**🔎 Diagnóstico:** {txt}")
                elif secao == "plano":
                    st.success(f"**✅ Plano de Ação:**\n\n{txt}")
                elif secao == "meta":
                    pass  # exibido no badge acima
                else:
                    st.markdown(txt)

            def _render_metricas_inline(txt):
                """Extrai pares chave:valor separados por | e exibe como métricas.
                Linhas com prefixo [Search]: ou [Meta Lead]: etc. são exibidas como subseções."""
                import re as _re

                linhas_num = txt.split("\n")
                for linha_num in linhas_num:
                    linha_num = linha_num.strip()
                    if not linha_num:
                        continue

                    # Detecta prefixo de subseção [Search]: / [Meta Lead]: / [YouTube VVC]:
                    sub_match = _re.match(r"^\[([^\]]+)\]\s*:?\s*(.*)", linha_num)
                    if sub_match:
                        sub_label = sub_match.group(1)
                        sub_rest = sub_match.group(2).strip()
                        st.caption(f"**{sub_label}**")
                        if sub_rest:
                            linha_num = sub_rest
                        else:
                            continue

                    # Extrai pares chave:valor separados por |
                    metricas = []
                    partes = [p.strip() for p in linha_num.split("|") if p.strip()]
                    for parte in partes:
                        if ":" in parte:
                            k, _, v = parte.partition(":")
                            metricas.append((k.strip(), v.strip()))
                        else:
                            metricas.append(("", parte))

                    if metricas:
                        chunk = 4
                        for idx in range(0, len(metricas), chunk):
                            grupo = metricas[idx:idx + chunk]
                            cols = st.columns(len(grupo))
                            for ci, (k, v) in enumerate(grupo):
                                if k:
                                    cols[ci].metric(k, v)
                                else:
                                    cols[ci].markdown(f"**{v}**")
                    else:
                        st.markdown(linha_num)

            for linha in linhas:
                linha_strip = linha.strip()
                detectou = False
                for chave, tipo_secao in SECOES.items():
                    if _re.match(rf"^{chave}\s*(\([^)]*\))?\s*:", linha_strip, _re.IGNORECASE):
                        if secao_atual is not None:
                            _flush_secao(secao_atual, buffer_secao)
                        secao_atual = tipo_secao
                        # Extrai o valor após "CHAVE:" ou "CHAVE (extra):"
                        valor_match = _re.match(rf"^{chave}\s*(?:\([^)]*\))?\s*:\s*(.*)", linha_strip, _re.IGNORECASE)
                        valor = valor_match.group(1).strip() if valor_match else ""
                        if tipo_secao == "meta":
                            meta_info[chave.upper()] = valor
                        buffer_secao = [valor] if valor else []
                        detectou = True
                        break
                if not detectou:
                    if "⚠️" in linha_strip and linha_strip:
                        if secao_atual is not None:
                            _flush_secao(secao_atual, buffer_secao)
                            buffer_secao = []
                        st.warning(linha_strip)
                        secao_atual = None
                    elif "🚨" in linha_strip and linha_strip:
                        if secao_atual is not None:
                            _flush_secao(secao_atual, buffer_secao)
                            buffer_secao = []
                        st.error(linha_strip)
                        secao_atual = None
                    else:
                        buffer_secao.append(linha)

            if secao_atual is not None:
                _flush_secao(secao_atual, buffer_secao)

            # Exibe metadados da campanha como badges no topo
            if meta_info:
                parts = []
                if "PLATAFORMA" in meta_info:
                    parts.append(f"**Plataforma:** {meta_info['PLATAFORMA']}")
                if "TIPO" in meta_info:
                    parts.append(f"**Tipo:** {meta_info['TIPO']}")
                if "STATUS" in meta_info:
                    parts.append(f"**Status:** {meta_info['STATUS']}")
                if parts:
                    st.markdown(" &nbsp;|&nbsp; ".join(parts))

    # ── Renderiza cada bloco ───────────────────────────────────────────────
    if tipo == "alerta":
        # Para alertas: renderiza diretamente sem subdivisão em blocos
        st.markdown(analise)
        return

    blocos = _split_blocos(analise)

    if len(blocos) <= 1:
        # Fallback: se não conseguiu separar, renderiza o markdown simples com destaque
        _render_conteudo(analise)
        return

    TABS_LABELS = []
    TABS_CONTENT = []
    for titulo, conteudo in blocos:
        if not conteudo.strip() and not titulo.strip():
            continue
        css_class, label = _cor_bloco(titulo)
        TABS_LABELS.append(label)
        TABS_CONTENT.append((css_class, titulo, conteudo))

    if len(TABS_LABELS) >= 2:
        tabs = st.tabs(TABS_LABELS)
        for tab, (css_class, titulo, conteudo) in zip(tabs, TABS_CONTENT):
            with tab:
                _render_conteudo(conteudo)
    else:
        for css_class, titulo, conteudo in TABS_CONTENT:
            _render_conteudo(conteudo)




def _get_anthropic_client():
    """Inicializa o client Anthropic de forma segura."""
    try:
        import anthropic
    except ImportError:
        return None, "❌ Biblioteca `anthropic` não instalada. Execute: `pip install anthropic`"

    api_key = None
    try:
        api_key = st.secrets["antropic"]["ANTHROPIC_API_KEY"]
    except (st.errors.StreamlitAPIException, KeyError, FileNotFoundError):
        pass
    if not api_key:
        api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None, "❌ API Key do Claude não configurada. Defina ANTHROPIC_API_KEY no .env ou Streamlit Secrets."

    # max_retries: o SDK faz retry automático com backoff exponencial para 529 (overloaded)
    return anthropic.Anthropic(api_key=api_key, max_retries=5), None

def analisar_com_claude(dados_consolidados, system_prompt=None, tipo_relatorio="completo_ads"):
    """Envia dados para o Claude e retorna a análise usando o prompt correto."""
    import time

    import anthropic as _anthropic

    client, erro = _get_anthropic_client()
    if erro:
        return erro

    if system_prompt is None:
        system_prompt = SYSTEM_PROMPT_ADS_V2

    if tipo_relatorio == "alerta":
        user_msg = f"Dados de ontem:\n\n{dados_consolidados}\n\nVerifique se há anomalias conforme as regras."
    else:
        user_msg = f"Segue o relatório de performance do período:\n\n{dados_consolidados}\n\nAnalise conforme a estrutura definida."

    max_tentativas = 4
    for tentativa in range(1, max_tentativas + 1):
        try:
            with client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=64000,
                thinking={
                    "type": "enabled",
                    "budget_tokens": 32000
                },
                system=system_prompt,
                messages=[{"role": "user", "content": user_msg}]
            ) as stream:
                texto = stream.get_final_text()
                final = stream.get_final_message()

            usage = final.usage
            print(
                f"[Claude API] model={final.model} | tentativa={tentativa} | input_tokens={usage.input_tokens} | "
                f"output_tokens={usage.output_tokens} | stop_reason={final.stop_reason}"
            )
            return texto

        except _anthropic.APIStatusError as e:
            if e.status_code == 529:  # overloaded_error
                espera = 2 ** tentativa  # 2s, 4s, 8s, 16s
                print(f"[Claude API] Sobrecarga na tentativa {tentativa}. Aguardando {espera}s...")
                if tentativa < max_tentativas:
                    time.sleep(espera)
                else:
                    return f"❌ API do Claude sobrecarregada após {max_tentativas} tentativas. Tente novamente em alguns minutos."
            else:
                return f"❌ Erro na API do Claude ({e.status_code}): {e.message}"

        except Exception as e:
            return f"❌ Erro inesperado ao chamar o Claude: {e}"

# =====================================================
# HISTÓRICO DE RELATÓRIOS (MySQL)
# Tabela: seducar.ai_reports
# Colunas: id, uuid, reference_date, type, generated_at, raw_data, ai_analysis
# =====================================================

def _get_writer_engine():
    """Obtém engine de escrita via conexao/mysql_connector."""
    try:
        from conexao.mysql_connector import conectar_mysql_writer
        return conectar_mysql_writer()
    except ImportError:
        return None


def salvar_relatorio(analise, dados_consolidados, data_ref, tipo="completo_ads"):
    """Salva o relatório no banco de dados MySQL."""
    import uuid as uuid_mod

    engine = _get_writer_engine()
    if engine:
        try:
            with engine.connect() as conn:
                conn.execute(
                    sql_text("""
                        INSERT INTO ai_reports (uuid, reference_date, type, generated_at, raw_data, ai_analysis)
                        VALUES (:uuid, :reference_date, :type, :generated_at, :raw_data, :ai_analysis)
                    """),
                    {
                        "uuid": str(uuid_mod.uuid4()),
                        "reference_date": data_ref,
                        "type": tipo,
                        "generated_at": datetime.now(),
                        "raw_data": dados_consolidados,
                        "ai_analysis": analise,
                    }
                )
                conn.commit()
            return "db"
        except Exception as e:
            st.warning(f"Erro ao salvar no banco: {e}. Salvando localmente.")

    # Fallback: salva em arquivo local
    os.makedirs(HISTORICO_DIR, exist_ok=True)
    relatorio = {
        "data": data_ref,
        "tipo": tipo,
        "gerado_em": datetime.now().isoformat(),
        "dados_brutos": dados_consolidados,
        "analise_claude": analise,
    }
    filepath = os.path.join(HISTORICO_DIR, f"relatorio_{tipo}_{data_ref}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(relatorio, f, ensure_ascii=False, indent=2)
    return filepath


def carregar_relatorios_historico(filtro_tipo=None):
    """Carrega relatórios do banco MySQL (com fallback para arquivos locais)."""
    relatorios = []

    # Tenta carregar do banco
    engine = _get_writer_engine()
    if engine:
        try:
            query = "SELECT id, uuid, reference_date, type, generated_at, raw_data, ai_analysis FROM ai_reports"
            params = {}
            if filtro_tipo:
                query += " WHERE type = :tipo"
                params["tipo"] = filtro_tipo
            query += " ORDER BY generated_at DESC LIMIT 50"

            with engine.connect() as conn:
                result = conn.execute(sql_text(query), params)
                for row in result:
                    gerado_em = row.generated_at.isoformat() if row.generated_at else ""
                    relatorios.append({
                        "id": row.id,
                        "uuid": row.uuid,
                        "data": row.reference_date,
                        "tipo": row.type,
                        "gerado_em": gerado_em,
                        "analise": row.ai_analysis or "",
                        "dados_brutos": row.raw_data or "",
                    })
            if relatorios:
                return relatorios
        except Exception as e:
            st.warning(f"Erro ao carregar do banco: {e}. Tentando arquivos locais.")

    # Fallback: arquivos locais
    if not os.path.exists(HISTORICO_DIR):
        return relatorios
    arquivos = sorted(glob.glob(os.path.join(HISTORICO_DIR, "relatorio_*.json")), reverse=True)
    for arq in arquivos:
        try:
            with open(arq, "r", encoding="utf-8") as f:
                data = json.load(f)
                tipo = data.get("tipo", "completo_ads")
                if filtro_tipo and tipo != filtro_tipo:
                    continue
                relatorios.append({
                    "id": None,
                    "uuid": None,
                    "data": data.get("data", ""),
                    "tipo": tipo,
                    "gerado_em": data.get("gerado_em", ""),
                    "analise": data.get("analise_claude", ""),
                    "dados_brutos": data.get("dados_brutos", ""),
                })
        except (json.JSONDecodeError, KeyError):
            continue
    return relatorios

# =====================================================
# PÁGINA STREAMLIT (v2.0)
# =====================================================

def run_page():
    st.title("🤖 Relatórios IA — Análise de Campanhas com Claude")
    st.markdown("Análise estratégica automatizada por **objetivo de campanha** com níveis de confiança (v2.0)")

    tab_ads, tab_alerta, tab_historico = st.tabs([
        "📊 Análise Completa (Ads)",
        "🚨 Alerta Diário",
        "📁 Histórico",
    ])

    # ----- SIDEBAR GLOBAL -----
    st.sidebar.header("⚙️ Configurações")
    hoje = datetime.now().date()
    ontem = hoje - timedelta(days=1)

    contas = st.sidebar.multiselect(
        "Contas para incluir:",
        ["Google Ads (Degrau)", "Google Ads (Central)", "Meta Ads (Degrau)", "Meta Ads (Central)"],
        default=["Google Ads (Degrau)", "Google Ads (Central)", "Meta Ads (Degrau)", "Meta Ads (Central)"],
        key="ria_contas"
    )

    # Agenda automática
    configs_auto = selecionar_config_automatica()
    nomes_auto = [c["nome"] for c in configs_auto]
    st.sidebar.info(f"📅 Hoje ({hoje.strftime('%d/%m/%Y')}): {', '.join(nomes_auto)}")

    # =========================================================
    # ABA 1: ANÁLISE COMPLETA DE ADS
    # =========================================================
    with tab_ads:
        st.header("📊 Análise Completa de Tráfego Pago")
        st.caption("Avalia cada campanha pelo seu **objetivo real** (LEADS, TRAFEGO, REMARKETING, VIDEO, VENDAS)")

        modo = st.radio("Período:", ["Últimos 7 dias", "Personalizado", "Personalizado + Comparação"], key="ria_ads_modo", horizontal=True)

        prev_start_custom = None
        prev_end_custom = None

        if modo == "Últimos 7 dias":
            start_date = hoje - timedelta(days=7)
            end_date = ontem
            janela_dias = 7
        elif modo == "Personalizado":
            periodo = st.date_input("Selecione o período:", [hoje - timedelta(days=7), ontem], key="ria_ads_periodo")
            if len(periodo) != 2:
                st.warning("Selecione um período válido.")
                st.stop()
            start_date, end_date = periodo
            janela_dias = (end_date - start_date).days + 1
        else:
            col_atual, col_comp = st.columns(2)
            with col_atual:
                st.markdown("**📅 Período Atual**")
                periodo = st.date_input("Período atual:", [hoje - timedelta(days=7), ontem], key="ria_ads_periodo_atual")
                if len(periodo) != 2:
                    st.warning("Selecione o período atual.")
                    st.stop()
                start_date, end_date = periodo
                janela_dias = (end_date - start_date).days + 1
            with col_comp:
                st.markdown("**📅 Período de Comparação**")
                default_prev_end = start_date - timedelta(days=1)
                default_prev_start = default_prev_end - timedelta(days=janela_dias - 1)
                periodo_comp = st.date_input("Período comparação:", [default_prev_start, default_prev_end], key="ria_ads_periodo_comp")
                if len(periodo_comp) != 2:
                    st.warning("Selecione o período de comparação.")
                    st.stop()
                prev_start_custom, prev_end_custom = periodo_comp

        # Exibe resumo dos períodos
        info_periodo = f"📅 **Atual:** {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')} ({janela_dias} dias)"
        if prev_start_custom and prev_end_custom:
            dias_comp = (prev_end_custom - prev_start_custom).days + 1
            info_periodo += f"  |  **Comparação:** {prev_start_custom.strftime('%d/%m/%Y')} a {prev_end_custom.strftime('%d/%m/%Y')} ({dias_comp} dias)"
        st.info(info_periodo)

        if st.button("🔍 Buscar Dados", type="primary", use_container_width=True, key="btn_ads_buscar"):
            _coletar_dados(contas, start_date, end_date, janela_dias, "ads_dados", prev_start_custom, prev_end_custom)
        dados_ads_prontos = "ads_dados" in st.session_state
        if st.button(
            "🤖 Analisar com IA",
            use_container_width=True,
            key="btn_ads_ia",
            disabled=not dados_ads_prontos,
        ):
            _enviar_para_ia("ads_dados", SYSTEM_PROMPT_ADS_V2, "completo_ads")

        if "ads_dados" in st.session_state:
            info = st.session_state["ads_dados"]
            st.info(f"📦 Dados prontos: **{info['data_ref']}** — clique em 'Analisar com IA' quando estiver pronto.")
            with st.expander("📋 Ver dados coletados"):
                st.code(info["dados_consolidados"], language="text")

    # =========================================================
    # ABA 2: ALERTA DIÁRIO
    # =========================================================
    with tab_alerta:
        st.header("🚨 Alerta Diário — Detecção de Anomalias")
        st.caption("Verifica apenas se há problemas que exigem ação imediata. Rápido e objetivo.")

        start_alerta = ontem
        end_alerta = ontem

        st.info(f"📅 Verificando dados de ontem: **{start_alerta.strftime('%d/%m/%Y')}**")

        if st.button("🔍 Buscar Dados", type="primary", use_container_width=True, key="btn_alerta_buscar"):
            _coletar_dados(contas, start_alerta, end_alerta, 1, "alerta_dados")
        dados_alerta_prontos = "alerta_dados" in st.session_state
        if st.button(
            "🚨 Analisar com IA",
            use_container_width=True,
            key="btn_alerta_ia",
            disabled=not dados_alerta_prontos,
        ):
            _enviar_para_ia("alerta_dados", SYSTEM_PROMPT_ALERTA_DIARIO, "alerta")

        if "alerta_dados" in st.session_state:
            info = st.session_state["alerta_dados"]
            st.info(f"📦 Dados prontos: **{info['data_ref']}** — clique em 'Analisar com IA' quando estiver pronto.")
            with st.expander("📋 Ver dados coletados"):
                st.code(info["dados_consolidados"], language="text")

    # =========================================================
    # ABA 3: HISTÓRICO
    # =========================================================
    with tab_historico:
        st.header("📁 Relatórios Anteriores")

        filtro = st.selectbox("Filtrar por tipo:", ["Todos", "completo_ads", "alerta"], key="ria_hist_filtro")
        filtro_tipo = None if filtro == "Todos" else filtro

        relatorios = carregar_relatorios_historico(filtro_tipo)

        if not relatorios:
            st.info("Nenhum relatório gerado ainda.")
        else:
            st.write(f"**{len(relatorios)} relatório(s)**")
            for idx, rel in enumerate(relatorios):
                gerado_em = ""
                if rel["gerado_em"]:
                    try:
                        dt_val = datetime.fromisoformat(rel["gerado_em"])
                        gerado_em = dt_val.strftime("%d/%m/%Y às %H:%M")
                    except ValueError:
                        gerado_em = rel["gerado_em"]

                icone = "🚨" if rel["tipo"] == "alerta" else "📊"
                with st.expander(f"{icone} {rel['data']} [{rel['tipo']}] — {gerado_em}"):
                    st.markdown(rel["analise"])
                    html_bytes = gerar_html_relatorio(
                        rel["analise"], rel["dados_brutos"], rel["data"], rel["tipo"]
                    )
                    st.download_button(
                        label="📥 Exportar Relatório HTML",
                        data=html_bytes,
                        file_name=f"relatorio_{rel['tipo']}_{rel['data']}.html",
                        mime="text/html",
                        use_container_width=True,
                        key=f"btn_html_hist_{idx}_{rel['tipo']}_{rel['data']}",
                    )
                    with st.expander("📋 Dados brutos"):
                        st.code(rel["dados_brutos"], language="text")


def _executar_analise(contas, start_date, end_date, janela_dias, system_prompt, tipo):
    """Executa a coleta + análise e exibe resultados."""
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    data_ref = start_str if start_str == end_str else f"{start_str}_a_{end_str}"

    df_google_degrau = pd.DataFrame()
    df_google_central = pd.DataFrame()
    df_facebook = pd.DataFrame()
    df_facebook_central = pd.DataFrame()

    # Coleta Google Ads Degrau
    if "Google Ads (Degrau)" in contas:
        with st.spinner("🔄 Buscando Google Ads (Degrau)..."):
            client_degrau = init_google_ads_client("google-ads.yaml")
            if client_degrau:
                try:
                    customer_id = str(st.secrets["google_ads"]["customer_id"])
                except Exception:
                    customer_id = "4934481887"
                df_google_degrau = get_google_ads_data(client_degrau, customer_id, start_str, end_str)
            else:
                st.warning("⚠️ Não foi possível conectar ao Google Ads (Degrau)")

    # Coleta Google Ads Central
    if "Google Ads (Central)" in contas:
        with st.spinner("🔄 Buscando Google Ads (Central)..."):
            client_central = init_google_ads_client_central()
            if client_central:
                try:
                    customer_id_c = str(st.secrets["google_ads_central"]["customer_id"])
                except Exception:
                    customer_id_c = "1646681121"
                df_google_central = get_google_ads_data(client_central, customer_id_c, start_str, end_str)
            else:
                st.warning("⚠️ Não foi possível conectar ao Google Ads (Central)")

    # Coleta Meta Ads (Degrau)
    if "Meta Ads (Degrau)" in contas:
        with st.spinner("🔄 Buscando Meta Ads (Degrau)..."):
            fb_account = init_facebook_api()
            if fb_account:
                df_facebook = get_facebook_data(fb_account, start_str, end_str)
            else:
                st.warning("⚠️ Não foi possível conectar ao Meta Ads (Degrau)")

    # Coleta Meta Ads (Central)
    if "Meta Ads (Central)" in contas:
        with st.spinner("🔄 Buscando Meta Ads (Central)..."):
            fb_account_central = init_facebook_api_central()
            if fb_account_central:
                df_facebook_central = get_facebook_data(fb_account_central, start_str, end_str)
            else:
                st.warning("⚠️ Não foi possível conectar ao Meta Ads (Central)")

    if df_google_degrau.empty and df_google_central.empty and df_facebook.empty and df_facebook_central.empty:
        st.error("❌ Nenhum dado coletado. Verifique as credenciais e o período.")
        return

    # Métricas rápidas
    st.subheader("📊 Dados Coletados")
    col1, col2, col3, col4 = st.columns(4)
    custo_gd = df_google_degrau['Custo'].sum() if not df_google_degrau.empty else 0
    custo_gc = df_google_central['Custo'].sum() if not df_google_central.empty else 0
    custo_fb = df_facebook['Custo'].sum() if not df_facebook.empty else 0
    custo_fbc = df_facebook_central['Custo'].sum() if not df_facebook_central.empty else 0
    col1.metric("Google Degrau", formatar_reais(custo_gd))
    col2.metric("Google Central", formatar_reais(custo_gc))
    col3.metric("Meta Degrau", formatar_reais(custo_fb))
    col4.metric("Meta Central", formatar_reais(custo_fbc))

    st.metric("💰 Total Investido", formatar_reais(custo_gd + custo_gc + custo_fb + custo_fbc))

    # Mostra distribuição por objetivo
    _mostrar_distribuicao_objetivos(df_google_degrau, df_google_central, df_facebook, df_facebook_central)

    # Tabelas detalhadas por conta Google Ads
    with st.expander("📋 Ver campanhas Google Ads por conta", expanded=False):
        if not df_google_degrau.empty:
            _mostrar_tabelas_google_ads(df_google_degrau, "Google Ads — Degrau")
        if not df_google_central.empty:
            _mostrar_tabelas_google_ads(df_google_central, "Google Ads — Central")

    # Formata e envia
    dados_consolidados = formatar_dados_para_claude(
        df_google_degrau, df_google_central, df_facebook, janela_dias,
        df_facebook_central=df_facebook_central,
        start_date=start_date, end_date=end_date
    )

    with st.spinner("🤖 Analisando com Claude..."):
        analise = analisar_com_claude(dados_consolidados, system_prompt, tipo)

    # Exibe
    icone = "🚨" if tipo == "alerta" else "🤖"
    st.subheader(f"{icone} Análise do Claude")
    _renderizar_analise(analise, tipo)

    filepath = salvar_relatorio(analise, dados_consolidados, data_ref, tipo)
    if filepath == "db":
        st.success("✅ Relatório salvo no banco de dados!")
    else:
        st.success(f"✅ Relatório salvo localmente!")

    # Botão de exportar relatório HTML
    html_bytes = gerar_html_relatorio(analise, dados_consolidados, data_ref, tipo)
    nome_html = f"relatorio_{tipo}_{data_ref}.html"
    st.download_button(
        label="📥 Exportar Relatório HTML",
        data=html_bytes,
        file_name=nome_html,
        mime="text/html",
        use_container_width=True,
        key=f"btn_html_{tipo}_{data_ref}",
    )

    with st.expander("📋 Ver dados brutos enviados ao Claude"):
        st.code(dados_consolidados, language="text")


def _mostrar_distribuicao_objetivos(df_gd, df_gc, df_fb, df_fbc=None):
    """Mostra um resumo visual da distribuição por objetivo de campanha."""
    dfs = []
    if not df_gd.empty:
        dfs.append(df_gd)
    if not df_gc.empty:
        dfs.append(df_gc)
    if not df_fb.empty:
        dfs.append(df_fb)
    if df_fbc is not None and not df_fbc.empty:
        dfs.append(df_fbc)

    if not dfs:
        return

    df_all = pd.concat(dfs, ignore_index=True)
    if 'Objetivo' not in df_all.columns:
        return

    resumo = df_all.groupby('Objetivo').agg(
        Campanhas=('Campanha', 'count'),
        Custo=('Custo', 'sum'),
        Conversões=('Conversões', 'sum'),
    ).reset_index().sort_values('Custo', ascending=False)

    st.subheader("🎯 Distribuição por Objetivo")
    cols = st.columns(len(resumo))
    for i, (_, row) in enumerate(resumo.iterrows()):
        with cols[i % len(cols)]:
            st.metric(
                f"{row['Objetivo']}",
                f"{int(row['Campanhas'])} camp.",
                f"R$ {row['Custo']:,.0f}".replace(",", ".")
            )


def _mostrar_tabelas_google_ads(df_google, label):
    """Exibe tabelas separadas para campanhas YouTube e demais campanhas do Google Ads."""
    if df_google is None or df_google.empty:
        return

    df_video = df_google[df_google['Canal'] == 'VIDEO'].copy()
    df_outros = df_google[df_google['Canal'] != 'VIDEO'].copy()

    # ── CAMPANHAS YOUTUBE ────────────────────────────────────────────────────
    if not df_video.empty:
        _mostrar_youtube_visual(df_video, label)

    # ── DEMAIS CAMPANHAS (Search, PMax, Display) ─────────────────────────────
    if not df_outros.empty:
        st.markdown(f"##### 🔍 Demais Campanhas — {label}")
        colunas_std = [
            'Campanha', 'Status', 'Canal', 'Tipo Lance',
            'Custo', 'Impressões', 'Cliques', 'CTR (%)',
            'CPC', 'CPM', 'Conversões', 'CPA', 'tCPA',
            'Taxa Conv (%)', 'Imp Lost Budget (%)', 'Imp Lost Rank (%)',
        ]
        colunas_std = [c for c in colunas_std if c in df_outros.columns]
        df_std_display = df_outros[colunas_std].copy()
        df_std_display.rename(columns={'tCPA': 'CPA Desejado (Lead)'}, inplace=True)

        for col in ['Custo', 'CPC', 'CPM', 'CPA', 'CPA Desejado (Lead)']:
            if col in df_std_display.columns:
                df_std_display[col] = df_std_display[col].apply(
                    lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    if pd.notna(v) and v > 0 else "-"
                )
        for col in ['CTR (%)', 'Taxa Conv (%)']:
            if col in df_std_display.columns:
                df_std_display[col] = df_std_display[col].apply(
                    lambda v: f"{v:.2f}%" if pd.notna(v) else "-"
                )
        for col in ['Imp Lost Budget (%)', 'Imp Lost Rank (%)']:
            if col in df_std_display.columns:
                df_std_display[col] = df_std_display[col].apply(
                    lambda v: f"{v:.1f}%" if pd.notna(v) else "-"
                )
        st.dataframe(df_std_display, use_container_width=True, hide_index=True)


def _fmt_brl(v, decimais=2):
    """Formata valor para R$ brasileiro."""
    if pd.isna(v) or v == 0:
        return "-"
    fmt = f"R$ {v:,.{decimais}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return fmt


def _fmt_pct(v, decimais=2):
    if pd.isna(v):
        return "-"
    return f"{v:.{decimais}f}%"


def _fmt_num(v):
    if pd.isna(v) or v == 0:
        return "-"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v / 1_000:.1f}k"
    return f"{v:,.0f}".replace(",", ".")


def _mostrar_youtube_visual(df_video, label):
    """Exibe campanhas YouTube com layout visual por pilares: Alcance, Retenção, Engajamento."""
    st.markdown(f"##### 📺 Campanhas YouTube — {label}")

    # ── VISÃO GERAL (métricas consolidadas) ──────────────────────────────
    total_imp = df_video['Impressões'].sum()
    total_unique = df_video['Usuários Exclusivos'].sum()
    total_custo = df_video['Custo'].sum()
    cpm_medio = (total_custo / total_imp * 1000) if total_imp > 0 else 0

    st.markdown(f"###### VISÃO GERAL (TOTAL DAS {len(df_video)} CAMPANHAS)")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Impressões", _fmt_num(total_imp))
    c2.metric("Usuários únicos", _fmt_num(total_unique))
    c3.metric("Custo total", _fmt_brl(total_custo))
    c4.metric("CPM médio", _fmt_brl(cpm_medio))
    st.markdown("---")

    # ── TABELA 1: ALCANCE ────────────────────────────────────────────────
    st.markdown("###### ALCANCE")
    df_alcance = pd.DataFrame({
        'CAMPANHA': df_video['Campanha'],
        'ORÇAM./DIA': df_video['Custo'].apply(lambda v: _fmt_brl(v / 7 if v > 0 else 0, 0)),
        'IMPR.': df_video['Impressões'].apply(lambda v: f"{v:,.0f}".replace(",", ".")),
        'USUÁRIOS EXCL.': df_video['Usuários Exclusivos'].apply(lambda v: f"{v:,.0f}".replace(",", ".")),
        'FREQ. 7D': df_video['Freq Méd Imp/Usuário'].apply(lambda v: f"{v:.1f}" if v > 0 else "-"),
        'CPM MÉD.': df_video['CPM'].apply(lambda v: _fmt_brl(v)),
    })
    st.dataframe(df_alcance, use_container_width=True, hide_index=True)

    # ── TABELA 2: RETENÇÃO DE VÍDEO ─────────────────────────────────────
    st.markdown("###### RETENÇÃO DE VÍDEO")
    df_retencao = pd.DataFrame({
        'CAMPANHA': df_video['Campanha'],
        'VIEW RATE': df_video['Video View Rate (%)'].apply(lambda v: _fmt_pct(v)),
        '25%': df_video['% Assistido 25'].apply(lambda v: _fmt_pct(v, 1)),
        '50%': df_video['% Assistido 50'].apply(lambda v: _fmt_pct(v, 1)),
        '75%': df_video['% Assistido 75'].apply(lambda v: _fmt_pct(v, 1)),
        '100%': df_video['% Assistido 100'].apply(lambda v: _fmt_pct(v, 1)),
    })
    st.dataframe(df_retencao, use_container_width=True, hide_index=True)

    # Gráfico de retenção (curvas por campanha)
    if len(df_video) > 0:
        fig = go.Figure()
        quartis = ['25%', '50%', '75%', '100%']
        x_labels = ['25%', '50%', '75%', '100%']
        cores = px.colors.qualitative.Set1
        for i, (_, row) in enumerate(df_video.iterrows()):
            nome = row['Campanha']
            if len(nome) > 30:
                nome = nome[:30] + "..."
            vals = [row['% Assistido 25'], row['% Assistido 50'], row['% Assistido 75'], row['% Assistido 100']]
            fig.add_trace(go.Scatter(
                x=x_labels, y=vals, mode='lines+markers',
                name=nome, line=dict(width=2, color=cores[i % len(cores)]),
                marker=dict(size=8),
            ))
        fig.update_layout(
            title="Curva de Retenção de Vídeo",
            xaxis_title="Quartil do vídeo",
            yaxis_title="% Audiência retida",
            yaxis=dict(range=[0, 100], ticksuffix="%"),
            height=350, margin=dict(t=40, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=-0.35, xanchor="center", x=0.5),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── TABELA 3: ENGAJAMENTO ────────────────────────────────────────────
    st.markdown("###### ENGAJAMENTO")
    df_eng = pd.DataFrame({
        'CAMPANHA': df_video['Campanha'],
        'CPV MÉD.': df_video['CPV'].apply(lambda v: _fmt_brl(v, 2)),
        'CPC MÉD.': df_video['CPC'].apply(lambda v: _fmt_brl(v)),
        'INTERAÇÕES': df_video['Engajamentos'].apply(lambda v: f"{v:,.0f}".replace(",", ".")),
        'TAXA DE INTER.': df_video['Taxa de Interação (%)'].apply(lambda v: _fmt_pct(v)),
        'VISUALIZAÇÕES': df_video['Video Views'].apply(lambda v: _fmt_num(v)),
    })
    st.dataframe(df_eng, use_container_width=True, hide_index=True)


def _coletar_dados(contas, start_date, end_date, janela_dias, session_key, prev_start_override=None, prev_end_override=None):
    """Coleta dados das APIs para o período selecionado E para o período anterior (WoW),
    exibe métricas e salva no session_state para análise posterior.
    Se prev_start_override e prev_end_override forem fornecidos, usa como período de comparação."""
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    data_ref = start_str if start_str == end_str else f"{start_str}_a_{end_str}"

    # Período anterior: customizado ou calculado automaticamente
    if prev_start_override and prev_end_override:
        prev_start_date = prev_start_override
        prev_end_date = prev_end_override
    else:
        duracao = (end_date - start_date).days + 1
        prev_end_date = start_date - timedelta(days=1)
        prev_start_date = prev_end_date - timedelta(days=duracao - 1)
    prev_start_str = prev_start_date.strftime('%Y-%m-%d')
    prev_end_str = prev_end_date.strftime('%Y-%m-%d')

    df_google_degrau = pd.DataFrame()
    df_google_central = pd.DataFrame()
    df_facebook = pd.DataFrame()
    df_facebook_central = pd.DataFrame()

    # DataFrames do período anterior
    prev_google_degrau = pd.DataFrame()
    prev_google_central = pd.DataFrame()
    prev_facebook = pd.DataFrame()
    prev_facebook_central = pd.DataFrame()

    if "Google Ads (Degrau)" in contas:
        with st.spinner("🔄 Buscando Google Ads (Degrau)..."):
            client_degrau = init_google_ads_client("google-ads.yaml")
            if client_degrau:
                try:
                    customer_id = str(st.secrets["google_ads"]["customer_id"])
                except Exception:
                    customer_id = "4934481887"
                df_google_degrau = get_google_ads_data(client_degrau, customer_id, start_str, end_str)
                prev_google_degrau = get_google_ads_data(client_degrau, customer_id, prev_start_str, prev_end_str)
            else:
                st.warning("⚠️ Não foi possível conectar ao Google Ads (Degrau)")

    if "Google Ads (Central)" in contas:
        with st.spinner("🔄 Buscando Google Ads (Central)..."):
            client_central = init_google_ads_client_central()
            if client_central:
                try:
                    customer_id_c = str(st.secrets["google_ads_central"]["customer_id"])
                except Exception:
                    customer_id_c = "1646681121"
                df_google_central = get_google_ads_data(client_central, customer_id_c, start_str, end_str)
                prev_google_central = get_google_ads_data(client_central, customer_id_c, prev_start_str, prev_end_str)
            else:
                st.warning("⚠️ Não foi possível conectar ao Google Ads (Central)")

    if "Meta Ads (Degrau)" in contas:
        with st.spinner("🔄 Buscando Meta Ads (Degrau)..."):
            fb_account = init_facebook_api()
            if fb_account:
                df_facebook = get_facebook_data(fb_account, start_str, end_str)
                prev_facebook = get_facebook_data(fb_account, prev_start_str, prev_end_str)
            else:
                st.warning("⚠️ Não foi possível conectar ao Meta Ads (Degrau)")

    if "Meta Ads (Central)" in contas:
        with st.spinner("🔄 Buscando Meta Ads (Central)..."):
            fb_account_central = init_facebook_api_central()
            if fb_account_central:
                df_facebook_central = get_facebook_data(fb_account_central, start_str, end_str)
                prev_facebook_central = get_facebook_data(fb_account_central, prev_start_str, prev_end_str)
            else:
                st.warning("⚠️ Não foi possível conectar ao Meta Ads (Central)")

    if df_google_degrau.empty and df_google_central.empty and df_facebook.empty and df_facebook_central.empty:
        st.error("❌ Nenhum dado coletado. Verifique as credenciais e o período.")
        return

    st.subheader("📊 Dados Coletados")
    col1, col2, col3, col4 = st.columns(4)
    custo_gd = df_google_degrau['Custo'].sum() if not df_google_degrau.empty else 0
    custo_gc = df_google_central['Custo'].sum() if not df_google_central.empty else 0
    custo_fb = df_facebook['Custo'].sum() if not df_facebook.empty else 0
    custo_fbc = df_facebook_central['Custo'].sum() if not df_facebook_central.empty else 0
    col1.metric("Google Degrau", formatar_reais(custo_gd))
    col2.metric("Google Central", formatar_reais(custo_gc))
    col3.metric("Meta Degrau", formatar_reais(custo_fb))
    col4.metric("Meta Central", formatar_reais(custo_fbc))
    st.metric("💰 Total Investido", formatar_reais(custo_gd + custo_gc + custo_fb + custo_fbc))

    _mostrar_distribuicao_objetivos(df_google_degrau, df_google_central, df_facebook, df_facebook_central)

    # Tabelas detalhadas por conta Google Ads
    with st.expander("📋 Ver campanhas Google Ads por conta", expanded=False):
        if not df_google_degrau.empty:
            _mostrar_tabelas_google_ads(df_google_degrau, "Google Ads — Degrau")
        if not df_google_central.empty:
            _mostrar_tabelas_google_ads(df_google_central, "Google Ads — Central")

    dados_consolidados = formatar_dados_para_claude(
        df_google_degrau, df_google_central, df_facebook, janela_dias,
        df_facebook_central=df_facebook_central,
        start_date=start_date, end_date=end_date,
        prev_google_degrau=prev_google_degrau,
        prev_google_central=prev_google_central,
        prev_facebook=prev_facebook,
        prev_facebook_central=prev_facebook_central,
        prev_start_date=prev_start_date,
        prev_end_date=prev_end_date,
    )

    st.session_state[session_key] = {
        "dados_consolidados": dados_consolidados,
        "data_ref": data_ref,
    }
    st.success("✅ Dados coletados! Revise abaixo e clique em 'Analisar com IA' quando estiver pronto.")
    with st.expander("📋 Ver dados que serão enviados à IA", expanded=True):
        st.code(dados_consolidados, language="text")


def _enviar_para_ia(session_key, system_prompt, tipo):
    """Lê os dados do session_state, envia ao Claude e exibe a análise."""
    if session_key not in st.session_state:
        st.warning("⚠️ Nenhum dado encontrado. Clique em 'Buscar Dados' primeiro.")
        return

    dados = st.session_state[session_key]
    dados_consolidados = dados["dados_consolidados"]
    data_ref = dados["data_ref"]

    with st.spinner("🤖 Analisando com Claude..."):
        analise = analisar_com_claude(dados_consolidados, system_prompt, tipo)

    icone = "🚨" if tipo == "alerta" else "🤖"
    st.subheader(f"{icone} Análise do Claude")
    _renderizar_analise(analise, tipo)

    filepath = salvar_relatorio(analise, dados_consolidados, data_ref, tipo)
    if filepath == "db":
        st.success("✅ Relatório salvo no banco de dados!")
    else:
        st.success("✅ Relatório salvo localmente!")

    html_bytes = gerar_html_relatorio(analise, dados_consolidados, data_ref, tipo)
    st.download_button(
        label="📥 Exportar Relatório HTML",
        data=html_bytes,
        file_name=f"relatorio_{tipo}_{data_ref}.html",
        mime="text/html",
        use_container_width=True,
        key=f"btn_html_{tipo}_{data_ref}",
    )
    with st.expander("📋 Ver dados brutos enviados ao Claude"):
        st.code(dados_consolidados, language="text")
