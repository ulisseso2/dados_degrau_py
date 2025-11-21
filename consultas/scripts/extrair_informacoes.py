import spacy

# Carregar modelo de linguagem natural do spaCy
nlp = spacy.load("pt_core_news_sm")

def extrair_informacoes(transcricoes):
    """
    Processa as transcrições e extrai informações estruturadas.

    Args:
        transcricoes (list): Lista de dicionários com o nome do arquivo e o conteúdo extraído.

    Returns:
        list: Lista de dicionários com as informações estruturadas.
    """
    dados_estruturados = []
    for transcricao in transcricoes:
        doc = nlp(transcricao["conteudo"])
        dados = {
            "arquivo": transcricao["arquivo"],
            "consultor": None,
            "interlocutor": None,
            "assunto": None,
            "concurso_interesse": None,
            "oferta_proposta": None,
            "objecao": None,
            "resposta_consultor": None,
        }

        # Exemplo de extração de entidades
        for ent in doc.ents:
            if ent.label_ == "PER":
                if not dados["consultor"]:
                    dados["consultor"] = ent.text
                elif not dados["interlocutor"]:
                    dados["interlocutor"] = ent.text
            elif ent.label_ == "ORG":
                dados["concurso_interesse"] = ent.text

        # Adicione mais regras de extração conforme necessário
        dados_estruturados.append(dados)

    return dados_estruturados

if __name__ == "__main__":
    # Exemplo de uso
    from processar_transcricoes import ler_transcricoes

    pasta_transcricoes = "../telefonia/transcricoes"
    transcricoes = ler_transcricoes(pasta_transcricoes)
    dados = extrair_informacoes(transcricoes)

    for dado in dados:
        print(dado)