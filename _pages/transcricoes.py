import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import json
import re
from datetime import datetime
from utils.sql_loader import carregar_dados
from utils.transcricao_analyzer import TranscricaoOpenAIAnalyzer
from utils.transcricao_mysql_writer import atualizar_avaliacao_transcricao

def extrair_dados_json(df):
    """Extrai dados do JSON e cria novas colunas"""
    
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
    
    df['ramal'] = json_data.apply(lambda x: x.get('ramal', ''))
    df['uuid'] = json_data.apply(lambda x: x.get('uuid', ''))
    
    # Extrai agente do JSON com tratamento robusto
    def extrair_agente(json_obj):
        agente = json_obj.get('agente', '')
        # Trata valores vazios, None, ou apenas espaços
        if not agente or (isinstance(agente, str) and agente.strip() == ''):
            return 'Não identificado'
        return str(agente).strip()
    
    df['agente'] = json_data.apply(extrair_agente)
    df['data_ligacao_json'] = json_data.apply(lambda x: x.get('data', ''))
    df['hora_ligacao_json'] = json_data.apply(lambda x: x.get('hora', ''))
    df['telefone_json'] = json_data.apply(lambda x: x.get('telefone', ''))
    df['duracao'] = json_data.apply(lambda x: x.get('duracao', 0.0))
    df['tipo'] = json_data.apply(lambda x: x.get('tipo') or 'N/Informado')
    
    return df


