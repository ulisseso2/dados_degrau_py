# _pages/custo_aula.py

import streamlit as st
import pandas as pd
import io
from datetime import datetime
from st_aggrid import AgGrid, GridOptionsBuilder
from st_aggrid.shared import JsCode

# Adiciona o diretório raiz ao path para encontrar os módulos
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.sql_loader import carregar_dados

# ==============================================================================
# 1. FUNÇÕES AUXILIARES
# ==============================================================================
def formatar_reais(valor):
    """Formata um número para o padrão monetário brasileiro."""
    if pd.isna(valor) or valor == 0: return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ==============================================================================
# 2. FUNÇÃO PRINCIPAL DA PÁGINA (run_page)
# ==============================================================================
def run_page():
    st.title("💰 Dashboard de Custo por Aula")
    TIMEZONE = 'America/Sao_Paulo'

    # --- 1. CARREGAMENTO E PREPARAÇÃO DOS DADOS ---
    # Use o caminho correto para sua nova query SQL
    df = carregar_dados("consultas/turmas/custo_aula.sql") 

    # Converte tipos de dados e fuso horário em um só lugar
    df['data_aula'] = pd.to_datetime(df['data_aula'], errors='coerce').dt.tz_localize(TIMEZONE, ambiguous='infer')
    df['valor_rateio_aula'] = pd.to_numeric(df['valor_rateio_aula'], errors='coerce')
    df['carga_horaria_decimal'] = pd.to_numeric(df['carga_horaria_decimal'], errors='coerce')
    df['inicio_grade'] = pd.to_datetime(df['inicio_grade'], errors='coerce').dt.tz_localize(TIMEZONE, ambiguous='infer')
    df['data_prevista'] = pd.to_datetime(df['data_prevista'], errors='coerce')
    df['turno'] = df['turno'].astype(str).replace('None', '')
    df['possui_grade'] = df['possui_grade'].astype(str).replace('None', '')
    
    # --- 2. FILTROS NA BARRA LATERAL ---
    st.sidebar.header("Filtros de Análise")

    empresas_list = df["empresa"].dropna().unique().tolist()
    empresa_selecionada = st.sidebar.radio("Selecione uma empresa:", empresas_list, index=0)
    df_opcoes_empresa = df[df["empresa"] == empresa_selecionada]

    # Pega a data de "hoje" já com o fuso horário correto
    hoje_aware = pd.Timestamp.now(tz=TIMEZONE).date()

    # Define os limites gerais do calendário (o mínimo e máximo que o usuário pode escolher)
    data_min_geral = df_opcoes_empresa['data_aula'].min().date() if not df_opcoes_empresa.empty else hoje_aware
    data_max_geral = df_opcoes_empresa['data_aula'].max().date() if not df_opcoes_empresa.empty else hoje_aware

    # Calcula o primeiro dia do mês atual para ser o início do período padrão
    primeiro_dia_mes_atual = hoje_aware.replace(day=1)

    # Garante que a data de início padrão não seja anterior à data mínima disponível nos dados
    data_inicio_padrao = max(primeiro_dia_mes_atual, data_min_geral)

    # Define o período padrão que será exibido ao carregar a página
    periodo = st.sidebar.date_input(
        "Período da Aula:",
        value=[data_inicio_padrao, hoje_aware], # <-- A MUDANÇA PRINCIPAL ESTÁ AQUI
        min_value=data_min_geral,
        max_value=data_max_geral,
        key="custo_aula_date_range" # Adiciona uma chave única para o widget
    )

    with st.sidebar.expander("Filtros Adicionais", expanded=True):
        # --- Nível 2: Unidade (dependente da empresa) ---
        unidades_list = sorted(df_opcoes_empresa['unidade'].dropna().unique())
        unidades_selecionadas = st.multiselect("Unidade:", unidades_list, default=unidades_list)
        
        # DataFrame intermediário filtrado também pela unidade
        df_opcoes_unidade = df_opcoes_empresa[df_opcoes_empresa['unidade'].isin(unidades_selecionadas)]

        # --- Nível 3: Professor (dependente da unidade) ---
        professores_list = sorted(df_opcoes_unidade['professor'].dropna().unique())
        professores_selecionados = st.multiselect("Professor:", professores_list, default=professores_list)
        
        # --- Nível 3: Curso Venda (também dependente da unidade) ---
        cursos_venda_list = sorted(df_opcoes_unidade['curso_venda'].dropna().unique())
        cursos_venda_selecionados = st.multiselect("Curso Venda:", cursos_venda_list, default=cursos_venda_list)

        # Outros filtros que podem ser úteis
        status_list = sorted(df_opcoes_unidade['status_aula'].dropna().unique())
        status_selecionado = st.multiselect("Status da Aula:", status_list, default=["Ativo"])

    # --- 3. APLICAÇÃO FINAL DOS FILTROS ---
    try:
        data_inicio_aware = pd.Timestamp(periodo[0], tz=TIMEZONE)
        data_fim_aware = pd.Timestamp(periodo[1], tz=TIMEZONE) + pd.Timedelta(days=1)
    except IndexError:
        st.warning("👈 Por favor, selecione um período de datas.")
        st.stop()

    df_filtrado = df[
        (df['empresa'] == empresa_selecionada) &
        (df['data_aula'] >= data_inicio_aware) &
        (df['data_aula'] < data_fim_aware) &
        (df['unidade'].isin(unidades_selecionadas)) &
        (df['professor'].isin(professores_selecionados)) &
        (df['curso_venda'].isin(cursos_venda_selecionados)) &
        (df['status_aula'].isin(status_selecionado))
    ].copy()

    st.info(f"Exibindo dados de **{periodo[0].strftime('%d/%m/%Y')}** a **{periodo[1].strftime('%d/%m/%Y')}**")

    # --- 4. EXIBIÇÃO DAS ANÁLISES ---
    if df_filtrado.empty:
        st.warning("Não há dados disponíveis para os filtros selecionados.")
        st.stop()

    st.header("📊 Resumo dos Custos")
    col1, col2, col3 = st.columns(3)
    
    total_aulas = df_filtrado['aula_id'].nunique()
    valor_previsto = df_filtrado['valor_rateio_aula'].sum()
    custo_medio = (valor_previsto / total_aulas) if total_aulas > 0 else 0

    col1.metric("Total de Aulas Únicas", f"{total_aulas:,}".replace(",", "."))
    col2.metric("Custo Previsto no Período", formatar_reais(valor_previsto))
    col3.metric("Custo Médio por Aula", formatar_reais(custo_medio))
    st.divider()

    st.header("Detalhamento das Aulas")
    
    colunas_para_exibir = [
        'data_aula', 'unidade', 'turma_nome', 'curso', 'professor', 'status_aula', 'carga_horaria_decimal', 'valor_rateio_aula'
    ]
    df_exibicao = df_filtrado[colunas_para_exibir].sort_values(by='data_aula', ascending=False)
    
    st.dataframe(
        df_exibicao,
        use_container_width=True,
        hide_index=True,
        column_config={
            "data_aula": st.column_config.DatetimeColumn("Data da Aula", format="DD/MM/YYYY"),
            "carga_horaria_decimal": st.column_config.NumberColumn("Horas", format="%.2f"),
            "valor_rateio_aula": st.column_config.NumberColumn("Custo Previsto (R$)", format="R$ %.2f")
        }
    )

    # --- Exportar para Excel ---
    tabela_para_exportar = df_exibicao.copy()
    tabela_para_exportar['data_aula'] = tabela_para_exportar['data_aula'].dt.tz_localize(None)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        tabela_para_exportar.to_excel(writer, index=False, sheet_name='Custo por Aula')
    buffer.seek(0)
    st.download_button(
        label="📥 Exportar para Excel",
        data=buffer,
        file_name="custo_por_aula.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_custo_aula"
    )

    st.divider()

    # --- 5. TABELA AGRUPADA POR CURSO ---
    st.header("📚 Custo Previsto por Curso")
    cursos_disponiveis = sorted(df_filtrado['curso'].dropna().unique())
    cursos_filtro = st.multiselect(
        "Filtrar cursos:", cursos_disponiveis, default=cursos_disponiveis, key="filtro_curso_agrupado"
    )
    df_por_curso = (
        df_filtrado[df_filtrado['curso'].isin(cursos_filtro)]
        .groupby('curso', dropna=False)
        .agg(
            total_aulas=('aula_id', 'nunique'),
            total_horas=('carga_horaria_decimal', 'sum'),
            custo_previsto=('valor_rateio_aula', 'sum')
        )
        .reset_index()
        .sort_values(by='custo_previsto', ascending=False)
    )
    st.dataframe(
        df_por_curso,
        use_container_width=True,
        hide_index=True,
        column_config={
            "curso": "Curso",
            "total_aulas": st.column_config.NumberColumn("Total de Aulas"),
            "total_horas": st.column_config.NumberColumn("Total de Horas", format="%.2f"),
            "custo_previsto": st.column_config.NumberColumn("Custo Previsto (R$)", format="R$ %.2f")
        }
    )

    buffer_curso = io.BytesIO()
    with pd.ExcelWriter(buffer_curso, engine='xlsxwriter') as writer:
        df_por_curso.to_excel(writer, index=False, sheet_name='Custo por Curso')
    buffer_curso.seek(0)
    st.download_button(
        label="📥 Exportar Cursos para Excel",
        data=buffer_curso,
        file_name="custo_por_curso.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_custo_curso"
    )

    st.divider()

    # --- 6. TABELA AGRUPADA POR TURMA ---
    st.header("🏫 Custo Previsto por Turma")
    df_por_turma = (
        df_filtrado
        .groupby(['turma_nome', 'curso'], dropna=False)
        .agg(
            total_aulas=('aula_id', 'nunique'),
            total_horas=('carga_horaria_decimal', 'sum'),
            custo_previsto=('valor_rateio_aula', 'sum')
        )
        .reset_index()
        .sort_values(by='custo_previsto', ascending=False)
    )
    st.dataframe(
        df_por_turma,
        use_container_width=True,
        hide_index=True,
        column_config={
            "turma_nome": "Turma",
            "curso": "Curso",
            "total_aulas": st.column_config.NumberColumn("Total de Aulas"),
            "total_horas": st.column_config.NumberColumn("Total de Horas", format="%.2f"),
            "custo_previsto": st.column_config.NumberColumn("Custo Previsto (R$)", format="R$ %.2f")
        }
    )

    buffer_turma = io.BytesIO()
    with pd.ExcelWriter(buffer_turma, engine='xlsxwriter') as writer:
        df_por_turma.to_excel(writer, index=False, sheet_name='Custo por Turma')
    buffer_turma.seek(0)
    st.download_button(
        label="📥 Exportar Turmas para Excel",
        data=buffer_turma,
        file_name="custo_por_turma.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_custo_turma"
    )

    st.divider()

    # ==========================================================================
    # 7. RELATÓRIO CONSOLIDADO DE TURMA
    # ==========================================================================
    st.header("📋 Relatório Consolidado de Turma")
    st.markdown("Os filtros abaixo impactam apenas o relatório consolidado, permitindo uma análise mais detalhada por turma.")

    # DataFrame base: mesma empresa selecionada no filtro da página
    df_consolidado_base = df[df['empresa'] == empresa_selecionada].copy()

    # Carregar matrículas por turma
    df_matriculas = carregar_dados("consultas/turmas/matriculas_turma.sql")
    df_matriculas['valor'] = pd.to_numeric(df_matriculas['valor'], errors='coerce')
    df_matriculas = df_matriculas[df_matriculas['empresa'] == empresa_selecionada]
    df_mat_turma = (
        df_matriculas
        .groupby('turma_id', dropna=False)
        .agg(matriculas=('order_id', 'nunique'), faturado=('valor', 'sum'))
        .reset_index()
    )

    # Carregar valor para iniciar por turma
    df_valor_iniciar = carregar_dados("consultas/turmas/curso_valor_iniciar.sql")
    df_valor_iniciar['valor_iniciar'] = pd.to_numeric(df_valor_iniciar['valor_iniciar'], errors='coerce')
    df_valor_iniciar = df_valor_iniciar[['turma_id', 'valor_iniciar']].drop_duplicates()

    # --- Filtros independentes ---
    col_f1, col_f2 = st.columns(2)

    with col_f1:
        # Filtro de data baseado em inicio_grade (padrão: mês atual)
        df_com_grade = df_consolidado_base.dropna(subset=['inicio_grade'])
        data_min_cons = df_com_grade['inicio_grade'].min().date() if not df_com_grade.empty else hoje_aware
        data_max_cons = df_com_grade['inicio_grade'].max().date() if not df_com_grade.empty else hoje_aware
        primeiro_dia_mes = hoje_aware.replace(day=1)
        data_inicio_cons_padrao = max(primeiro_dia_mes, data_min_cons)

        periodo_cons = st.date_input(
            "Período (Início da Grade):",
            value=[data_inicio_cons_padrao, data_max_cons],
            min_value=data_min_cons,
            key="cons_date_range"
        )

    with col_f2:
        possui_grade_list = sorted(df_consolidado_base['possui_grade'].dropna().unique())
        possui_grade_sel = st.multiselect(
            "Possui Grade:", possui_grade_list, default=possui_grade_list, key="cons_possui_grade"
        )

    try:
        inicio_cons_aware = pd.Timestamp(periodo_cons[0], tz=TIMEZONE)
        fim_cons_aware = pd.Timestamp(periodo_cons[1], tz=TIMEZONE) + pd.Timedelta(days=1)
    except IndexError:
        st.warning("👈 Por favor, selecione um período de datas para o relatório consolidado.")
        st.stop()

    # Aplica filtro de data e possui_grade primeiro para alimentar os demais filtros
    df_cons_pre = df_consolidado_base[
        (df_consolidado_base['inicio_grade'] >= inicio_cons_aware) &
        (df_consolidado_base['inicio_grade'] < fim_cons_aware) &
        (df_consolidado_base['possui_grade'].isin(possui_grade_sel))
    ]

    col_f3, col_f4, col_f5 = st.columns(3)

    with col_f3:
        unidades_cons_list = sorted(df_cons_pre['unidade'].dropna().unique())
        unidades_cons_sel = st.multiselect(
            "Unidade:", unidades_cons_list, default=unidades_cons_list, key="cons_unidade"
        )

    with col_f4:
        turno_cons_list = sorted(df_cons_pre['turno'].dropna().unique())
        turno_cons_sel = st.multiselect(
            "Turno:", turno_cons_list, default=turno_cons_list, key="cons_turno"
        )

    with col_f5:
        cursos_cons_list = sorted(df_cons_pre['curso'].dropna().unique())
        cursos_cons_sel = st.multiselect(
            "Curso:", cursos_cons_list, default=cursos_cons_list, key="cons_curso"
        )

    col_f6, col_f7 = st.columns(2)

    with col_f6:
        cursos_venda_cons_list = sorted(df_cons_pre['curso_venda'].dropna().unique())
        cursos_venda_cons_sel = st.multiselect(
            "Curso Venda:", cursos_venda_cons_list, default=cursos_venda_cons_list, key="cons_curso_venda"
        )

    with col_f7:
        turmas_cons_list = sorted(df_cons_pre['turma_nome'].dropna().unique())
        turmas_cons_sel = st.multiselect(
            "Turma:", turmas_cons_list, default=turmas_cons_list, key="cons_turma"
        )

    # Aplicação final dos filtros do consolidado
    df_cons = df_cons_pre[
        (df_cons_pre['unidade'].isin(unidades_cons_sel)) &
        (df_cons_pre['turno'].isin(turno_cons_sel)) &
        (df_cons_pre['curso'].isin(cursos_cons_sel)) &
        (df_cons_pre['curso_venda'].isin(cursos_venda_cons_sel)) &
        (df_cons_pre['turma_nome'].isin(turmas_cons_sel))
    ].copy()

    if df_cons.empty:
        st.warning("Não há dados para os filtros selecionados no relatório consolidado.")
        st.stop()

    # --- Montar coluna turma_compartilhada ---
    # Para cada aula (aula_id), descobrir todas as turmas que a compartilham
    aula_turmas = (
        df_consolidado_base[['aula_id', 'turma_nome']]
        .dropna(subset=['aula_id'])
        .drop_duplicates()
    )
    # Para cada turma, juntar as turmas que compartilham pelo menos uma aula
    turma_aulas = df_cons[['turma_id', 'turma_nome', 'aula_id']].dropna(subset=['aula_id']).drop_duplicates()
    merged = turma_aulas.merge(aula_turmas, on='aula_id', suffixes=('', '_comp'))
    # Remover a própria turma da lista de compartilhadas
    merged = merged[merged['turma_nome'] != merged['turma_nome_comp']]
    turma_compartilhada_map = (
        merged.groupby('turma_nome')['turma_nome_comp']
        .apply(lambda x: ', '.join(sorted(x.unique())))
        .reset_index()
        .rename(columns={'turma_nome_comp': 'turma_compartilhada'})
    )

    # --- Colunas auxiliares para aulas dadas e não compartilhadas ---
    hoje_ts = pd.Timestamp.now(tz=TIMEZONE)
    df_cons['aula_dada'] = df_cons['data_aula'] <= hoje_ts
    df_cons['aula_exclusiva'] = df_cons['turmas_compartilhadas'] == 1

    # --- Tabela agrupada por turma ---
    df_cons_turma = (
        df_cons
        .groupby(['turma_id', 'turma_nome', 'curso'], dropna=False)
        .agg(
            data_prevista=('data_prevista', 'first'),
            tipo_turma=('tipo_turma', 'first'),
            inicio_grade=('inicio_grade', 'first'),
            turno=('turno', 'first'),
            total_aulas=('aula_id', 'nunique'),
            aulas_dadas=('aula_dada', 'sum'),
            aulas_nao_compartilhadas=('aula_exclusiva', 'sum'),
            total_horas=('carga_horaria_decimal', 'sum'),
            custo_previsto=('valor_rateio_aula', 'sum')
        )
        .reset_index()
    )
    df_cons_turma['aulas_dadas'] = df_cons_turma['aulas_dadas'].astype(int)
    df_cons_turma['aulas_nao_compartilhadas'] = df_cons_turma['aulas_nao_compartilhadas'].astype(int)
    df_cons_turma = df_cons_turma.merge(turma_compartilhada_map, on='turma_nome', how='left')
    df_cons_turma['turma_compartilhada'] = df_cons_turma['turma_compartilhada'].fillna('')

    # Merge com matrículas
    df_cons_turma = df_cons_turma.merge(df_mat_turma, on='turma_id', how='left')
    df_cons_turma['matriculas'] = df_cons_turma['matriculas'].fillna(0).astype(int)
    df_cons_turma['faturado'] = df_cons_turma['faturado'].fillna(0)

    # Merge com valor para iniciar
    df_cons_turma = df_cons_turma.merge(df_valor_iniciar, on='turma_id', how='left')

    df_cons_turma['resultado'] = df_cons_turma['faturado'] - df_cons_turma['custo_previsto']

    colunas_cons = [
        'turma_nome', 'data_prevista', 'curso', 'tipo_turma', 'valor_iniciar', 'inicio_grade',
        'turno', 'turma_compartilhada', 'total_aulas', 'aulas_dadas',
        'aulas_nao_compartilhadas', 'total_horas', 'custo_previsto',
        'matriculas', 'faturado', 'resultado'
    ]
    df_cons_exib = df_cons_turma[colunas_cons].sort_values(by='turma_nome')

    st.dataframe(
        df_cons_exib,
        use_container_width=True,
        hide_index=True,
        column_config={
            "turma_nome": st.column_config.TextColumn("Turma", width="small"),
            "data_prevista": st.column_config.DateColumn("Data\nPrevista", format="DD/MM/YYYY"),
            "curso": st.column_config.TextColumn("Curso", width="medium"),
            "tipo_turma": st.column_config.TextColumn("Tipo\nTurma", width="small"),
            "valor_iniciar": st.column_config.NumberColumn("Valor\nIniciar (R$)", format="R$ %.2f"),
            "inicio_grade": st.column_config.DatetimeColumn("Início\nGrade", format="DD/MM/YYYY"),
            "turno": st.column_config.TextColumn("Turno", width="small"),
            "turma_compartilhada": st.column_config.TextColumn("Turmas\nCompartilhadas", width="medium"),
            "total_aulas": st.column_config.NumberColumn("Total\nAulas"),
            "aulas_dadas": st.column_config.NumberColumn("Aulas\nDadas"),
            "aulas_nao_compartilhadas": st.column_config.NumberColumn("Aulas Não\nCompart."),
            "total_horas": st.column_config.NumberColumn("Total\nHoras", format="%.2f"),
            "custo_previsto": st.column_config.NumberColumn("Custo\nPrevisto (R$)", format="R$ %.2f"),
            "matriculas": st.column_config.NumberColumn("Matrículas"),
            "faturado": st.column_config.NumberColumn("Faturado\n(R$)", format="R$ %.2f"),
            "resultado": st.column_config.NumberColumn("Resultado\n(R$)", format="R$ %.2f")
        }
    )

    # Exportar consolidado
    df_cons_export = df_cons_exib.copy()
    if 'inicio_grade' in df_cons_export.columns:
        df_cons_export['inicio_grade'] = df_cons_export['inicio_grade'].dt.tz_localize(None)
    buffer_cons = io.BytesIO()
    with pd.ExcelWriter(buffer_cons, engine='xlsxwriter') as writer:
        df_cons_export.to_excel(writer, index=False, sheet_name='Consolidado por Turma')
    buffer_cons.seek(0)
    st.download_button(
        label="📥 Exportar Consolidado para Excel",
        data=buffer_cons,
        file_name="relatorio_consolidado_turma.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_consolidado_turma"
    )

    st.divider()

    # ==========================================================================
    # 8. RELATÓRIO AGRUPADO DE TURMAS COMPARTILHADAS (AGGRID)
    # ==========================================================================
    st.header("🗂️ Visão Agrupada de Turmas Compartilhadas (Clusters)")
    st.markdown("Cria agrupamentos dinâmicos das turmas com base no compartilhamento das grades.")
    
    # Montar grafo de compartilhamentos para criar os Clusters
    adj = {}
    todas_turmas_cons = df_cons_turma['turma_nome'].dropna().unique()
    for t in todas_turmas_cons:
        adj[t] = set()
        
    for index, row in merged.iterrows():
        t1 = row['turma_nome']
        t2 = row['turma_nome_comp']
        if t1 in adj and t2 in adj:
            adj[t1].add(t2)
            adj[t2].add(t1)
            
    visited = set()
    clusters = {}
    cluster_idx = 1
    
    for t in sorted(adj.keys()): # Ordenado para garantir consistência dos índices
        if t not in visited:
            comp = set()
            stack = [t]
            while stack:
                curr = stack.pop()
                if curr not in visited:
                    visited.add(curr)
                    comp.add(curr)
                    stack.extend(adj[curr] - visited)
            
            # Buscar cursos das turmas nesse componente
            cursos_comp = df_cons_turma[df_cons_turma['turma_nome'].isin(comp)]['curso'].dropna().unique()
            cursos_str = " / ".join(sorted(cursos_comp)) if len(cursos_comp) > 0 else "Sem Curso definido"
            
            if len(comp) > 1:
                cluster_name = f"Grupo_{cluster_idx} - {cursos_str}"
                cluster_idx += 1
            else:
                cluster_name = f"Isolada - {list(comp)[0]}"
                
            for member in comp:
                clusters[member] = cluster_name
                
    df_aggrid = df_cons_turma.copy()
    df_aggrid['cluster_agrupador'] = df_aggrid['turma_nome'].map(clusters)
    
    # Preparar as colunas a serem exibidas (adequando tipos numéricos pro grid usar as funções de agregação) 
    df_aggrid['total_aulas'] = pd.to_numeric(df_aggrid['total_aulas'], errors='coerce').fillna(0)
    df_aggrid['aulas_dadas'] = pd.to_numeric(df_aggrid['aulas_dadas'], errors='coerce').fillna(0)
    df_aggrid['aulas_nao_compartilhadas'] = pd.to_numeric(df_aggrid['aulas_nao_compartilhadas'], errors='coerce').fillna(0)
    df_aggrid['total_horas'] = pd.to_numeric(df_aggrid['total_horas'], errors='coerce').fillna(0)
    df_aggrid['matriculas'] = pd.to_numeric(df_aggrid['matriculas'], errors='coerce').fillna(0)
    
    # Configuração da UI do AgGrid
    gb = GridOptionsBuilder.from_dataframe(df_aggrid)
    
    # Configura o cluster_agrupador
    gb.configure_column(
        field="cluster_agrupador",
        header_name="Grupo / Cluster",
        rowGroup=True,
        hide=True
    )
    
    # Esconder turma_id e turma_compartilhada do grid
    if 'turma_id' in df_aggrid.columns:
        gb.configure_column(field="turma_id", hide=True)
    if 'turma_compartilhada' in df_aggrid.columns:
        gb.configure_column(field="turma_compartilhada", hide=True)
        
    gb.configure_column(field="turma_nome", header_name="Turma", minWidth=200)
    gb.configure_column(field="curso", header_name="Curso")
    gb.configure_column(field="tipo_turma", header_name="Tipo")
    gb.configure_column(field="turno", header_name="Turno")
    
    gb.configure_column(
        field="data_prevista", 
        header_name="Data Prevista",
        type=["dateColumnFilter", "customDateTimeFormat"],
        custom_format_string='dd/MM/yyyy',
        minWidth=150
    )
    gb.configure_column(
        field="inicio_grade", 
        header_name="Início Grade",
        type=["dateColumnFilter", "customDateTimeFormat"],
        custom_format_string='dd/MM/yyyy',
        minWidth=150
    )

    # Métricas Quantitativas (Sum)
    gb.configure_column(field="total_aulas", header_name="Tot. Aulas", type=["numericColumn"], aggFunc="sum")
    gb.configure_column(field="aulas_dadas", header_name="Aulas Dadas", type=["numericColumn"], aggFunc="sum")
    gb.configure_column(field="aulas_nao_compartilhadas", header_name="Aulas Não Comp.", type=["numericColumn"], aggFunc="sum")
    gb.configure_column(field="total_horas", header_name="Tot. Horas", type=["numericColumn"], aggFunc="sum", valueFormatter=JsCode("function(params) { if(params.value == null) return ''; return params.value.toFixed(2); }"))
    gb.configure_column(field="matriculas", header_name="Matrículas", type=["numericColumn"], aggFunc="sum")

    # Métricas Financeiras
    formata_moeda_js = JsCode("""
        function(params) {
            if (params.value === undefined || params.value === null) return '';
            return 'R$ ' + params.value.toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
        }
    """)
    
    gb.configure_column(
        field="valor_iniciar",
        header_name="Valor Iniciar",
        type=["numericColumn"],
        aggFunc="max",  # usamos MAX porque somar valor do curso por turmas agrupadas pode gerar distorção.
        valueFormatter=formata_moeda_js
    )
    
    gb.configure_column(
        field="custo_previsto",
        header_name="Custo Previsto",
        type=["numericColumn"],
        aggFunc="sum",
        valueFormatter=formata_moeda_js
    )
    
    gb.configure_column(
        field="faturado",
        header_name="Faturado",
        type=["numericColumn"],
        aggFunc="sum",
        valueFormatter=formata_moeda_js
    )
    
    gb.configure_column(
        field="resultado",
        header_name="Resultado",
        type=["numericColumn"],
        aggFunc="sum",
        valueFormatter=formata_moeda_js
    )
    
    grid_options = gb.build()
    
    grid_options["autoGroupColumnDef"] = {
        "headerName": "Clusters / Turmas",
        "minWidth": 350,
        "cellRendererParams": {
            "suppressCount": False,
        }
    }
    grid_options["groupDisplayType"] = "groupRow"
    grid_options["groupDefaultExpanded"] = 0 # Recolhidos por padrão
    grid_options["groupIncludeFooter"] = True
    grid_options["groupIncludeTotalFooter"] = True
    
    AgGrid(
        df_aggrid,
        gridOptions=grid_options,
        height=600,
        width='100%',
        theme='streamlit',
        enable_enterprise_modules=True,
        update_mode='MODEL_CHANGED',
        allow_unsafe_jscode=True,
        fit_columns_on_grid_load=False
    )
