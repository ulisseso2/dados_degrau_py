#!/usr/bin/env python3
# setup_fbclid_system.py
# Script para configurar todo o sistema de rastreamento de FBclids

import os
import sys
import toml
import time
import sqlite3
import subprocess
from pathlib import Path

def print_header(title):
    print("\n" + "=" * 80)
    print(f"{title}".center(80))
    print("=" * 80 + "\n")

def setup_streamlit_secrets():
    print_header("CONFIGURAÇÃO DO STREAMLIT SECRETS")
    print("Este passo configura os segredos necessários para a aplicação Streamlit.")
    
    # Cria diretório .streamlit se não existir
    streamlit_dir = Path(".streamlit")
    if not streamlit_dir.exists():
        streamlit_dir.mkdir()
        print(f"Diretório {streamlit_dir} criado.")
    
    # Cria ou atualiza o arquivo secrets.toml
    secrets_file = streamlit_dir / "secrets.toml"
    
    # Inicializa o conteúdo do arquivo
    config = {}
    
    # Verifica se o arquivo já existe
    if secrets_file.exists():
        try:
            # Carrega configuração existente
            with open(secrets_file, "r") as f:
                config = toml.load(f)
            print(f"Arquivo secrets.toml existente carregado.")
        except Exception as e:
            print(f"Erro ao ler arquivo secrets.toml: {e}")
            print("Criando novo arquivo de secrets.")
    
    # Configurações do Facebook API
    if "facebook_api" not in config:
        config["facebook_api"] = {}
    
    # Solicita informações da API do Facebook
    print("\nPara integrar com a API do Facebook, precisamos das seguintes informações:")
    print("(Pressione Enter para pular ou manter o valor atual)")
    
    fb_app_id = input(f"App ID [{config.get('facebook_api', {}).get('app_id', '')}]: ").strip()
    if fb_app_id:
        config["facebook_api"]["app_id"] = fb_app_id
    
    fb_app_secret = input(f"App Secret [{config.get('facebook_api', {}).get('app_secret', '')}]: ").strip()
    if fb_app_secret:
        config["facebook_api"]["app_secret"] = fb_app_secret
    
    fb_access_token = input(f"Access Token [{config.get('facebook_api', {}).get('access_token', '')}]: ").strip()
    if fb_access_token:
        config["facebook_api"]["access_token"] = fb_access_token
    
    fb_ad_account_id = input(f"Ad Account ID [{config.get('facebook_api', {}).get('ad_account_id', '')}]: ").strip()
    if fb_ad_account_id:
        config["facebook_api"]["ad_account_id"] = fb_ad_account_id
    
    fb_pixel_id = input(f"Pixel ID [{config.get('facebook_api', {}).get('pixel_id', '')}]: ").strip()
    if fb_pixel_id:
        config["facebook_api"]["pixel_id"] = fb_pixel_id
    
    # Configurações de usuários
    if "users" not in config:
        config["users"] = {
            "admin": {
                "password": "admin123",
                "pages": "['Página Inicial', 'Matrículas', 'Financeiro', 'Análise GA', 'Análise Facebook']"
            },
            "usuario": {
                "password": "senha123",
                "pages": "['Página Inicial', 'Matrículas']"
            }
        }
        print("\nConfiguração de usuários padrão criada:")
        print("- Usuário: admin, Senha: admin123")
        print("- Usuário: usuario, Senha: senha123")
    
    # Salva o arquivo
    try:
        with open(secrets_file, "w") as f:
            toml.dump(config, f)
        print(f"\nArquivo {secrets_file} atualizado com sucesso!")
    except Exception as e:
        print(f"Erro ao salvar arquivo secrets.toml: {e}")
        return False
    
    return True

