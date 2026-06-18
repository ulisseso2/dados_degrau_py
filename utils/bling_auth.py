"""
Gerencia o token OAuth da Bling com refresh automático.
Funciona tanto localmente (lê/escreve .env) quanto no Streamlit Cloud (lê secrets).
"""

import base64
import os
import time

import requests
import streamlit as st

TOKEN_URL = "https://www.bling.com.br/Api/v3/oauth/token"
_MARGEM_SEGUNDOS = 120  # renova 2 min antes de expirar


def _ler_env(chave: str, fallback: str = "") -> str:
    try:
        return st.secrets.get(chave, os.getenv(chave, fallback))
    except Exception:
        return os.getenv(chave, fallback)


def _renovar_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    r = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def _salvar_env(access_token: str, refresh_token: str, expires_at: int):
    """Persiste novos tokens no .env quando rodando localmente."""
    try:
        from dotenv import set_key
        set_key(".env", "BLING_ACCESS_TOKEN", access_token)
        set_key(".env", "BLING_REFRESH_TOKEN", refresh_token)
        set_key(".env", "BLING_TOKEN_EXPIRES_AT", str(expires_at))
    except Exception:
        pass  # em produção (Streamlit Cloud) não há arquivo .env para escrever


def get_bling_token() -> str:
    """
    Retorna um access token válido da Bling.
    Renova automaticamente via refresh token se estiver expirado.
    Levanta RuntimeError se não for possível obter um token.
    """
    # Usa session_state como cache intra-sessão para não fazer requests desnecessários
    if "bling_access_token" in st.session_state:
        expires_at = st.session_state.get("bling_token_expires_at", 0)
        if time.time() < expires_at - _MARGEM_SEGUNDOS:
            return st.session_state["bling_access_token"]

    client_id = _ler_env("BLING_CLIENT_ID")
    client_secret = _ler_env("BLING_CLIENT_SECRET")
    access_token = _ler_env("BLING_ACCESS_TOKEN")
    refresh_token = _ler_env("BLING_REFRESH_TOKEN")
    expires_at = int(_ler_env("BLING_TOKEN_EXPIRES_AT", "0"))

    if not client_id or not client_secret:
        raise RuntimeError("BLING_CLIENT_ID e BLING_CLIENT_SECRET não configurados.")

    if not access_token:
        raise RuntimeError(
            "BLING_ACCESS_TOKEN não encontrado. "
            "Execute `python bling_setup_oauth.py` para obter os tokens iniciais."
        )

    # Token ainda válido
    if time.time() < expires_at - _MARGEM_SEGUNDOS:
        st.session_state["bling_access_token"] = access_token
        st.session_state["bling_token_expires_at"] = expires_at
        return access_token

    # Token expirado → renova
    if not refresh_token:
        raise RuntimeError(
            "BLING_REFRESH_TOKEN não encontrado. "
            "Execute `python bling_setup_oauth.py` novamente."
        )

    try:
        tokens = _renovar_token(client_id, client_secret, refresh_token)
        novo_access = tokens["access_token"]
        novo_refresh = tokens.get("refresh_token", refresh_token)
        novo_expires_at = int(time.time()) + int(tokens.get("expires_in", 3600))

        _salvar_env(novo_access, novo_refresh, novo_expires_at)

        st.session_state["bling_access_token"] = novo_access
        st.session_state["bling_token_expires_at"] = novo_expires_at
        return novo_access
    except requests.HTTPError as e:
        raise RuntimeError(
            f"Falha ao renovar token Bling ({e.response.status_code}). "
            "Execute `python bling_setup_oauth.py` para reautorizar."
        ) from e
