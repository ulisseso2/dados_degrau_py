import pandas as pd

def salvar_analises(dados_estruturados, caminho_saida):
    """
    Salva os dados estruturados em um arquivo CSV.

    Args:
        dados_estruturados (list): Lista de dicionários com as informações estruturadas.
        caminho_saida (str): Caminho para salvar o arquivo CSV.
    """
    if not dados_estruturados:
        print("Nenhum dado estruturado para salvar. Verifique o pipeline.")
        return

    df = pd.DataFrame(dados_estruturados)
    df.to_csv(caminho_saida, index=False)
    print(f"Análises salvas em {caminho_saida}")

if __name__ == "__main__":
    # Exemplo de uso
    from extrair_informacoes import extrair_informacoes
    from processar_transcricoes import ler_transcricoes

    pasta_transcricoes = "../telefonia/transcricoes"
    caminho_saida = "../resultados/analises.csv"

    transcricoes = ler_transcricoes(pasta_transcricoes)
    dados_estruturados = extrair_informacoes(transcricoes)
    salvar_analises(dados_estruturados, caminho_saida)