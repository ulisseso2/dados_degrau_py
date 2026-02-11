"""
Script para testar conexão com Groq API
"""
import os
from dotenv import load_dotenv

def test_groq_connection():
    """Testa conexão com Groq API"""
    
    print("=" * 60)
    print("🔍 Testando Conexão com Groq API")
    print("=" * 60)
    
    # Carrega variáveis de ambiente
    load_dotenv()
    
    # Verifica API Key
    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    
    if not api_key:
        print("❌ ERRO: GROQ_API_KEY não encontrada no arquivo .env")
        print("\n📋 Siga os passos:")
        print("1. Acesse: https://console.groq.com/keys")
        print("2. Crie uma API Key")
        print("3. Adicione no arquivo .env:")
        print("   GROQ_API_KEY=gsk_sua_chave_aqui")
        return False
    
    print(f"✅ API Key encontrada: {api_key[:15]}...{api_key[-4:]}")
    print(f"📦 Modelo configurado: {model}")
    print()
    
    # Verifica se biblioteca está instalada
    try:
        from groq import Groq
        print("✅ Biblioteca Groq instalada")
    except ImportError:
        print("❌ ERRO: Biblioteca Groq não instalada")
        print("\n📋 Execute: pip install groq")
        return False
    
    # Testa conexão
    try:
        print("🔄 Testando conexão com API...")
        client = Groq(api_key=api_key)
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "Você é um assistente útil."
                },
                {
                    "role": "user",
                    "content": "Responda apenas 'OK' se você está funcionando."
                }
            ],
            temperature=0.2,
            max_tokens=10
        )
        
        resposta = response.choices[0].message.content
        tokens_usados = response.usage.total_tokens
        
        print("✅ SUCESSO! Conexão estabelecida com Groq")
        print(f"📤 Resposta: {resposta}")
        print(f"🎯 Tokens usados: {tokens_usados}")
        print(f"💰 Custo: R$ 0,00 (Groq é gratuito! 🎉)")
        print()
        
        return True
        
    except Exception as e:
        print(f"❌ ERRO ao conectar com Groq: {str(e)}")
        
        if "invalid api key" in str(e).lower():
            print("\n💡 Dica: Verifique se a API Key está correta")
            print("   Acesse: https://console.groq.com/keys")
        elif "rate limit" in str(e).lower():
            print("\n💡 Dica: Limite de taxa atingido (6000 tokens/min)")
            print("   Aguarde 1 minuto e tente novamente")
        
        return False

def test_transcricao_analyzer():
    """Testa o TranscricaoIAAnalyzer com Groq"""
    
    print("=" * 60)
    print("🤖 Testando TranscricaoIAAnalyzer com Groq")
    print("=" * 60)
    
    try:
        from utils.transcricao_ia_analyzer import TranscricaoIAAnalyzer
        
        analyzer = TranscricaoIAAnalyzer()
        print("✅ TranscricaoIAAnalyzer importado com sucesso")
        
        # Transcrição de teste
        transcricao_teste = """
        Vendedor: Bom dia! Meu nome é João, da Degrau Cursos. Estou entrando em contato para falar sobre nossos cursos de pós-graduação. Posso conversar com você agora?
        Cliente: Bom dia, pode sim.
        Vendedor: Ótimo! Primeiro, me conta um pouco sobre você. Qual é sua formação e área de atuação atualmente?
        Cliente: Sou formada em Administração e trabalho em uma empresa de logística.
        Vendedor: Que legal! E você está sentindo alguma dificuldade na sua área que uma especialização poderia ajudar?
        Cliente: Sim, sinto que preciso me aprofundar em gestão de projetos para crescer na carreira.
        Vendedor: Entendo perfeitamente. E se você não fizer essa especialização agora, como isso pode impactar seu crescimento profissional?
        Cliente: Acho que vou ficar estagnada, as promoções estão indo para quem tem especialização.
        Vendedor: Exatamente. Nossa pós em Gestão de Projetos pode te dar essas ferramentas. Você gostaria de conhecer mais sobre o curso?
        Cliente: Sim, gostaria!
        Vendedor: Perfeito! Vou te enviar o material e agendar uma reunião para você conhecer melhor. Pode ser?
        Cliente: Pode sim, obrigada!
        """
        
        print("🔄 Analisando transcrição de teste com Groq...")
        print()
        
        resultado = analyzer.analisar_transcricao(transcricao_teste)
        
        if 'erro' in resultado:
            print(f"❌ ERRO na análise: {resultado['erro']}")
            return False
        
        print("✅ Análise concluída com sucesso!")
        print()
        print("📊 Resultados:")
        print(f"   Classificação: {resultado.get('classificacao_ligacao')}")
        print(f"   Qualidade: {resultado.get('qualidade_atendimento')}")
        print(f"   Pontos Positivos: {resultado.get('pontos_positivos')}")
        print(f"   Pontos de Melhoria: {resultado.get('pontos_melhoria')}")
        print()
        print("🎯 SPIN Selling:")
        print(f"   Situação: {resultado.get('spin_situacao')}")
        print(f"   Problema: {resultado.get('spin_problema')}")
        print(f"   Implicação: {resultado.get('spin_implicacao')}")
        print(f"   Necessidade: {resultado.get('spin_necessidade')}")
        print()
        print(f"📝 Resumo: {resultado.get('notas_ia')}")
        print(f"🎯 Tokens: {resultado.get('tokens_usados')}")
        print(f"💰 Custo: R$ 0,00 (Groq é gratuito! 🎉)")
        print()
        
        return True
        
    except ImportError as e:
        print(f"❌ Erro ao importar TranscricaoIAAnalyzer: {e}")
        return False
    except Exception as e:
        print(f"❌ Erro durante análise: {e}")
        return False

if __name__ == "__main__":
    # Teste 1: Conexão básica
    conexao_ok = test_groq_connection()
    
    if not conexao_ok:
        print("\n⚠️  Corrija os problemas de conexão antes de continuar.")
        exit(1)
    
    # Teste 2: Analyzer completo
    print()
    analyzer_ok = test_transcricao_analyzer()
    
    if analyzer_ok:
        print("=" * 60)
        print("✅ TODOS OS TESTES PASSARAM!")
        print("=" * 60)
        print()
        print("🎉 Sistema pronto para uso com Groq!")
        print("📝 Próximo passo: Testar na interface Streamlit")
        print()
        print("⚡ Groq é MUITO RÁPIDO: ~1-2 segundos por análise")
        print("💰 E completamente GRATUITO!")
    else:
        print("\n⚠️  Alguns testes falharam. Verifique os erros acima.")
        exit(1)
