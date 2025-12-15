"""
Script para gerar cache particionado por ano do backup central.
Executa uma vez e gera arquivos parquet por ano para versionamento.
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
from pathlib import Path
from utils.sql_loader import carregar_dados_secundario

# Diretório para os arquivos de cache
CACHE_DIR = Path(__file__).parent.parent / "data_cache" / "central_backup"

def gerar_cache_particionado():
    """
    Carrega dados do banco e particiona por ano em arquivos Parquet.
    Arquivos Parquet são compactados e eficientes.
    """
    print("🔄 Carregando dados do banco...")
    df = carregar_dados_secundario("consultas/consys/central_backup.sql")
    
    if df.empty:
        print("❌ Nenhum dado carregado")
        return
    
    print(f"✅ Carregados {len(df):,} registros")
    
    # Converte data para datetime
    df['data'] = pd.to_datetime(df['data'], errors='coerce')
    
    # Cria diretório se não existir
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Particiona por ano
    anos = df['data'].dt.year.dropna().unique()
    anos_sorted = sorted([int(ano) for ano in anos])
    
    print(f"\n📊 Particionando dados por ano...")
    total_size = 0
    
    for ano in anos_sorted:
        df_ano = df[df['data'].dt.year == ano].copy()
        
        # Converte data para string para serialização
        df_ano['data'] = df_ano['data'].dt.strftime('%Y-%m-%d')
        
        # Salva em Parquet (compactado)
        arquivo = CACHE_DIR / f"{ano}.parquet"
        df_ano.to_parquet(arquivo, compression='gzip', index=False)
        
        tamanho = arquivo.stat().st_size / (1024 * 1024)  # MB
        total_size += tamanho
        
        print(f"  ✅ {ano}: {len(df_ano):,} registros → {tamanho:.2f} MB")
    
    print(f"\n💾 Total: {total_size:.2f} MB em {len(anos_sorted)} arquivos")
    print(f"📁 Salvos em: {CACHE_DIR}")
    
    # Cria arquivo de metadados
    metadata = {
        'total_registros': len(df),
        'anos': anos_sorted,
        'data_geracao': pd.Timestamp.now().isoformat()
    }
    
    import json
    with open(CACHE_DIR / 'metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\n✅ Cache gerado com sucesso!")

if __name__ == "__main__":
    gerar_cache_particionado()
