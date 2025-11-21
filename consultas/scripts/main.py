import sys
import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Adicionar o diretório raiz ao sys.path para resolver o problema de importação
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.processar_transcricoes import ler_transcricoes
from scripts.extrair_informacoes_llm import extrair_informacoes_llm
from scripts.analisar_dados import salvar_analises

def main():
    """
    Orquestra o pipeline de processamento de transcrições usando LLM.
    """
    pasta_transcricoes = "consultas/telefonia"  # Atualizado para a pasta correta
    caminho_saida = "consultas/resultados/analises.csv"

    # Configurações
    provider = os.getenv("LLM_PROVIDER", "auto")
    
    # Etapa 1: Ler transcrições
    print("=" * 60)
    print("PIPELINE DE ANÁLISE DE TRANSCRIÇÕES COM LLM")
    print("=" * 60)
    print(f"\n[1/3] Lendo transcrições de {pasta_transcricoes}...")
    transcricoes = ler_transcricoes(pasta_transcricoes)
    print(f"✓ {len(transcricoes)} transcrições encontradas")

    # Etapa 2: Extrair informações com LLM
    print(f"\n[2/3] Extraindo informações com LLM (provider: {provider})...")
    print("⚠️  Isso pode levar alguns minutos dependendo do número de arquivos...")
    dados_estruturados = extrair_informacoes_llm(transcricoes, provider=provider)
    print(f"✓ {len(dados_estruturados)} transcrições processadas")

    # Etapa 3: Salvar análises
    print(f"\n[3/3] Salvando análises em {caminho_saida}...")
    salvar_analises(dados_estruturados, caminho_saida)

    print("\n" + "=" * 60)
    print("✓ Pipeline concluído com sucesso!")
    print("=" * 60)
    print(f"\nResultados salvos em: {caminho_saida}")
    print("Execute o Streamlit para visualizar: streamlit run consultas/scripts/visualizar_analises.py")

if __name__ == "__main__":
    main()