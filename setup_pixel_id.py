#!/usr/bin/env python3
# setup_pixel_id.py
# Script para configuração rápida do Pixel ID

import os
import sys
from pathlib import Path

def setup_pixel_id():
    print("=" * 80)
    print(" CONFIGURAÇÃO RÁPIDA DO PIXEL ID DO FACEBOOK")
    print("=" * 80)
    print("\nEste script irá configurar o Pixel ID para uso com a API de Conversões.\n")
    
    # Solicita o Pixel ID
    pixel_id = input("Digite o Pixel ID do Facebook: ").strip()
    
    if not pixel_id:
        print("Nenhum Pixel ID fornecido. Saindo...")
        return
    
    # Cria diretório .streamlit se não existir
    streamlit_dir = Path(".streamlit")
    if not streamlit_dir.exists():
        streamlit_dir.mkdir()
    
    # Cria ou atualiza o arquivo secrets.toml
    secrets_file = streamlit_dir / "secrets.toml"
    
    # Verifica se o arquivo já existe
    if secrets_file.exists():
        with open(secrets_file, "r") as f:
            content = f.read()
        
        # Verifica se já tem a seção [facebook_api]
        if "[facebook_api]" in content:
            # Verifica se já tem a linha do pixel_id
            lines = content.splitlines()
            in_facebook_section = False
            has_pixel = False
            new_lines = []
            
            for line in lines:
                if line.strip() == "[facebook_api]":
                    in_facebook_section = True
                    new_lines.append(line)
                elif in_facebook_section and line.strip().startswith("pixel_id"):
                    new_lines.append(f'pixel_id = "{pixel_id}"')
                    has_pixel = True
                elif line.strip().startswith("[") and line.strip() != "[facebook_api]":
                    if in_facebook_section and not has_pixel:
                        new_lines.append(f'pixel_id = "{pixel_id}"')
                    in_facebook_section = False
                    new_lines.append(line)
                else:
                    new_lines.append(line)
            
            if in_facebook_section and not has_pixel:
                new_lines.append(f'pixel_id = "{pixel_id}"')
                
            content = "\n".join(new_lines)
        else:
            # Adiciona a seção [facebook_api]
            if content and not content.endswith("\n"):
                content += "\n\n"
            else:
                content += "\n"
            
            content += "[facebook_api]\n"
            content += f'pixel_id = "{pixel_id}"\n'
        
        # Verifica se tem a seção [users]
        if "[users]" not in content:
            content += "\n[users]\n"
            content += '[users.admin]\n'
            content += 'password = "admin123"\n'
            content += 'pages = "[\'Página Inicial\', \'Matrículas\', \'Financeiro\', \'Análise GA\', \'Análise Facebook\']"\n'
            content += '\n[users.usuario]\n'
            content += 'password = "senha123"\n'
            content += 'pages = "[\'Página Inicial\', \'Matrículas\']"\n'
    else:
        # Cria um novo arquivo
        content = "[facebook_api]\n"
        content += f'pixel_id = "{pixel_id}"\n\n'
        content += "[users]\n"
        content += '[users.admin]\n'
        content += 'password = "admin123"\n'
        content += 'pages = "[\'Página Inicial\', \'Matrículas\', \'Financeiro\', \'Análise GA\', \'Análise Facebook\']"\n'
        content += '\n[users.usuario]\n'
        content += 'password = "senha123"\n'
        content += 'pages = "[\'Página Inicial\', \'Matrículas\']"\n'
    
    # Salva o arquivo
    with open(secrets_file, "w") as f:
        f.write(content)
    
    # Também salva no .env para uso local
    env_file = Path(".env")
    if env_file.exists():
        # Lê o conteúdo atual
        with open(env_file, "r") as f:
            env_content = f.read()
        
        # Verifica se FB_PIXEL_ID já existe
        if "FB_PIXEL_ID=" in env_content:
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
            
        with open(env_file, "w") as f:
            f.write(env_content)
    else:
        # Cria arquivo .env
        with open(env_file, "w") as f:
            f.write(f"FB_PIXEL_ID={pixel_id}\n")
    
    print(f"\nPixel ID '{pixel_id}' configurado com sucesso!")
    print("\nOs seguintes arquivos foram atualizados:")
    print(f"- {secrets_file.absolute()}")
    print(f"- {env_file.absolute()}")
    
    print("\nAgora você pode executar a análise do Facebook e consultar campanhas.")

if __name__ == "__main__":
    setup_pixel_id()
