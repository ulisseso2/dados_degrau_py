import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from collections import Counter
from datetime import datetime
from pathlib import Path
import json
import math
import re
import unicodedata

import pandas as pd
import streamlit as st

from conexao.mysql_connector import conectar_mysql
from fbclid_db import get_campaign_for_fbclid
from gclid_db import get_campaign_for_gclid as get_campaign_degrau
from gclid_db_central import get_campaign_for_gclid as get_campaign_central
from utils.prompts.analise_geral_prompt import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
    VALIDATION_PROMPT_TEMPLATE,
)
from _pages.relatorios_ia import (
    _get_anthropic_client,
    _renderizar_analise,
    carregar_relatorios_historico,
    gerar_html_relatorio,
    get_facebook_data,
    get_google_ads_data,
    init_facebook_api,
    init_facebook_api_central,
    init_google_ads_client,
    init_google_ads_client_central,
    salvar_relatorio,
)


TIMEZONE = 'America/Sao_Paulo'
QUERY_DIR = Path(__file__).resolve().parent.parent / 'consultas' / 'analise_geral'
TIPO_RELATORIO = 'analise_geral'
MODELOS_ANTHROPIC = ['claude-opus-4-7', 'claude-opus-4-6']
STATUS_VENDA_IDS_PERMITIDOS = {2, 3, 10, 14, 15}

EMPRESAS = {
    'Degrau': {
        'school_id': 1,
        'school_ids_csv': '1',
        'fb_cache_key': 'degrau',
        'marketing_label': 'Degrau Cultural',
        'google_customer_id_default': '4934481887',
    },
    'Central': {
        'school_id': 2,
        'school_ids_csv': '2',
        'fb_cache_key': 'central',
        'marketing_label': 'Central de Concursos',
        'google_customer_id_default': '1646681121',
    },
}

_CATS_VENDEDOR = {
    'rapport_conexao_0_10': ('Rapport e Conexão', 10),
    'qualificacao_leitura_contexto_0_15': ('Qualificação / Leitura', 15),
    'construcao_valor_diferenciacao_0_30': ('Construção de Valor', 30),
    'persuasao_etica_0_10': ('Persuasão Ética', 10),
    'objecoes_0_10': ('Tratamento de Objeções', 10),
    'conducao_fechamento_0_20': ('Condução ao Fechamento', 20),
    'clareza_compliance_0_5': ('Clareza / Compliance', 5),
}

_CATS_LEGACY = {
    'abertura_rapport_0_10': 'rapport_conexao_0_10',
    'investigacao_spin_0_30': 'qualificacao_leitura_contexto_0_15',
    'valor_capacidade_0_20': 'construcao_valor_diferenciacao_0_30',
    'compromisso_prox_passos_0_15': 'conducao_fechamento_0_20',
    'clareza_compliance_whatsapp_0_5': 'clareza_compliance_0_5',
}


def _safe_pct(num, den):
    return (num / den * 100) if den else 0.0


def _format_brl(value):
    if value is None or pd.isna(value):
        return 'R$ 0,00'
    return f"R$ {float(value):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')


def _format_pct(value):
    if value is None or pd.isna(value):
        return '0,0%'
    return f"{float(value):.1f}%".replace('.', ',')


def _format_num(value):
    if value is None or pd.isna(value):
        return '0'
    if isinstance(value, float):
        return f"{value:.1f}".replace('.', ',')
    return f"{int(value):,}".replace(',', '.')


def _coerce_tz(series: pd.Series) -> pd.Series:
    if series.empty:
        return series
    dt = pd.to_datetime(series, errors='coerce')
    if getattr(dt.dt, 'tz', None) is None:
        return dt.dt.tz_localize(TIMEZONE, ambiguous='infer', nonexistent='shift_forward')
    return dt.dt.tz_convert(TIMEZONE)


def _parse_json_payload(raw_value):
    if raw_value is None:
        return {}
    if isinstance(raw_value, dict):
        return raw_value
    if isinstance(raw_value, float) and pd.isna(raw_value):
        return {}
    text = str(raw_value).strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _split_items(series: pd.Series, sep=';'):
    items = []
    if series is None or series.empty:
        return items
    for value in series.fillna(''):
        for item in str(value).split(sep):
            clean = item.strip()
            if clean:
                items.append(clean)
    return items


def _top_items(series: pd.Series, limit=10):
    counter = Counter(_split_items(series))
    return counter.most_common(limit)


def _mode_value(series: pd.Series):
    if series is None or series.empty:
        return None
    clean = series.dropna().astype(str).str.strip()
    clean = clean[clean != '']
    if clean.empty:
        return None
    mode = clean.mode()
    return mode.iloc[0] if not mode.empty else clean.iloc[0]


def _build_lead_key(cliente_id, fallback_id):
    if pd.notna(cliente_id):
        try:
            return f'cli:{int(cliente_id)}'
        except (TypeError, ValueError):
            return f"cli:{str(cliente_id).strip()}"
    if pd.notna(fallback_id):
        try:
            return f'aux:{int(fallback_id)}'
        except (TypeError, ValueError):
            return f"aux:{str(fallback_id).strip()}"
    return None