def setup_env_file():
    print_header("CONFIGURAÇÃO DO ARQUIVO .ENV")
    print("Este passo configura as variáveis de ambiente para desenvolvimento local.")
    
    env_file = Path(".env")
    env_vars = {}
    
    # Carrega arquivo .env existente se houver
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()
        print(f"Arquivo .env existente carregado.")
    
    # Carrega informações do secrets.toml se existir
    secrets_file = Path(".streamlit/secrets.toml")
    if secrets_file.exists():
        try:
            config = toml.load(secrets_file)
            if "facebook_api" in config:
                fb_api = config["facebook_api"]
                if "app_id" in fb_api and fb_api["app_id"]:
                    env_vars["FB_APP_ID"] = fb_api["app_id"]
                if "app_secret" in fb_api and fb_api["app_secret"]:
                    env_vars["FB_APP_SECRET"] = fb_api["app_secret"]
                if "access_token" in fb_api and fb_api["access_token"]:
                    env_vars["FB_ACCESS_TOKEN"] = fb_api["access_token"]
                if "ad_account_id" in fb_api and fb_api["ad_account_id"]:
                    env_vars["FB_AD_ACCOUNT_ID"] = fb_api["ad_account_id"]
                if "pixel_id" in fb_api and fb_api["pixel_id"]:
                    env_vars["FB_PIXEL_ID"] = fb_api["pixel_id"]
            print("Informações carregadas do arquivo secrets.toml")
        except Exception as e:
            print(f"Erro ao carregar secrets.toml: {e}")
    
    # Solicita informações faltantes ou para atualizar
    print("\nPreencha as variáveis de ambiente (pressione Enter para pular ou manter o valor atual):")
    
    fb_app_id = input(f"FB_APP_ID [{env_vars.get('FB_APP_ID', '')}]: ").strip()
    if fb_app_id:
        env_vars["FB_APP_ID"] = fb_app_id
    
    fb_app_secret = input(f"FB_APP_SECRET [{env_vars.get('FB_APP_SECRET', '')}]: ").strip()
    if fb_app_secret:
        env_vars["FB_APP_SECRET"] = fb_app_secret
    
    fb_access_token = input(f"FB_ACCESS_TOKEN [{env_vars.get('FB_ACCESS_TOKEN', '')}]: ").strip()
    if fb_access_token:
        env_vars["FB_ACCESS_TOKEN"] = fb_access_token
    
    fb_ad_account_id = input(f"FB_AD_ACCOUNT_ID [{env_vars.get('FB_AD_ACCOUNT_ID', '')}]: ").strip()
    if fb_ad_account_id:
        env_vars["FB_AD_ACCOUNT_ID"] = fb_ad_account_id
    
    fb_pixel_id = input(f"FB_PIXEL_ID [{env_vars.get('FB_PIXEL_ID', '')}]: ").strip()
    if fb_pixel_id:
        env_vars["FB_PIXEL_ID"] = fb_pixel_id
    
    # Salva o arquivo .env
    try:
        with open(env_file, "w") as f:
            for key, value in env_vars.items():
                f.write(f"{key}={value}\n")
        print(f"\nArquivo {env_file} atualizado com sucesso!")
        return True
    except Exception as e:
        print(f"Erro ao salvar arquivo .env: {e}")
        return False

