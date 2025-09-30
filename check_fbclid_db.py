#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Este script verifica a estrutura do banco de dados de FBclids
e cria as tabelas necessárias se não existirem.

Também oferece opções para:
1. Verificar a estrutura do banco de dados
2. Listar os FBclids armazenados
3. Testar a formatação de FBclids
4. Exportar FBclids para CSV

Uso:
    python check_fbclid_db.py
"""

import os
import sys
import sqlite3
import pandas as pd
from datetime import datetime
import json

# Configurações
DB_FILE = "fbclid_cache.db"
TEST_FBCLID = "test_12345"

def create_colored_text(text, color_code):
    """Retorna o texto com a cor especificada para o terminal"""
    return f"\033[{color_code}m{text}\033[0m"

def red(text):
    return create_colored_text(text, 31)

def green(text):
    return create_colored_text(text, 32)

def yellow(text):
    return create_colored_text(text, 33)

def blue(text):
    return create_colored_text(text, 34)

def print_header(text):
    """Imprime um cabeçalho formatado"""
    print("\n" + "=" * 80)
    print(blue(text.center(80)))
    print("=" * 80)

def check_db_structure(db_file=DB_FILE):
    """Verifica a estrutura do banco de dados e cria as tabelas se não existirem"""
    print_header("VERIFICANDO ESTRUTURA DO BANCO DE DADOS")
    
    # Verifica se o arquivo existe
    if not os.path.exists(db_file):
        print(yellow(f"O arquivo {db_file} não existe. Será criado."))
    else:
        print(green(f"O arquivo {db_file} existe."))
        # Verifica o tamanho
        size_bytes = os.path.getsize(db_file)
        size_kb = size_bytes / 1024
        print(f"Tamanho: {size_kb:.2f} KB ({size_bytes} bytes)")
    
    # Conecta ao banco de dados
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # Lista as tabelas existentes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    print("\nTabelas encontradas:")
    for table in tables:
        print(f"- {table[0]}")
    
    # Verifica se a tabela fbclid_cache existe
    fbclid_table_exists = any(table[0] == "fbclid_cache" for table in tables)
    
    if not fbclid_table_exists:
        print(yellow("\nA tabela fbclid_cache não existe. Criando..."))
        
        # Cria a tabela
        cursor.execute('''
        CREATE TABLE fbclid_cache (
            fbclid TEXT PRIMARY KEY,
            campaign_name TEXT,
            campaign_id TEXT,
            adset_name TEXT,
            ad_name TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        conn.commit()
        print(green("Tabela fbclid_cache criada com sucesso."))
    else:
        # Verifica a estrutura da tabela
        cursor.execute("PRAGMA table_info(fbclid_cache)")
        columns = cursor.fetchall()
        
        print("\nEstrutura da tabela fbclid_cache:")
        for col in columns:
            print(f"- {col[1]} ({col[2]}){' PRIMARY KEY' if col[5] == 1 else ''}")
    
    # Conta registros na tabela
    if fbclid_table_exists:
        cursor.execute("SELECT COUNT(*) FROM fbclid_cache")
        count = cursor.fetchone()[0]
        print(f"\nTotal de registros na tabela fbclid_cache: {count}")
        
        # Exemplo de registros
        if count > 0:
            cursor.execute("SELECT * FROM fbclid_cache LIMIT 3")
            examples = cursor.fetchall()
            
            print("\nExemplos de registros:")
            for i, ex in enumerate(examples):
                print(f"Registro {i+1}:")
                for j, col in enumerate(columns):
                    print(f"  {col[1]}: {ex[j]}")
    
    conn.close()
    return fbclid_table_exists

def list_fbclids(db_file=DB_FILE, limit=10):
    """Lista os FBclids armazenados no banco de dados"""
    print_header(f"LISTANDO FBCLIDS (LIMITE: {limit})")
    
    if not os.path.exists(db_file):
        print(red(f"O arquivo {db_file} não existe."))
        return False
    
    # Conecta ao banco de dados
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # Verifica se a tabela fbclid_cache existe
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fbclid_cache'")
    if not cursor.fetchone():
        print(red("A tabela fbclid_cache não existe."))
        conn.close()
        return False
    
    # Conta registros na tabela
    cursor.execute("SELECT COUNT(*) FROM fbclid_cache")
    count = cursor.fetchone()[0]
    print(f"Total de registros na tabela fbclid_cache: {count}")
    
    if count == 0:
        print(yellow("A tabela está vazia."))
        conn.close()
        return True
    
    # Lista os FBclids mais recentes
    cursor.execute("""
    SELECT fbclid, campaign_name, campaign_id, last_updated
    FROM fbclid_cache
    ORDER BY last_updated DESC
    LIMIT ?
    """, (limit,))
    
    rows = cursor.fetchall()
    
    print("\nFBclids mais recentes:")
    for i, row in enumerate(rows):
        print(f"{i+1}. {row[0]}")
        print(f"   Campanha: {row[1]}")
        print(f"   ID da Campanha: {row[2]}")
        print(f"   Atualizado em: {row[3]}")
    
    # Estatísticas básicas
    cursor.execute("SELECT COUNT(*) FROM fbclid_cache WHERE campaign_name != 'Não encontrado' AND campaign_name NOT LIKE 'Erro:%'")
    found_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM fbclid_cache WHERE campaign_name = 'Não encontrado'")
    not_found_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM fbclid_cache WHERE campaign_name LIKE 'Erro:%'")
    error_count = cursor.fetchone()[0]
    
    print("\nEstatísticas:")
    print(f"- Campanhas encontradas: {found_count} ({found_count/count*100:.1f}%)")
    print(f"- Não encontrados: {not_found_count} ({not_found_count/count*100:.1f}%)")
    print(f"- Erros: {error_count} ({error_count/count*100:.1f}%)")
    
    conn.close()
    return True

def test_fbclid_formatting(fbclid=TEST_FBCLID):
    """Testa a formatação de FBclids"""
    print_header("TESTANDO FORMATAÇÃO DE FBCLIDS")
    
    # Importa a função format_fbclid
    try:
        # Tenta importar do módulo fbclid_db
        from fbclid_db import format_fbclid
        print(green("Função format_fbclid importada do módulo fbclid_db."))
    except ImportError:
        # Se não conseguir, usa a versão definida no arquivo test_fbclid_api.py
        try:
            from test_fbclid_api import format_fbclid
            print(green("Função format_fbclid importada do módulo test_fbclid_api."))
        except ImportError:
            # Se não conseguir, define uma versão básica
            print(yellow("Não foi possível importar a função format_fbclid. Usando versão local."))
            
            def format_fbclid(fbclid_raw, created_at=None):
                """Versão local de format_fbclid"""
                if fbclid_raw is None or fbclid_raw == "":
                    return None
                
                # Verifica se já está no formato correto (fb.1.timestamp.fbclid)
                import re
                if re.match(r'^fb\.\d+\.\d+\.', fbclid_raw):
                    return fbclid_raw
                
                # Usa o timestamp atual
                import time
                timestamp = int(time.time())
                
                # Formata o FBclid
                return f"fb.1.{timestamp}.{fbclid_raw}"
    
    # Testa com alguns FBclids
    test_cases = [
        fbclid,
        f"fbclid_{int(datetime.now().timestamp())}",
        "fb.1.1672531200.sample",
        "",
        None
    ]
    
    for i, test_case in enumerate(test_cases):
        print(f"\nCaso de teste {i+1}: {test_case}")
        try:
            formatted = format_fbclid(test_case)
            print(green(f"Formatado: {formatted}"))
        except Exception as e:
            print(red(f"Erro: {str(e)}"))
    
    # Testa com data de criação
    print("\nTestando com data de criação:")
    try:
        from datetime import datetime, timedelta
        
        # Data atual
        now = datetime.now()
        formatted = format_fbclid(fbclid, now)
        print(f"Com data atual: {formatted}")
        
        # Data passada (7 dias atrás)
        past_date = now - timedelta(days=7)
        formatted = format_fbclid(fbclid, past_date)
        print(f"Com data de 7 dias atrás: {formatted}")
        
        # Data futura (1 dia à frente)
        future_date = now + timedelta(days=1)
        formatted = format_fbclid(fbclid, future_date)
        print(f"Com data de 1 dia à frente: {formatted}")
        
    except Exception as e:
        print(red(f"Erro ao testar com data de criação: {str(e)}"))
    
    return True

def export_fbclids_to_csv(db_file=DB_FILE, output_file="fbclids_export.csv"):
    """Exporta os FBclids para um arquivo CSV"""
    print_header("EXPORTANDO FBCLIDS PARA CSV")
    
    if not os.path.exists(db_file):
        print(red(f"O arquivo {db_file} não existe."))
        return False
    
    # Conecta ao banco de dados
    try:
        conn = sqlite3.connect(db_file)
        
        # Verifica se a tabela fbclid_cache existe
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fbclid_cache'")
        if not cursor.fetchone():
            print(red("A tabela fbclid_cache não existe."))
            conn.close()
            return False
        
        # Carrega os dados para um DataFrame
        df = pd.read_sql_query("SELECT * FROM fbclid_cache", conn)
        
        # Fecha a conexão
        conn.close()
        
        # Verifica se tem registros
        if df.empty:
            print(yellow("A tabela não contém registros."))
            return False
        
        # Exporta para CSV
        df.to_csv(output_file, index=False)
        
        print(green(f"Dados exportados com sucesso para {output_file}"))
        print(f"Total de registros exportados: {len(df)}")
        
        return True
    
    except Exception as e:
        print(red(f"Erro ao exportar dados: {str(e)}"))
        return False

def main():
    print("=" * 80)
    print(blue("VERIFICAÇÃO DO BANCO DE DADOS DE FBCLIDS".center(80)))
    print("=" * 80)
    print(f"Data/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Arquivo de banco de dados: {DB_FILE}")
    
    # Menu de opções
    while True:
        print("\nEscolha uma opção:")
        print("1. Verificar estrutura do banco de dados")
        print("2. Listar FBclids armazenados")
        print("3. Testar formatação de FBclids")
        print("4. Exportar FBclids para CSV")
        print("0. Sair")
        
        choice = input("\nDigite sua escolha (0-4): ")
        
        if choice == "0":
            print("Encerrando o programa...")
            break
        elif choice == "1":
            check_db_structure()
        elif choice == "2":
            limit = input("Digite o limite de registros a mostrar (padrão: 10): ")
            try:
                limit = int(limit) if limit.strip() else 10
                list_fbclids(limit=limit)
            except ValueError:
                print(red("Valor inválido. Usando o padrão."))
                list_fbclids()
        elif choice == "3":
            fbclid = input(f"Digite um FBclid para testar (padrão: {TEST_FBCLID}): ")
            fbclid = fbclid.strip() if fbclid.strip() else TEST_FBCLID
            test_fbclid_formatting(fbclid)
        elif choice == "4":
            output_file = input("Digite o nome do arquivo de saída (padrão: fbclids_export.csv): ")
            output_file = output_file.strip() if output_file.strip() else "fbclids_export.csv"
            export_fbclids_to_csv(output_file=output_file)
        else:
            print(red("Opção inválida. Tente novamente."))

if __name__ == "__main__":
    main()
