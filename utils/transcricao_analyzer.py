"""
Módulo para análise de transcrições de ligações de vendas
Inclui análise quantitativa e qualitativa com IA (OpenAI)
"""

import json
import pandas as pd
import os
from typing import Dict, List, Optional
from openai import OpenAI
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()


class TranscricaoAnalyzer:
    """Classe para análise de transcrições de ligações"""
    
    def __init__(self):
        """Inicializa o analisador com configurações da OpenAI"""
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY não configurada no arquivo .env")
        
        self.client = OpenAI(api_key=api_key)
        self.model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
        self.temperature = float(os.getenv('OPENAI_TEMPERATURE', '0.2'))
        self.max_tokens = int(os.getenv('OPENAI_MAX_TOKENS', '4000'))
        
        # Carrega o contexto de avaliação SPIN
        self.contexto_spin = self._carregar_contexto_spin()
    
    def _carregar_contexto_spin(self) -> str:
        """Carrega o arquivo de contexto para avaliação SPIN"""
        contexto_path = 'consultas/transcricoes/contexto.txt'
        try:
            with open(contexto_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            print(f"Aviso: Arquivo {contexto_path} não encontrado")
            return ""
    
    def extrair_dados_json(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extrai dados do JSON na coluna json_completo
        
        Args:
            df: DataFrame com coluna json_completo
            
        Returns:
            DataFrame com colunas adicionais extraídas do JSON
        """
        def parse_json_safe(json_str):
            """Parse JSON com tratamento de erros"""
            if pd.isna(json_str) or json_str == '':
                return {}
            try:
                return json.loads(json_str)
            except (json.JSONDecodeError, TypeError):
                return {}
        
        # Extrai campos do JSON
        json_data = df['json_completo'].apply(parse_json_safe)
        
        df['data_ligacao_json'] = json_data.apply(lambda x: x.get('data', None))
        df['hora_ligacao_json'] = json_data.apply(lambda x: x.get('hora', None))
        df['uuid'] = json_data.apply(lambda x: x.get('uuid', None))
        df['ramal'] = json_data.apply(lambda x: x.get('ramal', None))
        df['agente'] = json_data.apply(lambda x: x.get('agente', None))
        df['telefone_json'] = json_data.apply(lambda x: x.get('telefone', None))
        df['transcricao_json'] = json_data.apply(lambda x: x.get('transcricao', None))
        
        return df
    
    def analisar_quantitativo(self, df: pd.DataFrame) -> Dict:
        """
        Realiza análise quantitativa das transcrições
        
        Args:
            df: DataFrame com dados das transcrições
            
        Returns:
            Dicionário com métricas quantitativas
        """
        # Extrai dados do JSON
        df_analise = self.extrair_dados_json(df.copy())
        
        # Converte datas
        df_analise['data_trancricao'] = pd.to_datetime(df_analise['data_trancricao'])
        
        # Métricas gerais
        metricas = {
            'total_ligacoes': len(df_analise),
            'ligacoes_por_empresa': df_analise['empresa'].value_counts().to_dict(),
            'ligacoes_por_data': df_analise.groupby(df_analise['data_trancricao'].dt.date).size().to_dict(),
            'ligacoes_por_etapa': df_analise['etapa'].value_counts().to_dict(),
            'ligacoes_por_origem': df_analise['origem'].value_counts().to_dict(),
            'ligacoes_por_modalidade': df_analise['modalidade'].value_counts().to_dict(),
            'ligacoes_por_agente': df_analise['agente'].value_counts().head(10).to_dict(),
            'ligacoes_por_ramal': df_analise['ramal'].value_counts().head(10).to_dict(),
        }
        
        # Análise temporal
        df_analise['hora'] = pd.to_datetime(df_analise['hora_ligacao'], format='%H:%M:%S', errors='coerce')
        df_analise['hora_numerica'] = df_analise['hora'].dt.hour
        
        metricas['ligacoes_por_hora'] = df_analise['hora_numerica'].value_counts().sort_index().to_dict()
        
        # Análise de duração das transcrições
        df_analise['tamanho_transcricao'] = df_analise['transcricao'].fillna('').str.len()
        metricas['duracao_media_caracteres'] = df_analise['tamanho_transcricao'].mean()
        metricas['duracao_mediana_caracteres'] = df_analise['tamanho_transcricao'].median()
        
        return metricas
    
    def classificar_ligacao(self, transcricao: str) -> Dict:
        """
        Classifica uma ligação quanto à validade usando IA
        
        Args:
            transcricao: Texto da transcrição
            
        Returns:
            Dict com classificação e motivo
        """
        if not transcricao or transcricao.strip() == '':
            return {
                'valida': False,
                'motivo': 'Transcrição vazia',
                'tipo': 'vazia'
            }
        
        prompt = f"""Analise a seguinte transcrição de ligação e classifique-a:

TRANSCRIÇÃO:
{transcricao[:500]}...

CLASSIFIQUE COMO:
1. "válida" - Conversa completa entre vendedor e cliente com conteúdo relevante
2. "caixa_postal" - Caiu em caixa postal/secretária eletrônica
3. "nao_atendeu" - Não atendeu, só toca música/URA
4. "desconexao" - Ligação caiu ou problemas técnicos
5. "invalida" - Outros motivos (trote, ligação muito curta, etc)

Responda APENAS em formato JSON:
{{"tipo": "um_dos_tipos_acima", "motivo": "breve explicação"}}
"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Você é um especialista em análise de ligações de vendas."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=200
            )
            
            resultado = json.loads(response.choices[0].message.content)
            resultado['valida'] = resultado.get('tipo') == 'válida'
            return resultado
            
        except Exception as e:
            print(f"Erro ao classificar ligação: {e}")
            return {
                'valida': False,
                'motivo': f'Erro na análise: {str(e)}',
                'tipo': 'erro'
            }
    
    def avaliar_atendimento_spin(self, transcricao: str) -> Dict:
        """
        Avalia o atendimento usando metodologia SPIN Selling
        
        Args:
            transcricao: Texto da transcrição completa
            
        Returns:
            Dict com avaliação completa segundo SPIN
        """
        if not self.contexto_spin:
            return {
                'erro': 'Contexto SPIN não carregado',
                'scores': {'total': 0}
            }
        
        prompt = f"""{self.contexto_spin}

TRANSCRIÇÃO A AVALIAR:
{transcricao}

Analise esta transcrição e retorne a avaliação em JSON conforme especificado no contexto acima.
"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Você é um avaliador sênior de vendas especializado em SPIN Selling."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            avaliacao = json.loads(response.choices[0].message.content)
            return avaliacao
            
        except Exception as e:
            print(f"Erro ao avaliar atendimento: {e}")
            return {
                'erro': f'Erro na análise SPIN: {str(e)}',
                'scores': {'total': 0}
            }
    
    def analisar_lote_classificacao(self, df: pd.DataFrame, limite: Optional[int] = None) -> pd.DataFrame:
        """
        Classifica um lote de transcrições
        
        Args:
            df: DataFrame com transcrições
            limite: Número máximo de registros a processar (None = todos)
            
        Returns:
            DataFrame com classificações adicionadas
        """
        df_analise = df.copy()
        
        if limite:
            df_analise = df_analise.head(limite)
        
        print(f"Classificando {len(df_analise)} transcrições...")
        
        classificacoes = []
        for idx, row in df_analise.iterrows():
            classificacao = self.classificar_ligacao(row['transcricao'])
            classificacoes.append(classificacao)
            
            if (idx + 1) % 10 == 0:
                print(f"Processadas {idx + 1}/{len(df_analise)} transcrições")
        
        df_analise['ligacao_valida'] = [c['valida'] for c in classificacoes]
        df_analise['tipo_ligacao'] = [c['tipo'] for c in classificacoes]
        df_analise['motivo_classificacao'] = [c['motivo'] for c in classificacoes]
        
        return df_analise
    
    def analisar_lote_spin(self, df: pd.DataFrame, apenas_validas: bool = True, 
                          limite: Optional[int] = None) -> pd.DataFrame:
        """
        Avalia um lote de transcrições com SPIN Selling
        
        Args:
            df: DataFrame com transcrições
            apenas_validas: Se True, avalia apenas ligações válidas
            limite: Número máximo de registros a processar
            
        Returns:
            DataFrame com avaliações SPIN adicionadas
        """
        df_analise = df.copy()
        
        if apenas_validas and 'ligacao_valida' in df_analise.columns:
            df_analise = df_analise[df_analise['ligacao_valida'] == True]
        
        if limite:
            df_analise = df_analise.head(limite)
        
        print(f"Avaliando {len(df_analise)} transcrições com SPIN...")
        
        avaliacoes = []
        for idx, row in df_analise.iterrows():
            avaliacao = self.avaliar_atendimento_spin(row['transcricao'])
            avaliacoes.append(avaliacao)
            
            if (idx + 1) % 5 == 0:
                print(f"Avaliadas {idx + 1}/{len(df_analise)} transcrições")
        
        # Extrai scores principais
        df_analise['score_total'] = [a.get('scores', {}).get('total', 0) for a in avaliacoes]
        df_analise['score_spin'] = [a.get('scores', {}).get('investigacao_spin', 0) for a in avaliacoes]
        df_analise['produto_principal'] = [a.get('produto_principal', 'INDEFINIDO') for a in avaliacoes]
        df_analise['avaliacao_completa'] = avaliacoes
        
        return df_analise


class TranscricaoOpenAIAnalyzer:
    """Classe para avaliação de transcrições usando OpenAI (novo fluxo)"""

    def __init__(self):
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY não configurada no arquivo .env")

        self.client = OpenAI(api_key=api_key)
        self.model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
        self.temperature = float(os.getenv('OPENAI_TEMPERATURE', '0.2'))
        self.max_tokens = int(os.getenv('OPENAI_MAX_TOKENS', '4000'))

        self.contexto = self._carregar_contexto()

    def _carregar_contexto(self) -> str:
        contexto_path = 'consultas/transcricoes/contexto.txt'
        try:
            with open(contexto_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return "Contexto não encontrado. Use análise genérica."

    def _criar_prompt_classificacao(self, transcricao: str) -> str:
                return f"""
Classifique a ligação APENAS com base na transcrição.

CATEGORIAS POSSÍVEIS (use exatamente um destes valores):
- "ura": apenas URA/robô/música/caixa postal, sem diálogo humano
- "dialogo_incompleto": conversa interrompida ou muito curta (poucos turnos)
- "dados_insuficientes": há diálogo, mas falta contexto mínimo para concluir
- "ligacao_interna": conversa entre colaboradores/ramais internos
- "chamada_errada": pessoa errada/engano/sem interesse por número incorreto
- "cancelamento": foco principal é cancelar/estornar/reembolsar
- "suporte": suporte técnico/pós-venda de cliente já ativo (acesso, login, senha, instabilidade)
- "venda": ligação de vendas com contexto suficiente
- "outros": qualquer outro caso

REGRAS:
- Se não houver interação humana além de URA, classifique como "ura".
- Se houver diálogo entre vendedor e cliente após URA, NÃO classifique como "ura".
- "dialogo_incompleto" é para conversas muito curtas ou encerradas cedo.
- "dados_insuficientes" é para diálogo existente, mas sem dados mínimos para avaliar.
- "suporte" SOMENTE quando o objetivo principal é resolver problema pós-venda de cliente já ativo.
- Dúvidas sobre acesso ou matrícula durante proposta comercial AINDA são "venda".
- Se o foco for cancelar/reembolsar/estornar, use "cancelamento".
- Se houver conversa de venda com contexto, use "venda".

RETORNE APENAS JSON VÁLIDO no formato:
{{
    "tipo": "...",
    "motivo": "...",
    "confianca": 0.0,
    "deve_avaliar": true
}}

ORIENTAÇÃO PARA deve_avaliar:
- true somente se "tipo" for "venda".
- false para todas as demais categorias.

TRANSCRIÇÃO (trecho):
{transcricao[:2000]}
"""

    def _classificar_por_heuristica(self, transcricao: str) -> Optional[Dict]:
        texto = " ".join(transcricao.lower().split())

        if len(texto) >= 255:
            return None

        if len(texto) < 15:
            return {
                'tipo': 'dados_insuficientes',
                'motivo': 'Transcrição muito curta',
                'confianca': 0.95,
                'deve_avaliar': False,
                'tokens_usados': 0
            }

        padroes_ura = [
            "caixa postal",
            "grave seu recado",
            "deixe a sua mensagem",
            "não receber recados",
            "este número está configurado para não receber recados",
            "mensagem na caixa postal"
        ]

        if any(p in texto for p in padroes_ura):
            return {
                'tipo': 'ura',
                'motivo': 'Mensagem automática/caixa postal detectada',
                'confianca': 0.9,
                'deve_avaliar': False,
                'tokens_usados': 0
            }

        padroes_sem_tempo = [
            "ligar outra hora",
            "ligar mais tarde",
            "não posso falar agora",
            "tô ocupado",
            "estou ocupado",
            "me liga mais tarde",
            "depois a gente fala",
            "não consigo falar agora",
            "agora não posso"
        ]

        marcadores_venda = [
            "proposta",
            "matrícula",
            "desconto",
            "parcela",
            "valor",
            "orçamento",
            "boleto",
            "cartão",
            "pagar",
            "curso",
            "convite de matrícula"
        ]

        sem_tempo = any(p in texto for p in padroes_sem_tempo)
        tem_venda = any(p in texto for p in marcadores_venda)

        if sem_tempo and not tem_venda:
            return {
                'tipo': 'dialogo_incompleto',
                'motivo': 'Ligação encerrada por indisponibilidade/retorno',
                'confianca': 0.8,
                'deve_avaliar': False,
                'tokens_usados': 0
            }

        if len(texto) < 80:
            return {
                'tipo': 'dialogo_incompleto',
                'motivo': 'Transcrição curta com dados insuficientes',
                'confianca': 0.7,
                'deve_avaliar': False,
                'tokens_usados': 0
            }

        return None

    def _criar_prompt_otimizado(self, transcricao: str, contexto_adicional: Optional[Dict] = None) -> str:
        prompt_base = f"""{self.contexto}

    Siga o CONTEXTO acima como verdade e retorne APENAS JSON válido no formato especificado ali.

    TRANSCRIÇÃO DA LIGAÇÃO:
    {transcricao[:4000]}"""

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

    def classificar_ligacao(self, transcricao: str) -> Dict:
        if not transcricao or len(transcricao.strip()) < 10:
            return {
                'tipo': 'dados_insuficientes',
                'motivo': 'Transcrição muito curta ou vazia',
                'confianca': 0.9,
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

            texto_norm = " ".join(transcricao.lower().split())
            tem_dialogo = ("vendedor:" in texto_norm) and ("cliente:" in texto_norm)
            marcadores_venda = [
                "proposta",
                "matrícula",
                "desconto",
                "parcela",
                "valor",
                "orçamento",
                "boleto",
                "cartão",
                "pagar",
                "curso",
                "convite de matrícula"
            ]
            tem_venda = any(p in texto_norm for p in marcadores_venda)

            if resultado.get('tipo') == 'ura' and tem_dialogo and len(texto_norm) >= 255:
                resultado['tipo'] = 'venda' if tem_venda else 'outros'
                resultado['motivo'] = 'Diálogo após URA detectado'
                resultado['deve_avaliar'] = True
            return resultado

        except Exception as e:
            return {
                'tipo': 'outros',
                'motivo': f'Erro ao classificar: {str(e)}',
                'confianca': 0,
                'deve_avaliar': False,
                'tokens_usados': 0
            }

    def analisar_transcricao(self, transcricao: str, contexto_adicional: Optional[Dict] = None) -> Dict:
        if not transcricao or len(transcricao.strip()) < 10:
            return {
                'erro': 'Transcrição muito curta ou vazia',
                'classificacao_ligacao': 'erro',
                'qualidade_atendimento': 'n/a'
            }

        try:
            classificacao = self.classificar_ligacao(transcricao)
            tipo = classificacao.get('tipo', 'outros')
            motivo = classificacao.get('motivo', 'Não informado')
            confianca = classificacao.get('confianca', 0)
            deve_avaliar = classificacao.get('deve_avaliar', False)

            if not deve_avaliar or tipo != 'venda':
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
                response_format={"type": "json_object"}
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

            tokens_avaliacao = getattr(getattr(response, "usage", None), "total_tokens", None)
            tokens_classificacao = classificacao.get('tokens_usados')
            tokens_usados = None
            if tokens_avaliacao is not None or tokens_classificacao is not None:
                tokens_usados = (tokens_avaliacao or 0) + (tokens_classificacao or 0)

            analise = {
                'avaliacao_completa': json.dumps(resultado, ensure_ascii=False),
                'tokens_usados': tokens_usados,
                'nota_vendedor': resultado.get('avaliacao_vendedor', {}).get('nota_final_0_100', 0),
                'lead_score': resultado.get('avaliacao_lead', {}).get('lead_score_0_100', 0),
                'lead_classificacao': resultado.get('avaliacao_lead', {}).get('classificacao', 'D'),
                'concurso_area': resultado.get('extracao', {}).get('concurso_area', 'Não identificado'),
                'produto_recomendado': resultado.get('recomendacao_final', {}).get('produto_principal', {}).get('produto', 'N/A')
            }

            return analise

        except json.JSONDecodeError as e:
            return {'erro': f'Erro ao decodificar JSON: {str(e)}', 'classificacao_ligacao': 'erro'}
        except Exception as e:
            return {'erro': f'Erro na análise: {type(e).__name__}: {str(e)}', 'classificacao_ligacao': 'erro'}
