# _pages/turmas.py

import streamlit as st
import pandas as pd
import io

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.sql_loader import carregar_dados


def _calcular_ch(df_base, df_grade, hoje):
    """Calcula as 4 colunas de carga horária por aluno."""
    turma_ids = df_base['turma_id'].dropna().unique()
    df_g = df_grade[df_grade['turma_id'].isin(turma_ids)].copy()

    ch_turma = (
        df_g.groupby('turma_id')['carga_horaria_decimal']
        .sum().reset_index().rename(columns={'carga_horaria_decimal': 'ch_turma'})
    )
    inicio_grade = (
        df_g.groupby('turma_id')['data_aula_dt']
        .min().reset_index().rename(columns={'data_aula_dt': 'inicio_grade'})
    )

    df = df_base.merge(ch_turma, on='turma_id', how='left')
    df = df.merge(inicio_grade, on='turma_id', how='left')
    df['ch_turma'] = df['ch_turma'].fillna(0)
    df['data_pagamento_dt'] = df['data_pagamento'].dt.date

    df_ol = df[['order_id', 'turma_id', 'data_pagamento_dt', 'inicio_grade']].merge(
        df_g[['turma_id', 'aula_id', 'data_aula_dt', 'carga_horaria_decimal']],
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

    for col, mask in [('ch_contratada', 'in_contratada'), ('ch_concluida', 'in_concluida'), ('ch_restante', 'in_restante')]:
        agg = (
            df_ol[df_ol[mask]].groupby('order_id')['carga_horaria_decimal']
            .sum().reset_index().rename(columns={'carga_horaria_decimal': col})
        )
        df = df.merge(agg, on='order_id', how='left')
        df[col] = df[col].fillna(0)

    return df


def _gerar_pdf(df_exib, empresa, filtros_desc):
    """Gera PDF da lista de alunos em retrato."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from datetime import datetime

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=1*cm, bottomMargin=1*cm,
        leftMargin=1*cm, rightMargin=1*cm
    )
    elements = []
    styles = getSampleStyleSheet()

    style_title = ParagraphStyle(
        'title', parent=styles['Normal'],
        fontSize=13, fontName='Helvetica-Bold',
        alignment=TA_LEFT, spaceAfter=4
    )
    style_info = ParagraphStyle(
        'info', parent=styles['Normal'],
        fontSize=8, fontName='Helvetica',
        alignment=TA_LEFT, spaceAfter=3
    )
    style_cell = ParagraphStyle(
        'cell', parent=styles['Normal'],
        fontSize=7, fontName='Helvetica',
        leading=9
    )
    style_cell_bold = ParagraphStyle(
        'cellbold', parent=styles['Normal'],
        fontSize=7, fontName='Helvetica-Bold',
        leading=9
    )

    elements.append(Paragraph("LISTA DE ALUNOS POR TURMA", style_title))
    elements.append(Paragraph(f"Empresa: {empresa} | Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", style_info))
    elements.append(Paragraph(filtros_desc, style_info))
    elements.append(Paragraph(f"Total de alunos: {len(df_exib)}", style_info))
    elements.append(Spacer(1, 0.4*cm))

    cols = ['Aluno', 'CPF', 'Turma', 'Status', 'Pagamento', 'Valor (R$)',
            'Data Mat.', 'CH Turma', 'CH Conc.', 'CH Cont.', 'CH Rest.']
    data_keys = ['nome_cliente', 'cpf', 'turma_nome', 'status',
                 'metodo_pagamento', 'total_pedido', 'data_pagamento',
                 'ch_turma', 'ch_concluida', 'ch_contratada', 'ch_restante']

    header = [Paragraph(c, style_cell_bold) for c in cols]
    table_data = [header]

    for _, row in df_exib.iterrows():
        linha = []
        for k in data_keys:
            val = row.get(k, '')
            if k == 'total_pedido':
                val = f"R$ {float(val):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') if pd.notna(val) else ''
            elif k == 'data_pagamento':
                val = pd.to_datetime(val).strftime('%d/%m/%Y') if pd.notna(val) else ''
            elif k in ('ch_turma', 'ch_concluida', 'ch_contratada', 'ch_restante'):
                val = f"{float(val):.2f}h" if pd.notna(val) else ''
            elif k == 'order_id':
                val = str(int(val)) if pd.notna(val) else ''
            else:
                val = str(val) if pd.notna(val) else ''
            linha.append(Paragraph(val, style_cell))
        table_data.append(linha)

    # Larguras em retrato A4 (~19 cm utilizável — soma exata = 19.0 cm)
    # Aluno  CPF    Turma  Status  Pgto   Valor  Data   CHt    CHc    CHco   CHr
    col_widths = [3.5*cm, 2.0*cm, 2.8*cm, 1.6*cm, 1.6*cm, 1.6*cm,
                  1.5*cm, 1.1*cm, 1.1*cm, 1.1*cm, 1.1*cm]

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#cccccc')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(table)

    doc.build(elements)
    buf.seek(0)
    return buf


def run_page():
    st.title("🏫 Turmas — Lista de Alunos")
    TIMEZONE = 'America/Sao_Paulo'
    hoje = pd.Timestamp.now(tz=TIMEZONE).date()

    # -------------------------------------------------------------------------
    # CARREGAMENTO
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # FILTROS SIDEBAR
    # -------------------------------------------------------------------------
    st.sidebar.header("Filtros")

    # Empresa
    empresas = df_orders['empresa'].dropna().unique().tolist()
    default_idx = empresas.index('Degrau') if 'Degrau' in empresas else 0
    empresa_sel = st.sidebar.radio("Empresa:", empresas, index=default_idx)
    df_emp = df_orders[df_orders['empresa'] == empresa_sel].copy()

    # --- Filtros Macro ---
    st.sidebar.subheader("Filtros Macro")
    st.sidebar.caption("Selecione pelo menos 2 para exibir a lista.")

    cvs_opts = sorted(df_emp['curso_venda'].dropna().unique())
    cvs_sel = st.sidebar.multiselect("Curso Venda:", cvs_opts, key="t_cvs")

    cursos_opts = sorted(df_emp['curso'].dropna().unique())
    cursos_sel = st.sidebar.multiselect("Curso:", cursos_opts, key="t_curso")

    unidades_opts = sorted(df_emp['unidade'].dropna().unique())
    unidades_sel = st.sidebar.multiselect("Unidade:", unidades_opts, key="t_unidade")

    turmas_opts = sorted(df_emp['turma_nome'].dropna().unique())
    turmas_sel = st.sidebar.multiselect("Turma:", turmas_opts, key="t_turma")

    filtros_ativos = sum([bool(cvs_sel), bool(cursos_sel), bool(unidades_sel), bool(turmas_sel)])

    if filtros_ativos < 2:
        st.info(
            "Selecione pelo menos **2 filtros macro** (Curso Venda, Curso, Unidade ou Turma) "
            "para visualizar a lista de alunos."
        )
        faltam = 2 - filtros_ativos
        st.caption(f"Faltam {faltam} filtro(s) macro.")
        return

    # Aplica filtros macro
    df_base = df_emp.copy()
    if cvs_sel:
        df_base = df_base[df_base['curso_venda'].isin(cvs_sel)]
    if cursos_sel:
        df_base = df_base[df_base['curso'].isin(cursos_sel)]
    if unidades_sel:
        df_base = df_base[df_base['unidade'].isin(unidades_sel)]
    if turmas_sel:
        df_base = df_base[df_base['turma_nome'].isin(turmas_sel)]

    # --- Filtros Específicos ---
    st.sidebar.subheader("Filtros Específicos")

    turmas_com_grade = set(df_grade['turma_id'].dropna().unique())
    grade_sel = st.sidebar.radio("Grade:", ["Com Grade", "Sem Grade", "Todas"], index=2, key="t_grade")
    if grade_sel == "Com Grade":
        df_base = df_base[df_base['turma_id'].isin(turmas_com_grade)]
    elif grade_sel == "Sem Grade":
        df_base = df_base[~df_base['turma_id'].isin(turmas_com_grade)]

    status_list = sorted(df_base['status'].dropna().unique().tolist())
    default_status = df_base[df_base['status_id'].isin([2, 3, 14, 15, 19])]['status'].unique().tolist()
    if not default_status:
        default_status = status_list
    status_sel = st.sidebar.multiselect("Status:", status_list, default=default_status, key="t_status")
    if status_sel:
        df_base = df_base[df_base['status'].isin(status_sel)]

    tipo_sel = st.sidebar.radio("Tipo de Aluno:", ["Todos", "Pagante", "Passaporte"], index=0, key="t_tipo")
    if tipo_sel == "Pagante":
        df_base = df_base[df_base['total_pedido'] > 0]
    elif tipo_sel == "Passaporte":
        df_base = df_base[df_base['total_pedido'] == 0]

    if df_base.empty:
        st.warning("Nenhum resultado para os filtros selecionados.")
        return

    # -------------------------------------------------------------------------
    # CÁLCULO DE CH
    # -------------------------------------------------------------------------
    df_final = _calcular_ch(df_base, df_grade, hoje)

    # -------------------------------------------------------------------------
    # MÉTRICAS
    # -------------------------------------------------------------------------
    col1, col2 = st.columns(2)
    col1.metric("Alunos", df_final.shape[0])
    col2.metric("Turmas", df_final['turma_nome'].nunique())

    st.divider()

    # -------------------------------------------------------------------------
    # TABELA
    # -------------------------------------------------------------------------
    colunas_exib = [
        'curso_venda', 'turma_nome', 'cpf', 'nome_cliente',
        'metodo_pagamento', 'status', 'unidade', 'total_pedido', 'data_pagamento',
        'ch_turma', 'ch_concluida', 'ch_contratada', 'ch_restante'
    ]
    df_exib = df_final[colunas_exib].sort_values(['turma_nome', 'nome_cliente'])

    st.dataframe(
        df_exib,
        use_container_width=True,
        hide_index=True,
        column_config={
            "curso_venda": st.column_config.TextColumn("Curso Venda"),
            "turma_nome": st.column_config.TextColumn("Turma"),
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
        }
    )

    # -------------------------------------------------------------------------
    # EXPORTAR / IMPRIMIR
    # -------------------------------------------------------------------------
    col_exp1, col_exp2 = st.columns(2)

    # Excel
    with col_exp1:
        df_export = df_exib.copy()
        if pd.api.types.is_datetime64_any_dtype(df_export['data_pagamento']):
            if getattr(df_export['data_pagamento'].dt, 'tz', None) is not None:
                df_export['data_pagamento'] = df_export['data_pagamento'].dt.tz_localize(None)
        buf_xl = io.BytesIO()
        with pd.ExcelWriter(buf_xl, engine='xlsxwriter') as writer:
            df_export.to_excel(writer, index=False, sheet_name='Alunos')
        buf_xl.seek(0)
        st.download_button(
            label="📥 Exportar Excel",
            data=buf_xl,
            file_name="turmas_alunos.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="t_download_excel"
        )

    # PDF
    with col_exp2:
        partes = []
        if cvs_sel:
            partes.append(f"Curso Venda: {', '.join(cvs_sel)}")
        if cursos_sel:
            partes.append(f"Curso: {', '.join(cursos_sel)}")
        if unidades_sel:
            partes.append(f"Unidade: {', '.join(unidades_sel)}")
        if turmas_sel:
            partes.append(f"Turma: {', '.join(turmas_sel)}")
        filtros_desc = " | ".join(partes) if partes else "Sem filtros adicionais"

        buf_pdf = _gerar_pdf(df_exib, empresa_sel, filtros_desc)
        st.download_button(
            label="🖨️ Imprimir Lista (PDF)",
            data=buf_pdf,
            file_name="lista_alunos_turmas.pdf",
            mime="application/pdf",
            key="t_download_pdf"
        )
