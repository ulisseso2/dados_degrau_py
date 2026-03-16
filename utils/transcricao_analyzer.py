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
try:
    import streamlit as st
except ImportError:
    st = None

# Carrega variáveis de ambiente
load_dotenv()


class TranscricaoAnalyzer:
    """Classe para análise de transcrições de ligações"""
    
    def __init__(self):
        """Inicializa o analisador com configurações da OpenAI"""
        # Tenta buscar do st.secrets primeiro (produção), depois do .env (local)
        api_key = None
        if st:
            try:
                api_key = st.secrets.get("OPENAI_API_KEY") or st.secrets.get("openai_api_key")
                if not api_key:
                    openai_section = st.secrets.get("openai") if hasattr(st.secrets, "get") else None
                    if openai_section:
                        api_key = openai_section.get("OPENAI_API_KEY") or openai_section.get("openai_api_key")
            except Exception:
                pass
        
        if not api_key:
            api_key = os.getenv('OPENAI_API_KEY')
        
        if not api_key:
            raise ValueError("OPENAI_API_KEY não configurada no arquivo .env ou secrets")
        
        self.client = OpenAI(api_key=api_key)
        
        # Busca configurações do modelo
        if st:
            try:
                openai_section = st.secrets.get("openai") if hasattr(st.secrets, "get") else None
                secrets_lookup = openai_section if openai_section else st.secrets
                self.model = secrets_lookup.get('OPENAI_MODEL') or secrets_lookup.get('openai_model', 'gpt-5.1')
                self.temperature = float(secrets_lookup.get('OPENAI_TEMPERATURE') or secrets_lookup.get('openai_temperature', '0.2'))
                self.max_tokens = int(secrets_lookup.get('OPENAI_MAX_TOKENS') or secrets_lookup.get('openai_max_tokens', '8000'))
                self.max_input_chars = int(secrets_lookup.get('OPENAI_MAX_INPUT_CHARS') or secrets_lookup.get('openai_max_input_chars', '25000'))
                self.max_input_chars_classificacao = int(secrets_lookup.get('OPENAI_MAX_INPUT_CHARS_CLASSIFICACAO') or secrets_lookup.get('openai_max_input_chars_classificacao', '4000'))
            except Exception:
                self.model = os.getenv('OPENAI_MODEL', 'gpt-5.1')
                self.temperature = float(os.getenv('OPENAI_TEMPERATURE', '0.2'))
                self.max_tokens = int(os.getenv('OPENAI_MAX_TOKENS', '8000'))
                self.max_input_chars = int(os.getenv('OPENAI_MAX_INPUT_CHARS', '25000'))
                self.max_input_chars_classificacao = int(os.getenv('OPENAI_MAX_INPUT_CHARS_CLASSIFICACAO', '4000'))
        else:
            self.model = os.getenv('OPENAI_MODEL', 'gpt-5.1')
            self.temperature = float(os.getenv('OPENAI_TEMPERATURE', '0.2'))
            self.max_tokens = int(os.getenv('OPENAI_MAX_TOKENS', '8000'))
            self.max_input_chars = int(os.getenv('OPENAI_MAX_INPUT_CHARS', '25000'))
            self.max_input_chars_classificacao = int(os.getenv('OPENAI_MAX_INPUT_CHARS_CLASSIFICACAO', '4000'))
        
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
{transcricao[:self.max_input_chars_classificacao]}...

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
        # Tenta buscar do st.secrets primeiro (produção), depois do .env (local)
        api_key = None
        if st:
            try:
                api_key = st.secrets.get("OPENAI_API_KEY") or st.secrets.get("openai_api_key")
                if not api_key:
                    openai_section = st.secrets.get("openai") if hasattr(st.secrets, "get") else None
                    if openai_section:
                        api_key = openai_section.get("OPENAI_API_KEY") or openai_section.get("openai_api_key")
            except Exception:
                pass
        
        if not api_key:
            api_key = os.getenv('OPENAI_API_KEY')
        
        if not api_key:
            raise ValueError("OPENAI_API_KEY não configurada no arquivo .env ou secrets")

        self.client = OpenAI(api_key=api_key)
        
        # Busca configurações do modelo
        if st:
            try:
                openai_section = st.secrets.get("openai") if hasattr(st.secrets, "get") else None
                secrets_lookup = openai_section if openai_section else st.secrets
                self.model = secrets_lookup.get('OPENAI_MODEL') or secrets_lookup.get('openai_model', 'gpt-5.1')
                self.model_classificacao = secrets_lookup.get('OPENAI_MODEL_CLASSIFICACAO') or secrets_lookup.get('openai_model_classificacao', 'gpt-5-nano')
                self.temperature = float(secrets_lookup.get('OPENAI_TEMPERATURE') or secrets_lookup.get('openai_temperature', '0.2'))
                self.max_tokens = int(secrets_lookup.get('OPENAI_MAX_TOKENS') or secrets_lookup.get('openai_max_tokens', '8000'))
                self.max_input_chars = int(secrets_lookup.get('OPENAI_MAX_INPUT_CHARS') or secrets_lookup.get('openai_max_input_chars', '25000'))
                self.max_input_chars_classificacao = int(secrets_lookup.get('OPENAI_MAX_INPUT_CHARS_CLASSIFICACAO') or secrets_lookup.get('openai_max_input_chars_classificacao', '4000'))
            except Exception:
                self.model = os.getenv('OPENAI_MODEL', 'gpt-5.1')
                self.model_classificacao = os.getenv('OPENAI_MODEL_CLASSIFICACAO', 'gpt-5-nano')
                self.temperature = float(os.getenv('OPENAI_TEMPERATURE', '0.2'))
                self.max_tokens = int(os.getenv('OPENAI_MAX_TOKENS', '8000'))
                self.max_input_chars = int(os.getenv('OPENAI_MAX_INPUT_CHARS', '25000'))
                self.max_input_chars_classificacao = int(os.getenv('OPENAI_MAX_INPUT_CHARS_CLASSIFICACAO', '4000'))
        else:
            self.model = os.getenv('OPENAI_MODEL', 'gpt-5.1')
            self.model_classificacao = os.getenv('OPENAI_MODEL_CLASSIFICACAO', 'gpt-5-nano')
            self.temperature = float(os.getenv('OPENAI_TEMPERATURE', '0.2'))
            self.max_tokens = int(os.getenv('OPENAI_MAX_TOKENS', '8000'))
            self.max_input_chars = int(os.getenv('OPENAI_MAX_INPUT_CHARS', '25000'))
            self.max_input_chars_classificacao = int(os.getenv('OPENAI_MAX_INPUT_CHARS_CLASSIFICACAO', '4000'))

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
{transcricao[:1500]}
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
    {transcricao[:self.max_input_chars]}"""

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

        for tentativa in range(2):  # tenta 2 vezes antes de desistir
            try:
                response = self.client.chat.completions.create(
                    model=self.model_classificacao,
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
                    max_completion_tokens=1000
                )

                finish_reason = getattr(response.choices[0], 'finish_reason', None)
                content = (response.choices[0].message.content or "").strip()
                print(f"[classificacao] tentativa={tentativa} finish_reason={finish_reason} content_len={len(content)}")

                if not content:
                    print(f"[classificacao] conteúdo vazio — finish_reason={finish_reason}")
                    if tentativa == 0:
                        continue  # tenta novamente
                    # após 2 tentativas vazias: dialogo_incompleto é mais seguro que assumir venda
                    return {
                        'tipo': 'dados_insuficientes',
                        'motivo': f'Classificação não retornou resposta (finish_reason={finish_reason})',
                        'confianca': 0.3,
                        'deve_avaliar': False,
                        'tokens_usados': 0
                    }

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

            except json.JSONDecodeError:
                if tentativa == 0:
                    continue  # tenta novamente com JSON mal-formado
                return {
                    'tipo': 'venda',
                    'motivo': 'Classificação retornou JSON inválido (assumido venda)',
                    'confianca': 0.5,
                    'deve_avaliar': True,
                    'tokens_usados': 0
                }
            except Exception as e:
                return {
                    'tipo': 'outros',
                    'motivo': f'Erro ao classificar: {str(e)}',
                    'confianca': 0,
                    'deve_avaliar': False,
                    'tokens_usados': 0
                }

        # fallback final (nunca deveria chegar aqui)
        return {
            'tipo': 'venda',
            'motivo': 'Fallback após tentativas de classificação',
            'confianca': 0.5,
            'deve_avaliar': True,
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

            # Tipos que definitivamente não devem ser avaliados
            TIPOS_SKIP = {'ura', 'dados_insuficientes', 'dialogo_incompleto',
                          'ligacao_interna', 'chamada_errada', 'cancelamento', 'suporte'}

            if tipo in TIPOS_SKIP:
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
                    'lead_score': None,
                    'lead_classificacao': 'NA',
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
                max_completion_tokens=min(self.max_tokens, 2000)
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
                'produto_recomendado': resultado.get('recomendacao_final', {}).get('produto_principal', {}).get('produto', 'N/A'),
                'confianca_avaliacao': resultado.get('confianca_avaliacao'),
                'motivo_baixa_confianca': resultado.get('motivo_baixa_confianca')
            }

            return analise

        except json.JSONDecodeError as e:
            return {'erro': f'Erro ao decodificar JSON: {str(e)}', 'classificacao_ligacao': 'erro'}
        except Exception as e:
            return {'erro': f'Erro na análise: {type(e).__name__}: {str(e)}', 'classificacao_ligacao': 'erro'}

    # ──────────────────────────────────────────────
    # REAVALIAÇÃO OTIMIZADA (economia de tokens)
    # ──────────────────────────────────────────────

    def _heuristica_reavaliacao(self, transcricao: str) -> Optional[Dict]:
        """Heurísticas expandidas para reavaliação — sem limite de 255 chars."""
        texto = " ".join(transcricao.lower().split())

        if len(texto) < 15:
            return {'tipo': 'dados_insuficientes', 'motivo': 'Transcrição muito curta',
                    'confianca': 0.95, 'deve_avaliar': False}

        turnos_vendedor = texto.count("vendedor:")
        turnos_cliente = texto.count("cliente:")
        total_turnos = turnos_vendedor + turnos_cliente

        if turnos_vendedor == 0 or turnos_cliente == 0:
            return {'tipo': 'dados_insuficientes', 'motivo': 'Apenas um lado da conversa identificado',
                    'confianca': 0.8, 'deve_avaliar': False}

        if total_turnos < 6:
            return {'tipo': 'dialogo_incompleto', 'motivo': 'Conversa muito curta para avaliação',
                    'confianca': 0.85, 'deve_avaliar': False}

        padroes_interno = [
            "ramal", "sala de reunião", "sala de reuniao", "coordenação", "coordenacao",
            "secretaria", "responsável", "responsavel"
        ]
        padroes_produto = [
            "curso", "matrícula", "matricula", "turma", "aula",
            "presencial", "live", "ead", "mensalidade", "pagamento"
        ]
        if any(p in texto for p in padroes_interno) and not any(p in texto for p in padroes_produto):
            return {'tipo': 'ligacao_interna', 'motivo': 'Conversa interna entre colaboradores/ramais',
                    'confianca': 0.85, 'deve_avaliar': False}

        padroes_cancelamento = [
            "cancelamento", "cancelar", "reembolso", "estorno",
            "quero cancelar", "solicitar cancelamento"
        ]
        if any(p in texto for p in padroes_cancelamento):
            return {'tipo': 'cancelamento', 'motivo': 'Solicitação de cancelamento/reembolso',
                    'confianca': 0.9, 'deve_avaliar': False}

        padroes_ura = [
            "caixa postal", "correio de voz", "grave seu recado",
            "deixe a sua mensagem", "deixe sua mensagem", "não receber recados",
            "não está disponível", "após o sinal", "grave a sua mensagem"
        ]
        tem_dialogo = ("vendedor:" in texto) and ("cliente:" in texto)
        if not tem_dialogo and any(p in texto for p in padroes_ura):
            return {'tipo': 'ura', 'motivo': 'Mensagem automática/caixa postal detectada',
                    'confianca': 0.9, 'deve_avaliar': False}

        padroes_ocupado = [
            "estou ocupado", "ocupado agora", "não posso falar", "não posso falar agora",
            "estou dirigindo", "dirigindo", "no trânsito", "no transito",
            "ligue depois", "me liga depois", "retorno depois", "pode ligar depois"
        ]
        if any(p in texto for p in padroes_ocupado) and total_turnos < 12:
            return {'tipo': 'dialogo_incompleto', 'motivo': 'Cliente ocupado/dirigindo; conversa interrompida',
                    'confianca': 0.85, 'deve_avaliar': False}

        return None

    def _detectar_troca_interlocutores(self, transcricao: str) -> Dict:
        """Detecta possível troca de rótulos vendedor/cliente."""
        texto = transcricao.lower()
        if "vendedor:" not in texto or "cliente:" not in texto:
            return {"interlocutores_invertidos": False, "confianca_interlocutores": 0.0,
                    "motivo_interlocutores": "Rótulos ausentes ou incompletos"}

        vendor_keywords = [
            "curso", "matrícula", "matricula", "mensalidade", "parcelamento",
            "turma", "aulas", "horário", "horario", "unidade", "presencial",
            "live", "ead", "desconto", "promoção", "promocao", "pagamento",
            "boleto", "pix", "cartão", "cartao"
        ]

        def _contar(prefixo):
            linhas = [l for l in texto.splitlines() if l.strip().startswith(prefixo)]
            return sum(" ".join(linhas).count(k) for k in vendor_keywords) if linhas else 0

        sv, sc = _contar("vendedor:"), _contar("cliente:")
        if sc >= sv + 3:
            return {"interlocutores_invertidos": True, "confianca_interlocutores": 0.7,
                    "motivo_interlocutores": "Cliente tem mais termos típicos do vendedor"}
        return {"interlocutores_invertidos": False,
                "confianca_interlocutores": 0.6 if sv > 0 else 0.3,
                "motivo_interlocutores": "Distribuição de termos compatível com os rótulos"}

    def _criar_prompt_reavaliacao(self, transcricao: str, avaliacao_existente: str) -> str:
        """Prompt condensado para reavaliação — ~50% menos tokens que avaliação completa."""
        return f"""Você é avaliador sênior QA de ligações de vendas de curso preparatório para concursos (+3 décadas, +100 mil aprovações).
