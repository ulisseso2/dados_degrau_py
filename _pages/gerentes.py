import sys
import os
import pandas as pd
import streamlit as st
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.sql_loader import carregar_dados


def run_page():
    st.title("📊 Dashboard Gerentes — Matrículas")
    TIMEZONE = 'America/Sao_Paulo'

    # Carrega orders
    df = carregar_dados("consultas/orders/orders.sql")
    if df is None or df.empty:
        st.warning("Nenhum dado de orders disponível.")
        return

    # Conversão de datas
    df["data_pagamento"] = pd.to_datetime(df["data_pagamento"]).dt.tz_localize(TIMEZONE, ambiguous='infer')

    # Filtros principais
    empresas = sorted(df["empresa"].dropna().unique().tolist())
    if not empresas:
        st.warning("Nenhuma empresa encontrada nos dados.")
        return

    default_index = 0
    if "Degrau" in empresas:
        default_index = empresas.index("Degrau")

    empresa_selecionada = st.sidebar.radio("Selecione uma empresa:", empresas, index=default_index)

    hoje_aware = pd.Timestamp.now(tz=TIMEZONE).date()
    periodo = st.sidebar.date_input("Período - Data Pagamento", [hoje_aware, hoje_aware])
    try:
        data_inicio_aware = pd.Timestamp(periodo[0], tz=TIMEZONE)
        data_fim_aware = pd.Timestamp(periodo[1], tz=TIMEZONE) + pd.Timedelta(days=1)
    except Exception:
        st.error("Período inválido")
        return

    # Prepara df por empresa para extrair opções
    df_empresa = df[df["empresa"] == empresa_selecionada]

    # Status
    status_list = sorted(df_empresa["status"].dropna().unique().tolist())
    status_default = df_empresa[df_empresa["status_id"].isin([2, 3, 14, 10, 15])]["status"].dropna().unique().tolist()
    if not status_default:
        status_default = status_list
    status_selecionado = st.sidebar.multiselect("Status:", options=status_list, default=status_default)

    # Categoria (explode das listas separadas por ', ')
    categorias_disponiveis = df_empresa['categoria'].dropna().str.split(', ').explode().str.strip().dropna().unique().tolist()
    categorias_disponiveis = sorted(categorias_disponiveis)
    categoria_selecionada = st.sidebar.multiselect("Categoria:", options=categorias_disponiveis, default=categorias_disponiveis)

    # Unidades
    unidades = sorted(df_empresa['unidade'].dropna().unique().tolist())
    unidade_selecionada = st.sidebar.multiselect("Unidade:", options=unidades, default=unidades)

    # Dono (gerente)
    donos = sorted(df_empresa['dono'].dropna().unique().tolist())
    dono_selecionado = st.sidebar.multiselect("Dono (Gerente):", options=donos, default=donos)

    # Vendedor (remover 'Indefinido' das opções)
    vendedores_disponiveis = sorted(df_empresa['vendedor'].dropna().unique().tolist())
    vendedores_disponiveis = [v for v in vendedores_disponiveis if v != 'Indefinido']
    vendedor_selecionado = st.sidebar.multiselect("Vendedor:", options=vendedores_disponiveis, default=vendedores_disponiveis)

    # Aplica filtros básicos
    filtros = (
        (df['empresa'] == empresa_selecionada) &
        (df['data_pagamento'] >= data_inicio_aware) &
        (df['data_pagamento'] < data_fim_aware) &
        (df['total_pedido'] != 0) &
        (~df['metodo_pagamento'].isin([5, 8, 13])) &
        (df['vendedor'] != 'Indefinido')
    )

    if status_selecionado:
        filtros = filtros & (df['status'].isin(status_selecionado))

    df_filtrado = df[filtros].copy()

    # Filtra por categorias (coluna pode ser CSV)
    if categoria_selecionada:
        df_filtrado = df_filtrado[df_filtrado['categoria'].fillna('').apply(lambda s: any(cat in s.split(', ') for cat in categoria_selecionada))]

    if unidade_selecionada:
        df_filtrado = df_filtrado[df_filtrado['unidade'].isin(unidade_selecionada)]

    if dono_selecionado:
        df_filtrado = df_filtrado[df_filtrado['dono'].isin(dono_selecionado)]

    if vendedor_selecionado:
        df_filtrado = df_filtrado[df_filtrado['vendedor'].isin(vendedor_selecionado)]

    # Verifica dados
    if df_filtrado.empty:
        st.info("Nenhum registro para os filtros selecionados.")
        return

    # Função para formatar reais
    def formatar_reais(valor):
        try:
            return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        except Exception:
            return "R$ 0,00"

    # Agregação principal por dono e unidade
    tabela = (
        df_filtrado.groupby(['dono', 'unidade'])
        .agg(
            pedidos_qtd=pd.NamedAgg(column='ordem_id', aggfunc='count'),
            faturamento=pd.NamedAgg(column='total_pedido', aggfunc='sum'),
            clientes_unicos=pd.NamedAgg(column='cliente_id', aggfunc=lambda x: x.nunique())
        )
        .reset_index()
    )

    tabela['ticket_medio'] = tabela['faturamento'] / tabela['pedidos_qtd']

    # Ordena por faturamento e prepara exibição
    tabela = tabela.sort_values('faturamento', ascending=False)
    tabela_exib = tabela.copy()
    tabela_exib['faturamento'] = tabela_exib['faturamento'].apply(formatar_reais)
    tabela_exib['ticket_medio'] = tabela_exib['ticket_medio'].apply(formatar_reais)

    st.subheader('Tabela Principal — Por Gerente / Unidade')
    st.dataframe(tabela_exib, use_container_width=True)

    # Export CSV
    csv_bytes = tabela.to_csv(index=False).encode('utf-8')
    st.download_button(
        label='Exportar CSV',
        data=csv_bytes,
        file_name=f'gerentes_{empresa_selecionada}_{data_inicio_aware.date()}_{(data_fim_aware - pd.Timedelta(seconds=1)).date()}.csv',
        mime='text/csv'
    )

    # --- Detalhamento Diário (Oportunidades x Matrículas) ---
    # Carrega oportunidades
    df_o = carregar_dados("consultas/oportunidades/oportunidades.sql")
    if df_o is None or df_o.empty:
        st.info("Dados de oportunidades não disponíveis para o detalhamento diário.")
        return

    df_o['criacao'] = pd.to_datetime(df_o['criacao']).dt.tz_localize(TIMEZONE, ambiguous='infer')

    # Filtra oportunidades pelo mesmo escopo (empresa e período)
    df_oportunidades_filtrado = df_o[
        (df_o['empresa'] == empresa_selecionada) &
        (df_o['criacao'] >= data_inicio_aware) &
        (df_o['criacao'] < data_fim_aware)
    ].copy()

    # Orders já filtrados em df_filtrado -> usar para contagem de matrículas
    df_orders_filtrado = df_filtrado.copy()

    # Normalizar/classificar modalidade para orders
    def classificar_modalidade_order(row):
        cat = row.get('categoria', '') or ''
        uni = row.get('unidade', '') or ''
        curso = row.get('curso_venda', '') or ''
        s = ','.join([str(cat), str(uni), str(curso)]).lower()
        if 'passaporte' in s:
            return 'Passaporte'
        if 'smart' in s:
            return 'Smart'
        if 'live' in s:
            return 'Live'
        if 'ead' in s or 'online' in s:
            return 'Online'
        if 'apostila' in s:
            return 'Apostila'
        if 'presencial' in s or 'curso' in s or uni:
            return 'Presencial'
        return 'Outros'

    # Normalizar/classificar modalidade para oportunidades (campo já existe em muitas queries)
    def classificar_modalidade_oportunidade(row):
        mod = row.get('modalidade', '') or ''
        s = str(mod).lower()
        if 'passaporte' in s:
            return 'Passaporte'
        if 'smart' in s:
            return 'Smart'
        if 'live' in s:
            return 'Live'
        if 'ead' in s or 'online' in s:
            return 'Online'
        if 'apostila' in s:
            return 'Apostila'
        if 'presencial' in s:
            return 'Presencial'
        return 'Outros'

    # Aplica classificação
    df_orders_filtrado['tipo_modalidade'] = df_orders_filtrado.apply(classificar_modalidade_order, axis=1)
    df_oportunidades_filtrado['tipo_modalidade'] = df_oportunidades_filtrado.apply(classificar_modalidade_oportunidade, axis=1)

    # Cria coluna dia
    df_orders_filtrado['dia'] = df_orders_filtrado['data_pagamento'].dt.date
    df_oportunidades_filtrado['dia'] = df_oportunidades_filtrado['criacao'].dt.date

    # Agregados por dia e modalidade - contagens
    matriculas_por_dia = (
        df_orders_filtrado.groupby(['dia', 'tipo_modalidade']).size().reset_index(name='matriculas')
    )

    oportunidades_por_dia = (
        df_oportunidades_filtrado.groupby(['dia', 'tipo_modalidade']).size().reset_index(name='oportunidades')
    )

    # Pivot para ter colunas por modalidade
    matriculas_pivot = matriculas_por_dia.pivot(index='dia', columns='tipo_modalidade', values='matriculas').fillna(0)
    oportunidades_pivot = oportunidades_por_dia.pivot(index='dia', columns='tipo_modalidade', values='oportunidades').fillna(0)

    # Range de datas
    todas_datas = pd.date_range(start=data_inicio_aware.date(), end=(data_fim_aware - pd.Timedelta(seconds=1)).date(), freq='D')
    df_completo = pd.DataFrame({'dia': todas_datas.date})

    df_completo = df_completo.merge(matriculas_pivot.reset_index(), left_on='dia', right_on='dia', how='left')
    df_completo = df_completo.merge(oportunidades_pivot.reset_index(), left_on='dia', right_on='dia', how='left', suffixes=('_mat', '_opp'))
    df_completo = df_completo.fillna(0)

    # Modalidades padronizadas e ordem
    modalidades = ['Presencial', 'Live', 'Online', 'Smart', 'Passaporte', 'Apostila', 'Outros']

    # Monta DataFrame final com colunas intercaladas: Oportunidades X Matrículas
    cols = ['Data']
    df_final = pd.DataFrame()
    df_final['Data'] = pd.to_datetime(df_completo['dia']).dt.strftime('%d/%m/%Y')

    for m in modalidades:
        col_opp = f'Oportunidades {m}'
        col_mat = f'Matrículas {m}'
        # col names in merged df may be present as modality or modality_mat/_opp
        opp_val = df_completo.get(m, df_completo.get(f'{m}', 0))
        mat_val = df_completo.get(m, df_completo.get(f'{m}', 0))
        # prefer suffixed columns
        opp_col_name = f'{m}_opp'
        mat_col_name = f'{m}_mat'
        if opp_col_name in df_completo.columns:
            df_final[col_opp] = df_completo[opp_col_name].astype(int)
        else:
            df_final[col_opp] = df_completo.get(m, 0).astype(int) if m in df_completo.columns else 0
        if mat_col_name in df_completo.columns:
            df_final[col_mat] = df_completo[mat_col_name].astype(int)
        else:
            df_final[col_mat] = df_completo.get(m, 0).astype(int) if m in df_completo.columns else 0

    st.subheader('Detalhamento Diário — Oportunidades x Matrículas (por Categoria)')
    st.dataframe(df_final, use_container_width=True)