def _with_lead_keys(df: pd.DataFrame, cliente_col: str, fallback_col: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df.copy()
    work_df = df.copy()
    cliente_series = work_df[cliente_col] if cliente_col in work_df.columns else pd.Series(index=work_df.index, dtype=object)
    fallback_series = work_df[fallback_col] if fallback_col in work_df.columns else pd.Series(index=work_df.index, dtype=object)
    work_df['lead_key'] = [
        _build_lead_key(cliente_id, fallback_id)
        for cliente_id, fallback_id in zip(cliente_series, fallback_series)
    ]
    return work_df


def _normalize_match_text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ''
    text = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode('ascii').lower()
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _token_set(value) -> set[str]:
    stopwords = {'de', 'da', 'do', 'das', 'dos', 'e', 'em', 'na', 'no', 'para', 'com', 'curso', 'cursos', 'turma'}
    return {
        token
        for token in _normalize_match_text(value).split()
        if len(token) > 2 and token not in stopwords
    }


def _text_overlap_score(left, right) -> int:
    left_text = _normalize_match_text(left)
    right_text = _normalize_match_text(right)
    if not left_text or not right_text:
        return 0

    score = len(_token_set(left_text) & _token_set(right_text))
    if right_text in left_text or left_text in right_text:
        score += 2
    return score


def _infer_sale_modality(row: pd.Series) -> str:
    text = ' '.join(
        str(row.get(col, '') or '')
        for col in ['categoria', 'curso_venda', 'produto', 'unidade']
    ).lower()
    if 'passaporte' in text:
        return 'Passaporte'
    if 'smart' in text:
        return 'Smart'
    if 'presencial' in text:
        return 'Presencial'
    if 'live' in text:
        return 'Live'
    if 'online' in text or 'ead' in text:
        return 'Online'
    if 'apostila' in text:
        return 'Apostila'
    return 'Outros'


def _markdown_value(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return '—'
    text = str(value)
    return text.replace('|', '/').replace('\n', ' ').strip() or '—'


def format_table_for_prompt(df: pd.DataFrame, title: str, max_rows=50) -> str:
    if df is None or df.empty:
        return f"### {title}\nSem dados disponíveis no período.\n"

    work_df = df.head(max_rows).copy()
    headers = list(work_df.columns)
    lines = [f"### {title}"]
    lines.append('| ' + ' | '.join(headers) + ' |')
    lines.append('| ' + ' | '.join(['---'] * len(headers)) + ' |')

    for _, row in work_df.iterrows():
        lines.append('| ' + ' | '.join(_markdown_value(row[col]) for col in headers) + ' |')

    if len(df) > max_rows:
        lines.append(f"*top {max_rows} de {len(df)} linhas*")
    return '\n'.join(lines) + '\n'


def _text_block(title: str, lines: list[str]) -> str:
    if not lines:
        return f"### {title}\nSem evidências disponíveis no período.\n"
    return f"### {title}\n" + '\n'.join(lines) + '\n'


def _extract_category_scores(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {}
    notas = payload.get('avaliacao_vendedor', {}).get('notas_por_categoria', {})
    if not isinstance(notas, dict):
        return {}

    result = {}
    for key, (_, max_value) in _CATS_VENDEDOR.items():
        current = notas.get(key)
        if current is None:
            continue
        try:
            result[key] = float(current) / max_value * 100
        except (TypeError, ValueError):
            continue

    if result:
        return result

    for old_key, new_key in _CATS_LEGACY.items():
        current = notas.get(old_key)
        if current is None:
            continue
        _, max_value = _CATS_VENDEDOR[new_key]
        try:
            result[new_key] = float(current) / max_value * 100
        except (TypeError, ValueError):
            continue

    for key in ('persuasao_etica_0_10', 'objecoes_0_10'):
        if key in result or key not in _CATS_VENDEDOR:
            continue
        current = notas.get(key)
        if current is None:
            continue
        _, max_value = _CATS_VENDEDOR[key]
        try:
            result[key] = float(current) / max_value * 100
        except (TypeError, ValueError):
            continue
    return result


def _prepare_chats(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    work_df = df.copy()
    if 'vendedor_disclaimer' in work_df.columns:
        work_df = work_df[work_df['vendedor_disclaimer'].fillna('').astype(str).str.strip() != ''].copy()
    if work_df.empty:
        return work_df
    work_df['data_chat'] = _coerce_tz(work_df['data_chat'])
    work_df['avaliada'] = work_df.get('avaliada', pd.Series(0, index=work_df.index)).astype(bool)
    work_df['avaliavel'] = work_df.get('avaliavel', pd.Series(0, index=work_df.index)).astype(bool)
    evaluation_series = work_df['evaluation_ia'] if 'evaluation_ia' in work_df.columns else pd.Series(index=work_df.index, dtype=float)
    lead_score_series = work_df['lead_score'] if 'lead_score' in work_df.columns else pd.Series(index=work_df.index, dtype=float)
    work_df['evaluation_ia'] = pd.to_numeric(evaluation_series, errors='coerce')
    work_df['lead_score'] = pd.to_numeric(lead_score_series, errors='coerce')
    work_df['parsed_json'] = work_df.get('ai_evaluation', pd.Series(dtype=str)).apply(_parse_json_payload)
    work_df['lead_classification'] = work_df['parsed_json'].apply(
        lambda payload: payload.get('avaliacao_lead', {}).get('classificacao')
        if isinstance(payload, dict) else None
    )
    work_df['notas_pct'] = work_df['parsed_json'].apply(_extract_category_scores)
    work_df['strengths'] = work_df['parsed_json'].apply(
        lambda payload: '; '.join(
            item.get('ponto', '').strip()
            for item in payload.get('avaliacao_vendedor', {}).get('pontos_fortes', [])
            if isinstance(item, dict) and item.get('ponto')
        ) if isinstance(payload, dict) else ''
    )
    work_df['improvements'] = work_df['parsed_json'].apply(
        lambda payload: '; '.join(
            item.get('melhoria', '').strip()
            for item in payload.get('avaliacao_vendedor', {}).get('melhorias', [])
            if isinstance(item, dict) and item.get('melhoria')
        ) if isinstance(payload, dict) else ''
    )
    work_df['most_expensive_mistake'] = work_df['parsed_json'].apply(
        lambda payload: (
            payload.get('avaliacao_vendedor', {}).get('erro_mais_caro', {}).get('descricao', '')
            if isinstance(payload.get('avaliacao_vendedor', {}).get('erro_mais_caro'), dict) else ''
        ) if isinstance(payload, dict) else ''
    )
    work_df['objections_text'] = work_df['parsed_json'].apply(
        lambda payload: '; '.join(payload.get('extracao', {}).get('restricoes', []))
        if isinstance(payload, dict) and isinstance(payload.get('extracao', {}).get('restricoes'), list)
        else ''
    )
    work_df['pain_points_text'] = work_df['parsed_json'].apply(
        lambda payload: '; '.join(payload.get('extracao', {}).get('dores_principais', []))
        if isinstance(payload, dict) and isinstance(payload.get('extracao', {}).get('dores_principais'), list)
        else ''
    )
    return work_df


def _prepare_calls(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    work_df = df.copy()
    if 'vendedor_disclaimer' in work_df.columns:
        work_df = work_df[work_df['vendedor_disclaimer'].fillna('').astype(str).str.strip() != ''].copy()
    if work_df.empty:
        return work_df
    work_df['data_ligacao'] = _coerce_tz(work_df['data_ligacao'])
    work_df['avaliada'] = work_df.get('insight_ia', pd.Series(dtype=str)).fillna('').astype(str).str.strip().ne('')
    work_df['avaliavel'] = work_df.get('avaliavel', pd.Series(0, index=work_df.index)).astype(bool)
    evaluation_series = work_df['evaluation_ia'] if 'evaluation_ia' in work_df.columns else pd.Series(index=work_df.index, dtype=float)
    lead_score_series = work_df['lead_score'] if 'lead_score' in work_df.columns else pd.Series(index=work_df.index, dtype=float)
    work_df['evaluation_ia'] = pd.to_numeric(evaluation_series, errors='coerce')
    work_df['lead_score'] = pd.to_numeric(lead_score_series, errors='coerce')
    work_df['parsed_json'] = work_df.get('insight_ia', pd.Series(dtype=str)).apply(_parse_json_payload)
    work_df['lead_classification'] = work_df['parsed_json'].apply(
        lambda payload: payload.get('avaliacao_lead', {}).get('classificacao')
        if isinstance(payload, dict) else None
    )
    work_df['lead_classification'] = work_df['lead_classification'].fillna(work_df.get('lead_classification'))
    work_df['notas_pct'] = work_df['parsed_json'].apply(_extract_category_scores)
    work_df['strengths'] = work_df.get('strengths', pd.Series(dtype=str)).fillna('')
    work_df['improvements'] = work_df.get('improvements', pd.Series(dtype=str)).fillna('')
    work_df['most_expensive_mistake'] = work_df.get('most_expensive_mistake', pd.Series(dtype=str)).fillna('')
    work_df['objections_text'] = work_df['parsed_json'].apply(
        lambda payload: '; '.join(payload.get('extracao', {}).get('restricoes', []))
        if isinstance(payload, dict) and isinstance(payload.get('extracao', {}).get('restricoes'), list)
        else ''
    )
    fallback_objections = work_df.get('principais_dores', pd.Series(dtype=str)).fillna('')
    work_df.loc[work_df['objections_text'].str.strip() == '', 'objections_text'] = fallback_objections
    return work_df


@st.cache_data(ttl=600, show_spinner=False)
def _run_sql_template(query_name: str, school_ids_csv: str, data_inicio: str, data_fim: str, where_extra: str = '') -> pd.DataFrame:
    sql_path = QUERY_DIR / query_name
    if not sql_path.exists():
        return pd.DataFrame()
    query = sql_path.read_text(encoding='utf-8').format(
        school_ids=school_ids_csv,
        data_inicio=data_inicio,
        data_fim=data_fim,
        where_extra=where_extra,
    )
    engine = conectar_mysql()
    if engine is None:
        return pd.DataFrame()
    try:
        return pd.read_sql(query, engine)
    except Exception as exc:
        st.error(f'Erro ao executar {query_name}: {exc}')
        return pd.DataFrame()


@st.cache_data(ttl=600, show_spinner=False)
def _load_base_frames(school_ids_csv: str, data_inicio: str, data_fim: str):
    return {
        'oportunidades': _run_sql_template('oportunidades_base.sql', school_ids_csv, data_inicio, data_fim),
        'vendas': _run_sql_template('vendas_base.sql', school_ids_csv, data_inicio, data_fim),
        'chats': _run_sql_template('chats_base.sql', school_ids_csv, data_inicio, data_fim),
        'ligacoes': _run_sql_template('ligacoes_base.sql', school_ids_csv, data_inicio, data_fim),
        'marketing_reports': _run_sql_template('marketing_reports_candidates.sql', school_ids_csv, data_inicio, data_fim),
    }


@st.cache_data(ttl=3600, show_spinner=False)
def _lookup_google_campaigns(empresa: str, gclids: tuple[str, ...]):
    if not gclids:
        return {}
    lookup = get_campaign_degrau if empresa == 'Degrau' else get_campaign_central
    result = {}
    for gclid in gclids:
        if gclid:
            result[gclid] = lookup(gclid)
    return result


@st.cache_data(ttl=3600, show_spinner=False)
def _lookup_meta_campaigns(cache_empresa: str, fbclids: tuple[str, ...]):
    if not fbclids:
        return {}
    result = {}
    for fbclid in fbclids:
        if fbclid:
            result[fbclid] = get_campaign_for_fbclid(fbclid, cache_empresa)
    return result


def _resolve_media_platform(row: pd.Series):
    utm_source = str(row.get('utm_source', '') or '').lower()
    utm_campaign = str(row.get('utm_campaign', '') or '').strip()
    origem = str(row.get('origem', '') or '').strip()
    if row.get('campanha_google') or row.get('gclid'):
        return 'Google Ads', row.get('campanha_google') or utm_campaign or origem or 'Google Ads (sem campanha resolvida)'
    if row.get('campanha_meta') or row.get('fbclid'):
        return 'Meta Ads', row.get('campanha_meta') or utm_campaign or origem or 'Meta Ads (sem campanha resolvida)'
    if str(row.get('tiktok', '') or '').strip() or 'tiktok' in utm_source:
        return 'TikTok Ads', utm_campaign or origem or 'TikTok (sem campanha)'
    if 'youtube' in utm_source:
        return 'YouTube', utm_campaign or origem or 'YouTube (sem campanha)'
    if 'google' in utm_source:
        return 'Google Ads', utm_campaign or origem or 'Google Ads (utm)'
    if any(token in utm_source for token in ['facebook', 'instagram', 'meta', 'fb', 'ig']):
        return 'Meta Ads', utm_campaign or origem or 'Meta Ads (utm)'
    return 'Sem mapeamento', utm_campaign or origem or 'Sem campanha identificada'


def _enrich_campaigns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    work_df = df.copy()
    work_df['campanha_google'] = None
    work_df['campanha_meta'] = None
    work_df['adset_meta'] = None
    work_df['ad_meta'] = None

    for empresa, cfg in EMPRESAS.items():
        mask = work_df['empresa'] == empresa
        if not mask.any():
            continue

        gclids = tuple(sorted({
            str(value).strip() for value in work_df.loc[mask, 'gclid'].dropna().tolist() if str(value).strip()
        }))
        google_map = _lookup_google_campaigns(empresa, gclids)
        if google_map:
            work_df.loc[mask, 'campanha_google'] = work_df.loc[mask, 'gclid'].map(google_map)

        fbclids = tuple(sorted({
            str(value).strip() for value in work_df.loc[mask, 'fbclid'].dropna().tolist() if str(value).strip()
        }))
        meta_map = _lookup_meta_campaigns(cfg['fb_cache_key'], fbclids)
        if meta_map:
            work_df.loc[mask, 'campanha_meta'] = work_df.loc[mask, 'fbclid'].apply(
                lambda value: (meta_map.get(value) or {}).get('campaign_name') if value in meta_map else None
            )
            work_df.loc[mask, 'adset_meta'] = work_df.loc[mask, 'fbclid'].apply(
                lambda value: (meta_map.get(value) or {}).get('adset_name') if value in meta_map else None
            )
            work_df.loc[mask, 'ad_meta'] = work_df.loc[mask, 'fbclid'].apply(
                lambda value: (meta_map.get(value) or {}).get('ad_name') if value in meta_map else None
            )

    media_resolution = work_df.apply(_resolve_media_platform, axis=1, result_type='expand')
    work_df['plataforma_midia'] = media_resolution[0]
    work_df['campanha_marketing'] = media_resolution[1]
    return work_df


@st.cache_data(ttl=1800, show_spinner=False)
def _load_live_marketing(empresa: str, data_inicio: str, data_fim: str):
    google_df = pd.DataFrame()
    meta_df = pd.DataFrame()
    error_messages = []

    if empresa == 'Degrau':
        client = init_google_ads_client('google-ads.yaml')
        customer_id = EMPRESAS[empresa]['google_customer_id_default']
        try:
            customer_id = str(st.secrets['google_ads']['customer_id'])
        except Exception:
            pass
        if client:
            google_df = get_google_ads_data(client, customer_id, data_inicio, data_fim)
        else:
            error_messages.append('Google Ads indisponível para Degrau.')

        account = init_facebook_api()
        if account:
            meta_df = get_facebook_data(account, data_inicio, data_fim)
        else:
            error_messages.append('Meta Ads indisponível para Degrau.')
    else:
        client = init_google_ads_client_central()
        customer_id = EMPRESAS[empresa]['google_customer_id_default']
        try:
            customer_id = str(st.secrets['google_ads_central']['customer_id'])
        except Exception:
            pass
        if client:
            google_df = get_google_ads_data(client, customer_id, data_inicio, data_fim)
        else:
            error_messages.append('Google Ads indisponível para Central.')

        account = init_facebook_api_central()
        if account:
            meta_df = get_facebook_data(account, data_inicio, data_fim)
        else:
            error_messages.append('Meta Ads indisponível para Central.')

    return {
        'google': google_df if google_df is not None else pd.DataFrame(),
        'meta': meta_df if meta_df is not None else pd.DataFrame(),
        'errors': error_messages,
    }


def _select_marketing_report(df_reports: pd.DataFrame, empresa: str) -> str:
    if df_reports is None or df_reports.empty:
        relatorios = carregar_relatorios_historico()
        if not relatorios:
            return 'Relatório de marketing indisponível no histórico.'
        df_reports = pd.DataFrame(relatorios)
        if df_reports.empty:
            return 'Relatório de marketing indisponível no histórico.'
        if 'analise' in df_reports.columns:
            df_reports = df_reports.rename(columns={'analise': 'ai_analysis', 'dados_brutos': 'raw_data', 'tipo': 'type', 'gerado_em': 'generated_at'})

    labels = [EMPRESAS[empresa]['marketing_label'].lower(), empresa.lower()]
    work_df = df_reports.copy()
    if 'generated_at' in work_df.columns:
        work_df['generated_at'] = pd.to_datetime(work_df['generated_at'], errors='coerce')
        work_df = work_df.sort_values('generated_at', ascending=False)

    for _, row in work_df.iterrows():
        payload = f"{row.get('raw_data', '')}\n{row.get('ai_analysis', '')}".lower()
        if any(label in payload for label in labels):
            analysis = str(row.get('ai_analysis', '') or '').strip()
            return analysis[:6000] if analysis else 'Relatório de marketing encontrado sem conteúdo textual útil.'

    return 'Relatório de marketing indisponível no histórico para esta empresa.'


def _apply_filters(df_op: pd.DataFrame, df_v: pd.DataFrame, df_c: pd.DataFrame, df_l: pd.DataFrame, filtros: dict):
    work_op = df_op.copy()
    work_v = df_v.copy()
    work_c = df_c.copy()
    work_l = df_l.copy()

    if not work_v.empty and 'status_id' in work_v.columns:
        work_v = work_v[work_v['status_id'].isin(STATUS_VENDA_IDS_PERMITIDOS)]

    if filtros['origens']:
        null_origem = work_op['origem'].isna() | (work_op['origem'].astype(str).str.strip() == '')
        work_op = work_op[work_op['origem'].isin(filtros['origens']) | null_origem]
    if filtros['campanhas']:
        work_op = work_op[work_op['campanha_marketing'].isin(filtros['campanhas'])]
    if filtros['vendedores']:
        null_dono = work_op['dono'].isna() | (work_op['dono'].astype(str).str.strip() == '')
        work_op = work_op[work_op['dono'].isin(filtros['vendedores']) | null_dono]
        if not work_v.empty:
            work_v = work_v[
                work_v.get('dono', pd.Series(dtype=str)).isin(filtros['vendedores']) |
                work_v.get('vendedor', pd.Series(dtype=str)).isin(filtros['vendedores'])
            ]
    if filtros['etapas']:
        null_etapa = work_op['etapa'].isna() | (work_op['etapa'].astype(str).str.strip() == '')
        work_op = work_op[work_op['etapa'].isin(filtros['etapas']) | null_etapa]
    if filtros['modalidades']:
        work_op = work_op[work_op['modalidade'].isin(filtros['modalidades'])]

    if not work_op.empty:
        allowed_opps = set(work_op['oportunidade_id'].dropna().tolist())
        work_c = work_c[work_c['oportunidade_id'].isin(allowed_opps)] if not work_c.empty else work_c
        work_l = work_l[work_l['oportunidade_id'].isin(allowed_opps)] if not work_l.empty else work_l
    else:
        work_c = work_c.iloc[0:0]
        work_l = work_l.iloc[0:0]

    if filtros['agentes']:
        if not work_c.empty:
            work_c = work_c[work_c['agente'].isin(filtros['agentes'])]
        if not work_l.empty:
            work_l = work_l[work_l['agente'].isin(filtros['agentes'])]

    if filtros['status_venda'] and not work_v.empty:
        work_v = work_v[work_v['status'].isin(filtros['status_venda'])]

    return work_op, work_v, work_c, work_l


def _aggregate_interactions(df: pd.DataFrame, key_col: str, id_col: str, date_col: str, prefix: str) -> pd.DataFrame:
    if df is None or df.empty or key_col not in df.columns:
        return pd.DataFrame(columns=[key_col])

    grouped_rows = []
    base_df = df.dropna(subset=[key_col]).copy()
    if base_df.empty:
        return pd.DataFrame(columns=[key_col])

    for group_key, group_df in base_df.groupby(key_col):
        grouped_rows.append({
            key_col: group_key,
            f'qtd_{prefix}': group_df[id_col].nunique() if id_col in group_df.columns else len(group_df),
            f'avaliadas_{prefix}': int(group_df.get('avaliada', pd.Series(0, index=group_df.index)).fillna(False).astype(bool).sum()),
            f'nota_media_{prefix}': group_df.get('evaluation_ia', pd.Series(dtype=float)).mean(),
            f'lead_score_medio_{prefix}': group_df.get('lead_score', pd.Series(dtype=float)).mean(),
            f'lead_class_{prefix}': _mode_value(group_df.get('lead_classification', pd.Series(dtype=str))),
            f'data_ultima_{prefix}': group_df.get(date_col, pd.Series(dtype='datetime64[ns]')).max(),
            f'strengths_{prefix}': '; '.join(item for item, _ in _top_items(group_df.get('strengths', pd.Series(dtype=str)), 5)),
            f'improvements_{prefix}': '; '.join(item for item, _ in _top_items(group_df.get('improvements', pd.Series(dtype=str)), 5)),
            f'mistakes_{prefix}': '; '.join(item for item, _ in _top_items(group_df.get('most_expensive_mistake', pd.Series(dtype=str)), 5)),
            f'objections_{prefix}': '; '.join(item for item, _ in _top_items(group_df.get('objections_text', pd.Series(dtype=str)), 5)),
        })
    return pd.DataFrame(grouped_rows)


def _link_sales_to_opportunities(
    df_v: pd.DataFrame,
    df_op: pd.DataFrame,
    chat_agg: pd.DataFrame,
    call_agg: pd.DataFrame,
) -> pd.DataFrame:
    if df_v is None or df_v.empty:
        return pd.DataFrame()

    sales_df = _with_lead_keys(df_v, 'cliente_id', 'ordem_id')
    if 'dono' in sales_df.columns:
        sales_df = sales_df.rename(columns={'dono': 'dono_venda'})
    sales_df['modalidade_venda'] = sales_df.apply(_infer_sale_modality, axis=1)
    sales_df['produto_referencia_campanha'] = (
        sales_df.get('curso_venda', pd.Series(index=sales_df.index, dtype=str)).fillna('')
        .replace('', pd.NA)
        .fillna(sales_df.get('produto', pd.Series(index=sales_df.index, dtype=str)).fillna('').replace('', pd.NA))
        .fillna(sales_df.get('categoria', pd.Series(index=sales_df.index, dtype=str)).fillna('').replace('', pd.NA))
    )

    default_columns = {
        'oportunidade_id_atribuida': pd.NA,
        'match_oportunidade': 'Sem oportunidade vinculada',
        'tem_oportunidade_vinculada': False,
        'origem_atribuida': pd.NA,
        'etapa_atribuida': pd.NA,
        'modalidade_atribuida': pd.NA,
        'sales_force_atribuido': pd.NA,
        'concurso_atribuido': pd.NA,
        'plataforma_midia_atribuida': pd.NA,
        'campanha_marketing_atribuida': pd.NA,
        'dono_oportunidade': pd.NA,
    }

    if df_op is None or df_op.empty:
        for col, value in default_columns.items():
            sales_df[col] = value
        sales_df['modalidade_validada'] = sales_df['modalidade_venda']
        sales_df['qtd_chat'] = 0
        sales_df['qtd_ligacao'] = 0
        sales_df['teve_chat'] = False
        sales_df['teve_ligacao'] = False
        sales_df['teve_interferencia_humana'] = False
        sales_df['responsavel_venda'] = (
            sales_df.get('dono_venda', pd.Series(index=sales_df.index, dtype=str)).fillna('').replace('', pd.NA)
            .fillna(sales_df.get('vendedor', pd.Series(index=sales_df.index, dtype=str)).fillna('').replace('', pd.NA))
            .fillna('Indefinido')
        )
        return sales_df

    opportunities_df = _with_lead_keys(df_op, 'cliente_id', 'oportunidade_id').sort_values('criacao')
    opportunities_df = opportunities_df[opportunities_df['cliente_id'].notna()].copy()

    if opportunities_df.empty:
        linked_df = sales_df.copy()
        for col, value in default_columns.items():
            linked_df[col] = value
    else:
        oportunidade_mais_recente = opportunities_df.groupby('cliente_id').tail(1).copy()

        oportunidade_1_15 = opportunities_df[opportunities_df['id_etapa'].isin([1, 15])].groupby('cliente_id').tail(1)
        origem_1_15 = oportunidade_1_15[['cliente_id', 'origem']].rename(columns={'origem': 'origem_1_15'})
        origem_geral = oportunidade_mais_recente[['cliente_id', 'origem']].rename(columns={'origem': 'origem_geral'})

        oportunidade_vendida = opportunities_df[opportunities_df['id_etapa'] == 15].groupby('cliente_id').tail(1)
        dados_oportunidade = (
            oportunidade_vendida.set_index('cliente_id')
            .combine_first(oportunidade_mais_recente.set_index('cliente_id'))
            .reset_index()
        )
        dados_oportunidade = dados_oportunidade.merge(origem_geral, on='cliente_id', how='left')
        dados_oportunidade = dados_oportunidade.merge(origem_1_15, on='cliente_id', how='left')
        dados_oportunidade['origem_ult_1_15'] = dados_oportunidade['origem_1_15'].fillna(dados_oportunidade['origem_geral'])

        cols_map = [
            'cliente_id',
            'oportunidade_id',
            'id_etapa',
            'etapa',
            'modalidade',
            'sales_force',
            'concurso',
            'plataforma_midia',
            'campanha_marketing',
            'dono',
            'origem_ult_1_15',
            'gclid',
            'fbclid',
            'utm_source',
            'utm_campaign',
            'utm_medium',
        ]
        cols_map = [col for col in cols_map if col in dados_oportunidade.columns]
        linked_df = sales_df.merge(dados_oportunidade[cols_map], on='cliente_id', how='left')

        linked_df['oportunidade_id_atribuida'] = linked_df.get('oportunidade_id')
        linked_df['tem_oportunidade_vinculada'] = linked_df['oportunidade_id_atribuida'].notna()
        linked_df['origem_atribuida'] = linked_df.get('origem_ult_1_15', linked_df.get('origem'))
        linked_df['etapa_atribuida'] = linked_df.get('etapa')
        linked_df['modalidade_atribuida'] = linked_df.get('modalidade')
        linked_df['sales_force_atribuido'] = linked_df.get('sales_force')
        linked_df['concurso_atribuido'] = linked_df.get('concurso')
        linked_df['plataforma_midia_atribuida'] = linked_df.get('plataforma_midia')
        linked_df['campanha_marketing_atribuida'] = linked_df.get('campanha_marketing')
        linked_df['dono_oportunidade'] = linked_df.get('dono')

        linked_df['match_oportunidade'] = 'cliente+mais_recente'
        if 'id_etapa' in linked_df.columns:
            linked_df.loc[linked_df['id_etapa'] == 15, 'match_oportunidade'] = 'cliente+etapa15'
        linked_df.loc[~linked_df['tem_oportunidade_vinculada'], 'match_oportunidade'] = 'Sem oportunidade vinculada'

        for col, value in default_columns.items():
            if col not in linked_df.columns:
                linked_df[col] = value

    linked_df['modalidade_validada'] = linked_df.get('modalidade_atribuida', pd.Series(index=linked_df.index)).fillna(linked_df['modalidade_venda'])
    linked_df['produto_referencia_campanha'] = linked_df.get('sales_force_atribuido', pd.Series(index=linked_df.index)).fillna(
        linked_df.get('concurso_atribuido', pd.Series(index=linked_df.index))
    ).fillna(linked_df['produto_referencia_campanha'])

    chat_sales_agg = chat_agg.rename(columns={'oportunidade_id': 'oportunidade_id_atribuida'}) if chat_agg is not None and not chat_agg.empty else pd.DataFrame(columns=['oportunidade_id_atribuida'])
    call_sales_agg = call_agg.rename(columns={'oportunidade_id': 'oportunidade_id_atribuida'}) if call_agg is not None and not call_agg.empty else pd.DataFrame(columns=['oportunidade_id_atribuida'])
    if not chat_sales_agg.empty:
        linked_df = linked_df.merge(chat_sales_agg, on='oportunidade_id_atribuida', how='left')
    if not call_sales_agg.empty:
        linked_df = linked_df.merge(call_sales_agg, on='oportunidade_id_atribuida', how='left')

    for col in ['qtd_chat', 'qtd_ligacao']:
        if col in linked_df.columns:
            linked_df[col] = linked_df[col].fillna(0).astype(int)
        else:
            linked_df[col] = 0

    linked_df['teve_chat'] = linked_df['qtd_chat'] > 0
    linked_df['teve_ligacao'] = linked_df['qtd_ligacao'] > 0
    linked_df['teve_interferencia_humana'] = linked_df['teve_chat'] | linked_df['teve_ligacao']
    linked_df['responsavel_venda'] = (
        linked_df.get('dono_venda', pd.Series(index=linked_df.index, dtype=str)).fillna('').replace('', pd.NA)
        .fillna(linked_df.get('dono_oportunidade', pd.Series(index=linked_df.index, dtype=str)).fillna('').replace('', pd.NA))
        .fillna(linked_df.get('vendedor', pd.Series(index=linked_df.index, dtype=str)).fillna('').replace('', pd.NA))
        .fillna('Indefinido')
    )
    return linked_df


def _build_campaign_journey(df_op: pd.DataFrame, df_sales: pd.DataFrame, platform: str) -> pd.DataFrame:
    opportunity_df = df_op.copy() if df_op is not None else pd.DataFrame()
    sales_df = df_sales.copy() if df_sales is not None else pd.DataFrame()

    if not opportunity_df.empty:
        opportunity_df = opportunity_df[opportunity_df['plataforma_midia'] == platform]
    if not sales_df.empty:
        sales_df = sales_df[sales_df['plataforma_midia_atribuida'] == platform]

    opportunities_group = (
        opportunity_df.groupby('campanha_marketing')
        .agg(Leads=('lead_key', 'nunique'), Oportunidades=('oportunidade_id', 'nunique'))
        .reset_index()
        .rename(columns={'campanha_marketing': 'Campanha'})
    ) if not opportunity_df.empty else pd.DataFrame(columns=['Campanha', 'Leads', 'Oportunidades'])

    sales_group = (
        sales_df.groupby('campanha_marketing_atribuida')
        .agg(
            Vendas=('ordem_id', 'nunique'),
            Receita=('total_pedido', 'sum'),
            Clientes=('lead_key', 'nunique'),
            vendas_com_interferencia_humana=('teve_interferencia_humana', 'sum'),
            produto_concurso_validado=('produto_referencia_campanha', lambda series: _mode_value(series) or '—'),
        )
        .reset_index()
        .rename(columns={
            'vendas_com_interferencia_humana': 'Vendas com interferência humana',
            'produto_concurso_validado': 'Produto/Concurso validado',
        })
        .rename(columns={'campanha_marketing_atribuida': 'Campanha'})
    ) if not sales_df.empty else pd.DataFrame(columns=['Campanha', 'Vendas', 'Receita', 'Clientes', 'Vendas com interferência humana', 'Produto/Concurso validado'])

    merged_df = opportunities_group.merge(sales_group, on='Campanha', how='outer')
    if merged_df.empty:
        return merged_df

    for col in ['Leads', 'Oportunidades', 'Vendas', 'Receita', 'Clientes', 'Vendas com interferência humana']:
        if col in merged_df.columns:
            merged_df[col] = merged_df[col].fillna(0)
    if 'Produto/Concurso validado' in merged_df.columns:
        merged_df['Produto/Concurso validado'] = merged_df['Produto/Concurso validado'].fillna('—')

    merged_df['Plataforma'] = platform
    merged_df['Conversão %'] = merged_df.apply(lambda row: _format_pct(_safe_pct(row.get('Vendas', 0), row.get('Leads', 0))), axis=1)
    merged_df = merged_df.sort_values(['Vendas', 'Receita', 'Oportunidades'], ascending=False)
    return merged_df


def _select_representative_opportunities(df_op: pd.DataFrame, sales_summary: pd.DataFrame) -> pd.DataFrame:
    if df_op is None or df_op.empty:
        return pd.DataFrame()

    work_df = df_op.copy().sort_values('criacao')
    work_df['lead_key'] = work_df['cliente_id'].apply(lambda value: f'cli:{int(value)}' if pd.notna(value) else None)
    work_df.loc[work_df['lead_key'].isna(), 'lead_key'] = work_df.loc[work_df['lead_key'].isna(), 'oportunidade_id'].apply(lambda value: f'opp:{int(value)}')

    sales_map = {}
    if sales_summary is not None and not sales_summary.empty:
        sales_map = sales_summary.set_index('cliente_id')['data_ultima_venda'].to_dict()

    selected_rows = []
    non_null_clients = work_df[work_df['cliente_id'].notna()].copy()
    for cliente_id, group_df in non_null_clients.groupby('cliente_id'):
        sale_date = sales_map.get(cliente_id)
        candidate_df = group_df
        if pd.notna(sale_date):
            before_sale_df = group_df[group_df['criacao'] <= sale_date]
            if not before_sale_df.empty:
                candidate_df = before_sale_df
        sold_stage_df = candidate_df[candidate_df['id_etapa'] == 15]
        chosen_row = sold_stage_df.iloc[-1] if not sold_stage_df.empty else candidate_df.iloc[-1]
        selected_rows.append(chosen_row.to_dict())

    selected_df = pd.DataFrame(selected_rows)
    null_client_df = work_df[work_df['cliente_id'].isna()].copy()
    if selected_df.empty:
        return null_client_df
    if not null_client_df.empty:
        selected_df = pd.concat([selected_df, null_client_df], ignore_index=True, sort=False)
    return selected_df


def _build_vendor_tables(df_attr: pd.DataFrame, df_chats: pd.DataFrame, df_calls: pd.DataFrame):
    if df_attr is None or df_attr.empty:
        empty_df = pd.DataFrame()
        return empty_df, empty_df, empty_df, '', ''

    vendor_col = 'responsavel_venda' if 'responsavel_venda' in df_attr.columns else 'dono'
    owner_map = df_attr[['oportunidade_id', vendor_col]].drop_duplicates()
    interaction_frames = []

    if df_chats is not None and not df_chats.empty:
        chat_df = df_chats.merge(owner_map, on='oportunidade_id', how='left')
        chat_df['canal'] = 'Chat'
        interaction_frames.append(chat_df)
    if df_calls is not None and not df_calls.empty:
        call_df = df_calls.merge(owner_map, on='oportunidade_id', how='left')
        call_df['canal'] = 'Ligação'
        interaction_frames.append(call_df)

    interaction_df = pd.concat(interaction_frames, ignore_index=True, sort=False) if interaction_frames else pd.DataFrame()
    interaction_df = interaction_df[interaction_df.get(vendor_col, pd.Series(dtype=str)).fillna('').astype(str).str.strip() != ''] if not interaction_df.empty else interaction_df

    vendor_df = (
        df_attr[df_attr.get(vendor_col, pd.Series(dtype=str)).fillna('').astype(str).str.strip() != '']
        .groupby(vendor_col)
        .agg(
            volume_atendido=('lead_key', 'nunique'),
            oportunidades=('oportunidade_id', 'nunique'),
            vendas=('tem_venda', 'sum'),
            receita=('receita_total', 'sum'),
            score_lead_recebido=('lead_score_proxy', 'mean'),
            score_atendimento=('score_atendimento_proxy', 'mean'),
        )
        .reset_index()
    )
    vendor_df['conversao_pct'] = vendor_df.apply(lambda row: _safe_pct(row['vendas'], row['volume_atendido']), axis=1)

    category_rows = []
    fortes_blocks = []
    erros_blocks = []
    for vendor in vendor_df[vendor_col].tolist():
        if interaction_df.empty:
            category_row = {'Vendedor': vendor}
            for label, _ in _CATS_VENDEDOR.values():
                category_row[label] = '—'
            category_rows.append(category_row)
            continue

        group_df = interaction_df[interaction_df[vendor_col] == vendor]
        category_scores = {}
        for key, (label, _) in _CATS_VENDEDOR.items():
            values = []
            for payload in group_df.get('notas_pct', pd.Series(dtype=object)):
                if isinstance(payload, dict) and key in payload and not pd.isna(payload[key]):
                    values.append(float(payload[key]))
            category_scores[label] = sum(values) / len(values) if values else None

        category_row = {'Vendedor': vendor}
        for label in [label for label, _ in _CATS_VENDEDOR.values()]:
            category_row[label] = _format_pct(category_scores[label]) if category_scores[label] is not None else '—'
        category_rows.append(category_row)

        fortes = _top_items(group_df.get('strengths', pd.Series(dtype=str)), 3)
        erros = _top_items(group_df.get('most_expensive_mistake', pd.Series(dtype=str)), 3)
        melhorias = _top_items(group_df.get('improvements', pd.Series(dtype=str)), 3)

        fortes_blocks.append(
            f"- {vendor}: " + (', '.join(item for item, _ in fortes) if fortes else 'Sem recorrência forte mapeada.')
        )

        erros_linhas = [item for item, _ in erros] + [item for item, _ in melhorias if item not in {x for x, _ in erros}]
        erros_blocks.append(
            f"- {vendor}: " + (', '.join(erros_linhas[:3]) if erros_linhas else 'Sem erro recorrente mapeado.')
        )

    category_df = pd.DataFrame(category_rows)

    major_gaps = []
    for _, row in category_df.iterrows():
        menor_label = 'Inconclusivo'
        menor_valor = math.inf
        for label in [label for label, _ in _CATS_VENDEDOR.values()]:
            raw = str(row.get(label, '—')).replace('%', '').replace(',', '.').strip()
            try:
                value = float(raw)
            except ValueError:
                continue
            if value < menor_valor:
                menor_valor = value
                menor_label = label
        major_gaps.append(menor_label)

    vendor_df['categoria_maior_gap'] = major_gaps if len(major_gaps) == len(vendor_df) else ['Inconclusivo'] * len(vendor_df)

    quality_rows = []
    for vendor in vendor_df[vendor_col].tolist():
        group_df = df_attr[df_attr[vendor_col] == vendor]
        class_counter = Counter(group_df.get('lead_classification_proxy', pd.Series(dtype=str)).fillna('—'))
        quality_rows.append({
            'Vendedor': vendor,
            'Score Lead Médio': _format_num(group_df['lead_score_proxy'].mean()),
            'Classe A': class_counter.get('A', 0),
            'Classe B': class_counter.get('B', 0),
            'Classe C': class_counter.get('C', 0),
            'Classe D': class_counter.get('D', 0),
        })
    quality_df = pd.DataFrame(quality_rows)

    vendor_df_formatted = vendor_df.rename(columns={
        vendor_col: 'Vendedor',
        'volume_atendido': 'Volume Atendido',
        'oportunidades': 'Oportunidades',
        'vendas': 'Vendas',
        'receita': 'Receita',
        'score_lead_recebido': 'Score Médio Lead',
        'score_atendimento': 'Score Médio Atendimento',
        'conversao_pct': 'Conversão %',
        'categoria_maior_gap': 'Maior Gap',
    })
    vendor_df_formatted['Receita'] = vendor_df_formatted['Receita'].apply(_format_brl)
    vendor_df_formatted['Score Médio Lead'] = vendor_df_formatted['Score Médio Lead'].apply(_format_num)
    vendor_df_formatted['Score Médio Atendimento'] = vendor_df_formatted['Score Médio Atendimento'].apply(_format_num)
    vendor_df_formatted['Conversão %'] = vendor_df_formatted['Conversão %'].apply(_format_pct)

    return (
        vendor_df_formatted,
        category_df,
        quality_df,
        _text_block('Pontos fortes recorrentes por vendedor', fortes_blocks),
        _text_block('Erros recorrentes por vendedor', erros_blocks),
    )


def _merge_marketing_live_with_crm(df_op: pd.DataFrame, df_sales: pd.DataFrame, marketing_live: dict) -> pd.DataFrame:
    rows = []
    google_crm = _build_campaign_journey(df_op, df_sales, 'Google Ads')
    meta_crm = _build_campaign_journey(df_op, df_sales, 'Meta Ads')

    if marketing_live.get('google') is not None and not marketing_live['google'].empty:
        for _, row in marketing_live['google'].iterrows():
            campaign = str(row.get('Campanha', '') or '').strip()
            crm_row = google_crm[google_crm['Campanha'] == campaign]
            crm_leads = int(crm_row['Leads'].sum()) if not crm_row.empty else 0
            crm_vendas = int(crm_row['Vendas'].sum()) if not crm_row.empty else 0
            crm_receita = float(crm_row['Receita'].sum()) if not crm_row.empty else 0.0
            investimento = float(row.get('Custo', 0) or 0)
            rows.append({
                'Plataforma': 'Google Ads',
                'Campanha/Conjunto': campaign,
                'Investimento': investimento,
                'Leads': crm_leads,
                'CPL': investimento / crm_leads if crm_leads else None,
                'Vendas atribuídas': crm_vendas,
                'Receita atribuída': crm_receita,
                'CAC': investimento / crm_vendas if crm_vendas else None,
                'Conversão lead-venda': _safe_pct(crm_vendas, crm_leads),
                'Produto/Concurso validado': crm_row['Produto/Concurso validado'].iloc[0] if not crm_row.empty else '—',
            })

    if marketing_live.get('meta') is not None and not marketing_live['meta'].empty:
        for _, row in marketing_live['meta'].iterrows():
            campaign = str(row.get('Campanha', '') or '').strip()
            crm_row = meta_crm[meta_crm['Campanha'] == campaign]
            crm_leads = int(crm_row['Leads'].sum()) if not crm_row.empty else 0
            crm_vendas = int(crm_row['Vendas'].sum()) if not crm_row.empty else 0
            crm_receita = float(crm_row['Receita'].sum()) if not crm_row.empty else 0.0
            investimento = float(row.get('Custo', 0) or 0)
            rows.append({
                'Plataforma': 'Meta Ads',
                'Campanha/Conjunto': campaign,
                'Investimento': investimento,
                'Leads': crm_leads,
                'CPL': investimento / crm_leads if crm_leads else None,
                'Vendas atribuídas': crm_vendas,
                'Receita atribuída': crm_receita,
                'CAC': investimento / crm_vendas if crm_vendas else None,
                'Conversão lead-venda': _safe_pct(crm_vendas, crm_leads),
                'Produto/Concurso validado': crm_row['Produto/Concurso validado'].iloc[0] if not crm_row.empty else '—',
            })

    extra_platforms = []
    if df_sales is not None and not df_sales.empty:
        for platform in ['TikTok Ads', 'YouTube']:
            platform_df = df_sales[df_sales['plataforma_midia_atribuida'] == platform]
            if platform_df.empty:
                continue
            grouped_df = (
                platform_df.groupby('campanha_marketing_atribuida')
                .agg(
                    leads=('lead_key', 'nunique'),
                    vendas=('ordem_id', 'nunique'),
                    receita=('total_pedido', 'sum'),
                    produto=('produto_referencia_campanha', lambda series: _mode_value(series) or '—'),
                )
                .reset_index()
            )
            for _, row in grouped_df.iterrows():
                extra_platforms.append({
                    'Plataforma': platform,
                    'Campanha/Conjunto': row['campanha_marketing_atribuida'],
                    'Investimento': None,
                    'Leads': int(row['leads']),
                    'CPL': None,
                    'Vendas atribuídas': int(row['vendas']),
                    'Receita atribuída': float(row['receita']),
                    'CAC': None,
                    'Conversão lead-venda': _safe_pct(row['vendas'], row['leads']),
                    'Produto/Concurso validado': row['produto'],
                })
    rows.extend(extra_platforms)

    marketing_df = pd.DataFrame(rows)
    if marketing_df.empty:
        return marketing_df
    marketing_df = marketing_df.sort_values(['Plataforma', 'Investimento', 'Leads'], ascending=[True, False, False])
    return marketing_df


def _build_context(empresa: str, df_op: pd.DataFrame, df_v: pd.DataFrame, df_c: pd.DataFrame, df_l: pd.DataFrame, marketing_live: dict, marketing_report_text: str, data_inicio: str, data_fim: str):
    alerts = []

    if df_op is None:
        df_op = pd.DataFrame()
    if df_v is None:
        df_v = pd.DataFrame()
    if df_c is None:
        df_c = pd.DataFrame()
    if df_l is None:
        df_l = pd.DataFrame()

    if df_op.empty:
        alerts.append('Sem oportunidades no período/filtros selecionados.')

    df_op_base = _with_lead_keys(df_op, 'cliente_id', 'oportunidade_id') if not df_op.empty else pd.DataFrame()
    df_v_base = _with_lead_keys(df_v, 'cliente_id', 'ordem_id') if not df_v.empty else pd.DataFrame()

    sales_summary = (
        df_v_base.dropna(subset=['cliente_id'])
        .groupby('cliente_id')
        .agg(
            qtd_vendas=('ordem_id', 'nunique'),
            receita_total=('total_pedido', 'sum'),
            ticket_medio=('total_pedido', 'mean'),
            data_primeira_venda=('data_pagamento', 'min'),
            data_ultima_venda=('data_pagamento', 'max'),
        )
        .reset_index()
    ) if not df_v.empty else pd.DataFrame(columns=['cliente_id', 'qtd_vendas', 'receita_total', 'ticket_medio', 'data_primeira_venda', 'data_ultima_venda'])

    chat_agg = _aggregate_interactions(df_c, 'oportunidade_id', 'chat_id', 'data_chat', 'chat')
    call_agg = _aggregate_interactions(df_l, 'oportunidade_id', 'transcricao_id', 'data_ligacao', 'ligacao')
    df_sales_enriched = _link_sales_to_opportunities(df_v_base, df_op, chat_agg, call_agg)

    vendas_com_oportunidade = int(df_sales_enriched['tem_oportunidade_vinculada'].sum()) if not df_sales_enriched.empty else 0
    vendas_sem_oportunidade = int((~df_sales_enriched['tem_oportunidade_vinculada']).sum()) if not df_sales_enriched.empty else 0
    vendas_com_chat = int(df_sales_enriched['teve_chat'].sum()) if not df_sales_enriched.empty else 0
    vendas_com_ligacao = int(df_sales_enriched['teve_ligacao'].sum()) if not df_sales_enriched.empty else 0
    vendas_com_interferencia = int(df_sales_enriched['teve_interferencia_humana'].sum()) if not df_sales_enriched.empty else 0
    if vendas_sem_oportunidade:
        alerts.append(f'{vendas_sem_oportunidade} venda(s) do período não encontraram oportunidade vinculada e seguem consideradas normalmente nas métricas de vendas.')

    df_attr = _select_representative_opportunities(df_op, sales_summary)
    if not df_attr.empty:
        df_attr = df_attr.merge(sales_summary, on='cliente_id', how='left')
        df_attr = df_attr.merge(chat_agg, on='oportunidade_id', how='left')
        df_attr = df_attr.merge(call_agg, on='oportunidade_id', how='left')
        for col in ['qtd_chat', 'avaliadas_chat', 'qtd_ligacao', 'avaliadas_ligacao', 'qtd_vendas']:
            if col in df_attr.columns:
                df_attr[col] = df_attr[col].fillna(0).astype(int)
        df_attr['receita_total'] = df_attr.get('receita_total', pd.Series(0, index=df_attr.index)).fillna(0)
        df_attr['tem_venda'] = df_attr['receita_total'] > 0
        df_attr['score_atendimento_proxy'] = df_attr[[c for c in ['nota_media_chat', 'nota_media_ligacao'] if c in df_attr.columns]].mean(axis=1)
        df_attr['lead_score_proxy'] = df_attr[[c for c in ['lead_score_medio_chat', 'lead_score_medio_ligacao'] if c in df_attr.columns]].mean(axis=1)
        df_attr['lead_classification_proxy'] = df_attr.get('lead_class_chat', pd.Series(index=df_attr.index)).fillna(df_attr.get('lead_class_ligacao', pd.Series(index=df_attr.index))).fillna('—')
        df_attr['canal_atendimento'] = 'Sem atendimento'
        df_attr.loc[(df_attr.get('qtd_chat', 0) > 0) & (df_attr.get('qtd_ligacao', 0) == 0), 'canal_atendimento'] = 'Chat'
        df_attr.loc[(df_attr.get('qtd_chat', 0) == 0) & (df_attr.get('qtd_ligacao', 0) > 0), 'canal_atendimento'] = 'Ligação'
        df_attr.loc[(df_attr.get('qtd_chat', 0) > 0) & (df_attr.get('qtd_ligacao', 0) > 0), 'canal_atendimento'] = 'Chat + Ligação'
        if not df_sales_enriched.empty and 'responsavel_venda' in df_sales_enriched.columns:
            resp_map = (
                df_sales_enriched.dropna(subset=['cliente_id'])
                .groupby('cliente_id')['responsavel_venda']
                .first()
                .reset_index()
            )
            df_attr = df_attr.merge(resp_map, on='cliente_id', how='left')
            df_attr['responsavel_venda'] = df_attr['responsavel_venda'].fillna(
                df_attr.get('dono', pd.Series(index=df_attr.index, dtype=str))
            ).fillna('Indefinido')
        else:
            df_attr['responsavel_venda'] = df_attr.get('dono', pd.Series(index=df_attr.index, dtype=str)).fillna('Indefinido')
    else:
        df_attr = pd.DataFrame(columns=['lead_key'])

    leads_total = int(df_op_base['lead_key'].nunique()) if not df_op_base.empty else 0
    oportunidades_total = int(df_op['oportunidade_id'].nunique()) if not df_op.empty else 0
    vendas_total = int(df_sales_enriched['ordem_id'].nunique()) if not df_sales_enriched.empty else 0
    receita_total = float(df_sales_enriched['total_pedido'].sum()) if not df_sales_enriched.empty else 0.0
    clientes_com_venda = int(df_sales_enriched['lead_key'].nunique()) if not df_sales_enriched.empty else 0
    conversao_geral = _safe_pct(clientes_com_venda, leads_total)

    vendas_agregada_df = pd.DataFrame([{
        'Empresa': empresa,
        'Leads únicos': _format_num(leads_total),
        'Oportunidades': _format_num(oportunidades_total),
        'Vendas': _format_num(vendas_total),
        'Clientes com venda': _format_num(clientes_com_venda),
        'Receita': _format_brl(receita_total),
        'Conversão lead-venda': _format_pct(conversao_geral),
        'Ticket médio': _format_brl(df_sales_enriched['total_pedido'].mean() if not df_sales_enriched.empty else 0),
        'Vendas c/ oportunidade': _format_num(vendas_com_oportunidade),
        'Vendas sem oportunidade': _format_num(vendas_sem_oportunidade),
        'Vendas c/ chat': _format_num(vendas_com_chat),
        'Vendas c/ ligação': _format_num(vendas_com_ligacao),
        'Vendas c/ interferência humana': _format_num(vendas_com_interferencia),
    }])

    vendas_por_vendedor_df = (
        df_sales_enriched.groupby('responsavel_venda')
        .agg(
            Vendas=('ordem_id', 'nunique'),
            Receita=('total_pedido', 'sum'),
            Ticket=('total_pedido', 'mean'),
            interferencia_humana=('teve_interferencia_humana', 'sum'),
        )
        .reset_index()
        .rename(columns={'interferencia_humana': 'Interferência humana'})
        .sort_values('Receita', ascending=False)
    ) if not df_sales_enriched.empty else pd.DataFrame(columns=['responsavel_venda', 'Vendas', 'Receita', 'Ticket', 'Interferência humana'])
    if not vendas_por_vendedor_df.empty:
        vendas_por_vendedor_df = vendas_por_vendedor_df.rename(columns={'responsavel_venda': 'Vendedor'})
        vendas_por_vendedor_df['Receita'] = vendas_por_vendedor_df['Receita'].apply(_format_brl)
        vendas_por_vendedor_df['Ticket'] = vendas_por_vendedor_df['Ticket'].apply(_format_brl)

    vendas_por_modalidade_df = (
        df_sales_enriched.groupby('modalidade_validada')
        .agg(Vendas=('ordem_id', 'nunique'), Receita=('total_pedido', 'sum'), Ticket=('total_pedido', 'mean'))
        .reset_index()
        .sort_values('Receita', ascending=False)
    ) if not df_sales_enriched.empty else pd.DataFrame(columns=['modalidade_validada', 'Vendas', 'Receita', 'Ticket'])
    if not vendas_por_modalidade_df.empty:
        vendas_por_modalidade_df = vendas_por_modalidade_df.rename(columns={'modalidade_validada': 'Modalidade'})
        vendas_por_modalidade_df['Receita'] = vendas_por_modalidade_df['Receita'].apply(_format_brl)
        vendas_por_modalidade_df['Ticket'] = vendas_por_modalidade_df['Ticket'].apply(_format_brl)

    vendas_por_concurso_df = (
        df_sales_enriched.groupby('produto_referencia_campanha')
        .agg(Vendas=('ordem_id', 'nunique'), Receita=('total_pedido', 'sum'))
        .reset_index()
        .sort_values('Receita', ascending=False)
    ) if not df_sales_enriched.empty else pd.DataFrame(columns=['produto_referencia_campanha', 'Vendas', 'Receita'])
    if not vendas_por_concurso_df.empty:
        vendas_por_concurso_df = vendas_por_concurso_df.rename(columns={'produto_referencia_campanha': 'Concurso'})
        vendas_por_concurso_df['Receita'] = vendas_por_concurso_df['Receita'].apply(_format_brl)

    oportunidades_por_origem_df = (
        df_op.groupby('origem')
        .agg(Leads=('cliente_id', 'nunique'), Oportunidades=('oportunidade_id', 'nunique'))
        .reset_index()
        .sort_values('Oportunidades', ascending=False)
    ) if not df_op.empty else pd.DataFrame(columns=['origem', 'Leads', 'Oportunidades'])
    if not oportunidades_por_origem_df.empty:
        oportunidades_por_origem_df = oportunidades_por_origem_df.rename(columns={'origem': 'Origem'})

    oportunidades_por_campanha_google_df = _build_campaign_journey(df_op_base, df_sales_enriched, 'Google Ads') if not df_op_base.empty or not df_sales_enriched.empty else pd.DataFrame()
    oportunidades_por_campanha_meta_df = _build_campaign_journey(df_op_base, df_sales_enriched, 'Meta Ads') if not df_op_base.empty or not df_sales_enriched.empty else pd.DataFrame()
    oportunidades_por_campanha_tiktok_df = _build_campaign_journey(df_op_base, df_sales_enriched, 'TikTok Ads') if not df_op_base.empty or not df_sales_enriched.empty else pd.DataFrame()
    oportunidades_por_campanha_youtube_df = _build_campaign_journey(df_op_base, df_sales_enriched, 'YouTube') if not df_op_base.empty or not df_sales_enriched.empty else pd.DataFrame()

    atribuicao_df = pd.concat(
        [
            df
            for df in [
                oportunidades_por_campanha_google_df,
                oportunidades_por_campanha_meta_df,
                oportunidades_por_campanha_tiktok_df,
                oportunidades_por_campanha_youtube_df,
            ]
            if df is not None and not df.empty
        ],
        ignore_index=True,
        sort=False,
    ) if any(df is not None and not df.empty for df in [
        oportunidades_por_campanha_google_df,
        oportunidades_por_campanha_meta_df,
        oportunidades_por_campanha_tiktok_df,
        oportunidades_por_campanha_youtube_df,
    ]) else pd.DataFrame(columns=['Campanha', 'Leads', 'Oportunidades', 'Vendas', 'Receita', 'Clientes', 'Vendas com interferência humana', 'Produto/Concurso validado', 'Plataforma', 'Conversão %'])
    if not atribuicao_df.empty and 'Receita' in atribuicao_df.columns:
        atribuicao_df['Receita'] = atribuicao_df['Receita'].apply(_format_brl)

    distribuicao_etapas_df = (
        df_op.groupby('etapa')
        .agg(Volume=('oportunidade_id', 'nunique'))
        .reset_index()
        .sort_values('Volume', ascending=False)
    ) if not df_op.empty else pd.DataFrame(columns=['etapa', 'Volume'])
    if not distribuicao_etapas_df.empty:
        distribuicao_etapas_df['% do total'] = distribuicao_etapas_df['Volume'].apply(lambda value: _format_pct(_safe_pct(value, distribuicao_etapas_df['Volume'].sum())))
        distribuicao_etapas_df['Tempo médio'] = 'N/D'
        distribuicao_etapas_df['Principal motivo de perda'] = 'Dado não disponível no payload'
        distribuicao_etapas_df = distribuicao_etapas_df.rename(columns={'etapa': 'Etapa'})

    contato_proxy_df = pd.DataFrame([{
        'Leads observados': _format_num(leads_total),
        'Com chat registrado': _format_num(int((df_attr.get('qtd_chat', pd.Series(dtype=int)) > 0).sum()) if not df_attr.empty else 0),
        'Com ligação registrada': _format_num(int((df_attr.get('qtd_ligacao', pd.Series(dtype=int)) > 0).sum()) if not df_attr.empty else 0),
        'Com qualquer atendimento': _format_num(int((df_attr.get('canal_atendimento', pd.Series(dtype=str)) != 'Sem atendimento').sum()) if not df_attr.empty else 0),
        'Taxa observável': _format_pct(_safe_pct(int((df_attr.get('canal_atendimento', pd.Series(dtype=str)) != 'Sem atendimento').sum()) if not df_attr.empty else 0, leads_total)),
        'Nota': 'Proxy por chat/ligação registrada; contato efetivo estrito não está disponível.'
    }])

    speed_to_lead_df = pd.DataFrame([{
        'Métrica': 'Speed-to-lead',
        'Status': 'Indisponível',
        'Observação': 'O projeto não expõe no payload atual um timestamp confiável de primeiro atendimento humano por lead para todo o período.'
    }])

    oportunidade_concurso_col = 'sales_force' if 'sales_force' in df_op_base.columns else 'concurso'
    leads_por_concurso_df = (
        df_op_base.groupby(oportunidade_concurso_col)
        .agg(Leads=('lead_key', 'nunique'))
        .reset_index()
        .rename(columns={oportunidade_concurso_col: 'Concurso'})
    ) if not df_op_base.empty else pd.DataFrame(columns=['Concurso', 'Leads'])
    vendas_por_concurso_base_df = (
        df_sales_enriched.groupby('produto_referencia_campanha')
        .agg(Vendas=('ordem_id', 'nunique'))
        .reset_index()
        .rename(columns={'produto_referencia_campanha': 'Concurso'})
    ) if not df_sales_enriched.empty else pd.DataFrame(columns=['Concurso', 'Vendas'])
    conversao_por_concurso_df = leads_por_concurso_df.merge(vendas_por_concurso_base_df, on='Concurso', how='outer')
    if not conversao_por_concurso_df.empty:
        conversao_por_concurso_df[['Leads', 'Vendas']] = conversao_por_concurso_df[['Leads', 'Vendas']].fillna(0)
        conversao_por_concurso_df = conversao_por_concurso_df.sort_values('Vendas', ascending=False)
    if not conversao_por_concurso_df.empty:
        conversao_por_concurso_df['Conversão %'] = conversao_por_concurso_df.apply(lambda row: _format_pct(_safe_pct(row['Vendas'], row['Leads'])), axis=1)

    leads_por_modalidade_df = (
        df_op_base.groupby('modalidade')
        .agg(Leads=('lead_key', 'nunique'))
        .reset_index()
        .rename(columns={'modalidade': 'Modalidade'})
    ) if not df_op_base.empty else pd.DataFrame(columns=['Modalidade', 'Leads'])
    vendas_por_modalidade_base_df = (
        df_sales_enriched.groupby('modalidade_validada')
        .agg(Vendas=('ordem_id', 'nunique'))
        .reset_index()
        .rename(columns={'modalidade_validada': 'Modalidade'})
    ) if not df_sales_enriched.empty else pd.DataFrame(columns=['Modalidade', 'Vendas'])
    conversao_por_modalidade_df = leads_por_modalidade_df.merge(vendas_por_modalidade_base_df, on='Modalidade', how='outer')
    if not conversao_por_modalidade_df.empty:
        conversao_por_modalidade_df[['Leads', 'Vendas']] = conversao_por_modalidade_df[['Leads', 'Vendas']].fillna(0)
        conversao_por_modalidade_df = conversao_por_modalidade_df.sort_values('Vendas', ascending=False)
    if not conversao_por_modalidade_df.empty:
        conversao_por_modalidade_df['Conversão %'] = conversao_por_modalidade_df.apply(lambda row: _format_pct(_safe_pct(row['Vendas'], row['Leads'])), axis=1)

    vendor_df, vendor_category_df, vendor_quality_df, fortes_text, erros_text = _build_vendor_tables(df_attr, df_c, df_l)

    volume_chat_vs_ligacao_df = pd.DataFrame()
    if not df_attr.empty:
        volume_chat_vs_ligacao_df = (
            df_attr.groupby('canal_atendimento')
            .agg(Leads=('lead_key', 'nunique'), Oportunidades=('oportunidade_id', 'nunique'))
            .reset_index()
            .sort_values('Leads', ascending=False)
            .rename(columns={'canal_atendimento': 'Canal'})
        )

    conversao_chat_vs_ligacao_df = pd.DataFrame()
    if not df_attr.empty:
        conversao_chat_vs_ligacao_df = (
            df_attr.groupby('canal_atendimento')
            .agg(Leads=('lead_key', 'nunique'), Vendas=('tem_venda', 'sum'))
            .reset_index()
            .sort_values('Vendas', ascending=False)
            .rename(columns={'canal_atendimento': 'Canal'})
        )
        conversao_chat_vs_ligacao_df['Conversão %'] = conversao_chat_vs_ligacao_df.apply(lambda row: _format_pct(_safe_pct(row['Vendas'], row['Leads'])), axis=1)

    tempo_resposta_chat_df = pd.DataFrame([{
        'Métrica': 'Tempo de resposta do chat',
        'Status': 'Indisponível',
        'Observação': 'A query analítica usa a data real da conversa, mas não expõe um timestamp confiável de primeira resposta humana em toda a série histórica.'
    }])

    objecoes_chat_df = pd.DataFrame(_top_items(df_c.get('objections_text', pd.Series(dtype=str)), 10), columns=['Objeção', 'Frequência']) if not df_c.empty else pd.DataFrame(columns=['Objeção', 'Frequência'])
    objecoes_ligacao_df = pd.DataFrame(_top_items(df_l.get('objections_text', pd.Series(dtype=str)), 10), columns=['Objeção', 'Frequência']) if not df_l.empty else pd.DataFrame(columns=['Objeção', 'Frequência'])

    sold_opps = set(df_attr[df_attr['tem_venda']]['oportunidade_id'].tolist()) if not df_attr.empty else set()
    sold_calls_df = df_l[df_l['oportunidade_id'].isin(sold_opps)] if not df_l.empty else pd.DataFrame()
    lost_calls_df = df_l[~df_l['oportunidade_id'].isin(sold_opps)] if not df_l.empty else pd.DataFrame()

    padroes_vendidos_text = _text_block(
        'Padrões observados em ligações de oportunidades vendidas',
        [
            '- Pontos fortes recorrentes: ' + (', '.join(item for item, _ in _top_items(sold_calls_df.get('strengths', pd.Series(dtype=str)), 5)) or 'Sem padrão forte mapeado.'),
            '- Melhorias ainda presentes: ' + (', '.join(item for item, _ in _top_items(sold_calls_df.get('improvements', pd.Series(dtype=str)), 5)) or 'Sem melhoria recorrente mapeada.'),
        ]
    )
    padroes_perdidos_text = _text_block(
        'Padrões observados em ligações de oportunidades não convertidas',
        [
            '- Erros mais caros: ' + (', '.join(item for item, _ in _top_items(lost_calls_df.get('most_expensive_mistake', pd.Series(dtype=str)), 5)) or 'Sem erro recorrente mapeado.'),
            '- Objeções recorrentes: ' + (', '.join(item for item, _ in _top_items(lost_calls_df.get('objections_text', pd.Series(dtype=str)), 5)) or 'Sem objeção recorrente mapeada.'),
        ]
    )

    marketing_integrado_df = _merge_marketing_live_with_crm(df_op_base, df_sales_enriched, marketing_live)
    if marketing_integrado_df.empty:
        alerts.append('Dados estruturados de marketing indisponíveis; o bloco de marketing dependerá do histórico de IA e da atribuição por campanha no CRM.')

    marketing_block_parts = []
    if marketing_live.get('errors'):
        marketing_block_parts.append('### Alertas de coleta de marketing\n' + '\n'.join(f'- {item}' for item in marketing_live['errors']))
    marketing_block_parts.append(format_table_for_prompt(marketing_integrado_df.assign(
        Investimento=marketing_integrado_df.get('Investimento', pd.Series(dtype=float)).apply(lambda value: _format_brl(value) if pd.notna(value) else 'N/D'),
        **{'Receita atribuída': marketing_integrado_df.get('Receita atribuída', pd.Series(dtype=float)).apply(lambda value: _format_brl(value) if pd.notna(value) else 'N/D')},
        CPL=marketing_integrado_df.get('CPL', pd.Series(dtype=float)).apply(lambda value: _format_brl(value) if pd.notna(value) else 'N/D'),
        CAC=marketing_integrado_df.get('CAC', pd.Series(dtype=float)).apply(lambda value: _format_brl(value) if pd.notna(value) else 'N/D'),
        **{'Conversão lead-venda': marketing_integrado_df.get('Conversão lead-venda', pd.Series(dtype=float)).apply(lambda value: _format_pct(value) if pd.notna(value) else 'N/D')}
    ) if not marketing_integrado_df.empty else marketing_integrado_df, 'Dados estruturados de marketing'))
    marketing_block_parts.append('### Relatório IA de marketing mais recente\n' + (marketing_report_text or 'Indisponível.'))
    marketing_block = '\n'.join(marketing_block_parts)

    payload = USER_PROMPT_TEMPLATE.format(
        nome_empresa=empresa,
        school_id=EMPRESAS[empresa]['school_id'],
        data_inicio=data_inicio,
        data_fim=data_fim,
        dias=(pd.Timestamp(data_fim) - pd.Timestamp(data_inicio)).days + 1,
        data_geracao=datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
        tabela_vendas_agregada=format_table_for_prompt(vendas_agregada_df, 'Resumo de vendas e matrículas'),
        tabela_vendas_por_vendedor=format_table_for_prompt(vendas_por_vendedor_df, 'Vendas por vendedor'),
        tabela_vendas_por_modalidade=format_table_for_prompt(vendas_por_modalidade_df, 'Vendas por modalidade'),
        tabela_vendas_por_concurso=format_table_for_prompt(vendas_por_concurso_df, 'Vendas por concurso'),
        tabela_oportunidades_por_origem=format_table_for_prompt(oportunidades_por_origem_df, 'Oportunidades por origem'),
        tabela_oportunidades_por_campanha_google=format_table_for_prompt(oportunidades_por_campanha_google_df, 'Oportunidades por campanha Google'),
        tabela_oportunidades_por_campanha_meta=format_table_for_prompt(oportunidades_por_campanha_meta_df, 'Oportunidades por campanha Meta'),
        tabela_oportunidades_por_campanha_tiktok=format_table_for_prompt(oportunidades_por_campanha_tiktok_df, 'Oportunidades por campanha TikTok'),
        tabela_oportunidades_por_campanha_youtube=format_table_for_prompt(oportunidades_por_campanha_youtube_df, 'Oportunidades por campanha YouTube'),
        tabela_atribuicao_lead_venda=format_table_for_prompt(atribuicao_df, 'Atribuição lead-venda por plataforma e campanha'),
        tabela_distribuicao_etapas=format_table_for_prompt(distribuicao_etapas_df, 'Distribuição de etapas do funil'),
        tabela_taxa_contato_efetivo=format_table_for_prompt(contato_proxy_df, 'Contato observável no funil (proxy)'),
        tabela_speed_to_lead=format_table_for_prompt(speed_to_lead_df, 'Speed-to-lead'),
        tabela_conversao_por_concurso=format_table_for_prompt(conversao_por_concurso_df, 'Conversão por concurso'),
        tabela_conversao_por_modalidade=format_table_for_prompt(conversao_por_modalidade_df, 'Conversão por modalidade'),
        tabela_score_medio_por_vendedor=format_table_for_prompt(vendor_df[['Vendedor', 'Volume Atendido', 'Score Médio Lead', 'Conversão %', 'Score Médio Atendimento', 'Maior Gap']] if not vendor_df.empty else vendor_df, 'Score médio por vendedor'),
        tabela_score_por_categoria_por_vendedor=format_table_for_prompt(vendor_category_df, 'Score por categoria por vendedor'),
        tabela_volume_por_vendedor=format_table_for_prompt(vendor_df[['Vendedor', 'Volume Atendido', 'Oportunidades', 'Vendas', 'Receita']] if not vendor_df.empty else vendor_df, 'Volume por vendedor'),
        tabela_qualidade_lead_recebido_por_vendedor=format_table_for_prompt(vendor_quality_df, 'Qualidade do lead recebido por vendedor'),
        tabela_conversao_por_vendedor=format_table_for_prompt(vendor_df[['Vendedor', 'Volume Atendido', 'Vendas', 'Conversão %']] if not vendor_df.empty else vendor_df, 'Conversão por vendedor'),
        amostra_pontos_fortes_recorrentes_por_vendedor=fortes_text,
        amostra_erros_recorrentes_por_vendedor=erros_text,
        tabela_volume_chat_vs_ligacao=format_table_for_prompt(volume_chat_vs_ligacao_df, 'Volume por canal de atendimento'),
        tabela_conversao_chat_vs_ligacao=format_table_for_prompt(conversao_chat_vs_ligacao_df, 'Conversão por canal de atendimento'),
        tabela_tempo_resposta_chat=format_table_for_prompt(tempo_resposta_chat_df, 'Tempo de resposta do chat'),
        tabela_objecoes_recorrentes_chat=format_table_for_prompt(objecoes_chat_df, 'Objeções recorrentes em chats'),
        tabela_objecoes_recorrentes_ligacao=format_table_for_prompt(objecoes_ligacao_df, 'Objeções recorrentes em ligações'),
        amostra_padroes_ligacoes_vendidas=padroes_vendidos_text,
        amostra_padroes_ligacoes_perdidas=padroes_perdidos_text,
        relatorio_ia_marketing_consolidado=marketing_block,
    )

    return {
        'empresa': empresa,
        'alerts': alerts,
        'metrics': {
            'leads_total': leads_total,
            'oportunidades_total': oportunidades_total,
            'vendas_total': vendas_total,
            'clientes_com_venda': clientes_com_venda,
            'receita_total': receita_total,
            'conversao_geral': conversao_geral,
        },
        'payload': payload,
        'tables': {
            'vendas_agregada': vendas_agregada_df,
            'vendas_por_vendedor': vendas_por_vendedor_df,
            'atribuicao': atribuicao_df,
            'etapas': distribuicao_etapas_df,
            'vendor': vendor_df,
            'marketing': marketing_integrado_df,
        },
    }


def _call_claude(system_prompt: str, user_prompt: str, max_tokens=8000, temperature=0.3):
    client, error = _get_anthropic_client()
    if error:
        return None, {'error': error}
    if client is None:
        return None, {'error': 'Cliente Anthropic indisponível.'}

    import anthropic as _anthropic

    last_error = None
    for model_name in MODELOS_ANTHROPIC:
        for _ in range(2):
            try:
                response = client.messages.create(
                    model=model_name,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_prompt,
                    messages=[{'role': 'user', 'content': user_prompt}],
                )
                text_chunks = []
                for block in getattr(response, 'content', []):
                    block_text = getattr(block, 'text', None)
                    if block_text:
                        text_chunks.append(block_text)
                usage = getattr(response, 'usage', None)
                return ''.join(text_chunks), {
                    'model': model_name,
                    'input_tokens': getattr(usage, 'input_tokens', None),
                    'output_tokens': getattr(usage, 'output_tokens', None),
                    'custo_estimado_usd': None,
                }
            except _anthropic.APIStatusError as exc:
                last_error = f'Erro na API Claude ({model_name}): {exc.status_code} - {exc.message}'
                continue
            except Exception as exc:
                last_error = f'Erro ao chamar Claude ({model_name}): {exc}'
                continue
    return None, {'error': last_error or 'Falha desconhecida ao chamar Claude.'}


def _render_company_summary(context: dict):
    metrics = context['metrics']
    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Leads únicos', _format_num(metrics['leads_total']))
    c2.metric('Oportunidades', _format_num(metrics['oportunidades_total']))
    c3.metric('Vendas', _format_num(metrics['vendas_total']))
    c4.metric('Receita', _format_brl(metrics['receita_total']))
    c5, c6 = st.columns(2)
    c5.metric('Clientes com venda', _format_num(metrics['clientes_com_venda']))
    c6.metric('Conversão lead-venda', _format_pct(metrics['conversao_geral']))

    for alert in context['alerts']:
        st.warning(alert)

    tables = context['tables']
    if not tables['vendas_agregada'].empty:
        st.markdown('#### Resumo comercial')
        st.dataframe(tables['vendas_agregada'], use_container_width=True, hide_index=True)
    if not tables['atribuicao'].empty:
        st.markdown('#### Atribuição por plataforma e campanha')
        st.dataframe(tables['atribuicao'], use_container_width=True, hide_index=True)
    if not tables['vendor'].empty:
        st.markdown('#### Desempenho por vendedor')
        st.dataframe(tables['vendor'], use_container_width=True, hide_index=True)
    if not tables['etapas'].empty:
        st.markdown('#### Distribuição de etapas')
        st.dataframe(tables['etapas'], use_container_width=True, hide_index=True)
    if not tables['marketing'].empty:
        marketing_ui_df = tables['marketing'].copy()
        marketing_ui_df['Investimento'] = marketing_ui_df['Investimento'].apply(lambda value: _format_brl(value) if pd.notna(value) else 'N/D')
        marketing_ui_df['CPL'] = marketing_ui_df['CPL'].apply(lambda value: _format_brl(value) if pd.notna(value) else 'N/D')
        marketing_ui_df['CAC'] = marketing_ui_df['CAC'].apply(lambda value: _format_brl(value) if pd.notna(value) else 'N/D')
        marketing_ui_df['Conversão lead-venda'] = marketing_ui_df['Conversão lead-venda'].apply(lambda value: _format_pct(value) if pd.notna(value) else 'N/D')
        st.markdown('#### Investimento x oportunidades x vendas')
        st.dataframe(marketing_ui_df, use_container_width=True, hide_index=True)


def run_page():
    st.title('🧠 Análise Geral Integrada')
    st.caption('Painel consolidado para cruzar oportunidades, vendas, chats, ligações e marketing, com payload estruturado para IA.')

    st.sidebar.header('Filtros')
    escopo = st.sidebar.radio('Escopo:', ['Degrau', 'Central', 'Comparativo'], index=0)
    st.sidebar.caption('Origem, campanha, etapa, modalidade e agente afetam oportunidades e atendimento. Vendas permanecem completas no período, respeitando apenas os filtros próprios de venda.')
    hoje = pd.Timestamp.now(tz=TIMEZONE).date()
    periodo = st.sidebar.date_input('Período:', [hoje - pd.Timedelta(days=30), hoje], key='analise_geral_periodo')
    incluir_marketing_ao_vivo = st.sidebar.checkbox('Incluir dados de Ads ao vivo', value=True)

    try:
        data_inicio = pd.Timestamp(periodo[0], tz=TIMEZONE)
        data_fim = pd.Timestamp(periodo[1], tz=TIMEZONE)
    except (IndexError, TypeError):
        st.sidebar.warning('Selecione um período completo.')
        st.stop()

    if escopo == 'Comparativo':
        school_ids_csv = '1, 2'
        empresas_alvo = ['Degrau', 'Central']
    else:
        school_ids_csv = EMPRESAS[escopo]['school_ids_csv']
        empresas_alvo = [escopo]

    with st.spinner('Carregando bases comerciais...'):
        frames = _load_base_frames(school_ids_csv, data_inicio.strftime('%Y-%m-%d'), data_fim.strftime('%Y-%m-%d'))

    df_oportunidades = _enrich_campaigns(frames['oportunidades'])
    if not df_oportunidades.empty:
        df_oportunidades['criacao'] = _coerce_tz(df_oportunidades['criacao'])
    df_vendas = frames['vendas'].copy()
    if not df_vendas.empty:
        df_vendas['data_pagamento'] = _coerce_tz(df_vendas['data_pagamento'])
        if 'status_id' in df_vendas.columns:
            df_vendas = df_vendas[df_vendas['status_id'].isin(STATUS_VENDA_IDS_PERMITIDOS)].copy()
    df_chats = _prepare_chats(frames['chats'])
    df_ligacoes = _prepare_calls(frames['ligacoes'])
    df_reports = frames['marketing_reports'].copy()

    if df_oportunidades.empty and df_vendas.empty and df_chats.empty and df_ligacoes.empty:
        st.warning('Nenhum dado encontrado para o período selecionado.')
        st.stop()

    origens_disp = sorted([value for value in df_oportunidades.get('origem', pd.Series(dtype=str)).dropna().unique().tolist() if str(value).strip()])
    campanhas_disp = sorted([value for value in df_oportunidades.get('campanha_marketing', pd.Series(dtype=str)).dropna().unique().tolist() if str(value).strip()])
    vendedores_disp = sorted(set(
        [value for value in df_oportunidades.get('dono', pd.Series(dtype=str)).dropna().unique().tolist() if str(value).strip()] +
        [value for value in df_vendas.get('dono', pd.Series(dtype=str)).dropna().unique().tolist() if str(value).strip()] +
        [value for value in df_vendas.get('vendedor', pd.Series(dtype=str)).dropna().unique().tolist() if str(value).strip()]
    ))
    etapas_disp = sorted([value for value in df_oportunidades.get('etapa', pd.Series(dtype=str)).dropna().unique().tolist() if str(value).strip()])
    modalidades_disp = sorted([value for value in df_oportunidades.get('modalidade', pd.Series(dtype=str)).dropna().unique().tolist() if str(value).strip()])
    agentes_disp = sorted(set(
        [value for value in df_chats.get('agente', pd.Series(dtype=str)).dropna().unique().tolist() if str(value).strip()] +
        [value for value in df_ligacoes.get('agente', pd.Series(dtype=str)).dropna().unique().tolist() if str(value).strip()]
    ))
    status_venda_disp = sorted([value for value in df_vendas.get('status', pd.Series(dtype=str)).dropna().unique().tolist() if str(value).strip()])

    filtros = {
        'origens': st.sidebar.multiselect('Origem:', origens_disp, default=origens_disp),
        'campanhas': st.sidebar.multiselect('Campanha:', campanhas_disp, default=campanhas_disp),
        'vendedores': st.sidebar.multiselect('Responsável comercial:', vendedores_disp, default=vendedores_disp),
        'etapas': st.sidebar.multiselect('Etapa da oportunidade:', etapas_disp, default=etapas_disp),
        'modalidades': st.sidebar.multiselect('Modalidade:', modalidades_disp, default=modalidades_disp),
        'agentes': st.sidebar.multiselect('Agente de atendimento:', agentes_disp, default=agentes_disp),
        'status_venda': st.sidebar.multiselect('Status da venda:', status_venda_disp, default=status_venda_disp),
    }

    df_oportunidades, df_vendas, df_chats, df_ligacoes = _apply_filters(df_oportunidades, df_vendas, df_chats, df_ligacoes, filtros)

    contextos = {}
    with st.spinner('Consolidando payloads por empresa...'):
        for empresa in empresas_alvo:
            op_df = df_oportunidades[df_oportunidades['empresa'] == empresa].copy() if not df_oportunidades.empty else pd.DataFrame()
            v_df = df_vendas[df_vendas['empresa'] == empresa].copy() if not df_vendas.empty else pd.DataFrame()
            c_df = df_chats[df_chats['empresa'] == empresa].copy() if not df_chats.empty else pd.DataFrame()
            l_df = df_ligacoes[df_ligacoes['empresa'] == empresa].copy() if not df_ligacoes.empty else pd.DataFrame()
            marketing_live = _load_live_marketing(empresa, data_inicio.strftime('%Y-%m-%d'), data_fim.strftime('%Y-%m-%d')) if incluir_marketing_ao_vivo else {'google': pd.DataFrame(), 'meta': pd.DataFrame(), 'errors': ['Coleta ao vivo desabilitada pelo usuário.']}
            marketing_report_text = _select_marketing_report(df_reports, empresa)
            contextos[empresa] = _build_context(
                empresa,
                op_df,
                v_df,
                c_df,
                l_df,
                marketing_live,
                marketing_report_text,
                data_inicio.strftime('%Y-%m-%d'),
                data_fim.strftime('%Y-%m-%d'),
            )

    tab_resumo, tab_payload, tab_ia, tab_historico = st.tabs([
        '📊 Resumo',
        '🧾 Payload IA',
        '🤖 Relatório IA',
        '📁 Histórico',
    ])

    with tab_resumo:
        if escopo == 'Comparativo':
            comparativo_df = pd.DataFrame([
                {
                    'Empresa': empresa,
                    'Leads únicos': _format_num(ctx['metrics']['leads_total']),
                    'Oportunidades': _format_num(ctx['metrics']['oportunidades_total']),
                    'Vendas': _format_num(ctx['metrics']['vendas_total']),
                    'Clientes com venda': _format_num(ctx['metrics']['clientes_com_venda']),
                    'Receita': _format_brl(ctx['metrics']['receita_total']),
                    'Conversão lead-venda': _format_pct(ctx['metrics']['conversao_geral']),
                }
                for empresa, ctx in contextos.items()
            ])
            st.markdown('### Comparativo executivo')
            st.dataframe(comparativo_df, use_container_width=True, hide_index=True)

        for empresa in empresas_alvo:
            st.markdown(f'### {empresa}')
            _render_company_summary(contextos[empresa])

    with tab_payload:
        empresa_payload = empresas_alvo[0] if len(empresas_alvo) == 1 else st.selectbox('Empresa do payload:', empresas_alvo, key='analise_geral_payload_empresa')
        payload = contextos[empresa_payload]['payload']
        st.metric('Tamanho aproximado do payload', f"{len(payload):,} caracteres".replace(',', '.'))
        with st.expander('Ver payload completo', expanded=True):
            st.code(payload, language='text')

    with tab_ia:
        empresa_ia = empresas_alvo[0] if len(empresas_alvo) == 1 else st.selectbox('Empresa do relatório IA:', empresas_alvo, key='analise_geral_ia_empresa')
        contexto_ia = contextos[empresa_ia]
        payload = contexto_ia['payload']
        data_ref = f"{empresa_ia.lower()}_{data_inicio.strftime('%Y-%m-%d')}_a_{data_fim.strftime('%Y-%m-%d')}"
        resultados = st.session_state.setdefault('analise_geral_resultados', {})
        resultado_key = f"{empresa_ia}_{data_ref}"

        if st.button('Gerar relatório com IA', type='primary', use_container_width=True, key='analise_geral_btn_gerar'):
            with st.spinner('Gerando análise estratégica com Claude...'):
                report, meta = _call_claude(SYSTEM_PROMPT, payload)
            if meta.get('error'):
                st.error(meta['error'])
            else:
                dados_brutos = json.dumps({
                    'empresa': empresa_ia,
                    'school_id': EMPRESAS[empresa_ia]['school_id'],
                    'data_inicio': data_inicio.strftime('%Y-%m-%d'),
                    'data_fim': data_fim.strftime('%Y-%m-%d'),
                    'payload': payload,
                    'model': meta.get('model'),
                    'input_tokens': meta.get('input_tokens'),
                    'output_tokens': meta.get('output_tokens'),
                    'custo_estimado_usd': meta.get('custo_estimado_usd'),
                }, ensure_ascii=False, indent=2)
                salvar_relatorio(report, dados_brutos, data_ref, tipo=TIPO_RELATORIO)
                resultados[resultado_key] = {'report': report, 'meta': meta, 'payload': payload}
                st.session_state['analise_geral_resultados'] = resultados

        resultado = resultados.get(resultado_key)
        if resultado:
            meta = resultado.get('meta', {})
            c1, c2, c3 = st.columns(3)
            c1.metric('Modelo', meta.get('model', 'N/D'))
            c2.metric('Input tokens', _format_num(meta.get('input_tokens')))
            c3.metric('Output tokens', _format_num(meta.get('output_tokens')))
            _renderizar_analise(resultado['report'], tipo='analise_geral')

            html_bytes = gerar_html_relatorio(resultado['report'], resultado['payload'], data_ref, TIPO_RELATORIO)
            st.download_button(
                label='Exportar HTML do relatório',
                data=html_bytes,
                file_name=f'relatorio_{TIPO_RELATORIO}_{data_ref}.html',
                mime='text/html',
                use_container_width=True,
                key='analise_geral_html_download',
            )

            if st.button('Validar uso dos dados', use_container_width=True, key='analise_geral_validar_btn'):
                validation_prompt = VALIDATION_PROMPT_TEMPLATE.format(
                    payload=resultado['payload'],
                    report=resultado['report'],
                )
                with st.spinner('Validando cobertura do payload...'):
                    validation_report, validation_meta = _call_claude(
                        'Você é um auditor técnico de qualidade analítica. Seja direto e específico.',
                        validation_prompt,
                        max_tokens=3000,
                        temperature=0.1,
                    )
                if validation_meta.get('error'):
                    st.error(validation_meta['error'])
                else:
                    st.markdown('### Auditoria de uso dos dados')
                    st.markdown(validation_report)
        else:
            st.info('Gere o relatório da empresa selecionada para visualizar o resultado e rodar a auditoria de uso do payload.')

    with tab_historico:
        historico = carregar_relatorios_historico(TIPO_RELATORIO)
        if not historico:
            st.info('Nenhum relatório de análise geral salvo ainda.')
        else:
            for idx, item in enumerate(historico):
                with st.expander(f"{item['data']} [{item['tipo']}]"):
                    st.markdown(item['analise'])
                    with st.expander('Payload / dados salvos'):
                        st.code(item['dados_brutos'], language='json')
                    html_bytes = gerar_html_relatorio(item['analise'], item['dados_brutos'], item['data'], item['tipo'])
                    st.download_button(
                        label='Exportar HTML do histórico',
                        data=html_bytes,
                        file_name=f"historico_{item['tipo']}_{idx}.html",
                        mime='text/html',
                        use_container_width=True,
                        key=f'analise_geral_hist_html_{idx}',
                    )


if __name__ == '__main__':
    run_page()