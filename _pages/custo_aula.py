# _pages/custo_aula.py

import streamlit as st
import pandas as pd
import io
from datetime import datetime

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