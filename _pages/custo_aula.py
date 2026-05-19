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
    st.markdown(
        "Análise gerencial e pedagógica por turma, com foco em progresso da grade, "
        "conexões entre turmas (compartilhamento de aulas) e resultado financeiro."
    )

    # DataFrame base: mesma empresa selecionada no filtro da página
    df_consolidado_base = df[df['empresa'] == empresa_selecionada].copy()

    # Carregar matrículas por turma
    df_matriculas = carregar_dados("consultas/turmas/matriculas_turma.sql")
    df_matriculas['valor'] = pd.to_numeric(df_matriculas['valor'], errors='coerce')
    df_matriculas['valor_pago'] = pd.to_numeric(df_matriculas['valor_pago'], errors='coerce')
    df_matriculas['valor_devolvido'] = pd.to_numeric(df_matriculas['valor_devolvido'], errors='coerce')
    df_matriculas['data_pagamento'] = pd.to_datetime(df_matriculas['data_pagamento'], errors='coerce')
    df_matriculas = df_matriculas[df_matriculas['empresa'] == empresa_selecionada]
    status_pagamento_list = sorted(df_matriculas['status_pagamento'].dropna().unique())

    # Carregar valor para iniciar por turma
    df_valor_iniciar = carregar_dados("consultas/turmas/curso_valor_iniciar.sql")
    df_valor_iniciar['valor_iniciar'] = pd.to_numeric(df_valor_iniciar['valor_iniciar'], errors='coerce')
    df_valor_iniciar = df_valor_iniciar[['turma_id', 'valor_iniciar']].drop_duplicates() 

    # --- Filtros independentes do consolidado ---
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        tipo_recorte_tempo = st.radio(
            "Recorte Temporal da Análise:",
            ["Abrangente (sem recorte)", "Por Início da Grade", "Por Data da Aula"],
            index=0,
            key="cons_tipo_recorte"
        )

    with col_f2:
        possui_grade_list = sorted(df_consolidado_base['possui_grade'].dropna().unique())
        possui_grade_sel = st.multiselect(
            "Possui Grade:", possui_grade_list, default=possui_grade_list, key="cons_possui_grade"
        )

    status_pagamento_sel = st.multiselect(
        "Status do Pagamento:",
        status_pagamento_list,
        default=status_pagamento_list,
        key="cons_status_pagamento"
    )

    periodo_cons = None
    inicio_cons_aware = None
    fim_cons_aware = None
    coluna_recorte = None

    if tipo_recorte_tempo != "Abrangente (sem recorte)":
        coluna_recorte = 'inicio_grade' if tipo_recorte_tempo == "Por Início da Grade" else 'data_aula'
        df_datas = df_consolidado_base.dropna(subset=[coluna_recorte])
        data_min_cons = df_datas[coluna_recorte].min().date() if not df_datas.empty else hoje_aware
        data_max_cons = df_datas[coluna_recorte].max().date() if not df_datas.empty else hoje_aware

        periodo_cons = st.date_input(
            f"Período ({'Início da Grade' if coluna_recorte == 'inicio_grade' else 'Data da Aula'}):",
            value=[data_min_cons, data_max_cons],
            min_value=data_min_cons,
            max_value=data_max_cons,
            key="cons_date_range"
        )

        try:
            inicio_cons_aware = pd.Timestamp(periodo_cons[0], tz=TIMEZONE)
            fim_cons_aware = pd.Timestamp(periodo_cons[1], tz=TIMEZONE) + pd.Timedelta(days=1)
        except IndexError:
            st.warning("👈 Por favor, selecione um período de datas para o relatório consolidado.")
            st.stop()

    aplicar_periodo_no_pagamento = st.checkbox(
        "Aplicar recorte temporal também no pagamento (data_pagamento)",
        value=False,
        key="cons_aplicar_periodo_pagamento"
    )

    # Base inicial do consolidado
    df_cons_pre = df_consolidado_base[df_consolidado_base['possui_grade'].isin(possui_grade_sel)].copy()

    if coluna_recorte is not None:
        df_cons_pre = df_cons_pre[
            df_cons_pre[coluna_recorte].notna() &
            (df_cons_pre[coluna_recorte] >= inicio_cons_aware) &
            (df_cons_pre[coluna_recorte] < fim_cons_aware)
        ]

    if df_cons_pre.empty:
        st.warning("Não há dados para os filtros principais do relatório consolidado.")
        st.stop()

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

    # Matrículas/faturamento para as turmas filtradas
    turma_ids_filtradas = df_cons['turma_id'].dropna().unique()
    df_matriculas_filtrado = df_matriculas[
        df_matriculas['status_pagamento'].isin(status_pagamento_sel) &
        df_matriculas['turma_id'].isin(turma_ids_filtradas)
    ].copy()

    if (
        aplicar_periodo_no_pagamento and
        coluna_recorte is not None and
        inicio_cons_aware is not None and
        fim_cons_aware is not None
    ):
        inicio_pagamento = inicio_cons_aware.tz_localize(None)
        fim_pagamento = fim_cons_aware.tz_localize(None)
        df_matriculas_filtrado = df_matriculas_filtrado[
            df_matriculas_filtrado['data_pagamento'].notna() &
            (df_matriculas_filtrado['data_pagamento'] >= inicio_pagamento) &
            (df_matriculas_filtrado['data_pagamento'] < fim_pagamento)
        ]

    # A query de matrículas pode repetir o mesmo pedido por item; deduplicamos por pedido/turma.
    df_matriculas_filtrado = df_matriculas_filtrado.drop_duplicates(subset=['order_id', 'turma_id'])

    df_mat_turma = (
        df_matriculas_filtrado
        .groupby('turma_id', dropna=False)
        .agg(
            matriculas=('order_id', 'nunique'),
            fat_canc=('valor', 'sum'),
            fat_total=('valor_pago', 'sum'),
            cancelado=('valor_devolvido', 'sum')
        )
        .reset_index()
    )

    # --- Montar conexões entre turmas por compartilhamento de aulas ---
    aula_turmas = (
        df_consolidado_base[['aula_id', 'turma_id', 'turma_nome']]
        .dropna(subset=['aula_id', 'turma_id'])
        .drop_duplicates()
    )
    turma_aulas = (
        df_cons[['turma_id', 'turma_nome', 'aula_id']]
        .dropna(subset=['aula_id', 'turma_id'])
        .drop_duplicates()
    )
    merged = turma_aulas.merge(aula_turmas, on='aula_id', suffixes=('', '_comp'))
    merged = merged[merged['turma_id'] != merged['turma_id_comp']]

    turma_compartilhada_map = (
        merged.groupby('turma_id')['turma_nome_comp']
        .apply(lambda x: ', '.join(sorted(x.unique())))
        .reset_index()
        .rename(columns={'turma_nome_comp': 'turma_compartilhada'})
    )

    ligacoes_map = (
        merged.groupby('turma_id')['turma_id_comp']
        .nunique()
        .reset_index()
        .rename(columns={'turma_id_comp': 'qtd_turmas_ligadas'})
    )

    # --- Colunas auxiliares para progresso da grade ---
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
            possui_grade=('possui_grade', 'first'),
            total_aulas=('aula_id', 'nunique'),
            aulas_dadas=('aula_dada', 'sum'),
            aulas_nao_compartilhadas=('aula_exclusiva', 'sum'),
            total_horas=('carga_horaria_decimal', 'sum'),
            custo_previsto=('valor_rateio_aula', 'sum')
        )
        .reset_index()
    )

    df_cons_turma = df_cons_turma.merge(turma_compartilhada_map, on='turma_id', how='left')
    df_cons_turma = df_cons_turma.merge(ligacoes_map, on='turma_id', how='left')
    df_cons_turma['turma_compartilhada'] = df_cons_turma['turma_compartilhada'].fillna('')
    df_cons_turma['qtd_turmas_ligadas'] = df_cons_turma['qtd_turmas_ligadas'].fillna(0).astype(int)

    # Merge com matrículas/faturamento
    df_cons_turma = df_cons_turma.merge(df_mat_turma, on='turma_id', how='left')
    df_cons_turma['matriculas'] = df_cons_turma['matriculas'].fillna(0).astype(int)
    df_cons_turma['fat_canc'] = df_cons_turma['fat_canc'].fillna(0)
    df_cons_turma['fat_total'] = df_cons_turma['fat_total'].fillna(0)
    df_cons_turma['cancelado'] = df_cons_turma['cancelado'].fillna(0)

    # Merge com valor para iniciar
    df_cons_turma = df_cons_turma.merge(df_valor_iniciar, on='turma_id', how='left')

    # Indicadores gerenciais
    df_cons_turma['aulas_dadas'] = df_cons_turma['aulas_dadas'].astype(int)
    df_cons_turma['aulas_nao_compartilhadas'] = df_cons_turma['aulas_nao_compartilhadas'].astype(int)
    df_cons_turma['aulas_restantes'] = (df_cons_turma['total_aulas'] - df_cons_turma['aulas_dadas']).clip(lower=0)
    total_aulas_base = df_cons_turma['total_aulas'].where(df_cons_turma['total_aulas'] != 0)
    df_cons_turma['progresso_grade_pct'] = (
        df_cons_turma['aulas_dadas'] / total_aulas_base * 100
    ).fillna(0).round(1)
    df_cons_turma['resultado'] = df_cons_turma['fat_canc'] - df_cons_turma['custo_previsto']
    df_cons_turma['result_bruto'] = df_cons_turma['fat_total'] - df_cons_turma['custo_previsto']
    fat_canc_base = df_cons_turma['fat_canc'].where(df_cons_turma['fat_canc'] != 0)
    df_cons_turma['margem_pct'] = (
        df_cons_turma['resultado'] / fat_canc_base * 100
    ).fillna(0).round(1)
    matriculas_base = df_cons_turma['matriculas'].where(df_cons_turma['matriculas'] != 0)
    df_cons_turma['custo_por_matricula'] = (
        df_cons_turma['custo_previsto'] / matriculas_base
    ).fillna(0)
    df_cons_turma['ticket_medio'] = (
        df_cons_turma['fat_canc'] / matriculas_base
    ).fillna(0)
    df_cons_turma['status_conexao'] = df_cons_turma['qtd_turmas_ligadas'].apply(
        lambda x: 'Conectada' if x > 0 else 'Isolada'
    )
    df_cons_turma['status_financeiro'] = df_cons_turma['resultado'].apply(
        lambda x: 'Déficit' if x < 0 else ('Superávit' if x > 0 else 'Equilíbrio')
    )

    colunas_cons = [
        'turma_nome', 'curso', 'tipo_turma', 'unidade', 'turno', 'possui_grade',
        'inicio_grade', 'data_prevista', 'status_conexao', 'qtd_turmas_ligadas',
        'turma_compartilhada', 'total_aulas', 'aulas_dadas', 'aulas_restantes',
        'progresso_grade_pct', 'total_horas', 'matriculas', 'valor_iniciar',
        'custo_previsto', 'fat_total', 'result_bruto', 'cancelado', 'fat_canc', 'resultado', 'margem_pct',
        'custo_por_matricula', 'ticket_medio', 'status_financeiro'
    ]

    # unidade vem de df_cons (não de df_cons_turma), então trazemos o primeiro valor por turma
    unidade_map = (
        df_cons.groupby('turma_id', dropna=False)['unidade']
        .first()
        .reset_index()
    )
    df_cons_turma = df_cons_turma.merge(unidade_map, on='turma_id', how='left')

    df_cons_exib = df_cons_turma[colunas_cons].sort_values(
        by=['data_prevista', 'inicio_grade', 'turma_nome'],
        ascending=[False, False, True]
    )

    st.dataframe(
        df_cons_exib,
        use_container_width=True,
        hide_index=True,
        column_config={
            "turma_nome": st.column_config.TextColumn("Turma", width="small"),
            "curso": st.column_config.TextColumn("Curso", width="medium"),
            "tipo_turma": st.column_config.TextColumn("Tipo\nTurma", width="small"),
            "unidade": st.column_config.TextColumn("Unidade", width="small"),
            "turno": st.column_config.TextColumn("Turno", width="small"),
            "possui_grade": st.column_config.TextColumn("Possui\nGrade", width="small"),
            "inicio_grade": st.column_config.DatetimeColumn("Início\nGrade", format="DD/MM/YYYY"),
            "data_prevista": st.column_config.DateColumn("Data\nPrevista", format="DD/MM/YYYY"),
            "status_conexao": st.column_config.TextColumn("Status\nConexão", width="small"),
            "qtd_turmas_ligadas": st.column_config.NumberColumn("Turmas\nLigadas"),
            "turma_compartilhada": st.column_config.TextColumn("Turmas\nConectadas", width="large"),
            "total_aulas": st.column_config.NumberColumn("Total\nAulas"),
            "aulas_dadas": st.column_config.NumberColumn("Aulas\nDadas"),
            "aulas_restantes": st.column_config.NumberColumn("Aulas\nRestantes"),
            "progresso_grade_pct": st.column_config.NumberColumn("Progresso\nGrade", format="%.1f%%"),
            "total_horas": st.column_config.NumberColumn("Total\nHoras", format="%.2f"),
            "matriculas": st.column_config.NumberColumn("Matrículas"),
            "valor_iniciar": st.column_config.NumberColumn("Valor\nIniciar (R$)", format="R$ %.2f"),
            "custo_previsto": st.column_config.NumberColumn("Custo\nPrevisto (R$)", format="R$ %.2f"),
            "fat_total": st.column_config.NumberColumn("Fat. Total\n(R$)", format="R$ %.2f"),
            "result_bruto": st.column_config.NumberColumn("Resut Bruto\n(R$)", format="R$ %.2f"),
            "cancelado": st.column_config.NumberColumn("Cancelado\n(R$)", format="R$ %.2f"),
            "fat_canc": st.column_config.NumberColumn("Fat - Canc\n(R$)", format="R$ %.2f"),
            "resultado": st.column_config.NumberColumn("Resultado\n(R$)", format="R$ %.2f"),
            "margem_pct": st.column_config.NumberColumn("Margem\n(%)", format="%.1f%%"),
            "custo_por_matricula": st.column_config.NumberColumn("Custo/\nMatrícula", format="R$ %.2f"),
            "ticket_medio": st.column_config.NumberColumn("Ticket\nMédio", format="R$ %.2f"),
            "status_financeiro": st.column_config.TextColumn("Status\nFinanceiro", width="small")
        }
    )

    # Exportar consolidado
    df_cons_export = df_cons_exib.copy()
    if 'inicio_grade' in df_cons_export.columns:
        df_cons_export['inicio_grade'] = pd.to_datetime(df_cons_export['inicio_grade'], errors='coerce').dt.tz_localize(None)
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
    # 8. VISÃO GERAL DE CLUSTERS + DETALHAMENTO
    # ==========================================================================
    st.header("🗂️ Visão Geral de Clusters de Turmas")
    st.markdown(
        "Agrupa turmas conectadas por compartilhamento de aulas para leitura executiva do cenário geral "
        "(pedagógico e financeiro)."
    )

    # Montar grafo de compartilhamentos para criar os clusters
    adj = {tid: set() for tid in df_cons_turma['turma_id'].dropna().unique()}
    for _, row in merged.iterrows():
        t1 = row['turma_id']
        t2 = row['turma_id_comp']
        if t1 in adj and t2 in adj:
            adj[t1].add(t2)
            adj[t2].add(t1)

    visited = set()
    cluster_map = {}
    cluster_idx = 1

    for tid in sorted(adj.keys()):
        if tid in visited:
            continue

        comp = set()
        stack = [tid]
        while stack:
            curr = stack.pop()
            if curr in visited:
                continue
            visited.add(curr)
            comp.add(curr)
            stack.extend(adj[curr] - visited)

        cursos_cluster = (
            df_cons_turma[df_cons_turma['turma_id'].isin(comp)]['curso']
            .dropna()
            .astype(str)
            .sort_values()
            .unique()
            .tolist()
        )
        if len(cursos_cluster) == 1:
            base_nome_cluster = cursos_cluster[0]
        elif len(cursos_cluster) > 1:
            base_nome_cluster = " / ".join(cursos_cluster)
        else:
            base_nome_cluster = "Sem Curso"

        if len(comp) > 1:
            cluster_nome = f"{base_nome_cluster} (Cluster {cluster_idx:02d} - {len(comp)} turmas)"
        else:
            cluster_nome = f"{base_nome_cluster} (Turma Isolada)"
        cluster_idx += 1

        for member in comp:
            cluster_map[member] = cluster_nome

    df_aggrid = df_cons_turma.copy()
    df_aggrid['cluster_agrupador'] = df_aggrid['turma_id'].map(cluster_map).fillna('Turma Isolada')

    # Métricas executivas do cenário geral
    total_turmas_cons = int(df_aggrid['turma_id'].nunique())
    turmas_conectadas = int((df_aggrid['qtd_turmas_ligadas'] > 0).sum())
    turmas_deficit = int((df_aggrid['status_financeiro'] == 'Déficit').sum())
    resultado_total = float(df_aggrid['resultado'].sum())

    col_k1, col_k2, col_k3, col_k4 = st.columns(4)
    col_k1.metric("Turmas no Recorte", f"{total_turmas_cons}")
    col_k2.metric("Turmas Conectadas", f"{turmas_conectadas}")
    col_k3.metric("Turmas em Déficit", f"{turmas_deficit}")
    col_k4.metric("Resultado Total", formatar_reais(resultado_total))

    # Resumo executivo por cluster
    cluster_turmas = (
        df_aggrid.groupby('cluster_agrupador')['turma_nome']
        .apply(lambda x: ', '.join(sorted(x.dropna().unique())))
        .reset_index()
        .rename(columns={'turma_nome': 'turmas'})
    )
    cluster_cursos = (
        df_aggrid.groupby('cluster_agrupador')['curso']
        .apply(lambda x: ' / '.join(sorted(x.dropna().unique())))
        .reset_index()
        .rename(columns={'curso': 'cursos'})
    )

    df_cluster_resumo = (
        df_aggrid
        .groupby('cluster_agrupador', dropna=False)
        .agg(
            data_prevista_mais_recente=('data_prevista', 'max'),
            inicio_grade_mais_recente=('inicio_grade', 'max'),
            qtd_turmas=('turma_id', 'nunique'),
            total_aulas=('total_aulas', 'sum'),
            aulas_dadas=('aulas_dadas', 'sum'),
            aulas_restantes=('aulas_restantes', 'sum'),
            matriculas=('matriculas', 'sum'),
            custo_previsto=('custo_previsto', 'sum'),
            fat_total=('fat_total', 'sum'),
            result_bruto=('result_bruto', 'sum'),
            cancelado=('cancelado', 'sum'),
            fat_canc=('fat_canc', 'sum'),
            resultado=('resultado', 'sum'),
            turmas_deficit=('status_financeiro', lambda x: (x == 'Déficit').sum())
        )
        .reset_index()
    )
    total_aulas_cluster_base = df_cluster_resumo['total_aulas'].where(df_cluster_resumo['total_aulas'] != 0)
    df_cluster_resumo['progresso_grade_pct'] = (
        df_cluster_resumo['aulas_dadas'] / total_aulas_cluster_base * 100
    ).fillna(0).round(1)
    fat_canc_cluster_base = df_cluster_resumo['fat_canc'].where(df_cluster_resumo['fat_canc'] != 0)
    df_cluster_resumo['margem_pct'] = (
        df_cluster_resumo['resultado'] / fat_canc_cluster_base * 100
    ).fillna(0).round(1)
    matriculas_cluster_base = df_cluster_resumo['matriculas'].where(df_cluster_resumo['matriculas'] != 0)
    df_cluster_resumo['custo_por_matricula'] = (
        df_cluster_resumo['custo_previsto'] / matriculas_cluster_base
    ).fillna(0)
    df_cluster_resumo['ticket_medio'] = (
        df_cluster_resumo['fat_canc'] / matriculas_cluster_base
    ).fillna(0)
    df_cluster_resumo['status_cluster'] = df_cluster_resumo.apply(
        lambda r: 'Crítico' if (r['resultado'] < 0 and r['progresso_grade_pct'] > 70)
        else ('Atenção' if r['resultado'] < 0 else 'Saudável'),
        axis=1
    )

    df_cluster_resumo = df_cluster_resumo.merge(cluster_turmas, on='cluster_agrupador', how='left')
    df_cluster_resumo = df_cluster_resumo.merge(cluster_cursos, on='cluster_agrupador', how='left')
    df_cluster_resumo = df_cluster_resumo.sort_values(
        by=['data_prevista_mais_recente', 'inicio_grade_mais_recente', 'cluster_agrupador'],
        ascending=[False, False, True]
    )
    df_cluster_resumo = df_cluster_resumo.drop(
        columns=['data_prevista_mais_recente', 'inicio_grade_mais_recente'],
        errors='ignore'
    )

    st.subheader("Resumo Executivo por Cluster")
    st.dataframe(
        df_cluster_resumo,
        use_container_width=True,
        hide_index=True,
        column_config={
            "cluster_agrupador": st.column_config.TextColumn("Cluster", width="small"),
            "status_cluster": st.column_config.TextColumn("Status", width="small"),
            "qtd_turmas": st.column_config.NumberColumn("Qtd. Turmas"),
            "cursos": st.column_config.TextColumn("Cursos", width="medium"),
            "turmas": st.column_config.TextColumn("Turmas", width="large"),
            "total_aulas": st.column_config.NumberColumn("Total Aulas"),
            "aulas_dadas": st.column_config.NumberColumn("Aulas Dadas"),
            "aulas_restantes": st.column_config.NumberColumn("Aulas Restantes"),
            "progresso_grade_pct": st.column_config.NumberColumn("Progresso Grade", format="%.1f%%"),
            "matriculas": st.column_config.NumberColumn("Matrículas"),
            "custo_previsto": st.column_config.NumberColumn("Custo Previsto", format="R$ %.2f"),
            "fat_total": st.column_config.NumberColumn("Fat. Total", format="R$ %.2f"),
            "result_bruto": st.column_config.NumberColumn("Resut Bruto", format="R$ %.2f"),
            "cancelado": st.column_config.NumberColumn("Cancelado", format="R$ %.2f"),
            "fat_canc": st.column_config.NumberColumn("Fat - Canc", format="R$ %.2f"),
            "resultado": st.column_config.NumberColumn("Resultado", format="R$ %.2f"),
            "margem_pct": st.column_config.NumberColumn("Margem", format="%.1f%%"),
            "custo_por_matricula": st.column_config.NumberColumn("Custo/Matrícula", format="R$ %.2f"),
            "ticket_medio": st.column_config.NumberColumn("Ticket Médio", format="R$ %.2f"),
            "turmas_deficit": st.column_config.NumberColumn("Turmas em Déficit")
        }
    )

    buffer_cluster_resumo = io.BytesIO()
    df_cluster_export = df_cluster_resumo.copy()
    with pd.ExcelWriter(buffer_cluster_resumo, engine='xlsxwriter') as writer:
        df_cluster_export.to_excel(writer, index=False, sheet_name='Clusters Resumo')
    buffer_cluster_resumo.seek(0)
    st.download_button(
        label="📥 Exportar Clusters para Excel",
        data=buffer_cluster_resumo,
        file_name="clusters_resumo.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_cluster_resumo"
    )

    st.divider()

    # Detalhamento por turma no cluster (AgGrid)
    st.subheader("Detalhamento por Turma dentro do Cluster")

    df_aggrid = df_aggrid.sort_values(
        by=['data_prevista', 'inicio_grade', 'turma_nome'],
        ascending=[False, False, True]
    )

    df_aggrid['total_aulas'] = pd.to_numeric(df_aggrid['total_aulas'], errors='coerce').fillna(0)
    df_aggrid['aulas_dadas'] = pd.to_numeric(df_aggrid['aulas_dadas'], errors='coerce').fillna(0)
    df_aggrid['aulas_restantes'] = pd.to_numeric(df_aggrid['aulas_restantes'], errors='coerce').fillna(0)
    df_aggrid['total_horas'] = pd.to_numeric(df_aggrid['total_horas'], errors='coerce').fillna(0)
    df_aggrid['matriculas'] = pd.to_numeric(df_aggrid['matriculas'], errors='coerce').fillna(0)
    df_aggrid['progresso_grade_pct'] = pd.to_numeric(df_aggrid['progresso_grade_pct'], errors='coerce').fillna(0)

    gb = GridOptionsBuilder.from_dataframe(df_aggrid)
    gb.configure_column(field="cluster_agrupador", header_name="Cluster", rowGroup=True, hide=True)

    if 'turma_id' in df_aggrid.columns:
        gb.configure_column(field="turma_id", hide=True)

    gb.configure_column(field="turma_nome", header_name="Turma", minWidth=180)
    gb.configure_column(field="curso", header_name="Curso", minWidth=140)
    gb.configure_column(field="tipo_turma", header_name="Tipo", minWidth=100)
    gb.configure_column(field="turno", header_name="Turno", minWidth=100)
    gb.configure_column(field="status_financeiro", header_name="Status Financeiro", minWidth=140)
    gb.configure_column(field="qtd_turmas_ligadas", header_name="Turmas Ligadas", type=["numericColumn"], aggFunc="sum")
    gb.configure_column(field="progresso_grade_pct", header_name="Progresso Grade (%)", type=["numericColumn"], aggFunc="avg")
    gb.configure_column(field="total_aulas", header_name="Tot. Aulas", type=["numericColumn"], aggFunc="sum")
    gb.configure_column(field="aulas_dadas", header_name="Aulas Dadas", type=["numericColumn"], aggFunc="sum")
    gb.configure_column(field="aulas_restantes", header_name="Aulas Restantes", type=["numericColumn"], aggFunc="sum")
    gb.configure_column(
        field="total_horas",
        header_name="Tot. Horas",
        type=["numericColumn"],
        aggFunc="sum",
        valueFormatter=JsCode("function(params){ if(params.value == null) return ''; return params.value.toFixed(2); }")
    )
    gb.configure_column(field="matriculas", header_name="Matrículas", type=["numericColumn"], aggFunc="sum")

    formata_moeda_js = JsCode("""
        function(params) {
            if (params.value === undefined || params.value === null) return '';
            return 'R$ ' + params.value.toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
        }
    """)

    gb.configure_column(field="valor_iniciar", header_name="Valor Iniciar", type=["numericColumn"], aggFunc="max", valueFormatter=formata_moeda_js)
    gb.configure_column(field="custo_previsto", header_name="Custo Previsto", type=["numericColumn"], aggFunc="sum", valueFormatter=formata_moeda_js)
    gb.configure_column(field="fat_total", header_name="Fat. Total", type=["numericColumn"], aggFunc="sum", valueFormatter=formata_moeda_js)
    gb.configure_column(field="result_bruto", header_name="Resut Bruto", type=["numericColumn"], aggFunc="sum", valueFormatter=formata_moeda_js)
    gb.configure_column(field="cancelado", header_name="Cancelado", type=["numericColumn"], aggFunc="sum", valueFormatter=formata_moeda_js)
    gb.configure_column(field="fat_canc", header_name="Fat - Canc", type=["numericColumn"], aggFunc="sum", valueFormatter=formata_moeda_js)
    gb.configure_column(field="resultado", header_name="Resultado", type=["numericColumn"], aggFunc="sum", valueFormatter=formata_moeda_js)

    grid_options = gb.build()
    grid_options["autoGroupColumnDef"] = {
        "headerName": "Clusters / Turmas",
        "minWidth": 320,
        "cellRendererParams": {"suppressCount": False}
    }
    grid_options["groupDisplayType"] = "groupRow"
    grid_options["groupDefaultExpanded"] = 0
    grid_options["groupIncludeFooter"] = True
    grid_options["groupIncludeTotalFooter"] = True

    AgGrid(
        df_aggrid,
        gridOptions=grid_options,
        height=620,
        width='100%',
        theme='streamlit',
        enable_enterprise_modules=True,
        update_mode='MODEL_CHANGED',
        allow_unsafe_jscode=True,
        fit_columns_on_grid_load=False
    )

    colunas_aggrid_export = [
        'cluster_agrupador', 'turma_nome', 'curso', 'tipo_turma', 'turno',
        'status_financeiro', 'qtd_turmas_ligadas', 'progresso_grade_pct',
        'total_aulas', 'aulas_dadas', 'aulas_restantes', 'total_horas',
        'matriculas', 'valor_iniciar', 'custo_previsto', 'fat_total', 'result_bruto', 'cancelado', 'fat_canc', 'resultado'
    ]
    df_aggrid_export = df_aggrid[[c for c in colunas_aggrid_export if c in df_aggrid.columns]].copy()
    buffer_aggrid = io.BytesIO()
    with pd.ExcelWriter(buffer_aggrid, engine='xlsxwriter') as writer:
        df_aggrid_export.to_excel(writer, index=False, sheet_name='Detalhamento Clusters')
    buffer_aggrid.seek(0)
    st.download_button(
        label="📥 Exportar Detalhamento para Excel",
        data=buffer_aggrid,
        file_name="detalhamento_clusters.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_aggrid_detalhamento"
    )

    st.divider()

    # ==========================================================================
    # 9. ANÁLISE DE JANELAS DE COMPARTILHAMENTO DE GRADE
    # ==========================================================================
    st.header("📐 Análise de Janelas de Compartilhamento de Grade")
    st.markdown(
        "Para cada par de turmas conectadas, mostra em que posição da grade a turma entrante "
        "começou a compartilhar aulas com a turma pioneira. "
        "**Aulas antes do compartilhamento** são aulas que a pioneira já havia dado sozinha — "
        "representam janelas de aproveitamento e matrícula que poderiam ter sido compartilhadas."
    )

    # Aulas por turma ordenadas por data (base filtrada por empresa + filtros da seção 7)
    _seq = (
        df_cons
        .dropna(subset=['aula_id', 'turma_id', 'data_aula'])
        [['turma_id', 'turma_nome', 'aula_id', 'data_aula', 'curso', 'unidade', 'inicio_grade', 'data_prevista']]
        .drop_duplicates(subset=['turma_id', 'aula_id'])
        .sort_values(['turma_id', 'data_aula'])
    )
    _seq['seq_na_grade'] = _seq.groupby('turma_id').cumcount() + 1
    _total = _seq.groupby('turma_id')['aula_id'].count().reset_index(name='total_aulas_grade')
    _seq = _seq.merge(_total, on='turma_id')

    _meta = (
        df_cons
        .groupby('turma_id')
        .agg(
            turma_nome=('turma_nome', 'first'),
            curso=('curso', 'first'),
            unidade=('unidade', 'first'),
            inicio_grade=('inicio_grade', 'first'),
            data_prevista=('data_prevista', 'first'),
        )
        .reset_index()
    )

    # Pares de turmas que compartilham aulas (ambas dentro dos filtros ativos)
    _aulas_filtradas = _seq[['aula_id', 'turma_id']].drop_duplicates()
    _pares_raw = _aulas_filtradas.merge(_aulas_filtradas, on='aula_id', suffixes=('_a', '_b'))
    _pares_raw = _pares_raw[_pares_raw['turma_id_a'] != _pares_raw['turma_id_b']]
    _pares = _pares_raw[['turma_id_a', 'turma_id_b']].drop_duplicates()

    _pares = _pares.merge(
        _meta[['turma_id', 'inicio_grade']].rename(columns={'turma_id': 'turma_id_a', 'inicio_grade': 'ig_a'}),
        on='turma_id_a', how='left'
    )
    _pares = _pares.merge(
        _meta[['turma_id', 'inicio_grade']].rename(columns={'turma_id': 'turma_id_b', 'inicio_grade': 'ig_b'}),
        on='turma_id_b', how='left'
    )
    _pares = _pares.dropna(subset=['ig_a', 'ig_b'])

    # Normalizar: A é sempre a pioneira (início mais antigo); descartar duplicatas espelhadas
    _pares[['tid_a', 'tid_b', 'ig_a_n', 'ig_b_n']] = _pares.apply(
        lambda r: pd.Series(
            (r['turma_id_a'], r['turma_id_b'], r['ig_a'], r['ig_b'])
            if r['ig_a'] <= r['ig_b']
            else (r['turma_id_b'], r['turma_id_a'], r['ig_b'], r['ig_a'])
        ),
        axis=1
    )
    _pares = (
        _pares[['tid_a', 'tid_b', 'ig_a_n', 'ig_b_n']]
        .rename(columns={'ig_a_n': 'ig_a', 'ig_b_n': 'ig_b'})
        .drop_duplicates(subset=['tid_a', 'tid_b'])
    )

    # Índice: turma_id → df de aulas (aula_id como índice)
    _aulas_idx = {
        tid: grp.set_index('aula_id')
        for tid, grp in _seq.groupby('turma_id')
    }

    _rows = []
    for _, par in _pares.iterrows():
        tid_a, tid_b = par['tid_a'], par['tid_b']
        ig_a, ig_b = par['ig_a'], par['ig_b']

        if tid_a not in _aulas_idx or tid_b not in _aulas_idx:
            continue

        df_a = _aulas_idx[tid_a][['seq_na_grade', 'data_aula', 'total_aulas_grade']]
        aulas_b_ids = set(_aulas_idx[tid_b].index)
        shared_in_a = df_a[df_a.index.isin(aulas_b_ids)]

        if shared_in_a.empty:
            continue

        first_seq = int(shared_in_a['seq_na_grade'].min())
        last_seq = int(shared_in_a['seq_na_grade'].max())
        total_a = int(df_a['total_aulas_grade'].iloc[0])
        total_shared = len(shared_in_a)
        aulas_antes = first_seq - 1
        pct_entrada = round(aulas_antes / total_a * 100, 1) if total_a > 0 else 0.0
        gap_dias = int((ig_b - ig_a).days) if pd.notna(ig_a) and pd.notna(ig_b) else None

        meta_a_rows = _meta[_meta['turma_id'] == tid_a]
        meta_b_rows = _meta[_meta['turma_id'] == tid_b]
        if meta_a_rows.empty or meta_b_rows.empty:
            continue
        ma, mb = meta_a_rows.iloc[0], meta_b_rows.iloc[0]

        _rows.append({
            'cluster': cluster_map.get(tid_a, cluster_map.get(tid_b, '—')),
            'turma_pioneira': ma['turma_nome'],
            'turma_entrante': mb['turma_nome'],
            'curso': ma['curso'],
            'unidade': ma['unidade'],
            'inicio_grade_pioneira': ig_a,
            'inicio_grade_entrante': ig_b,
            'gap_dias': gap_dias,
            'total_aulas_grade_pioneira': total_a,
            'seq_entrada_na_grade': first_seq,
            'aulas_antes_compartilhamento': aulas_antes,
            'total_aulas_compartilhadas': total_shared,
            'aulas_exclusivas_pos_entrada': total_a - last_seq,
            'pct_grade_consumida_na_entrada': pct_entrada,
            'janela_perdida': 'Sim' if aulas_antes > 0 else 'Não',
        })

    df_janelas = pd.DataFrame(_rows)

    if df_janelas.empty:
        st.info("Nenhum compartilhamento entre turmas encontrado para os filtros atuais.")
    else:
        df_janelas = df_janelas.sort_values(
            by=['pct_grade_consumida_na_entrada', 'cluster'],
            ascending=[False, True]
        ).reset_index(drop=True)

        col_j1, col_j2, col_j3, col_j4 = st.columns(4)
        col_j1.metric("Pares Analisados", f"{len(df_janelas)}")
        col_j2.metric("Com Janela Perdida", f"{int((df_janelas['janela_perdida'] == 'Sim').sum())}")
        col_j3.metric("Média Aulas Antes Compartilhamento", f"{round(df_janelas['aulas_antes_compartilhamento'].mean(), 1)}")
        col_j4.metric("% Médio da Grade Consumida na Entrada", f"{round(df_janelas['pct_grade_consumida_na_entrada'].mean(), 1)}%")

        st.dataframe(
            df_janelas,
            use_container_width=True,
            hide_index=True,
            column_config={
                "cluster": st.column_config.TextColumn("Cluster", width="medium"),
                "turma_pioneira": st.column_config.TextColumn("Turma Pioneira", width="medium"),
                "turma_entrante": st.column_config.TextColumn("Turma Entrante", width="medium"),
                "curso": st.column_config.TextColumn("Curso", width="medium"),
                "unidade": st.column_config.TextColumn("Unidade", width="small"),
                "inicio_grade_pioneira": st.column_config.DatetimeColumn("Início Grade\nPioneira", format="DD/MM/YYYY"),
                "inicio_grade_entrante": st.column_config.DatetimeColumn("Início Grade\nEntrante", format="DD/MM/YYYY"),
                "gap_dias": st.column_config.NumberColumn("Gap (dias)"),
                "total_aulas_grade_pioneira": st.column_config.NumberColumn("Total Aulas\nGrade Pioneira"),
                "seq_entrada_na_grade": st.column_config.NumberColumn("Aula Nº\nEntrada"),
                "aulas_antes_compartilhamento": st.column_config.NumberColumn("Aulas Antes do\nCompartilhamento"),
                "total_aulas_compartilhadas": st.column_config.NumberColumn("Aulas\nCompartilhadas"),
                "aulas_exclusivas_pos_entrada": st.column_config.NumberColumn("Aulas Exclusivas\nPós Entrada"),
                "pct_grade_consumida_na_entrada": st.column_config.NumberColumn("% Grade Consumida\nna Entrada", format="%.1f%%"),
                "janela_perdida": st.column_config.TextColumn("Janela\nPerdida", width="small"),
            }
        )

        _export = df_janelas.copy()
        for col in ['inicio_grade_pioneira', 'inicio_grade_entrante']:
            if col in _export.columns:
                _export[col] = pd.to_datetime(_export[col], errors='coerce').dt.tz_localize(None)
        _buf_janelas = io.BytesIO()
        with pd.ExcelWriter(_buf_janelas, engine='xlsxwriter') as writer:
            _export.to_excel(writer, index=False, sheet_name='Janelas Compartilhamento')
        _buf_janelas.seek(0)
        st.download_button(
            label="📥 Exportar Análise de Janelas para Excel",
            data=_buf_janelas,
            file_name="janelas_compartilhamento.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_janelas_compartilhamento"
        )
