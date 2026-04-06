# _pages/analise_consumo_individual.py

import streamlit as st
import pandas as pd
import io

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.sql_loader import carregar_dados


def run_page():
    st.title("📚 Análise de Consumo Individual")
    TIMEZONE = 'America/Sao_Paulo'
    hoje = pd.Timestamp.now(tz=TIMEZONE).date()

    # ==========================================================================
    # 1. CARREGAMENTO DE DADOS
    # ==========================================================================
    df_orders = carregar_dados("consultas/turmas/matriculas_consumo.sql")
    df_grade = carregar_dados("consultas/turmas/grade_consumo.sql")

    df_orders['data_pagamento'] = pd.to_datetime(df_orders['data_pagamento'], errors='coerce')
    df_orders['total_pedido'] = pd.to_numeric(df_orders['total_pedido'], errors='coerce')
    df_orders['turma_id'] = pd.to_numeric(df_orders['turma_id'], errors='coerce')
    df_orders['status_id'] = pd.to_numeric(df_orders['status_id'], errors='coerce')

    df_grade['data_aula'] = pd.to_datetime(df_grade['data_aula'], errors='coerce')
    df_grade['carga_horaria_decimal'] = pd.to_numeric(df_grade['carga_horaria_decimal'], errors='coerce').fillna(0)
    df_grade['turma_id'] = pd.to_numeric(df_grade['turma_id'], errors='coerce')
    df_grade['data_aula_dt'] = df_grade['data_aula'].dt.date

    # ==========================================================================
    # 2. FILTROS NA BARRA LATERAL
    # ==========================================================================
    st.sidebar.header("Filtros")

    # Empresa
    empresas = df_orders['empresa'].dropna().unique().tolist()
    default_idx = empresas.index('Degrau') if 'Degrau' in empresas else 0
    empresa_sel = st.sidebar.radio("Empresa:", empresas, index=default_idx)
    df_emp = df_orders[df_orders['empresa'] == empresa_sel].copy()

    # Período (data de pagamento / matrícula)
    hoje_aware = pd.Timestamp.now(tz=TIMEZONE).date()
    primeiro_dia_mes = hoje_aware.replace(day=1)
    periodo = st.sidebar.date_input(
        "Período (Data de Matrícula):",
        value=[primeiro_dia_mes, hoje_aware],
        key="consumo_date_range"
    )

    # Status
    status_list = sorted(df_emp['status'].dropna().unique().tolist())
    default_status = df_emp[df_emp['status_id'].isin([2, 3, 14, 15, 19])]['status'].unique().tolist()
    if not default_status:
        default_status = status_list
    status_sel = st.sidebar.multiselect("Status do Pedido:", status_list, default=default_status)

    try:
        data_ini = pd.Timestamp(periodo[0])
        data_fim = pd.Timestamp(periodo[1]) + pd.Timedelta(days=1)
    except IndexError:
        st.warning("Por favor, selecione um período de datas.")
        st.stop()

    df_base = df_emp[
        (df_emp['data_pagamento'] >= data_ini) &
        (df_emp['data_pagamento'] < data_fim) &
        (df_emp['status'].isin(status_sel))
    ].copy()

    # Filtro: Grade
    turmas_com_grade = set(df_grade['turma_id'].dropna().unique())
    opcoes_grade = {"Com Grade": True, "Sem Grade": False}
    grade_sel = st.sidebar.radio("Turma:", list(opcoes_grade.keys()), index=0, key="ci_grade")
    df_base = df_base[df_base['turma_id'].isin(turmas_com_grade) == opcoes_grade[grade_sel]]

    # Filtro: Tipo de aluno (Pagante / Passaporte)
    tipo_aluno_sel = st.sidebar.radio(
        "Tipo de Aluno:",
        ["Todos", "Pagante", "Passaporte"],
        index=0,
        key="ci_tipo_aluno"
    )
    if tipo_aluno_sel == "Pagante":
        df_base = df_base[df_base['total_pedido'] > 0]
    elif tipo_aluno_sel == "Passaporte":
        df_base = df_base[df_base['total_pedido'] == 0]

    # Filtros adicionais em expander
    with st.sidebar.expander("Filtros Adicionais", expanded=True):
        unidades = sorted(df_base['unidade'].dropna().unique())
        unidades_sel = st.multiselect("Unidade:", unidades, default=unidades, key="ci_unidade")
        df_base = df_base[df_base['unidade'].isin(unidades_sel)]

        cursos = sorted(df_base['curso'].dropna().unique())
        cursos_sel = st.multiselect("Curso:", cursos, default=cursos, key="ci_curso")
        df_base = df_base[df_base['curso'].isin(cursos_sel)]

        cvs = sorted(df_base['curso_venda'].dropna().unique())
        cvs_sel = st.multiselect("Curso Venda:", cvs, default=cvs, key="ci_curso_venda")
        df_base = df_base[df_base['curso_venda'].isin(cvs_sel)]

        turmas = sorted(df_base['turma_nome'].dropna().unique())
        turmas_sel = st.multiselect("Turma:", turmas, default=turmas, key="ci_turma")
        df_base = df_base[df_base['turma_nome'].isin(turmas_sel)]

    # ==========================================================================
    # 3. TABELA INDIVIDUAL DE MATRÍCULAS
    # ==========================================================================
    if not df_base.empty:
        turma_ids = df_base['turma_id'].dropna().unique()
        df_grade_filtrada = df_grade[df_grade['turma_id'].isin(turma_ids)].copy()

        ch_turma = (
            df_grade_filtrada.groupby('turma_id')['carga_horaria_decimal']
            .sum().reset_index().rename(columns={'carga_horaria_decimal': 'ch_turma'})
        )
        inicio_grade = (
            df_grade_filtrada.groupby('turma_id')['data_aula_dt']
            .min().reset_index().rename(columns={'data_aula_dt': 'inicio_grade'})
        )

        df_base = df_base.merge(ch_turma, on='turma_id', how='left')
        df_base = df_base.merge(inicio_grade, on='turma_id', how='left')
        df_base['ch_turma'] = df_base['ch_turma'].fillna(0)
        df_base['data_pagamento_dt'] = df_base['data_pagamento'].dt.date

        df_ol = df_base[['order_id', 'turma_id', 'data_pagamento_dt', 'inicio_grade']].merge(
            df_grade_filtrada[['turma_id', 'aula_id', 'data_aula_dt', 'carga_horaria_decimal']],
            on='turma_id', how='left'
        )
        df_ol['enrolled_before'] = (
            df_ol['inicio_grade'].isna() |
            (df_ol['data_pagamento_dt'] <= df_ol['inicio_grade'])
        )
        df_ol['in_contratada'] = (
            df_ol['enrolled_before'] |
            (~df_ol['enrolled_before'] & (df_ol['data_aula_dt'] >= df_ol['data_pagamento_dt']))
        )
        df_ol['in_concluida'] = df_ol['in_contratada'] & (df_ol['data_aula_dt'] <= hoje)
        df_ol['in_restante'] = df_ol['in_contratada'] & (df_ol['data_aula_dt'] > hoje)

        ch_contratada_agg = (
            df_ol[df_ol['in_contratada']].groupby('order_id')['carga_horaria_decimal']
            .sum().reset_index().rename(columns={'carga_horaria_decimal': 'ch_contratada'})
        )
        ch_concluida_agg = (
            df_ol[df_ol['in_concluida']].groupby('order_id')['carga_horaria_decimal']
            .sum().reset_index().rename(columns={'carga_horaria_decimal': 'ch_concluida'})
        )
        ch_restante_agg = (
            df_ol[df_ol['in_restante']].groupby('order_id')['carga_horaria_decimal']
            .sum().reset_index().rename(columns={'carga_horaria_decimal': 'ch_restante'})
        )

        df_final = df_base.merge(ch_contratada_agg, on='order_id', how='left')
        df_final = df_final.merge(ch_concluida_agg, on='order_id', how='left')
        df_final = df_final.merge(ch_restante_agg, on='order_id', how='left')
        df_final['ch_contratada'] = df_final['ch_contratada'].fillna(0)
        df_final['ch_concluida'] = df_final['ch_concluida'].fillna(0)
        df_final['ch_restante'] = df_final['ch_restante'].fillna(0)

        # --- EXIBIÇÃO ---
        st.info(
            f"Exibindo matrículas de **{periodo[0].strftime('%d/%m/%Y')}** "
            f"a **{periodo[1].strftime('%d/%m/%Y')}**"
        )

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total de Matrículas", df_final.shape[0])
        col2.metric("CH Total da Turma (soma)", f"{df_final['ch_turma'].sum():,.1f}h")
        col3.metric("CH Total Contratada", f"{df_final['ch_contratada'].sum():,.1f}h")
        col4.metric("CH Total Restante", f"{df_final['ch_restante'].sum():,.1f}h")

        st.divider()
        st.subheader("Lista de Alunos Matriculados — Consumo Individual")

        colunas_exib = [
            'order_id', 'curso_venda', 'turma_nome', 'turno', 'cpf', 'nome_cliente',
            'metodo_pagamento', 'status', 'unidade', 'total_pedido', 'data_pagamento',
            'ch_turma', 'ch_concluida', 'ch_contratada', 'ch_restante',
            'vendedor'
        ]

        df_exib = df_final[colunas_exib].sort_values('data_pagamento', ascending=False)

        st.dataframe(
            df_exib,
            use_container_width=True,
            hide_index=True,
            column_config={
                "order_id": st.column_config.NumberColumn("Pedido", format="%d"),
                "curso_venda": st.column_config.TextColumn("Curso Venda"),
                "turma_nome": st.column_config.TextColumn("Turma"),
                "turno": st.column_config.TextColumn("Turno"),
                "cpf": st.column_config.TextColumn("CPF"),
                "nome_cliente": st.column_config.TextColumn("Aluno"),
                "metodo_pagamento": st.column_config.TextColumn("Pagamento"),
                "status": st.column_config.TextColumn("Status"),
                "unidade": st.column_config.TextColumn("Unidade"),
                "total_pedido": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
                "data_pagamento": st.column_config.DatetimeColumn("Data Matrícula", format="DD/MM/YYYY"),
                "ch_turma": st.column_config.NumberColumn("CH Turma (h)", format="%.2f"),
                "ch_concluida": st.column_config.NumberColumn("CH Concluída (h)", format="%.2f"),
                "ch_contratada": st.column_config.NumberColumn("CH Contratada (h)", format="%.2f"),
                "ch_restante": st.column_config.NumberColumn("CH Restante (h)", format="%.2f"),
                "vendedor": st.column_config.TextColumn("Vendedor"),
            }
        )

        df_export = df_exib.copy()
        if pd.api.types.is_datetime64_any_dtype(df_export['data_pagamento']):
            tz = getattr(df_export['data_pagamento'].dt, 'tz', None)
            if tz is not None:
                df_export['data_pagamento'] = df_export['data_pagamento'].dt.tz_localize(None)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_export.to_excel(writer, index=False, sheet_name='Consumo Individual')
        buffer.seek(0)
        st.download_button(
            label="📥 Exportar para Excel",
            data=buffer,
            file_name="consumo_individual.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_consumo_individual"
        )
    else:
        st.warning("Não há matrículas para o período e filtros selecionados.")

    # ==========================================================================
    # 5. ANÁLISE AGRUPADA POR TURMA (totalmente independente da data acima)
    # ==========================================================================
    st.divider()
    st.header("🏫 Resumo por Turma")

    # Base independente: parte de df_orders filtrado apenas por empresa
    df_turma_base = df_orders[df_orders['empresa'] == empresa_sel].copy()

    # Aplica filtro de status da sidebar
    df_turma_base = df_turma_base[df_turma_base['status'].isin(status_sel)]

    # Aplica filtro de grade da sidebar
    if opcoes_grade[grade_sel]:
        df_turma_base = df_turma_base[df_turma_base['turma_id'].isin(turmas_com_grade)]
    else:
        df_turma_base = df_turma_base[~df_turma_base['turma_id'].isin(turmas_com_grade)]

    # Aplica filtro de tipo de aluno da sidebar
    if tipo_aluno_sel == "Pagante":
        df_turma_base = df_turma_base[df_turma_base['total_pedido'] > 0]
    elif tipo_aluno_sel == "Passaporte":
        df_turma_base = df_turma_base[df_turma_base['total_pedido'] == 0]

    # Início da grade (1ª aula) por turma
    inicio_grade_all = (
        df_grade.groupby('turma_id')['data_aula']
        .min().reset_index().rename(columns={'data_aula': 'inicio_grade_turma'})
    )
    inicio_grade_all['inicio_grade_dt'] = inicio_grade_all['inicio_grade_turma'].dt.date
    df_turma_base = df_turma_base.merge(
        inicio_grade_all[['turma_id', 'inicio_grade_dt']], on='turma_id', how='left'
    )

    # Filtros próprios desta seção
    col_ft1, col_ft2 = st.columns(2)
    with col_ft1:
        periodo_turma = st.date_input(
            "Período (Início da Turma — 1ª aula da grade):",
            value=[hoje.replace(month=1, day=1), hoje],
            key="ci_periodo_turma"
        )
    try:
        turma_data_ini = periodo_turma[0]
        turma_data_fim = periodo_turma[1]
    except IndexError:
        st.warning("Por favor, selecione um período para a tabela de turmas.")
        return

    df_turma_base = df_turma_base[
        df_turma_base['inicio_grade_dt'].notna() &
        (df_turma_base['inicio_grade_dt'] >= turma_data_ini) &
        (df_turma_base['inicio_grade_dt'] <= turma_data_fim)
    ]

    if df_turma_base.empty:
        st.warning("Não há turmas para os filtros selecionados.")
        return

    # Grade data para as turmas filtradas
    turma_ids_resumo = df_turma_base['turma_id'].dropna().unique()
    df_grade_resumo = df_grade[df_grade['turma_id'].isin(turma_ids_resumo)].copy()

    # CH da grade por turma — dados puros da grade, sem considerar matrículas
    ch_turma_grade = (
        df_grade_resumo.groupby('turma_id')['carga_horaria_decimal']
        .sum().rename('ch_turma_grade')
    )
    ch_concluida_grade = (
        df_grade_resumo[df_grade_resumo['data_aula_dt'] <= hoje]
        .groupby('turma_id')['carga_horaria_decimal']
        .sum().rename('ch_concluida_grade')
    )

    # Matrículas por turma — respeita filtro pagante/passaporte
    df_turma = (
        df_turma_base.groupby(['turma_id', 'turma_nome', 'curso', 'turno', 'inicio_grade_dt'])
        .agg(matriculas=('order_id', 'nunique'))
        .reset_index()
    )
    df_turma = df_turma.merge(ch_turma_grade, on='turma_id', how='left')
    df_turma = df_turma.merge(ch_concluida_grade, on='turma_id', how='left')
    df_turma['ch_turma_grade'] = df_turma['ch_turma_grade'].fillna(0)
    df_turma['ch_concluida_grade'] = df_turma['ch_concluida_grade'].fillna(0)

    df_turma['pct_restante'] = (
        (df_turma['ch_turma_grade'] - df_turma['ch_concluida_grade'])
        / df_turma['ch_turma_grade'].replace(0, pd.NA) * 100
    ).fillna(0).round(1)

    def cor_progresso(pct):
        if pct < 25:
            return '🔴'
        elif pct < 50:
            return '🟠'
        elif pct < 75:
            return '🟡'
        else:
            return '🟢'

    df_turma[''] = df_turma['pct_restante'].apply(cor_progresso)

    # Filtro independente por faixa de % restante
    FAIXAS = {
        '🔴  < 25% restante': lambda p: p < 25,
        '🟠  25% a 50% restante': lambda p: (p >= 25) & (p < 50),
        '🟡  50% a 75% restante': lambda p: (p >= 50) & (p < 75),
        '🟢  > 75% restante': lambda p: p >= 75,
    }
    with col_ft2:
        faixas_sel = st.multiselect(
            "Filtrar por % restante da grade:",
            list(FAIXAS.keys()),
            default=list(FAIXAS.keys()),
            key="ci_faixa_progresso"
        )
    if faixas_sel:
        mask = pd.Series(False, index=df_turma.index)
        for faixa in faixas_sel:
            mask = mask | FAIXAS[faixa](df_turma['pct_restante'])
        df_turma = df_turma[mask]

    df_turma['inicio_grade_fmt'] = pd.to_datetime(df_turma['inicio_grade_dt']).dt.strftime('%d/%m/%Y')

    df_turma_exib = (
        df_turma[['', 'turma_nome', 'curso', 'turno', 'inicio_grade_fmt', 'matriculas',
                   'ch_turma_grade', 'ch_concluida_grade', 'pct_restante']]
        .sort_values('turma_nome')
    )

    st.dataframe(
        df_turma_exib,
        use_container_width=True,
        hide_index=True,
        column_config={
            "": st.column_config.TextColumn("", width="small"),
            "turma_nome": st.column_config.TextColumn("Turma"),
            "curso": st.column_config.TextColumn("Curso"),
            "turno": st.column_config.TextColumn("Turno"),
            "inicio_grade_fmt": st.column_config.TextColumn("Início Grade"),
            "matriculas": st.column_config.NumberColumn("Matrículas"),
            "ch_turma_grade": st.column_config.NumberColumn("CH Turma (h)", format="%.2f"),
            "ch_concluida_grade": st.column_config.NumberColumn("CH Concluída (h)", format="%.2f"),
            "pct_restante": st.column_config.NumberColumn("% Restante", format="%.1f%%"),
        }
    )

    # Download por turmas selecionadas — usa df_turma_base (sem filtro de data_pagamento)
    st.markdown("##### Baixar lista de alunos por turma")
    turmas_disponiveis = df_turma_exib['turma_nome'].tolist()
    if turmas_disponiveis:
        incluir_todas = st.checkbox("Incluir todas as turmas do filtro", key="ci_incluir_todas_turmas")
        if incluir_todas:
            turmas_download = turmas_disponiveis
        else:
            turmas_download = st.multiselect(
                "Selecione as turmas:", turmas_disponiveis, key="ci_turma_download"
            )
        if turmas_download:
            df_down = df_turma_base[df_turma_base['turma_nome'].isin(turmas_download)].copy()

            # Calcular CH individual para os alunos do download
            down_turma_ids = df_down['turma_id'].dropna().unique()
            df_grade_down = df_grade[df_grade['turma_id'].isin(down_turma_ids)].copy()

            ch_turma_down = (
                df_grade_down.groupby('turma_id')['carga_horaria_decimal']
                .sum().reset_index().rename(columns={'carga_horaria_decimal': 'ch_turma'})
            )
            inicio_grade_down = (
                df_grade_down.groupby('turma_id')['data_aula_dt']
                .min().reset_index().rename(columns={'data_aula_dt': 'inicio_grade'})
            )
            df_down = df_down.merge(ch_turma_down, on='turma_id', how='left')
            df_down = df_down.merge(inicio_grade_down, on='turma_id', how='left')
            df_down['ch_turma'] = df_down['ch_turma'].fillna(0)
            df_down['data_pagamento_dt'] = df_down['data_pagamento'].dt.date

            df_ol_down = df_down[['order_id', 'turma_id', 'data_pagamento_dt', 'inicio_grade']].merge(
                df_grade_down[['turma_id', 'aula_id', 'data_aula_dt', 'carga_horaria_decimal']],
                on='turma_id', how='left'
            )
            df_ol_down['enrolled_before'] = (
                df_ol_down['inicio_grade'].isna() |
                (df_ol_down['data_pagamento_dt'] <= df_ol_down['inicio_grade'])
            )
            df_ol_down['in_contratada'] = (
                df_ol_down['enrolled_before'] |
                (~df_ol_down['enrolled_before'] & (df_ol_down['data_aula_dt'] >= df_ol_down['data_pagamento_dt']))
            )
            df_ol_down['in_concluida'] = df_ol_down['in_contratada'] & (df_ol_down['data_aula_dt'] <= hoje)
            df_ol_down['in_restante'] = df_ol_down['in_contratada'] & (df_ol_down['data_aula_dt'] > hoje)

            for col_name, mask_col in [('ch_contratada', 'in_contratada'), ('ch_concluida', 'in_concluida'), ('ch_restante', 'in_restante')]:
                agg = (
                    df_ol_down[df_ol_down[mask_col]]
                    .groupby('order_id')['carga_horaria_decimal']
                    .sum().reset_index().rename(columns={'carga_horaria_decimal': col_name})
                )
                df_down = df_down.merge(agg, on='order_id', how='left')
                df_down[col_name] = df_down[col_name].fillna(0)

            colunas_download = [
                'order_id', 'curso_venda', 'turma_nome', 'turno', 'cpf', 'nome_cliente',
                'metodo_pagamento', 'status', 'unidade', 'total_pedido', 'data_pagamento',
                'vendedor', 'ch_turma', 'ch_concluida', 'ch_contratada', 'ch_restante'
            ]
            df_down = df_down[colunas_download]
            if pd.api.types.is_datetime64_any_dtype(df_down['data_pagamento']):
                if getattr(df_down['data_pagamento'].dt, 'tz', None) is not None:
                    df_down['data_pagamento'] = df_down['data_pagamento'].dt.tz_localize(None)
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                df_down.to_excel(writer, index=False, sheet_name='Alunos da Turma')
            buf.seek(0)
            label = f"📥 Baixar alunos ({len(turmas_download)} turma(s) — {len(df_down)} alunos)"
            st.download_button(
                label=label,
                data=buf,
                file_name="alunos_turmas_selecionadas.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_turma_sel"
            )
