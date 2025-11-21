import sys
import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Adicionar o diretório raiz ao sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.processar_transcricoes import ler_transcricoes
from scripts.extrair_informacoes_llm import extrair_informacoes_llm
from scripts.analisar_dados import salvar_analises

def main():
    """
    Pipeline de teste - processa apenas 3 transcrições para validação.
    """
    pasta_transcricoes = "consultas/telefonia"
    caminho_saida = "consultas/resultados/analises_teste.csv"
    num_teste = 3  # Número de transcrições para testar

    provider = os.getenv("LLM_PROVIDER", "auto")
    
    print("=" * 60)
    print("TESTE DO PIPELINE - Processando apenas 3 transcrições")
    print("=" * 60)
    
    # Etapa 1: Ler transcrições
    print(f"\n[1/3] Lendo transcrições de {pasta_transcricoes}...")
    todas_transcricoes = ler_transcricoes(pasta_transcricoes)
    transcricoes = todas_transcricoes[:num_teste]
    print(f"✓ Selecionadas {len(transcricoes)} de {len(todas_transcricoes)} transcrições para teste")
    
    for i, t in enumerate(transcricoes, 1):
        print(f"  {i}. {t['arquivo']}")

    # Etapa 2: Extrair informações com LLM
    print(f"\n[2/3] Extraindo informações com LLM (provider: {provider})...")
    dados_estruturados = extrair_informacoes_llm(transcricoes, provider=provider)
    print(f"✓ {len(dados_estruturados)} transcrições processadas")

    # Etapa 3: Salvar análises
    print(f"\n[3/3] Salvando análises de teste em {caminho_saida}...")
    salvar_analises(dados_estruturados, caminho_saida)

    # Mostrar resultados
    print("\n" + "=" * 60)
    print("RESULTADOS DO TESTE:")
    print("=" * 60)
    
    import pandas as pd
    df = pd.read_csv(caminho_saida)
    print(df.to_string())
    
    print("\n" + "=" * 60)
    print("✓ Teste concluído com sucesso!")
    print("=" * 60)
    print(f"\nSe os resultados parecerem bons, execute o pipeline completo:")
    print("  python consultas/scripts/main.py")

if __name__ == "__main__":
    main()
