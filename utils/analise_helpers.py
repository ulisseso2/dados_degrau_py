"""Helpers compartilhados entre as páginas de análise (transcrições, chats, geral)."""

import re
import collections
import pandas as pd

_PAT_CAT = re.compile(r'^\[([^\]]+)\]\s*')


def _strip_cat(txt: str) -> str:
    return _PAT_CAT.sub('', str(txt)).strip()


def _extract_cat(txt: str) -> str:
    m = _PAT_CAT.match(str(txt))
    return m.group(1) if m else 'outros'


def _safe_pct(num, den) -> float:
    return (num / den * 100) if den else 0.0


def _cor_nota(nota) -> str:
    try:
        n = float(nota)
    except (TypeError, ValueError):
        return ""
    if n >= 75:
        return "🟢"
    if n >= 50:
        return "🟡"
    return "🔴"


def _top_items(series: pd.Series, n: int = 10) -> list:
    """Retorna top-n textos (sem prefixo [categoria]) com contagem."""
    itens = []
    for v in series.fillna(''):
        itens.extend([t.strip() for t in str(v).split(';') if t.strip()])
    contagem: dict = {}
    for item in itens:
        texto = _strip_cat(item)
        if texto:
            contagem[texto] = contagem.get(texto, 0) + 1
    return sorted(contagem.items(), key=lambda x: -x[1])[:n]


