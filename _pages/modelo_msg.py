import os
import requests
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from facebook_api_utils import init_facebook_api

load_dotenv()


def get_waba_id_from_env_or_secrets():
    try:
        waba = st.secrets["facebook_api"].get("waba_id")
        if waba:
            return waba
    except Exception:
        pass

    return os.getenv("FB_WABA_ID")


def fetch_whatsapp_templates(waba_id: str, access_token: str, locale: str = None):
    """
    Consulta a API Graph para listar message templates do WhatsApp Business Account (WABA).
    Retorna um DataFrame com os campos retornados pela API.
    """
    if not waba_id or not access_token:
        raise ValueError("WABA ID e access_token são necessários para consultar templates.")

    base_url = f"https://graph.facebook.com/v18.0/{waba_id}/message_templates"
    params = {"access_token": access_token}
    if locale:
        params["locale"] = locale

    resp = requests.get(base_url, params=params, timeout=30)
    data = resp.json()

    if resp.status_code != 200:
        msg = data.get("error", {}).get("message", str(data))
        raise RuntimeError(f"Erro ao buscar templates: {msg}")

    items = data.get("data", [])
    if not items:
        return pd.DataFrame()

    # Normaliza JSON para DataFrame — mantém colunas úteis
    rows = []
    for it in items:
        rows.append({
            "name": it.get("name"),
            "language": it.get("language"),
            "status": it.get("status"),
            "category": it.get("category"),
            "id": it.get("id"),
            "raw": it,
        })

    df = pd.DataFrame(rows)
    return df