Prioridade: Presencial e Live (ticket ~R$2.000). EAD é secundário (ticket ~R$300).

REGRAS DA REAVALIAÇÃO:
1. INTERLOCUTORES: Rótulos "Vendedor:"/"Cliente:" podem estar invertidos.
   Identifique o vendedor pelo contexto (quem apresenta produto/benefícios/preço).
   NÃO penalize o vendedor por trechos com rótulos trocados.
2. WHATSAPP: Se houver menção a WhatsApp/zap/wpp, inclua em "observacoes": ["Vendedor sugeriu continuar no WhatsApp"]
3. SCORING — pesos obrigatórios:
   Vendedor (0-100): rapport(0-10), SPIN(0-30), valor_produto(0-20), gatilhos(0-10), objeções(0-10), fechamento(0-15), clareza(0-5)
   Lead (0-100): fit(0-30), intenção(0-30), orientação_valor(0-20), abertura(0-10), restrições_invertido(0-10)
   Lead class: A(80-100), B(60-79), C(40-59), D(0-39)
4. Use EVIDÊNCIAS da transcrição (citações até 15 palavras). Não invente.
5. Confiança: base 0.90. Descontos: <10 turnos(-0.20), ruído(-0.15), atores ambíguos(-0.15), concurso NI(-0.10), unilateral(-0.10), produto NM(-0.10). Min 0.30, Max 0.90.
6. Pontos fortes (3), melhorias (3), erro mais caro: use textos concisos e padronizados.

