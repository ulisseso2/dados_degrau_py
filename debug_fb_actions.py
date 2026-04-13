"""
Script de diagnóstico: imprime os action_types reais retornados pela API do Facebook,
e exibe o mapeamento de Custom Conversions (ID → nome).
Uso: python debug_fb_actions.py
"""
import os
from dotenv import load_dotenv
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adsinsights import AdsInsights
from facebook_business.adobjects.customconversion import CustomConversion

load_dotenv()
load_dotenv('.facebook_credentials.env', override=True)

app_id       = os.getenv("FB_APP_ID")
app_secret   = os.getenv("FB_APP_SECRET")
access_token = os.getenv("FB_ACCESS_TOKEN")
ad_account_id = os.getenv("FB_AD_ACCOUNT_ID")

if not all([app_id, app_secret, access_token, ad_account_id]):
    print("❌ Variáveis de ambiente não encontradas. Verifique .facebook_credentials.env")
    exit(1)

FacebookAdsApi.init(app_id=app_id, app_secret=app_secret, access_token=access_token)
account = AdAccount(ad_account_id)

# ── Mapeamento de Custom Conversions ────────────────────────────────────────
print("\n" + "="*60)
print("CUSTOM CONVERSIONS DA CONTA")
print("="*60)
custom_map = {}
try:
    convs = account.get_custom_conversions(
        fields=[CustomConversion.Field.id, CustomConversion.Field.name]
    )
    for conv in convs:
        cid  = conv.get(CustomConversion.Field.id, '')
        name = conv.get(CustomConversion.Field.name, '')
        key  = f'offsite_conversion.custom.{cid}'
        custom_map[key] = name.lower().strip()
        print(f"  {key}  →  {name}")
except Exception as e:
    print(f"  Erro ao buscar custom conversions: {e}")

# ── Insights por campanha ────────────────────────────────────────────────────
fields = [
    AdsInsights.Field.campaign_name,
    AdsInsights.Field.spend,
    AdsInsights.Field.actions,
]
params = {
    'level': 'campaign',
    'time_range': {'since': '2026-04-03', 'until': '2026-04-09'},
}

insights = account.get_insights(fields=fields, params=params)

for insight in insights:
    nome = insight.get(AdsInsights.Field.campaign_name, "")
    spend = insight.get(AdsInsights.Field.spend, "0")
    actions = insight.get(AdsInsights.Field.actions, [])

    if not actions:
        continue  # pula campanhas sem nenhuma ação

    print(f"\n{'='*60}")
    print(f"Campanha : {nome}")
    print(f"Gasto    : R$ {spend}")
    print("Actions (custom events com nome resolvido):")
    for a in actions:
        atype = a.get('action_type', '')
        val   = a.get('value', '0')
        nome_resolvido = custom_map.get(atype, '')
        sufixo = f"  → {nome_resolvido}" if nome_resolvido else ""
        print(f"  action_type={atype}  value={val}{sufixo}")