def run_page():
    st.title("✉️ Modelos de Mensagem (WhatsApp Business)")

    st.markdown(
        "Nesta página você pode listar os modelos (message templates) do seu WhatsApp Business Account (WABA)."
    )

    # Inicializa credenciais via utilitário já existente
    app_id, app_secret, access_token, ad_account_id, account = init_facebook_api()

    # Obtém WABA ID (do st.secrets ou env)
    waba_id = get_waba_id_from_env_or_secrets()

    with st.expander("⚙️ Informações sobre credenciais e requisitos", expanded=True):
        st.markdown(
            "- Você precisa de um `access_token` com permissão `whatsapp_business_management` (e geralmente `whatsapp_business_messaging` para operações relacionadas)."
        )
        st.markdown("- É necessário o ID do WhatsApp Business Account (WABA). Pode vir via `st.secrets['facebook_api']['waba_id']` ou variável de ambiente `FB_WABA_ID`.")
        st.markdown("- O usuário que gerou o token deve ter papel administrativo no Business Manager que contém a conta do WhatsApp.")
        st.markdown("- Endpoint usado: `/v18.0/{WABA_ID}/message_templates` (Graph API).")

    if not all([app_id, app_secret, access_token]):
        st.error("As credenciais do Facebook não foram carregadas. Verifique `st.secrets` ou o arquivo .env.`")
        return

    st.sidebar.header("Parâmetros da Consulta")
    if waba_id:
        st.sidebar.text_input("WABA ID", value=waba_id, key="waba_id_input")
    else:
        st.sidebar.text_input("WABA ID", value="", placeholder="Insira o WABA ID (ex: 123456789)", key="waba_id_input")

    locale = st.sidebar.text_input("Locale (opcional)", value="", placeholder="ex: pt_BR")

    st.sidebar.markdown("---")
    st.sidebar.subheader("Credenciais e IDs")
    fb_app_id = st.sidebar.text_input("FB App ID", value=app_id or "", key="fb_app_id")
    fb_app_secret = st.sidebar.text_input("FB App Secret", value=app_secret or "", key="fb_app_secret")
    fb_access_token = st.sidebar.text_input("FB Access Token", value=access_token or "", key="fb_access_token")
    fb_ad_account = st.sidebar.text_input("FB Ad Account ID", value=ad_account_id or "", key="fb_ad_account")
    phone_number_id = st.sidebar.text_input("Phone Number ID (opcional)", value=os.getenv('FB_PHONE_NUMBER_ID',''), key="phone_number_id")
    waba_id_input = st.sidebar.text_input("WABA ID (opcional)", value=get_waba_id_from_env_or_secrets() or "", key="waba_id_input_manual")

    if st.sidebar.button("💾 Salvar credenciais em .facebook_credentials.env"):
        # Escreve as credenciais no arquivo local (cuidado: este arquivo contém tokens)
        try:
            with open('.facebook_credentials.env', 'w') as f:
                if fb_app_id:
                    f.write(f"FB_APP_ID={fb_app_id}\n")
                if fb_app_secret:
                    f.write(f"FB_APP_SECRET={fb_app_secret}\n")
                if fb_access_token:
                    f.write(f"FB_ACCESS_TOKEN={fb_access_token}\n")
                if fb_ad_account:
                    f.write(f"FB_AD_ACCOUNT_ID={fb_ad_account}\n")
                if phone_number_id:
                    f.write(f"FB_PHONE_NUMBER_ID={phone_number_id}\n")
                if waba_id_input:
                    f.write(f"FB_WABA_ID={waba_id_input}\n")

            st.success("Arquivo '.facebook_credentials.env' atualizado com sucesso (local).")
        except Exception as e:
            st.error(f"Falha ao salvar arquivo: {e}")

    if st.sidebar.button("🔎 Obter WABA a partir do Phone Number ID"):
        phone_id_use = st.session_state.get('phone_number_id') or phone_number_id
        token_use = st.session_state.get('fb_access_token') or fb_access_token or access_token
        if not phone_id_use:
            st.error("Informe o Phone Number ID na barra lateral para tentar obter o WABA ID.")
        elif not token_use:
            st.error("Access token ausente. Configure o token na barra lateral ou em .facebook_credentials.env.")
        else:
            with st.spinner("Consultando Graph API para obter WABA ID..."):
                try:
                    url = f"https://graph.facebook.com/v18.0/{phone_id_use}"
                    params = {"fields": "whatsapp_business_account", "access_token": token_use}
                    resp = requests.get(url, params=params, timeout=30)
                    data = resp.json()
                    if resp.status_code == 200 and 'whatsapp_business_account' in data:
                        waba_found = data['whatsapp_business_account'].get('id')
                        st.success(f"WABA ID encontrado: {waba_found}")
                        # Preenche o campo manual para possível salvamento
                        st.session_state['waba_id_input_manual'] = waba_found
                    else:
                        err = data.get('error', {}).get('message', str(data))
                        st.error(f"Não foi possível obter WABA ID: {err}")
                except Exception as e:
                    st.error(f"Erro ao consultar Graph API: {e}")

    st.sidebar.markdown("---")

    if st.sidebar.button("🔎 Listar templates"):
        waba_id_use = st.session_state.get("waba_id_input")
        if not waba_id_use:
            st.error("WABA ID é obrigatório para consultar os templates.")
            st.stop()

        with st.spinner("Buscando templates do WhatsApp Business..."):
            try:
                df = fetch_whatsapp_templates(waba_id_use, access_token, locale or None)
            except Exception as e:
                st.error(f"Falha ao buscar templates: {e}")
                st.stop()

        if df.empty:
            st.info("Nenhum template encontrado para os parâmetros informados.")
            return

        # Exibir tabela resumida
        st.subheader("Templates encontrados")
        display_df = df.drop(columns=["raw"]) if "raw" in df.columns else df
        st.dataframe(display_df, use_container_width=True)

        # Mostrar detalhe do template selecionado
        sel = st.selectbox("Selecione um template para ver detalhes", options=df.index.map(lambda i: f"{df.at[i,'name']} ({df.at[i,'language']})"))
        idx = int(sel.split(" ")[0]) if sel and sel[0].isdigit() else df.index[0]
        # Safe access: find matching row by name+language
        name_lang = sel.rsplit("(", 1)[0].strip() if sel else None
        # Find row by constructed string
        row = df.iloc[0]
        try:
            # try to find by name+language
            nm, lang = sel.rsplit("(", 1)
            lang = lang.rstrip(")")
            row = df[(df["name"] == nm.strip()) & (df["language"] == lang.strip())].iloc[0]
        except Exception:
            row = df.iloc[0]

        st.subheader("Detalhe do template")
        st.json(row["raw"])

        # Download
        csv = df.drop(columns=["raw"]).to_csv(index=False)
        st.download_button("📥 Baixar CSV", data=csv, file_name="whatsapp_templates.csv", mime="text/csv")


if __name__ == "__main__":
    # Para execução local rápida
    run_page()