AVALIAÇÃO ANTERIOR (referência — ajuste conforme necessário):
{avaliacao_existente[:2500]}

TRANSCRIÇÃO DA LIGAÇÃO:
{transcricao[:self.max_input_chars]}

Retorne APENAS JSON válido:
{{
  "avaliacao_vendedor": {{
    "nota_final_0_100": 0,
    "notas_por_categoria": {{
      "rapport_0_10": 0, "spin_0_30": 0, "valor_produto_0_20": 0,
      "gatilhos_0_10": 0, "objecoes_0_10": 0, "fechamento_0_15": 0, "clareza_0_5": 0
    }},
    "pontos_fortes": [{{"categoria": "...", "ponto": "...", "evidencia": "..."}}],
    "melhorias": [{{"categoria": "...", "melhoria": "...", "evidencia": "..."}}],
    "erro_mais_caro": {{"categoria": "...", "descricao": "...", "evidencia": "..."}}
  }},
  "avaliacao_lead": {{
    "lead_score_0_100": 0,
    "classificacao": "A|B|C|D",
    "dimensoes": {{
      "fit_0_30": 0, "intencao_0_30": 0, "orientacao_valor_0_20": 0,
      "abertura_0_10": 0, "restricoes_invertido_0_10": 0
    }}
  }},
  "extracao": {{
    "concurso_area": "...",
    "dores_principais": ["..."],
    "restricoes": ["..."]
  }},
  "recomendacao_final": {{
    "produto_principal": {{"produto": "Presencial|Live|EAD|Passaporte|Smart|Não identificado"}}
  }},
  "confianca_avaliacao": 0.0,
  "motivo_baixa_confianca": "preencher se < 0.70"
}}"""

    def reavaliar_transcricao(self, transcricao: str, insight_ia_existente: str = None) -> Dict:
        """
        Reavalia transcrição com economia de tokens:
        - Layer 1: Heurísticas expandidas (0 tokens)
        - Layer 2: Classificação IA (modelo leve, ~300 tokens)
        - Layer 3: Prompt condensado de reavaliação (~50% menos tokens)
        """
        if not transcricao or len(transcricao.strip()) < 10:
            return {
                'erro': 'Transcrição muito curta ou vazia',
                'classificacao_ligacao': 'erro',
                'qualidade_atendimento': 'n/a'
            }

        def _observacoes_whatsapp():
            if any(p in transcricao.lower() for p in ["whatsapp", "zap", "wpp", "whats"]):
                return ["Vendedor sugeriu continuar no WhatsApp"]
            return []

        def _retorno_na(tipo, motivo, confianca, tokens=0):
            observacoes = _observacoes_whatsapp()
            return {
                'avaliacao_completa': json.dumps({
                    'classificacao_ligacao': tipo,
                    'motivo_classificacao': motivo,
                    'confianca_classificacao': confianca,
                    'observacoes': observacoes,
                    'reavaliacao': True
                }, ensure_ascii=False),
                'tokens_usados': tokens,
                'nota_vendedor': 0,
                'lead_score': None,
                'lead_classificacao': 'NA',
                'concurso_area': 'Não identificado',
                'produto_recomendado': 'N/A',
                'reavaliacao': True,
                'reavaliacao_motivo': motivo
            }

        # ── Layer 1: Heurísticas expandidas (0 tokens) ──
        heuristica = self._heuristica_reavaliacao(transcricao)
        if heuristica and not heuristica.get('deve_avaliar', False):
            return _retorno_na(heuristica['tipo'], heuristica['motivo'],
                               heuristica.get('confianca', 0), tokens=0)

        # ── Layer 2: Classificação IA (modelo leve) ──
        classificacao = self.classificar_ligacao(transcricao)
        tipo = classificacao.get('tipo', 'outros')
        motivo = classificacao.get('motivo', 'Não informado')
        confianca = classificacao.get('confianca', 0)

        TIPOS_SKIP = {'ura', 'dados_insuficientes', 'dialogo_incompleto',
                      'ligacao_interna', 'chamada_errada', 'cancelamento', 'suporte'}

        if tipo in TIPOS_SKIP:
            return _retorno_na(tipo, motivo, confianca,
                               tokens=classificacao.get('tokens_usados', 0))

        # ── Layer 3: Prompt condensado de reavaliação ──
        try:
            info_interloc = self._detectar_troca_interlocutores(transcricao)
            prompt = self._criar_prompt_reavaliacao(transcricao, insight_ia_existente or '{}')

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system",
                     "content": "Você é um especialista em análise de vendas educacionais. Retorna sempre JSON válido."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature,
                max_completion_tokens=min(self.max_tokens, 2000)
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
            resultado['interlocutores_invertidos'] = info_interloc.get('interlocutores_invertidos')
            resultado['confianca_interlocutores'] = info_interloc.get('confianca_interlocutores')
            resultado['motivo_interlocutores'] = info_interloc.get('motivo_interlocutores')
            resultado['reavaliacao'] = True

            observacoes = _observacoes_whatsapp()
            if observacoes:
                obs_existente = resultado.get('observacoes', [])
                if not isinstance(obs_existente, list):
                    obs_existente = []
                for o in observacoes:
                    if o not in obs_existente:
                        obs_existente.append(o)
                resultado['observacoes'] = obs_existente

            tokens_avaliacao = getattr(getattr(response, "usage", None), "total_tokens", None)
            tokens_classificacao = classificacao.get('tokens_usados')
            tokens_usados = None
            if tokens_avaliacao is not None or tokens_classificacao is not None:
                tokens_usados = (tokens_avaliacao or 0) + (tokens_classificacao or 0)

            return {
                'avaliacao_completa': json.dumps(resultado, ensure_ascii=False),
                'tokens_usados': tokens_usados,
                'nota_vendedor': resultado.get('avaliacao_vendedor', {}).get('nota_final_0_100', 0),
                'lead_score': resultado.get('avaliacao_lead', {}).get('lead_score_0_100', 0),
                'lead_classificacao': resultado.get('avaliacao_lead', {}).get('classificacao', 'D'),
                'concurso_area': resultado.get('extracao', {}).get('concurso_area', 'Não identificado'),
                'produto_recomendado': resultado.get('recomendacao_final', {}).get('produto_principal', {}).get('produto', 'N/A'),
                'confianca_avaliacao': resultado.get('confianca_avaliacao'),
                'reavaliacao': True,
                'reavaliacao_motivo': 'Reavaliação completa com prompt otimizado'
            }

        except json.JSONDecodeError as e:
            return {'erro': f'Erro ao decodificar JSON na reavaliação: {str(e)}',
                    'classificacao_ligacao': 'erro'}
        except Exception as e:
            return {'erro': f'Erro na reavaliação: {type(e).__name__}: {str(e)}',
                    'classificacao_ligacao': 'erro'}
