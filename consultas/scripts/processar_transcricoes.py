from docx import Document
import os

def ler_transcricoes(pasta):
    """
    Lê todos os arquivos .docx em uma pasta e retorna uma lista de transcrições.

    Args:
        pasta (str): Caminho para a pasta contendo os arquivos .docx.

    Returns:
        list: Lista de dicionários com o nome do arquivo e o conteúdo extraído.
    """
    transcricoes = []
    for arquivo in os.listdir(pasta):
        if arquivo.endswith('.docx'):
            caminho = os.path.join(pasta, arquivo)
            doc = Document(caminho)
            texto = "\n".join([paragrafo.text for paragrafo in doc.paragraphs])
            transcricoes.append({"arquivo": arquivo, "conteudo": texto})
    return transcricoes

if __name__ == "__main__":
    # Exemplo de uso
    pasta_transcricoes = "../telefonia/transcricoes"
    transcricoes = ler_transcricoes(pasta_transcricoes)
    for transcricao in transcricoes:
        print(f"Arquivo: {transcricao['arquivo']}")
        print(f"Conteúdo:\n{transcricao['conteudo'][:200]}...")  # Mostra os primeiros 200 caracteres