#!/bin/bash

# Script para Renovar Token do Facebook
# Este script facilita o processo de renovação do token de acesso do Facebook

echo "=========================================="
echo "  Renovação de Token do Facebook"
echo "=========================================="
echo ""

# Verifica se o token de curta duração foi fornecido
if [ -z "$1" ]; then
    echo "❌ Erro: Token de curta duração não fornecido"
    echo ""
    echo "Como usar:"
    echo "  ./renovar_token_facebook.sh SEU_TOKEN_DE_CURTA_DURACAO"
    echo ""
    echo "📝 Passos para obter o token de curta duração:"
    echo "  1. Acesse: https://developers.facebook.com/tools/explorer/"
    echo "  2. Selecione seu aplicativo"
    echo "  3. Clique em 'Gerar Token de Acesso'"
    echo "  4. Selecione as permissões necessárias:"
    echo "     - ads_management"
    echo "     - ads_read"
    echo "     - business_management"
    echo "     - pages_read_engagement"
    echo "  5. Copie o token gerado"
    echo "  6. Execute: ./renovar_token_facebook.sh TOKEN_COPIADO"
    echo ""
    exit 1
fi

SHORT_TOKEN="$1"

# Carrega as credenciais do arquivo .env
if [ -f ".facebook_credentials.env" ]; then
    export $(grep -v '^#' .facebook_credentials.env | xargs)
else
    echo "❌ Erro: Arquivo .facebook_credentials.env não encontrado"
    exit 1
fi

echo "🔄 Trocando token de curta duração por token de longa duração..."
echo ""

# Faz a requisição para trocar o token
RESPONSE=$(curl -s -G \
  -d "grant_type=fb_exchange_token" \
  -d "client_id=$FB_APP_ID" \
  -d "client_secret=$FB_APP_SECRET" \
  -d "fb_exchange_token=$SHORT_TOKEN" \
  "https://graph.facebook.com/v18.0/oauth/access_token")

# Verifica se houve erro
if echo "$RESPONSE" | grep -q "error"; then
    echo "❌ Erro na requisição:"
    echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
    echo ""
    echo "Verifique se:"
    echo "  - O token de curta duração está correto"
    echo "  - O token não expirou (válido por poucas horas)"
    echo "  - As credenciais no .facebook_credentials.env estão corretas"
    exit 1
fi

# Extrai o novo token
NEW_TOKEN=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null)

if [ -z "$NEW_TOKEN" ]; then
    echo "❌ Erro: Não foi possível extrair o token da resposta"
    echo "$RESPONSE"
    exit 1
fi

echo "✅ Token de longa duração gerado com sucesso!"
echo ""
echo "=========================================="
echo "  Novo Token (válido por ~60 dias):"
echo "=========================================="
echo ""
echo "$NEW_TOKEN"
echo ""
echo "=========================================="
echo ""

# Atualiza o arquivo .facebook_credentials.env
echo "🔄 Atualizando arquivo .facebook_credentials.env..."

# Cria backup do arquivo atual
cp .facebook_credentials.env .facebook_credentials.env.backup_$(date +%Y%m%d_%H%M%S)

# Atualiza o token no arquivo
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    sed -i '' "s|^FB_ACCESS_TOKEN=.*|FB_ACCESS_TOKEN=$NEW_TOKEN|" .facebook_credentials.env
else
    # Linux
    sed -i "s|^FB_ACCESS_TOKEN=.*|FB_ACCESS_TOKEN=$NEW_TOKEN|" .facebook_credentials.env
fi

echo "✅ Arquivo .facebook_credentials.env atualizado!"
echo "📦 Backup criado com sucesso"
echo ""

# Verifica se o token está funcionando
echo "🔍 Verificando se o novo token está funcionando..."
echo ""

python3 << EOF
import requests
import os

token = "$NEW_TOKEN"
url = "https://graph.facebook.com/v18.0/me"
params = {"access_token": token}

try:
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Token validado com sucesso!")
        print(f"   Usuário: {data.get('name', 'N/A')}")
        print(f"   ID: {data.get('id', 'N/A')}")
    else:
        print(f"⚠️  Aviso: Status {response.status_code}")
        print(f"   {response.text}")
except Exception as e:
    print(f"⚠️  Erro na validação: {e}")
EOF

echo ""
echo "=========================================="
echo "  ⏰ LEMBRETE IMPORTANTE"
echo "=========================================="
echo ""
echo "Este token expira em aproximadamente 60 dias."
echo "Data de expiração estimada: $(date -d '+60 days' '+%d/%m/%Y' 2>/dev/null || date -v+60d '+%d/%m/%Y' 2>/dev/null || echo 'Calcule manualmente')"
echo ""
echo "Configure um lembrete para renovar novamente!"
echo ""
echo "✅ Processo concluído com sucesso!"
