"""
Análise de transcrições usando IA (Groq)
Usa contexto completo do negócio para avaliações detalhadas
"""
import os
import json
from typing import Dict, Optional
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

class TranscricaoIAAnalyzer:
    def __init__(self):
        """Inicializa cliente Groq"""
        self.api_key = os.getenv("GROQ_API_KEY")
        self.client = Groq(api_key=self.api_key) if self.api_key else None
        self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.temperature = float(os.getenv("GROQ_TEMPERATURE", "0.2"))
        self.max_tokens = int(os.getenv("GROQ_MAX_TOKENS", "8000"))  # Aumentado para análise completa
        
        # Carrega contexto do arquivo
        self.contexto = self._carregar_contexto()
    
    def _carregar_contexto(self) -> str:
        """Carrega arquivo de contexto"""
        contexto_path = os.path.join(os.path.dirname(__file__), '..', 'consultas', 'transcricoes', 'contexto.txt')
        try:
            with open(contexto_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return "Contexto não encontrado. Use análise genérica."
    
    def _criar_prompt_completo(self, transcricao: str) -> str:
        """
        Cria prompt completo usando contexto do negócio
        """
        return f"""{self.contexto}

TRANSCRIÇÃO DA LIGAÇÃO:
{transcricao[:4000]}

Analise esta transcrição e retorne APENAS JSON válido no formato especificado acima."""

    def _criar_prompt_classificacao(self, transcricao: str) -> str:
        """
        Prompt para classificar o tipo de ligação antes da avaliação completa
        """
        return f"""
Classifique a ligação APENAS com base na transcrição.

CATEGORIAS POSSÍVEIS (use exatamente um destes valores):
- "ura": apenas URA/robô/música
- "dialogo_incompleto": conversa interrompida ou muito curta
- "dados_insuficientes": sem contexto suficiente para avaliar
- "ligacao_interna": conversa entre colaboradores/ramais internos
- "chamada_errada": pessoa errada/número errado/sem interesse por engano
    - "cancelamento": solicitação de cancelamento, troca ou reembolso
- "venda": ligação de vendas com conteúdo suficiente
- "outros": qualquer outro caso

REGRAS:
- Se não houver interação humana além de URA, classifique como "ura".
- Se houver poucos turnos e não há contexto, use "dialogo_incompleto".
- Se o diálogo existe, mas sem dados mínimos para avaliar, use "dados_insuficientes".
- Se parecer conversa interna, use "ligacao_interna".
- Se o lead disser que foi engano, use "chamada_errada".
- Se o foco for cancelamento, use "cancelamento".
- Se houver conversa de venda com contexto, use "venda".

RETORNE APENAS JSON VÁLIDO no formato:
{{
    "tipo": "...",
    "motivo": "...",
    "confianca": 0.0,
    "deve_avaliar": true
}}

TRANSCRIÇÃO (trecho):
{transcricao[:2000]}
"""

    def _classificar_por_heuristica(self, transcricao: str) -> Optional[Dict]:
        texto = " ".join(transcricao.lower().split())

        if len(texto) < 15:
            return {
                'tipo': 'dados_insuficientes',
                'motivo': 'Transcrição muito curta',
                'confianca': 0.95,
                'deve_avaliar': False,
                'tokens_usados': 0
            }

        padroes_cancelamento = [
            "cancelamento",
            "cancelar",
            "reembolso",
            "estorno",
            "quero cancelar",
            "solicitar cancelamento",
            "procedimento de cancelamento"
        ]

        if any(p in texto for p in padroes_cancelamento):
            return {
                'tipo': 'cancelamento',
                'motivo': 'Solicitação de cancelamento/reembolso',
                'confianca': 0.9,
                'deve_avaliar': False,
                'tokens_usados': 0
            }

        padroes_ura = [
            "caixa postal",
            "correio de voz",
            "grave seu recado",
            "deixe a sua mensagem",
            "deixe sua mensagem",
            "não receber recados",
            "este número está configurado para não receber recados",
            "ura:",
            "obrigado por ligar",
            "mensagem na caixa postal",
            "permaneça na linha",
            "pessoa não está disponível",
            "não está disponível",
            "grave a sua mensagem",
            "após o sinal",
            "deixe outra mensagem",
            "vamos entregar o seu recado",
            "poderei ver se esta pessoa está disponível"
        ]

        tem_dialogo = ("vendedor:" in texto) and ("cliente:" in texto)
        if not tem_dialogo and any(p in texto for p in padroes_ura):
            return {
                'tipo': 'ura',
                'motivo': 'Mensagem automática/caixa postal detectada',
                'confianca': 0.9,
                'deve_avaliar': False,
                'tokens_usados': 0
            }

        return None

    def _criar_prompt_otimizado(self, transcricao: str, contexto_adicional: Optional[Dict] = None) -> str:
        """
        Monta prompt com contexto do negócio e dados adicionais opcionais
        """
        prompt_base = self._criar_prompt_completo(transcricao)
        if contexto_adicional:
            try:
                contexto_json = json.dumps(contexto_adicional, ensure_ascii=False)
            except (TypeError, ValueError):
                contexto_json = "{}"
            prompt_base += f"""

DADOS ADICIONAIS (SE USAR, NÃO INVENTE):
{contexto_json}
"""
        return prompt_base

    def analisar_transcricao(self, transcricao: str, contexto_adicional: Optional[Dict] = None) -> Dict:
        """
        Analisa transcrição usando IA
        
        Args:
            transcricao: Texto da transcrição
            contexto_adicional: Dados extras (nome, telefone, origem, etc)
            
        Returns:
            Dicionário com análise estruturada
        """
        if not transcricao or len(transcricao.strip()) < 10:
            return {
                'erro': 'Transcrição muito curta ou vazia',
                'classificacao_ligacao': 'erro',
                'qualidade_atendimento': 'n/a'
            }
        
        if not self.api_key:
            return {
                'erro': 'GROQ_API_KEY não configurada no .env',
                'classificacao_ligacao': 'erro',
                'qualidade_atendimento': 'n/a'
            }

        if not self.client:
            return {
                'erro': 'Cliente Groq não inicializado',
                'classificacao_ligacao': 'erro',
                'qualidade_atendimento': 'n/a'
            }

        try:
            classificacao = self.classificar_ligacao(transcricao)
            tipo = classificacao.get('tipo', 'outros')
            motivo = classificacao.get('motivo', 'Não informado')
            confianca = classificacao.get('confianca', 0)
            deve_avaliar = classificacao.get('deve_avaliar', False)

            if tipo == 'venda':
                deve_avaliar = True

            if not deve_avaliar or tipo != 'venda':
                if tipo == 'outros' and isinstance(motivo, str) and motivo.lower().startswith('erro ao classificar'):
                    deve_avaliar = True
                else:
                    retorno_minimo = {
                        'classificacao_ligacao': tipo,
                        'motivo_classificacao': motivo,
                        'confianca_classificacao': confianca,
                        'avaliacao_completa': json.dumps({
                            'classificacao_ligacao': tipo,
                            'motivo_classificacao': motivo,
                            'confianca_classificacao': confianca
                        }, ensure_ascii=False),
                        'tokens_usados': classificacao.get('tokens_usados'),
                        'nota_vendedor': 0,
                        'lead_score': 0,
                        'lead_classificacao': 'D',
                        'concurso_area': 'Não identificado',
                        'produto_recomendado': 'N/A'
                    }
                    return retorno_minimo

            prompt = self._criar_prompt_otimizado(transcricao, contexto_adicional)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Você é um especialista em análise de vendas educacionais. Retorna sempre JSON válido."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"}  # Groq suporta JSON mode
            )
            
            content = (response.choices[0].message.content or "").strip()

            if content.startswith("```"):
                content = content.strip("`")
                if content.lower().startswith("json"):
                    content = content[4:].strip()

            resultado = json.loads(content)

            resultado['classificacao_ligacao'] = tipo
            resultado['motivo_classificacao'] = motivo
            resultado['confianca_classificacao'] = confianca
            
            # Retorna resultado completo com estrutura do avaliacao.txt
            tokens_avaliacao = getattr(getattr(response, "usage", None), "total_tokens", None)
            tokens_classificacao = classificacao.get('tokens_usados')
            tokens_usados = None
            if tokens_avaliacao is not None or tokens_classificacao is not None:
                tokens_usados = (tokens_avaliacao or 0) + (tokens_classificacao or 0)

            analise = {
                'avaliacao_completa': json.dumps(resultado, ensure_ascii=False),
                'tokens_usados': tokens_usados,
                
                # Extrai campos principais para compatibilidade com banco
                'nota_vendedor': resultado.get('avaliacao_vendedor', {}).get('nota_final_0_100', 0),
                'lead_score': resultado.get('avaliacao_lead', {}).get('lead_score_0_100', 0),
                'lead_classificacao': resultado.get('avaliacao_lead', {}).get('classificacao', 'D'),
                'concurso_area': resultado.get('extracao', {}).get('concurso_area', 'Não identificado'),
                'produto_recomendado': resultado.get('recomendacao_final', {}).get('produto_principal', {}).get('produto', 'N/A')
            }
            
            return analise
            
        except json.JSONDecodeError as e:
            print("Erro ao decodificar JSON retornado pela Groq:")
            print(content[:1000])
            return {'erro': f'Erro ao decodificar JSON: {str(e)}', 'classificacao_ligacao': 'erro'}
        except Exception as e:
            print("Erro na análise Groq:")
            print(repr(e))
            return {'erro': f'Erro na análise: {type(e).__name__}: {str(e)}', 'classificacao_ligacao': 'erro'}

    def classificar_ligacao(self, transcricao: str) -> Dict:
        """
        Classifica o tipo de ligação para decidir se deve avaliar
        """
        if not transcricao or len(transcricao.strip()) < 10:
            return {
                'tipo': 'dados_insuficientes',
                'motivo': 'Transcrição muito curta ou vazia',
                'confianca': 0.9,
                'deve_avaliar': False,
                'tokens_usados': 0
            }

        if not self.client:
            return {
                'tipo': 'outros',
                'motivo': 'Cliente Groq não inicializado',
                'confianca': 0,
                'deve_avaliar': False,
                'tokens_usados': 0
            }

        heuristica = self._classificar_por_heuristica(transcricao)
        if heuristica:
            return heuristica

        prompt = self._criar_prompt_classificacao(transcricao)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Você é um especialista em triagem de ligações. Retorna sempre JSON válido."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,
                max_tokens=300,
                response_format={"type": "json_object"}
            )

            content = (response.choices[0].message.content or "").strip()
            if content.startswith("```"):
                content = content.strip("`")
                if content.lower().startswith("json"):
                    content = content[4:].strip()

            resultado = json.loads(content)
            resultado['tokens_usados'] = getattr(getattr(response, "usage", None), "total_tokens", None)
            if 'deve_avaliar' not in resultado:
                resultado['deve_avaliar'] = resultado.get('tipo') == 'venda'
            if resultado.get('tipo') == 'venda':
                resultado['deve_avaliar'] = True
            if 'confianca' not in resultado:
                resultado['confianca'] = 0.5
            if 'motivo' not in resultado:
                resultado['motivo'] = 'Não informado'
            return resultado

        except Exception as e:
            print("Erro ao classificar ligação:")
            print(repr(e))
            return {
                'tipo': 'outros',
                'motivo': f'Erro ao classificar: {str(e)}',
                'confianca': 0,
                'deve_avaliar': False,
                'tokens_usados': 0
            }
    
    def analisar_lote(self, transcricoes: list, callback_progresso=None) -> list:
        """
        Analisa múltiplas transcrições
        
        Args:
            transcricoes: Lista de dicts com 'oportunidade_id' e 'transcricao'
            callback_progresso: Função chamada a cada análise (opcional)
        
        Returns:
            Lista de resultados
        """
        resultados = []
        total = len(transcricoes)
        
        for i, item in enumerate(transcricoes):
            resultado = self.analisar_transcricao(item.get('transcricao', ''))
            resultado['oportunidade_id'] = item.get('oportunidade_id')
            resultados.append(resultado)
            
            if callback_progresso:
                callback_progresso(i + 1, total)
        
        return resultados
