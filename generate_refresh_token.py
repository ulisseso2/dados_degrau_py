# generate_refresh_token.py
import argparse
import google.oauth2.credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Escopos necessários para a API do Google Ads.
SCOPES = ["https://www.googleapis.com/auth/adwords"]

def main(client_id, client_secret):
    """Gera e imprime um refresh_token para a API do Google Ads."""
    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://accounts.google.com/o/oauth2/token",
            }
        },
        SCOPES,
    )

    # Inicia o fluxo de autenticação no navegador
    credentials = flow.run_local_server(port=0)

    # Imprime o resultado final
    print("\nGuarde este token em um local seguro. Ele é necessário para configurar sua aplicação.")
    print(f"Refresh token: '{credentials.refresh_token}'")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Gera um refresh token para a API do Google Ads."
    )
    parser.add_argument(
        "--client_id", required=True, help="O Client ID do seu projeto no Google Cloud."
    )
    parser.add_argument(
        "--client_secret", required=True, help="O Client Secret do seu projeto no Google Cloud."
    )
    args = parser.parse_args()

    main(args.client_id, args.client_secret)