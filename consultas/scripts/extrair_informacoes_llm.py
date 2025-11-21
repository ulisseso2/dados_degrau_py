import os
import json
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Importações condicionais para diferentes provedores
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False


PROMPT_TEMPLATE = """Você é um assistente especializado em análise de conversas de vendas. Analise a transcrição abaixo e extraia as seguintes informações:

1. **Consultor**: Nome do vendedor/atendente (pessoa que está oferecendo o produto)
2. **Interlocutor**: Nome do cliente/lead (pessoa que está sendo atendida)
3. **Assunto**: Tema principal da conversa (em 1-2 palavras)
4. **Concurso de Interesse**: Qual concurso público o cliente tem interesse (ex: PRF, TJ, Banco do Brasil, etc.)
5. **Oferta Proposta**: Qual produto/curso foi oferecido pelo consultor
6. **Objeção**: Principal objeção ou dúvida levantada pelo cliente
7. **Resposta do Consultor**: Como o consultor respondeu à objeção

**IMPORTANTE**: 
- Se alguma informação não estiver presente na transcrição, retorne null
- Seja preciso e extraia apenas informações explícitas no texto
- Nomes de pessoas devem ser nomes próprios completos quando possível
- Para concursos, use siglas oficiais (PRF, TJ-SP, BB, CEF, etc.)

**TRANSCRIÇÃO**:
{transcricao}

**Retorne APENAS um JSON válido no seguinte formato (sem markdown, sem explicações)**:
{{
    "consultor": "Nome do Consultor ou null",
    "interlocutor": "Nome do Cliente ou null",
    "assunto": "Assunto ou null",
    "concurso_interesse": "Concurso ou null",
    "oferta_proposta": "Oferta ou null",
    "objecao": "Objeção ou null",
    "resposta_consultor": "Resposta ou null"
}}"""


def extrair_com_anthropic(transcricao: str) -> Dict:
    """Extrai informações usando Claude (Anthropic)."""
    if not ANTHROPIC_AVAILABLE:
        raise ImportError("anthropic não está instalado. Execute: pip install anthropic")
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY não encontrada no .env")
    
    client = anthropic.Anthropic(api_key=api_key)
    
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": PROMPT_TEMPLATE.format(transcricao=transcricao)
        }]
    )
    
    # Extrair o JSON da resposta
    content = response.content[0].text
    # Remover possíveis markdown code blocks
    content = content.replace("```json", "").replace("```", "").strip()
    return json.loads(content)


def extrair_com_openai(transcricao: str) -> Dict:
    """Extrai informações usando GPT (OpenAI)."""
    if not OPENAI_AVAILABLE:
        raise ImportError("openai não está instalado. Execute: pip install openai")
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY não encontrada no .env")
    
    client = openai.OpenAI(api_key=api_key)
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": PROMPT_TEMPLATE.format(transcricao=transcricao)
        }],
        temperature=0.1
    )
    
    content = response.choices[0].message.content
    content = content.replace("```json", "").replace("```", "").strip()
    return json.loads(content)


def extrair_com_ollama(transcricao: str, modelo: str = "llama3.2") -> Dict:
    """Extrai informações usando Ollama (modelo local)."""
    if not OLLAMA_AVAILABLE:
        raise ImportError("ollama não está instalado. Execute: pip install ollama")
    
    response = ollama.chat(
        model=modelo,
        messages=[{
            "role": "user",
            "content": PROMPT_TEMPLATE.format(transcricao=transcricao)
        }]
    )
    
    content = response['message']['content']
    content = content.replace("```json", "").replace("```", "").strip()
    return json.loads(content)


def extrair_informacoes_llm(transcricoes: List[Dict], provider: str = "auto") -> List[Dict]:
    """
    Processa as transcrições e extrai informações estruturadas usando LLM.

    Args:
        transcricoes (list): Lista de dicionários com o nome do arquivo e o conteúdo extraído.
        provider (str): Provedor de LLM ("anthropic", "openai", "ollama", ou "auto")

    Returns:
        list: Lista de dicionários com as informações estruturadas.
    """
    # Determinar qual provedor usar
    if provider == "auto":
        if ANTHROPIC_AVAILABLE and os.getenv("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        elif OPENAI_AVAILABLE and os.getenv("OPENAI_API_KEY"):
            provider = "openai"
        elif OLLAMA_AVAILABLE:
            provider = "ollama"
        else:
            raise ValueError(
                "Nenhum provedor de LLM disponível. Instale e configure:\n"
                "- anthropic: pip install anthropic + ANTHROPIC_API_KEY no .env\n"
                "- openai: pip install openai + OPENAI_API_KEY no .env\n"
                "- ollama: pip install ollama + ollama instalado localmente"
            )
    
    print(f"Usando provedor: {provider}")
    
    # Selecionar função de extração
    if provider == "anthropic":
        extrair_func = extrair_com_anthropic
    elif provider == "openai":
        extrair_func = extrair_com_openai
    elif provider == "ollama":
        extrair_func = extrair_com_ollama
    else:
        raise ValueError(f"Provedor inválido: {provider}")
    
    dados_estruturados = []
    total = len(transcricoes)
    
    for idx, transcricao in enumerate(transcricoes, 1):
        print(f"Processando {idx}/{total}: {transcricao['arquivo']}")
        
        try:
            # Extrair informações via LLM
            info = extrair_func(transcricao["conteudo"])
            
            # Adicionar nome do arquivo
            info["arquivo"] = transcricao["arquivo"]
            
            dados_estruturados.append(info)
            
        except Exception as e:
            print(f"Erro ao processar {transcricao['arquivo']}: {e}")
            # Adicionar registro com valores nulos em caso de erro
            dados_estruturados.append({
                "arquivo": transcricao["arquivo"],
                "consultor": None,
                "interlocutor": None,
                "assunto": None,
                "concurso_interesse": None,
                "oferta_proposta": None,
                "objecao": None,
                "resposta_consultor": None,
            })
    
    return dados_estruturados


if __name__ == "__main__":
    # Exemplo de uso
    from processar_transcricoes import ler_transcricoes

    pasta_transcricoes = "../telefonia"
    transcricoes = ler_transcricoes(pasta_transcricoes)
    
    # Processar apenas as primeiras 3 transcrições para teste
    transcricoes_teste = transcricoes[:3]
    dados = extrair_informacoes_llm(transcricoes_teste, provider="auto")

    for dado in dados:
        print(json.dumps(dado, indent=2, ensure_ascii=False))