def run_page():
    """Página de análise de transcrições de ligações"""
    
    TIMEZONE = 'America/Sao_Paulo'
    
    st.title("📞 Análise de Transcrições de Ligações")

    def _limpar_selecao(zerar_select_all: bool = False):
        st.session_state.transcricoes_selecionadas = []
        if zerar_select_all and "selecionar_todas" in st.session_state:
            st.session_state.pop("selecionar_todas", None)
        for key in list(st.session_state.keys()):
            if key.startswith("select_"):
                del st.session_state[key]
    
    # Carrega dados
    df = carregar_dados("consultas/transcricoes/transcricoes.sql")
    
    # Verifica se há dados antes de processar
    if df.empty:
        st.warning("⚠️ Não foi possível carregar os dados. Verifique a conexão com o banco de dados.")
        st.stop()
    
    # Pré-processamento
    df["data_ligacao"] = pd.to_datetime(df["data_ligacao"]).dt.tz_localize(TIMEZONE, ambiguous='infer')
    
    # Extrai dados do JSON
    df = extrair_dados_json(df)
    
    # === FILTROS SIDEBAR ===
    
    # Filtro: empresa
    empresas = df["empresa"].dropna().unique().tolist()
    
    if not empresas:
        st.warning("⚠️ Nenhuma empresa encontrada nos dados.")
        st.stop()
    
    empresa_selecionada = st.sidebar.radio(
        "Selecione uma empresa:",
        empresas,
        key="empresa_selecionada",
        on_change=lambda: _limpar_selecao(True)
    )
    df_filtrado_empresa = df[df["empresa"] == empresa_selecionada]
    
    # Filtro: data (padrão: últimos 7 dias)
    hoje_aware = pd.Timestamp.now(tz=TIMEZONE).date()
    data_inicio_padrao = hoje_aware - pd.Timedelta(days=7)
    
    periodo = st.sidebar.date_input(
        "Período de criação:",
        [data_inicio_padrao, hoje_aware],
        key="date_transcricoes",
        on_change=lambda: _limpar_selecao(True)
    )
    
    try:
        data_inicio_aware = pd.Timestamp(periodo[0], tz=TIMEZONE)
        data_fim_aware = pd.Timestamp(periodo[1], tz=TIMEZONE) + pd.Timedelta(days=1)
    except IndexError:
        st.warning("Por favor, selecione um período de datas.")
        st.stop()
    
    # Filtros adicionais
    etapas = sorted(df_filtrado_empresa["etapa"].dropna().unique())
    etapa_selecionada = st.sidebar.multiselect(
        "Selecione a etapa:",
        etapas,
        default=etapas,
        key="etapa_selecionada",
        on_change=lambda: _limpar_selecao(True)
    )
    
    modalidades = sorted(df_filtrado_empresa["modalidade"].dropna().unique())
    modalidade_selecionada = st.sidebar.multiselect(
        "Selecione a modalidade:",
        modalidades,
        default=modalidades,
        key="modalidade_selecionada",
        on_change=lambda: _limpar_selecao(True)
    )
    
    origens = sorted(df_filtrado_empresa["origem"].dropna().unique())
    origem_selecionada = st.sidebar.multiselect(
        "Selecione a origem:",
        origens,
        default=origens,
        key="origem_selecionada",
        on_change=lambda: _limpar_selecao(True)
    )
    
    tipo_ligacao = sorted(df_filtrado_empresa["tipo"].dropna().unique())
    tipo_ligacao_selecionada = st.sidebar.multiselect(
        "Selecione o tipo de ligação:",
        tipo_ligacao,
        default=tipo_ligacao,
        key="tipo_ligacao_selecionada",
        on_change=lambda: _limpar_selecao(True)
    )

    agentes = sorted(df_filtrado_empresa["agente"].fillna('Não identificado').unique())
    agente_selecionado = st.sidebar.multiselect(
        "Selecione o agente:",
        agentes,
        default=agentes,
        key="agente_selecionado",
        on_change=lambda: _limpar_selecao(True)
    )
    
    # === APLICAR FILTROS ===
    
    df_filtrado = df.copy()
    
    # Filtro empresa
    if empresa_selecionada:
        df_filtrado = df_filtrado[df_filtrado["empresa"] == empresa_selecionada]
    
    # Filtro de data sempre aplicado
    df_filtrado = df_filtrado[
        (df_filtrado["data_ligacao"] >= data_inicio_aware) &
        (df_filtrado["data_ligacao"] < data_fim_aware)
    ]
    
    # Filtros adicionais
    if etapa_selecionada:
        df_filtrado = df_filtrado[df_filtrado["etapa"].isin(etapa_selecionada) | df_filtrado["etapa"].isna()]
    
    if modalidade_selecionada:
        df_filtrado = df_filtrado[df_filtrado["modalidade"].isin(modalidade_selecionada) | df_filtrado["modalidade"].isna()]
    
    if tipo_ligacao_selecionada:
        df_filtrado = df_filtrado[df_filtrado["tipo"].isin(tipo_ligacao_selecionada)]
    
    if origem_selecionada:
        df_filtrado = df_filtrado[df_filtrado["origem"].isin(origem_selecionada) | df_filtrado["origem"].isna()]

    if agente_selecionado:
        df_filtrado = df_filtrado[df_filtrado["agente"].isin(agente_selecionado)]

    def _formatar_duracao(segundos) -> str:
        try:
            total = float(segundos)
        except (TypeError, ValueError):
            return "00:00"

        total = max(0.0, total)
        minutos = int(total // 60)
        segundos_rest = int(total % 60)
        if minutos >= 60:
            horas = minutos // 60
            minutos = minutos % 60
            return f"{horas:02d}:{minutos:02d}:{segundos_rest:02d}"
        return f"{minutos:02d}:{segundos_rest:02d}"

    def _cor_duracao(segundos) -> str:
        try:
            total = float(segundos)
        except (TypeError, ValueError):
            return "🔴"
        if total > 60:
            return "🔵"
        if total >= 30:
            return "🟡"
        return "🔴"

    def _renderizar_transcricao_linhas(transcricao: str):
        texto = str(transcricao)
        padrao = re.compile(r"(?i)\b(ura|vendedor|cliente)\s*:")
        matches = list(padrao.finditer(texto))
        if not matches:
            st.markdown(texto)
            return

        for idx, match in enumerate(matches):
            marcador = match.group(1).lower()
            inicio = match.end()
            fim = matches[idx + 1].start() if idx + 1 < len(matches) else len(texto)
            conteudo = texto[inicio:fim].strip()
            if not conteudo:
                continue

            if marcador == "ura":
                st.markdown(f"**URA:** {conteudo}")
            elif marcador == "vendedor":
                st.markdown(f"**Vendedor:** {conteudo}")
            elif marcador == "cliente":
                st.markdown(f"**Cliente:** {conteudo}")
            else:
                st.markdown(conteudo)

    def _transcricao_avaliavel(texto: str) -> bool:
        if not isinstance(texto, str):
            return False
        texto_norm = " ".join(texto.lower().split())

        tem_dialogo = ("vendedor:" in texto_norm) and ("cliente:" in texto_norm)
        padroes_ura = [
            "caixa postal",
            "correio de voz",
            "grave seu recado",
            "deixe a sua mensagem",
            "deixe sua mensagem",
            "não receber recados",
            "este número está configurado para não receber recados",
            "mensagem na caixa postal",
            "pessoa não está disponível",
            "não está disponível",
            "grave a sua mensagem",
            "após o sinal",
            "deixe outra mensagem"
        ]

        if not tem_dialogo and any(p in texto_norm for p in padroes_ura):
            return False

        if len(texto_norm) > 255:
            return True

        return False

    df_filtrado['avaliavel'] = df_filtrado['transcricao'].apply(_transcricao_avaliavel)
    
    # === MÉTRICAS PRINCIPAIS ===
    
    col2, col3, col4 = st.columns(3)
    
    with col2:
        com_transcricao = df_filtrado['transcricao'].notna().sum()
        st.metric("Transcrições", com_transcricao)

    with col3:
        avaliaveis = int(df_filtrado['avaliavel'].sum())
        st.metric("Transcrições Avaliáveis", avaliaveis)

    with col4:
        ruins = max(0, com_transcricao - avaliaveis)
        st.metric("Transcrições Ruins", ruins)
    
    
    # === GRÁFICOS ===
    
    # Transcrições por dia
    st.subheader("📊 Transcrições por Dia")
    df_diario = df_filtrado.groupby(df_filtrado["data_ligacao"].dt.date).size().reset_index()
    df_diario.columns = ["Data", "Total"]
    df_diario["Data"] = pd.to_datetime(df_diario["Data"]).dt.strftime('%d/%m')
    
    fig_diario = px.bar(
        df_diario,
        x="Data",
        y="Total",
        title="Transcrições por Dia",
        text_auto=True
    )
    st.plotly_chart(fig_diario, use_container_width=True)
    
    # Gráficos em 2 colunas
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Por Modalidade CRM")
        df_modalidade = df_filtrado.groupby("modalidade").size().reset_index(name='Quantidade')
        fig_modalidade = px.pie(
            df_modalidade,
            names="modalidade",
            values="Quantidade",
            hole=0.4
        )
        st.plotly_chart(fig_modalidade, use_container_width=True)
        
    
    with col2:
        st.subheader("Por Origem CRM")
        df_origem = df_filtrado.groupby("origem").size().reset_index(name='Quantidade')
        fig_origem = px.pie(
            df_origem,
            names="origem",
            values="Quantidade"
        )
        st.plotly_chart(fig_origem, use_container_width=True)
        
    st.subheader("Por Tipo de Ligação")
    df_tipo_ligacao = df_filtrado.groupby("tipo").size().reset_index(name='Quantidade')
    fig_tipo_ligacao = px.bar(
        df_tipo_ligacao,
        x="tipo",
        y="Quantidade",
        text_auto=True
    )
    st.plotly_chart(fig_tipo_ligacao, use_container_width=True)
    
    
    # === TABELA DE DADOS COM AVALIAÇÃO ===
    
    st.subheader("📋 Detalhamento das Transcrições")
    
    # Inicializa IA
    ia_analyzer = TranscricaoOpenAIAnalyzer()

    if 'ultimo_erro_mysql' not in st.session_state:
        st.session_state.ultimo_erro_mysql = None
    

    # Estatísticas de avaliações (MySQL)
    total_avaliacoes = 0
    if 'insight_ia' in df_filtrado.columns:
        total_avaliacoes = int(
            df_filtrado['insight_ia']
            .fillna('')
            .astype(str)
            .str.strip()
            .ne('')
            .sum()
        )
    col_stat1, col_stat2, col_stat4 = st.columns(3)
    with col_stat1:
        st.metric("Avaliações Realizadas", total_avaliacoes)
    with col_stat2:
        st.metric("Base", "MySQL")
    with col_stat4:
        total_avaliaveis = len(df_filtrado[(df_filtrado['transcricao'].notna()) & (df_filtrado['avaliavel'] == True)])
        nao_avaliadas = total_avaliaveis - total_avaliacoes
        st.metric("Não Avaliadas", max(0, nao_avaliadas))

    if st.session_state.ultimo_erro_mysql:
        st.error(st.session_state.ultimo_erro_mysql)
        if st.button("Limpar erro", key="limpar_erro_mysql"):
            st.session_state.ultimo_erro_mysql = None
    
    # Tabs para visualização
    tab1, tab2, tab3 = st.tabs(["📊 Avaliar Transcrições", "✅ Avaliações Realizadas", "📤 Exportar"])
    
    with tab1:
        st.subheader("Transcrições Disponíveis")

        filtro_avaliavel = st.sidebar.radio(
            "Exibir transcrições:",
            ["Avaliáveis", "Não avaliáveis", "Todas"],
            index=0,
            key="filtro_avaliavel",
            on_change=lambda: _limpar_selecao(True)
        )
        
        # Filtro: apenas com transcrição
        df_com_transcricao = df_filtrado[df_filtrado['transcricao'].notna()].sort_values('data_ligacao', ascending=False).reset_index(drop=True)

        if filtro_avaliavel == "Avaliáveis":
            df_com_transcricao = df_com_transcricao[df_com_transcricao['avaliavel'] == True]
        elif filtro_avaliavel == "Não avaliáveis":
            df_com_transcricao = df_com_transcricao[df_com_transcricao['avaliavel'] == False]
        
        # Adiciona coluna de status de avaliação
        if 'insight_ia' in df_com_transcricao.columns:
            df_com_transcricao['avaliada'] = (
                df_com_transcricao['insight_ia']
                .fillna('')
                .astype(str)
                .str.strip()
                .ne('')
            )
        else:
            df_com_transcricao['avaliada'] = False
        
        # Métricas
        total_transcricoes = len(df_com_transcricao)
        ja_avaliadas = df_com_transcricao['avaliada'].sum()
        pendentes = total_transcricoes - ja_avaliadas
        
        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            st.metric("Total", total_transcricoes)
        with col_m2:
            st.metric("Avaliadas", ja_avaliadas)
        with col_m3:
            st.metric("Pendentes", pendentes)
        
        # Inicializa estado de seleção
        if 'transcricoes_selecionadas' not in st.session_state:
            st.session_state.transcricoes_selecionadas = []

        # Tabela interativa
        st.divider()
        
        # Preparar dados para exibição
        colunas_exibir = ['data_ligacao', 'nome_lead', 'empresa', 'telefone_lead', 'etapa', 'modalidade', 'tipo', 'duracao', 'avaliavel', 'avaliada', 'transcricao', 'agente']
        if 'transcricao_id' in df_com_transcricao.columns:
            colunas_exibir.append('transcricao_id')
        if 'insight_ia' in df_com_transcricao.columns:
            colunas_exibir.append('insight_ia')
        if 'evaluation_ia' in df_com_transcricao.columns:
            colunas_exibir.append('evaluation_ia')

        df_exibir = df_com_transcricao[colunas_exibir].copy()
        df_exibir['data_ligacao'] = df_exibir['data_ligacao'].dt.strftime('%d/%m/%Y %H:%M')
        df_exibir['status'] = df_exibir['avaliada'].apply(lambda x: '✅ Avaliada' if x else '⏳ Pendente')
        df_exibir['selo_avaliavel'] = df_exibir['avaliavel'].apply(lambda x: '🟢 Avaliável' if x else '🔴 Não avaliável')
        df_exibir['duracao_fmt'] = df_exibir['duracao'].apply(_formatar_duracao)
        df_exibir['duracao_cor'] = df_exibir['duracao'].apply(_cor_duracao)
        
        # Filtro por status
        filtro_status = st.radio(
            "Filtrar por:",
            ["Todas", "Apenas Pendentes", "Apenas Avaliadas"],
            horizontal=True,
            key="filtro_status",
            on_change=lambda: _limpar_selecao(True)
        )
        
        if filtro_status == "Apenas Pendentes":
            df_exibir = df_exibir[df_exibir['avaliada'] == False]
        elif filtro_status == "Apenas Avaliadas":
            df_exibir = df_exibir[df_exibir['avaliada'] == True]

        
        st.write(f"**Exibindo:** {len(df_exibir)} transcrições")
        
        if len(df_exibir) == 0:
            st.info("Nenhuma transcrição encontrada com os filtros aplicados.")
        else:
            col_p1, col_p2, col_p3 = st.columns([2, 1, 1])
            with col_p1:
                page_size = st.selectbox("Itens por página:", [25, 50, 100], index=1)
            total_pages = max(1, (len(df_exibir) + page_size - 1) // page_size)
            with col_p2:
                pagina = st.number_input("Página", min_value=1, max_value=total_pages, value=1, step=1)
            with col_p3:
                selecionar_todas = st.checkbox("Selecionar todas", key="selecionar_todas")
            inicio = (pagina - 1) * page_size
            fim = inicio + page_size

            # Renderizar lista amigável
            pagina_df = df_exibir.iloc[inicio:fim]
            if selecionar_todas:
                ids_pagina = pagina_df[pagina_df['avaliada'] == False]['transcricao_id'].dropna().tolist()
                for tid in ids_pagina:
                    if tid not in st.session_state.transcricoes_selecionadas:
                        st.session_state.transcricoes_selecionadas.append(tid)
            else:
                ids_pagina = set(pagina_df['transcricao_id'].dropna().tolist())
                st.session_state.transcricoes_selecionadas = [
                    tid for tid in st.session_state.transcricoes_selecionadas if tid not in ids_pagina
                ]

            for idx, row in pagina_df.iterrows():
                with st.container(border=True):
                    topo1, topo2, topo3 = st.columns([5, 2, 1])
                    with topo1:
                        st.markdown(f"**{row['nome_lead']}**")
                        agente_nome = row.get('agente', 'Não identificado')
                        st.caption(f"{row['data_ligacao']} • {row['empresa']} • {agente_nome} • Tel: {row['telefone_lead']}")
                    with topo2:
                        st.write(f"{row['duracao_cor']} {row['duracao_fmt']} | {row['selo_avaliavel']}")
                        st.caption(f"Etapa: {row['etapa']} • Modalidade: {row['modalidade']} • {row['tipo']}")
                    with topo3:
                        st.write(row['status'])
                        if not row['avaliada']:
                            transcricao_id = row.get('transcricao_id')
                            key = f"select_{idx}_{transcricao_id}"
                            if st.checkbox("Selecionar", key=key, value=transcricao_id in st.session_state.transcricoes_selecionadas):
                                if transcricao_id not in st.session_state.transcricoes_selecionadas:
                                    st.session_state.transcricoes_selecionadas.append(transcricao_id)
                            else:
                                if transcricao_id in st.session_state.transcricoes_selecionadas:
                                    st.session_state.transcricoes_selecionadas.remove(transcricao_id)

                    with st.expander("📝 Transcrição Completa", expanded=False):
                        with st.container(height=220):
                            _renderizar_transcricao_linhas(row['transcricao'])
        
        # Ações em lote
        st.divider()
        
        num_selecionadas = len(st.session_state.transcricoes_selecionadas)
        
        col_acao1, col_acao2, col_acao3 = st.columns([2, 1, 1])
        
        with col_acao1:
            st.write(f"**{num_selecionadas} transcrição(ões) selecionada(s)**")
        
        with col_acao2:
            if num_selecionadas > 0:
                if st.button("🗑️ Limpar Seleção"):
                    _limpar_selecao(False)
                    st.rerun()
        
        with col_acao3:
            if num_selecionadas > 0:
                if st.button(f"🤖 Avaliar {num_selecionadas} Selecionada(s)", type="primary"):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    # Filtrar apenas as transcrições selecionadas
                    df_selecionadas = df_com_transcricao[df_com_transcricao['transcricao_id'].isin(st.session_state.transcricoes_selecionadas)]
                    
                    sucesso = 0
                    erros = 0
                    
                    for idx, (i, row) in enumerate(df_selecionadas.iterrows()):
                        nome_lead = row.get('nome_lead', 'Lead sem nome')
                        status_text.text(f"Avaliando {idx + 1}/{num_selecionadas}: {nome_lead}...")
                        
                        try:
                            # Validação mínima - apenas verifica se tem transcrição
                            if pd.isna(row.get('transcricao')) or len(str(row.get('transcricao', '')).strip()) < 10:
                                st.warning(f"Transcrição insuficiente: {nome_lead}")
                                erros += 1
                                continue
                            
                            # Executa análise
                            analise = ia_analyzer.analisar_transcricao(row['transcricao'])
                            
                            # Debug: mostra resultado da análise
                            print(f"Análise retornada: {list(analise.keys())}")
                            
                            # Verifica se houve erro na análise
                            if 'erro' in analise:
                                print(f"Erro detalhado da análise: {analise.get('erro')}")
                                st.error(f"Erro na análise de {nome_lead}: {analise['erro']}")
                                erros += 1
                                continue
                            
                            # Prepara dados - oportunidade_id é opcional
                            oportunidade_id = row.get('oportunidade')
                            if pd.notna(oportunidade_id):
                                oportunidade_id = int(oportunidade_id)
                            else:
                                oportunidade_id = None
                            
                            transcricao_id = row.get('transcricao_id')
                            insight_ia = analise.get('avaliacao_completa')
                            evaluation_ia = analise.get('nota_vendedor')
                            atualizado = False
                            erro_mysql = None
                            if insight_ia is not None:
                                atualizado, erro_mysql = atualizar_avaliacao_transcricao(
                                    transcricao_id=transcricao_id,
                                    insight_ia=insight_ia,
                                    evaluation_ia=evaluation_ia,
                                )

                            if atualizado:
                                sucesso += 1
                                st.success(f"✅ {nome_lead} avaliado!", icon="✅")
                            else:
                                detalhe = f" ({erro_mysql})" if erro_mysql else ""
                                print(f"Erro MySQL ao salvar {nome_lead}{detalhe}")
                                st.error(f"❌ Erro ao salvar avaliação no MySQL de {nome_lead}{detalhe}")
                                st.session_state.ultimo_erro_mysql = f"Erro MySQL: {nome_lead}{detalhe}"
                                erros += 1
                            
                        except Exception as e:
                            st.error(f"Erro ao avaliar {nome_lead}: {str(e)}")
                            erros += 1
                        
                        progress_bar.progress((idx + 1) / num_selecionadas)
                    
                    status_text.empty()
                    progress_bar.empty()
                    
                    # Limpa seleção e atualiza
                    st.session_state.transcricoes_selecionadas = []
                    carregar_dados.clear()
                    
                    # Resultado final
                    if sucesso > 0:
                        st.success(f"✅ {sucesso} avaliação(ões) concluída(s) com sucesso!")
                    if erros > 0:
                        st.warning(f"⚠️ {erros} erro(s) durante o processo")
                    
                    st.rerun()
            
            # Preview - removido, já mostramos na tabela acima
    
    with tab2:
        st.subheader("Avaliações Concluídas")
        
        avaliacoes = df_filtrado[df_filtrado['transcricao'].notna()].copy()
        if 'insight_ia' in avaliacoes.columns:
            avaliacoes = avaliacoes[
                avaliacoes['insight_ia']
                .fillna('')
                .astype(str)
                .str.strip()
                .ne('')
            ]
        else:
            avaliacoes = avaliacoes.iloc[0:0]

        if avaliacoes.empty:
            st.info("Nenhuma avaliação realizada ainda.")
        else:
            def _parse_insight(insight_value):
                if insight_value is None:
                    return {}
                try:
                    return json.loads(insight_value)
                except (TypeError, json.JSONDecodeError):
                    return {}

            avaliacoes['insight_json'] = avaliacoes['insight_ia'].apply(_parse_insight)
            avaliacoes['lead_classificacao'] = avaliacoes['insight_json'].apply(
                lambda x: x.get('avaliacao_lead', {}).get('classificacao', 'N/A')
            )
            avaliacoes['lead_score'] = avaliacoes['insight_json'].apply(
                lambda x: x.get('avaliacao_lead', {}).get('lead_score_0_100', 0)
            )
            if 'evaluation_ia' in avaliacoes.columns:
                avaliacoes['nota_vendedor'] = pd.to_numeric(avaliacoes['evaluation_ia'], errors='coerce').fillna(0)
            else:
                avaliacoes['nota_vendedor'] = avaliacoes['insight_json'].apply(
                    lambda x: x.get('avaliacao_vendedor', {}).get('nota_final_0_100', 0)
                )

            # Filtros
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                classificacoes = avaliacoes['lead_classificacao'].unique().tolist()
                filtro_class = st.multiselect("Filtrar por classificação do lead:", classificacoes, default=classificacoes)
            with col_f2:
                min_nota = st.slider("Nota mínima do vendedor:", 0, 100, 0)

            avaliacoes_filtradas = avaliacoes[
                (avaliacoes['lead_classificacao'].isin(filtro_class)) &
                (avaliacoes['nota_vendedor'] >= min_nota)
            ]
            
            st.write(f"**Exibindo:** {len(avaliacoes_filtradas)} avaliações")
            
            # Visualização por linha
            st.subheader("Visualizar Avaliações")

            for _, row in avaliacoes_filtradas.iterrows():
                nome = row.get('nome_lead', 'Lead sem nome')
                oportunidade_id = row.get('oportunidade')
                titulo = f"#{int(oportunidade_id)} - {nome}" if pd.notna(oportunidade_id) else f"Sem oportunidade - {nome}"

                nota_vendedor = row.get('nota_vendedor', 0)
                lead_score = row.get('lead_score', 0)
                lead_classificacao = row.get('lead_classificacao', 'N/A')

                with st.container(border=True):
                    topo1, topo2, topo3, topo4 = st.columns([4, 1, 1, 1])
                    with topo1:
                        st.markdown(f"**{titulo}**")
                        empresa = row.get('empresa', 'N/A')
                        agente_nome = row.get('agente', 'Não identificado')
                        st.caption(f"Empresa: {empresa} • Agente: {agente_nome}")
                    with topo2:
                        st.metric("Nota", nota_vendedor)
                    with topo3:
                        st.metric("Lead", lead_score)
                    with topo4:
                        st.metric("Class", lead_classificacao)

                    with st.expander("Ver Avaliação", expanded=False):
                        try:
                            avaliacao_json = row.get('insight_json') or {}

                            if row.get('transcricao'):
                                st.subheader("📝 Transcrição")
                                with st.container(height=220):
                                    _renderizar_transcricao_linhas(row['transcricao'])

                            melhorias = avaliacao_json.get('avaliacao_vendedor', {}).get('melhorias', [])
                            if melhorias:
                                st.subheader("🛠️ Pontos de Melhoria")
                                for item in melhorias:
                                    melhoria = item.get('melhoria', '')
                                    como_fazer = item.get('como_fazer', '')
                                    evidencia = item.get('evidencia_do_gap', '')
                                    st.write(f"• **{melhoria}**")
                                    if como_fazer:
                                        st.caption(f"Como fazer: {como_fazer}")
                                    if evidencia:
                                        st.caption(f"Evidência: {evidencia}")

                            col_s1, col_s2, col_s3 = st.columns(3)
                            with col_s1:
                                nota_vend = avaliacao_json.get('avaliacao_vendedor', {}).get('nota_final_0_100', 0)
                                st.metric("Nota do Vendedor", f"{nota_vend}/100")
                            with col_s2:
                                score_lead = avaliacao_json.get('avaliacao_lead', {}).get('lead_score_0_100', 0)
                                st.metric("Score do Lead", f"{score_lead}/100")
                            with col_s3:
                                class_lead = avaliacao_json.get('avaliacao_lead', {}).get('classificacao', 'N/A')
                                st.metric("Classificação", class_lead)

                            with st.expander("🔍 Ver Avaliação Completa (JSON)"):
                                st.json(avaliacao_json)

                            ac1, ac2 = st.columns([1, 3])
                            with ac1:
                                if st.button("🔁 Reavaliar", key=f"reavaliar_{row.name}"):
                                    if not row.get('transcricao'):
                                        st.error("Transcrição não encontrada para reavaliar.")
                                    else:
                                        analise = ia_analyzer.analisar_transcricao(row['transcricao'])
                                        if 'erro' in analise:
                                            st.error(f"Erro na reavaliação: {analise['erro']}")
                                        else:
                                            transcricao_id = row.get('transcricao_id')
                                            insight_ia = analise.get('avaliacao_completa')
                                            evaluation_ia = analise.get('nota_vendedor')
                                            atualizado, erro_mysql = atualizar_avaliacao_transcricao(
                                                transcricao_id=transcricao_id,
                                                insight_ia=insight_ia,
                                                evaluation_ia=evaluation_ia,
                                            )
                                            if atualizado:
                                                carregar_dados.clear()
                                                st.success("Reavaliação concluída!")
                                                st.rerun()
                                            else:
                                                detalhe = f" ({erro_mysql})" if erro_mysql else ""
                                                print(f"Erro MySQL na reavaliação {nome}{detalhe}")
                                                st.error(f"Erro ao salvar reavaliação no MySQL{detalhe}")
                                                st.session_state.ultimo_erro_mysql = f"Erro MySQL (reavaliação): {nome}{detalhe}"
                            with ac2:
                                comentario = st.text_area(
                                    "Comentários adicionais:",
                                    value=row.get('comentarios_usuario', ''),
                                    key=f"comentario_av_{row.name}"
                                )
                                if st.button("💾 Salvar Comentário", key=f"save_av_{row.name}"):
                                    st.info("Comentários não são salvos no MySQL neste fluxo.")
                        except json.JSONDecodeError:
                            st.error("Erro ao decodificar avaliação")

            # Métricas e gráficos
            st.divider()
            st.subheader("📈 Métricas e Gráficos")

            com_nota = int((avaliacoes_filtradas['nota_vendedor'] > 0).sum())
            sem_nota = int((avaliacoes_filtradas['nota_vendedor'] <= 0).sum())
            nota_media_agente = (
                avaliacoes_filtradas.groupby('agente')['nota_vendedor']
                .mean()
                .dropna()
                .mean()
            )
            nota_media_agentes = avaliacoes_filtradas['nota_vendedor'].mean()
            nota_media_lead = avaliacoes_filtradas['lead_score'].mean()

            col_g1, col_g2, col_g3, col_g4 = st.columns(4)
            with col_g1:
                st.metric("Com Nota", com_nota)
            with col_g2:
                st.metric("Sem Nota", sem_nota)
            with col_g3:
                st.metric("Nota média agente", f"{nota_media_agente:.1f}" if pd.notna(nota_media_agente) else "0")
            with col_g4:
                st.metric("Média lead", f"{nota_media_lead:.1f}" if pd.notna(nota_media_lead) else "0")

            col_g5, col_g6 = st.columns(2)
            with col_g5:
                df_class = (
                    avaliacoes_filtradas['lead_classificacao']
                    .fillna('N/A')
                    .value_counts()
                    .reset_index()
                )
                df_class.columns = ['classificacao', 'quantidade']
                fig_class = px.pie(
                    df_class,
                    names='classificacao',
                    values='quantidade',
                    title='Classificação do Lead'
                )
                st.plotly_chart(fig_class, use_container_width=True)

            with col_g6:
                df_tipo = (
                    avaliacoes_filtradas.groupby('tipo')
                    .agg(nota_media=('nota_vendedor', 'mean'), quantidade=('nota_vendedor', 'size'))
                    .reset_index()
                )
                df_tipo['label'] = df_tipo.apply(
                    lambda x: f"{int(x['quantidade'])} • {x['nota_media']:.1f}" if pd.notna(x['quantidade']) else "0",
                    axis=1
                )
                fig_tipo = px.bar(
                    df_tipo,
                    x='tipo',
                    y='nota_media',
                    text='label',
                    title='Média de Nota por Tipo (Qtde Avaliações)'
                )
                st.plotly_chart(fig_tipo, use_container_width=True)

            df_agente = (
                    avaliacoes_filtradas.groupby('agente')
                    .agg(nota_media=('nota_vendedor', 'mean'), quantidade=('nota_vendedor', 'size'))
                    .reset_index()
                )
            df_agente['label'] = df_agente.apply(
                    lambda x: f"{int(x['quantidade'])} - NM {x['nota_media']:.1f}" if pd.notna(x['quantidade']) else "0",
                    axis=1
                )
            fig_agente = px.bar(
                    df_agente,
                    y='agente',
                    x='nota_media',
                    text='label',
                    title='Média de Nota por Agente (Qtde Avaliações)',
                    orientation='h'
                )
            st.plotly_chart(fig_agente, use_container_width=True)

    
    with tab3:
        st.subheader("📤 Exportar Avaliações")
        
        col_export1, col_export2 = st.columns(2)
        
        with col_export1:
            if st.button("Baixar Todas Avaliações (CSV)"):
                if not avaliacoes.empty:
                    csv = avaliacoes.to_csv(index=False)
                    st.download_button(
                        label="⬇️ Download CSV",
                        data=csv,
                        file_name=f"avaliacoes_transcricoes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("Nenhuma avaliação disponível")
        
        with col_export2:
            if st.button("Baixar Pendentes de Sincronização"):
                st.info("Sincronização não aplicável com MySQL direto.")