def init_fbclid_database():
    print_header("INICIALIZAÇÃO DO BANCO DE DADOS FBCLID")
    print("Este passo inicializa o banco de dados SQLite para armazenar FBclids.")
    
    db_file = Path("fbclid_cache.db")
    backup_dir = Path("backup")
    
    # Cria diretório de backup se não existir
    if not backup_dir.exists():
        backup_dir.mkdir()
        print(f"Diretório {backup_dir} criado.")
    
    # Verifica se o banco de dados já existe
    if db_file.exists():
        backup_file = backup_dir / f"fbclid_cache_{int(time.time())}.db"
        print(f"Banco de dados existente encontrado.")
        
        choice = input("Deseja resetar o banco de dados? (s/n): ").lower()
        if choice == 's':
            # Cria backup
            try:
                # Cria uma conexão de backup
                source = sqlite3.connect(db_file)
                backup = sqlite3.connect(backup_file)
                
                source.backup(backup)
                
                # Fecha as conexões
                source.close()
                backup.close()
                
                print(f"Backup criado em: {backup_file}")
            except Exception as e:
                print(f"Erro ao criar backup: {e}")
                return False
            
            # Reseta o banco de dados
            try:
                conn = sqlite3.connect(db_file)
                cursor = conn.cursor()
                
                # Dropa a tabela se existir
                cursor.execute("DROP TABLE IF EXISTS fbclid_cache")
                
                # Cria a nova tabela
                cursor.execute("""
                CREATE TABLE fbclid_cache (
                    fbclid TEXT PRIMARY KEY,
                    formatted_fbclid TEXT,
                    campaign_name TEXT,
                    campaign_id TEXT,
                    adset_name TEXT,
                    ad_name TEXT,
                    empresa TEXT DEFAULT 'degrau',
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
                
                conn.commit()
                conn.close()
                
                print("Banco de dados resetado com sucesso!")
            except Exception as e:
                print(f"Erro ao resetar banco de dados: {e}")
                return False
        else:
            print("Mantendo banco de dados existente.")
    else:
        # Cria novo banco de dados
        try:
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            
            # Cria a tabela
            cursor.execute("""
            CREATE TABLE fbclid_cache (
                fbclid TEXT PRIMARY KEY,
                formatted_fbclid TEXT,
                campaign_name TEXT,
                campaign_id TEXT,
                adset_name TEXT,
                ad_name TEXT,
                empresa TEXT DEFAULT 'degrau',
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            
            conn.commit()
            conn.close()
            
            print("Banco de dados criado com sucesso!")
        except Exception as e:
            print(f"Erro ao criar banco de dados: {e}")
            return False
    
    return True

def install_dependencies():
    print_header("INSTALAÇÃO DE DEPENDÊNCIAS")
    print("Este passo verifica e instala as dependências necessárias.")
    
    requirements_file = Path("requirements.txt")
    if not requirements_file.exists():
        print("Arquivo requirements.txt não encontrado.")
        return False
    
    try:
        print("Instalando dependências...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
        print("Dependências instaladas com sucesso!")
        return True
    except Exception as e:
        print(f"Erro ao instalar dependências: {e}")
        return False

def main():
    print_header("CONFIGURAÇÃO DO SISTEMA DE RASTREAMENTO DE FBCLIDS")
    print("Este script irá configurar todo o ambiente necessário para o sistema de rastreamento de FBclids.")
    
    steps = [
        ("Instalar dependências", install_dependencies),
        ("Configurar secrets do Streamlit", setup_streamlit_secrets),
        ("Configurar arquivo .env", setup_env_file),
        ("Inicializar banco de dados", init_fbclid_database)
    ]
    
    # Executa cada etapa
    for i, (step_name, step_func) in enumerate(steps, 1):
        print(f"\n[Passo {i}/{len(steps)}] {step_name}")
        
        if step_func():
            print(f"✅ {step_name} concluído com sucesso!")
        else:
            print(f"❌ {step_name} falhou.")
            retry = input("Deseja tentar novamente? (s/n): ").lower()
            if retry == 's':
                if step_func():
                    print(f"✅ {step_name} concluído com sucesso na segunda tentativa!")
                else:
                    print(f"❌ {step_name} falhou novamente. Continuando com os próximos passos...")
            else:
                print("Continuando com os próximos passos...")
    
    print_header("CONFIGURAÇÃO CONCLUÍDA")
    print("""
O sistema de rastreamento de FBclids foi configurado com sucesso!

Para executar a aplicação, use o comando:
    streamlit run main.py

Para consultar campanhas do Facebook:
1. Acesse a página "Análise de Campanhas - Meta (Facebook Ads)"
2. Na seção "Auditoria de Conversões com FBCLID", clique no botão "Consultar Campanhas no Facebook"

Para mais informações, consulte o arquivo FBCLID_RASTREAMENTO.md
    """)

if __name__ == "__main__":
    main()
