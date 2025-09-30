#!/usr/bin/env python3
# configure_pixel_id.py
# Script para configurar o Pixel ID do Facebook para uso com a API de Conversões

import os
import sys
from dotenv import load_dotenv
import json

# Carrega variáveis de ambiente
load_dotenv()

def print_header():
    print("=" * 80)
    print("          CONFIGURAÇÃO DO PIXEL ID DO FACEBOOK")
    print("=" * 80)
    print("\nEste script configura o Pixel ID do Facebook para uso com a API de Conversões.")
    print("O Pixel ID é necessário para consultar informações de campanhas a partir de FBclids.")
    print("Você pode encontrar o Pixel ID no Facebook Business Manager > Eventos > Pixel.")
    print("\n")

def check_existing_pixel_id():
    # Verifica se já existe um Pixel ID configurado
    pixel_id = os.getenv("FB_PIXEL_ID")
    
    if pixel_id:
        print(f"Pixel ID atual: {pixel_id}")
        return pixel_id
    else:
        print("Nenhum Pixel ID configurado.")
        return None

def update_env_file(pixel_id):
    # Atualiza o arquivo .env com o Pixel ID
    try:
        env_file = ".env"
        env_content = ""
        
        # Lê o conteúdo atual do arquivo .env se existir
        if os.path.exists(env_file):
            with open(env_file, "r") as f:
                env_content = f.read()
        
        # Verifica se FB_PIXEL_ID já existe no arquivo
        if "FB_PIXEL_ID" in env_content:
            # Substitui a linha existente
            lines = env_content.splitlines()
            new_lines = []
            
            for line in lines:
                if line.startswith("FB_PIXEL_ID="):
                    new_lines.append(f"FB_PIXEL_ID={pixel_id}")
                else:
                    new_lines.append(line)
            
            env_content = "\n".join(new_lines)
        else:
            # Adiciona nova linha
            if env_content and not env_content.endswith("\n"):
                env_content += "\n"
            
            env_content += f"FB_PIXEL_ID={pixel_id}\n"
        
        # Escreve o conteúdo de volta ao arquivo
        with open(env_file, "w") as f:
            f.write(env_content)
        
        print(f"Arquivo .env atualizado com o Pixel ID: {pixel_id}")
        return True
    
    except Exception as e:
        print(f"Erro ao atualizar arquivo .env: {e}")
        return False

def update_secrets_toml(pixel_id):
    # Atualiza o arquivo .streamlit/secrets.toml com o Pixel ID
    try:
        secrets_dir = ".streamlit"
        secrets_file = os.path.join(secrets_dir, "secrets.toml")
        
        # Garante que o diretório .streamlit existe
        if not os.path.exists(secrets_dir):
            os.makedirs(secrets_dir)
        
        # Lê o conteúdo atual do arquivo secrets.toml se existir
        secrets_content = ""
        if os.path.exists(secrets_file):
            with open(secrets_file, "r") as f:
                secrets_content = f.read()
        
        # Verifica se a seção [facebook_api] já existe
        if "[facebook_api]" in secrets_content:
            # Substitui a linha existente
            lines = secrets_content.splitlines()
            in_facebook_section = False
            has_pixel_id = False
            new_lines = []
            
            for line in lines:
                if line.strip() == "[facebook_api]":
                    in_facebook_section = True
                    new_lines.append(line)
                elif in_facebook_section and line.startswith("pixel_id"):
                    new_lines.append(f'pixel_id = "{pixel_id}"')
                    has_pixel_id = True
                elif line.strip().startswith("[") and line.strip().endswith("]") and line.strip() != "[facebook_api]":
                    # Se encontramos outra seção e ainda não adicionamos o pixel_id
                    if in_facebook_section and not has_pixel_id:
                        new_lines.append(f'pixel_id = "{pixel_id}"')
                    in_facebook_section = False
                    new_lines.append(line)
                else:
                    new_lines.append(line)
            
            # Se ainda estamos na seção facebook_api e não adicionamos o pixel_id
            if in_facebook_section and not has_pixel_id:
                new_lines.append(f'pixel_id = "{pixel_id}"')
            
            secrets_content = "\n".join(new_lines)
        else:
            # Adiciona nova seção
            if secrets_content and not secrets_content.endswith("\n"):
                secrets_content += "\n\n"
            else:
                secrets_content += "\n"
            
            secrets_content += "[facebook_api]\n"
            secrets_content += f'pixel_id = "{pixel_id}"\n'
        
        # Escreve o conteúdo de volta ao arquivo
        with open(secrets_file, "w") as f:
            f.write(secrets_content)
        
        print(f"Arquivo {secrets_file} atualizado com o Pixel ID: {pixel_id}")
        return True
    
    except Exception as e:
        print(f"Erro ao atualizar arquivo secrets.toml: {e}")
        return False

def main():
    print_header()
    
    # Verifica se já existe um Pixel ID configurado
    existing_pixel_id = check_existing_pixel_id()
    
    # Solicita o Pixel ID
    if existing_pixel_id:
        response = input(f"\nDeseja atualizar o Pixel ID atual ({existing_pixel_id})? (s/n): ")
        if response.lower() != 's':
            print("Configuração mantida. Saindo...")
            return
    
    pixel_id = input("\nDigite o Pixel ID do Facebook: ").strip()
    
    if not pixel_id:
        print("Nenhum Pixel ID fornecido. Saindo...")
        return
    
    # Atualiza o arquivo .env
    env_updated = update_env_file(pixel_id)
    
    # Atualiza o arquivo .streamlit/secrets.toml
    secrets_updated = update_secrets_toml(pixel_id)
    
    if env_updated or secrets_updated:
        print("\nPixel ID configurado com sucesso!")
        print("\nPróximos passos:")
        print("1. Execute o script migrate_fbclid_format.py para migrar os FBclids existentes")
        print("2. Reinicie a aplicação Streamlit para aplicar as alterações")
        print("3. Teste a consulta de campanhas na dashboard")
    else:
        print("\nFalha ao configurar o Pixel ID. Verifique os erros acima.")

if __name__ == "__main__":
    main()
