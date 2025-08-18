#!/bin/bash
# Script para inicializar e configurar a infraestrutura de FBclids

echo "=== CONFIGURAÇÃO DO SISTEMA DE FBCLID ==="
echo "Iniciando configuração..."

# Verifica se o Python está instalado
if ! command -v python3 &> /dev/null; then
    echo "ERRO: Python 3 não está instalado. Por favor, instale o Python 3 antes de continuar."
    exit 1
fi

# Verifica as dependências necessárias
echo -e "\n1. Verificando dependências..."
python3 -c "import sqlite3, pandas, streamlit, facebook_business" 2>/dev/null || {
    echo "AVISO: Algumas dependências Python estão faltando."
    echo "Instalando dependências necessárias..."
    pip install pandas streamlit facebook-business python-dotenv
}

# Executa o script de migração do banco de dados
echo -e "\n2. Configurando banco de dados de FBclids..."
python3 check_fbclid_migration.py

# Verifica se o arquivo .env existe
echo -e "\n3. Verificando configuração de ambiente..."
if [ ! -f .env ]; then
    echo "AVISO: Arquivo .env não encontrado."
    echo "Criando arquivo .env com base no template..."
    cp .env-example .env
    echo "Por favor, edite o arquivo .env com suas credenciais do Facebook."
fi

echo -e "\n=== CONFIGURAÇÃO CONCLUÍDA ==="
echo "Para obter um token de acesso de longa duração do Facebook, execute:"
echo "python3 generate_facebook_refresh_token.py --token <seu-token-de-curta-duração>"
echo ""
echo "Para começar a usar o sistema, execute:"
echo "streamlit run main.py"
echo ""
