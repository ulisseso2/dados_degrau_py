"""
Script de diagnóstico: compara action_types com action_breakdowns
para ver se lead_presencial aparece como evento pixel individual.
"""
import os
from dotenv import load_dotenv
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adsinsights import AdsInsights

load_dotenv()
load_dotenv('.facebook_credentials.env', override=True)

app_id       = os.getenv("FB_APP_ID")
app_secret   = os.getenv("FB_APP_SECRET")
access_token = os.getenv("FB_ACCESS_TOKEN")
ad_account_id = os.getenv("FB_AD_ACCOUNT_ID")

FacebookAdsApi.init(app_id=app_id, app_secret=app_secret, access_token=access_token)
account = AdAccount(ad_account_id)

PERIODO = {'since': '2026-04-03', 'until': '2026-04-09'}

# ── Teste 1: actions normais (o que já temos) ────────────────────────────
print("=" * 70)
print("TESTE 1: actions padrão")
print("=" * 70)
params = {
    'level': 'campaign',
    'time_range': PERIODO,
    'filtering': [{'field': 'campaign.name', 'operator': 'CONTAIN', 'value': 'PMERJ'}],
    'use_account_attribution_setting': True,
}
insights = account.get_insights(
    fields=[AdsInsights.Field.campaign_name, AdsInsights.Field.actions],
    params=params,
)
for insight in insights:
    nome = insight.get('campaign_name', '')
    if 'LEADS' not in nome.upper():
        continue
    print(f"\n  {nome}")
    for a in insight.get('actions', []):
        at = a['action_type']
        if 'custom' in at or 'lead' in at or 'pixel_custom' in at:
            print(f"    {at} = {a['value']}")

# ── Teste 2: com action_breakdowns ──────────────────────────────────────
print("\n" + "=" * 70)
print("TESTE 2: com action_breakdowns=['action_type']")
print("=" * 70)
params2 = {
    'level': 'campaign',
    'time_range': PERIODO,
    'filtering': [{'field': 'campaign.name', 'operator': 'CONTAIN', 'value': 'PMERJ'}],
    'use_account_attribution_setting': True,
    'action_breakdowns': ['action_type'],
}
insights2 = account.get_insights(
    fields=[AdsInsights.Field.campaign_name, AdsInsights.Field.actions],
    params=params2,
)
for insight in insights2:
    nome = insight.get('campaign_name', '')
    if 'LEADS' not in nome.upper():
        continue
    print(f"\n  {nome}")
    for a in insight.get('actions', []):
        at = a['action_type']
        if 'custom' in at or 'lead' in at or 'pixel_custom' in at:
            print(f"    {at} = {a['value']}")

# ── Teste 3: buscar conversions separado ────────────────────────────────
print("\n" + "=" * 70)
print("TESTE 3: campo 'conversions' (se diferente de actions)")
print("=" * 70)
try:
    params3 = {
        'level': 'campaign',
        'time_range': PERIODO,
        'filtering': [{'field': 'campaign.name', 'operator': 'CONTAIN', 'value': 'PMERJ'}],
        'use_account_attribution_setting': True,
    }
    insights3 = account.get_insights(
        fields=[AdsInsights.Field.campaign_name, 'conversions'],
        params=params3,
    )
    for insight in insights3:
        nome = insight.get('campaign_name', '')
        if 'LEADS' not in nome.upper():
            continue
        print(f"\n  {nome}")
        convs = insight.get('conversions', [])
        if not convs:
            print("    (campo 'conversions' vazio ou não retornado)")
        for c in convs:
            at = c.get('action_type', '')
            if 'custom' in at or 'lead' in at or 'pixel_custom' in at:
                print(f"    {at} = {c['value']}")
except Exception as e:
    print(f"  Erro: {e}")

# ── Teste 4: TODOS os action_types (sem filtro) ──────────────────────────
print("\n" + "=" * 70)
print("TESTE 4: TODOS os action_types (busca lead_ que não é custom)")
print("=" * 70)
params4 = {
    'level': 'campaign',
    'time_range': PERIODO,
    'filtering': [{'field': 'campaign.name', 'operator': 'CONTAIN', 'value': 'PMERJ'}],
    'use_account_attribution_setting': True,
}
insights4 = account.get_insights(
    fields=[AdsInsights.Field.campaign_name, AdsInsights.Field.actions],
    params=params4,
)
for insight in insights4:
    nome = insight.get('campaign_name', '')
    if 'LEADS' not in nome.upper():
        continue
    print(f"\n  {nome} - TODOS action_types:")
    for a in insight.get('actions', []):
        print(f"    {a['action_type']} = {a['value']}")
