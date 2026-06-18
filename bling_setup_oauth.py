"""
Rode este script UMA VEZ para obter os tokens OAuth da Bling.

Pré-requisito: configure http://localhost:8888/callback como URL de redirecionamento
no painel Bling → Configurações → API → seu aplicativo.

Uso:
    python bling_setup_oauth.py
"""

import base64
import os
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv, set_key

load_dotenv()

CLIENT_ID = os.getenv("BLING_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("BLING_CLIENT_SECRET", "")
REDIRECT_URI = "http://localhost:8888/callback"
AUTH_URL = "https://www.bling.com.br/Api/v3/oauth/authorize"
TOKEN_URL = "https://www.bling.com.br/Api/v3/oauth/token"
ENV_FILE = ".env"

_code_received = None
_state_esperado = secrets.token_hex(16)


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _code_received
        parsed = urlparse(self.path)
        if parsed.path == "/callback":
            params = parse_qs(parsed.query)
            state = params.get("state", [""])[0]
            code = params.get("code", [""])[0]

            if state != _state_esperado:
                self._responder(400, "State inválido. Tente novamente.")
                return

            if code:
                _code_received = code
                self._responder(200, "✅ Autorização recebida! Pode fechar esta aba.")
            else:
                erro = params.get("error_description", params.get("error", ["desconhecido"]))[0]
                self._responder(400, f"Erro da Bling: {erro}")
        else:
            self._responder(404, "Página não encontrada.")

    def _responder(self, status, mensagem):
        body = f"<html><body><h2>{mensagem}</h2></body></html>".encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # silencia logs do servidor


def trocar_codigo_por_tokens(code: str) -> dict:
    credentials = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    r = requests.post(TOKEN_URL, headers=headers, data=data, timeout=15)
    r.raise_for_status()
    return r.json()


def salvar_tokens(tokens: dict):
    access_token = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")
    expires_in = tokens.get("expires_in", 3600)
    expires_at = int(time.time()) + int(expires_in)

    set_key(ENV_FILE, "BLING_ACCESS_TOKEN", access_token)
    set_key(ENV_FILE, "BLING_REFRESH_TOKEN", refresh_token)
    set_key(ENV_FILE, "BLING_TOKEN_EXPIRES_AT", str(expires_at))
    print(f"✅ Tokens salvos no .env (expira em {expires_in}s)")


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("❌ BLING_CLIENT_ID e BLING_CLIENT_SECRET precisam estar no .env")
        return

    params = urlencode({
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "state": _state_esperado,
    })
    url_auth = f"{AUTH_URL}?{params}"

    servidor = HTTPServer(("localhost", 8888), CallbackHandler)
    t = threading.Thread(target=servidor.serve_forever, daemon=True)
    t.start()

    print("🌐 Abrindo navegador para autorização Bling...")
    print(f"   Se não abrir automaticamente, acesse:\n   {url_auth}\n")
    webbrowser.open(url_auth)

    print("⏳ Aguardando callback em http://localhost:8888/callback ...")
    timeout = 120
    inicio = time.time()
    while _code_received is None and (time.time() - inicio) < timeout:
        time.sleep(0.5)

    servidor.shutdown()

    if _code_received is None:
        print("❌ Tempo esgotado. Tente novamente.")
        return

    print("🔄 Trocando código por tokens...")
    try:
        tokens = trocar_codigo_por_tokens(_code_received)
        salvar_tokens(tokens)
        print("🎉 Configuração concluída! Agora pode rodar o Streamlit normalmente.")
    except requests.HTTPError as e:
        print(f"❌ Erro ao trocar tokens: {e.response.status_code} — {e.response.text}")


if __name__ == "__main__":
    main()