def _gerar_html_relatorio(
    agente: str,
    df_tab: pd.DataFrame,
    periodo_ini: str,
    periodo_fim: str,
    kpis: dict | None = None,
    df_raw: pd.DataFrame | None = None,
) -> str:
    """Gera HTML estilizado para download/impressão como PDF."""
    kpi_html = ""
    if kpis:
        kpi_items = "".join(
            f'<div class="kpi"><span class="kpi-label">{k}</span><span class="kpi-val">{v}</span></div>'
            for k, v in kpis.items()
        )
        kpi_html = f'<div class="kpi-row">{kpi_items}</div>'

    graficos_html = ""
    pontos_html = ""

    if df_raw is not None and not df_raw.empty:

        def _barra(label, n, total, cor):
            pct = round(n / total * 100) if total > 0 else 0
            return (
                f'<div class="bar-row">'
                f'<span class="bar-label">{label}</span>'
                f'<div class="bar-wrap"><div class="bar-fill" style="width:{pct}%;background:{cor}"></div></div>'
                f'<span class="bar-count">{n}</span></div>'
            )

        notas = df_raw['evaluation_ia'].dropna()
        if not notas.empty:
            faixas = [('0–20', 0, 20, '#dc3545'), ('21–40', 21, 40, '#fd7e14'),
                      ('41–60', 41, 60, '#ffc107'), ('61–80', 61, 80, '#28a745'), ('81–100', 81, 100, '#007bff')]
            bars = "".join(_barra(lbl, int(((notas >= lo) & (notas <= hi)).sum()), len(notas), cor)
                           for lbl, lo, hi, cor in faixas)
            graficos_html += f'<div class="chart-box"><h3>&#128202; Distribuição de Notas</h3><div class="bar-chart">{bars}</div></div>'

        if 'lead_classification' in df_raw.columns:
            lead_vc = df_raw['lead_classification'].dropna().value_counts()
            if not lead_vc.empty:
                CORES_LEAD = {'A': '#28a745', 'B': '#17a2b8', 'C': '#ffc107', 'D': '#dc3545'}
                total_leads = int(lead_vc.sum())
                bars_l = "".join(_barra(cls, int(lead_vc.get(cls, 0)), total_leads, CORES_LEAD.get(cls, '#999'))
                                 for cls in ['A', 'B', 'C', 'D'])
                graficos_html += f'<div class="chart-box"><h3>&#127919; Classificação de Leads</h3><div class="bar-chart">{bars_l}</div></div>'

        graficos_section = f'<div class="charts-row">{graficos_html}</div>' if graficos_html else ""

        if 'strengths' in df_raw.columns:
            all_s = [s.strip() for v in df_raw['strengths'].dropna()
                     for s in str(v).split(';') if s.strip()]
            if all_s:
                top_s = collections.Counter(all_s).most_common(5)
                items = "".join(f"<li>{t} <em>({c}x)</em></li>" for t, c in top_s)
                pontos_html += f'<div class="pontos-box pontos-forte"><h3>&#9989; Pontos Fortes (Top 5)</h3><ul>{items}</ul></div>'

        if 'improvements' in df_raw.columns:
            all_i = [s.strip() for v in df_raw['improvements'].dropna()
                     for s in str(v).split(';') if s.strip()]
            if all_i:
                top_i = collections.Counter(all_i).most_common(5)
                items = "".join(f"<li>{t} <em>({c}x)</em></li>" for t, c in top_i)
                pontos_html += f'<div class="pontos-box pontos-melhoria"><h3>&#9888;&#65039; Melhorias (Top 5)</h3><ul>{items}</ul></div>'

        if 'most_expensive_mistake' in df_raw.columns:
            erros = df_raw['most_expensive_mistake'].dropna()
            erros = erros[erros.str.strip() != '']
            if not erros.empty:
                top_e = erros.value_counts().head(5)
                items = "".join(f"<li>{t} <em>({c}x)</em></li>" for t, c in top_e.items())
                pontos_html += f'<div class="pontos-box pontos-erro"><h3>&#128184; Erros Mais Caros (Top 5)</h3><ul>{items}</ul></div>'

        pontos_section = f'<div class="pontos-row">{pontos_html}</div>' if pontos_html else ""
    else:
        graficos_section = ""
        pontos_section = ""

    colunas = [c for c in df_tab.columns if c != 'Transcrição']
    thead = "".join(f"<th>{c}</th>" for c in colunas)
    tbody = ""
    for _, row in df_tab.iterrows():
        cells = "".join(f"<td>{row.get(c, '')}</td>" for c in colunas)
        tbody += f"<tr>{cells}</tr>\n"

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head><meta charset="utf-8"><title>Relatório – {agente}</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 24px; color: #222; }}
  h1 {{ font-size: 20px; margin-bottom: 4px; }}
  h2 {{ font-size: 15px; margin: 20px 0 6px; }}
  h3 {{ font-size: 13px; margin: 8px 0 6px; }}
  p.sub {{ color: #666; font-size: 13px; margin-top: 0; }}
  .kpi-row {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 14px 0; }}
  .kpi {{ background: #f0f4ff; border-radius: 6px; padding: 8px 14px; min-width: 110px; }}
  .kpi-label {{ display: block; font-size: 11px; color: #666; }}
  .kpi-val {{ display: block; font-size: 18px; font-weight: bold; color: #1e6fb5; }}
  .charts-row {{ display: flex; flex-wrap: wrap; gap: 16px; margin: 16px 0; }}
  .chart-box {{ flex: 1; min-width: 220px; background: #f9fbff; border: 1px solid #dde4f0; border-radius: 8px; padding: 12px; }}
  .bar-chart {{ margin-top: 6px; }}
  .bar-row {{ display: flex; align-items: center; margin-bottom: 5px; gap: 6px; }}
  .bar-label {{ width: 46px; font-size: 11px; text-align: right; flex-shrink: 0; }}
  .bar-wrap {{ flex: 1; background: #e8edf5; border-radius: 3px; height: 13px; overflow: hidden; }}
  .bar-fill {{ height: 100%; border-radius: 3px; }}
  .bar-count {{ width: 26px; font-size: 11px; color: #555; flex-shrink: 0; }}
  .pontos-row {{ display: flex; flex-wrap: wrap; gap: 14px; margin: 14px 0; }}
  .pontos-box {{ flex: 1; min-width: 200px; border-radius: 8px; padding: 10px 14px; }}
  .pontos-forte {{ background: #e8f5e9; border: 1px solid #a5d6a7; }}
  .pontos-melhoria {{ background: #fff8e1; border: 1px solid #ffe082; }}
  .pontos-erro {{ background: #fce4ec; border: 1px solid #f48fb1; }}
  .pontos-box ul {{ margin: 4px 0 0; padding-left: 16px; font-size: 12px; line-height: 1.75; }}
  .pontos-box em {{ color: #888; font-size: 11px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 12px; font-size: 12px; }}
  th {{ background: #1e6fb5; color: #fff; padding: 8px 10px; text-align: left; }}
  td {{ padding: 6px 10px; border-bottom: 1px solid #e0e0e0; }}
  tr:nth-child(even) {{ background: #f7f9fc; }}
  @media print {{ body {{ margin: 10px; }} .charts-row, .pontos-row {{ page-break-inside: avoid; }} }}
</style>
</head>
<body>
<h1>Relatório de Vendedor: {agente}</h1>
<p class="sub">Período: {periodo_ini} – {periodo_fim} &middot; {len(df_tab)} avaliação(ões)</p>
{kpi_html}
{graficos_section}
{pontos_section}
<h2>&#128203; Ligações Avaliadas</h2>
<table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>
</body></html>"""
