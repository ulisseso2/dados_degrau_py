import sys
import os
import io
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime
import calendar
from style.config_collor import CATEGORIA_PRODUTO
from utils.sql_loader import carregar_dados

def run_page():
    st.title("📊 Relatório de Desempenho Mensal de Vendas")
    TIMEZONE = 'America/Sao_Paulo'

    # ✅ Carrega os dados com cache (10 min por padrão, pode ajustar no sql_loader.py)
    dfo = carregar_dados("consultas/orders/orders.sql")
    dfi = carregar_dados("consultas/oportunidades/oportunidades.sql")

    # Converte as datas para timezone aware
    dfo["data_pagamento"] = pd.to_datetime(dfo["data_pagamento"]).dt.tz_localize(TIMEZONE, ambiguous='infer')
    dfi["criacao"] = pd.to_datetime(dfi["criacao"]).dt.tz_localize(TIMEZONE, ambiguous='infer')

    # ========== FILTROS NA SIDEBAR ==========
    st.sidebar.header("Filtros")
    
    # Filtro: empresa
    empresas = sorted(dfo["empresa"].dropna().unique().tolist())
    default_index = 0
    if "Degrau" in empresas:
        default_index = empresas.index("Degrau")
        
    empresa_selecionada = st.sidebar.radio("Selecione uma empresa:", empresas, index=default_index)

    # Filtro: Mês e Ano
    st.sidebar.subheader("Período")
    
    # Obter o ano e mês atual
    hoje = pd.Timestamp.now(tz=TIMEZONE)
    ano_atual = hoje.year
    mes_atual = hoje.month
    
    # Criar lista de anos disponíveis nos dados
    anos_orders = dfo["data_pagamento"].dt.year.dropna().unique()
    anos_oportunidades = dfi["criacao"].dt.year.dropna().unique()
    # Converter para int para evitar problemas com float64
    anos_disponiveis = sorted(set([int(x) for x in anos_orders] + [int(x) for x in anos_oportunidades]), reverse=True)
    
    # Se não houver anos, usar o ano atual
    if len(anos_disponiveis) == 0:
        anos_disponiveis = [ano_atual]
    
    # Filtro de ano
    ano_selecionado = st.sidebar.selectbox(
        "Ano:",
        options=anos_disponiveis,
        index=0 if ano_atual in anos_disponiveis else 0
    )
    
    # Filtro de mês
    meses = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    
    mes_selecionado = st.sidebar.selectbox(
        "Mês:",
        options=list(meses.keys()),
        format_func=lambda x: meses[x],
        index=mes_atual - 1
    )

    # Filtro independente para tabela de matrículas
    st.sidebar.subheader("Período (Tabela de Matrículas)")
    data_inicio_padrao = pd.Timestamp(ano_atual, mes_atual, 1, tz=TIMEZONE).date()
    data_fim_padrao = pd.Timestamp.now(tz=TIMEZONE).date()
    data_inicio_tabela = st.sidebar.date_input(
        "Data inicial:",
        value=data_inicio_padrao,
        key="data_inicio_tabela"
    )
    data_fim_tabela = st.sidebar.date_input(
        "Data final:",
        value=data_fim_padrao,
        key="data_fim_tabela"
    )

    # Filtro de origem (apenas para a tabela de matrículas)
    st.sidebar.subheader("Origem (Tabela de Matrículas)")

    # Calcular o primeiro e último dia do mês selecionado
    primeiro_dia = pd.Timestamp(year=ano_selecionado, month=mes_selecionado, day=1, tz=TIMEZONE)
    ultimo_dia_mes = calendar.monthrange(ano_selecionado, mes_selecionado)[1]
    ultimo_dia = pd.Timestamp(year=ano_selecionado, month=mes_selecionado, day=ultimo_dia_mes, tz=TIMEZONE) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

    # ========== FILTRAGEM DOS DADOS ==========
    
    # Filtrar Orders (Matrículas)
    df_orders_filtrado = dfo[
        (dfo["empresa"] == empresa_selecionada) &
        (dfo["data_pagamento"] >= primeiro_dia) &
        (dfo["data_pagamento"] <= ultimo_dia) &
        (dfo["total_pedido"] != 0) &
        (~dfo["metodo_pagamento"].isin([5, 8, 13])) &
        (dfo["status_id"].isin([2, 3, 14, 10, 15]))  # Status de pagamento confirmado
    ].copy()

    # Filtrar Oportunidades
    df_oportunidades_filtrado = dfi[
        (dfi["empresa"] == empresa_selecionada) &
        (dfi["criacao"] >= primeiro_dia) &
        (dfi["criacao"] <= ultimo_dia)
    ].copy()

    # ========== TABELA DE MATRÍCULAS (PERÍODO INDEPENDENTE) ==========
    inicio_tabela = pd.Timestamp(data_inicio_tabela, tz=TIMEZONE)
    fim_tabela = pd.Timestamp(data_fim_tabela, tz=TIMEZONE) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

    df_matriculas_tabela = dfo[
        (dfo["empresa"] == empresa_selecionada) &
        (dfo["data_pagamento"] >= inicio_tabela) &
        (dfo["data_pagamento"] <= fim_tabela) &
        (dfo["total_pedido"] != 0) &
        (~dfo["metodo_pagamento"].isin([5, 8, 13])) &
        (dfo["status_id"].isin([2, 3, 14, 10, 15]))
    ].copy()

    oportunidades_periodo = dfi[
        (dfi["empresa"] == empresa_selecionada) &
        (dfi["criacao"] >= inicio_tabela) &
        (dfi["criacao"] <= fim_tabela)
    ].copy()

    # Origem mais recente para clientes com etapa 1 ou 15 (no período da tabela)
    if "id_etapa" in oportunidades_periodo.columns:
        oportunidades_periodo_ordenado = oportunidades_periodo.sort_values("criacao")

        oportunidades_origem_1_15 = oportunidades_periodo_ordenado[
            oportunidades_periodo_ordenado["id_etapa"].isin([1, 15])
        ].copy()
        origem_mais_recente_1_15 = (
            oportunidades_origem_1_15.groupby("cliente_id").tail(1)[["cliente_id", "origem"]]
        ).rename(columns={"origem": "origem_1_15"})

        origem_mais_recente_geral = (
            oportunidades_periodo_ordenado.groupby("cliente_id").tail(1)[["cliente_id", "origem"]]
        ).rename(columns={"origem": "origem_geral"})

        origem_mais_recente = origem_mais_recente_geral.merge(
            origem_mais_recente_1_15,
            on="cliente_id",
            how="left"
        )
        origem_mais_recente["origem_ult_1_15"] = origem_mais_recente["origem_1_15"].fillna(
            origem_mais_recente["origem_geral"]
        )
        origem_mais_recente = origem_mais_recente[["cliente_id", "origem_ult_1_15"]]
    else:
        origem_mais_recente = pd.DataFrame(columns=["cliente_id", "origem_ult_1_15"])

    # Buscar oportunidade vendido ou mais recente para trazer dados adicionais
    colunas_oportunidade = ["cliente_id", "concurso", "gclid", "fbclid", "utm_source", "utm_campaign", "utm_medium", "id_etapa"]
    if "id_etapa" in oportunidades_periodo.columns:
        # Primeiro tentar pegar oportunidades com etapa 15 (vendido)
        oportunidades_vendido = oportunidades_periodo[
            oportunidades_periodo["id_etapa"] == 15
        ].sort_values("criacao").groupby("cliente_id").tail(1)[colunas_oportunidade].copy()
        
        # Para clientes sem vendido, pegar a mais recente
        oportunidades_mais_recente = oportunidades_periodo_ordenado.groupby("cliente_id").tail(1)[colunas_oportunidade].copy()
        
        # Combinar: vendido tem prioridade, senão a mais recente
        dados_oportunidade = oportunidades_vendido.combine_first(oportunidades_mais_recente)
        dados_oportunidade = dados_oportunidade.drop("id_etapa", axis=1)
    else:
        dados_oportunidade = pd.DataFrame(columns=["cliente_id", "concurso", "gclid", "fbclid", "utm_source", "utm_campaign", "utm_medium"])

    oportunidades_por_cliente = (
        oportunidades_periodo.groupby("cliente_id").size().reset_index(name="qtd_oportunidades")
    )

    df_matriculas_tabela = df_matriculas_tabela.merge(
        oportunidades_por_cliente,
        on="cliente_id",
        how="left"
    )
    df_matriculas_tabela = df_matriculas_tabela.merge(
        origem_mais_recente,
        on="cliente_id",
        how="left"
    )
    df_matriculas_tabela = df_matriculas_tabela.merge(
        dados_oportunidade,
        on="cliente_id",
        how="left"
    )
    df_matriculas_tabela["qtd_oportunidades"] = df_matriculas_tabela["qtd_oportunidades"].fillna(0).astype(int)

    df_matriculas_tabela["origem_exibicao"] = df_matriculas_tabela["origem_ult_1_15"].fillna("Sem origem")
    origens_disponiveis = sorted(df_matriculas_tabela["origem_exibicao"].dropna().unique().tolist())
    origens_selecionadas = st.sidebar.multiselect(
        "Origem:",
        options=origens_disponiveis,
        default=origens_disponiveis
    )
    if origens_selecionadas:
        df_matriculas_tabela = df_matriculas_tabela[
            df_matriculas_tabela["origem_exibicao"].isin(origens_selecionadas)
        ].copy()

    # Filtro de categoria de produto
    categorias_disponiveis = sorted(df_matriculas_tabela["categoria"].dropna().unique().tolist())
    categorias_selecionadas = st.sidebar.multiselect(
        "Categoria de Produto:",
        options=categorias_disponiveis,
        default=categorias_disponiveis
    )
    if categorias_selecionadas:
        df_matriculas_tabela = df_matriculas_tabela[
            df_matriculas_tabela["categoria"].isin(categorias_selecionadas)
        ].copy()

    # Filtro de concurso
    concursos_disponiveis = sorted(df_matriculas_tabela["concurso"].dropna().unique().tolist())
    if concursos_disponiveis:
        concursos_selecionados = st.sidebar.multiselect(
            "Concurso:",
            options=concursos_disponiveis,
            default=concursos_disponiveis
        )
        if concursos_selecionados:
            df_matriculas_tabela = df_matriculas_tabela[
                df_matriculas_tabela["concurso"].isin(concursos_selecionados) | 
                df_matriculas_tabela["concurso"].isna()
            ].copy()

    # Filtros de presença de parâmetros (checkbox)
    st.sidebar.subheader("Parâmetros de Rastreamento")
    
    filtro_gclid = st.sidebar.checkbox("Apenas com GCLID", value=False)
    if filtro_gclid:
        df_matriculas_tabela = df_matriculas_tabela[
            df_matriculas_tabela["gclid"].notna() & (df_matriculas_tabela["gclid"] != "")
        ].copy()
    
    filtro_fbclid = st.sidebar.checkbox("Apenas com FBCLID", value=False)
    if filtro_fbclid:
        df_matriculas_tabela = df_matriculas_tabela[
            df_matriculas_tabela["fbclid"].notna() & (df_matriculas_tabela["fbclid"] != "")
        ].copy()
    
    filtro_utm_source = st.sidebar.checkbox("Apenas com UTM Source", value=False)
    if filtro_utm_source:
        df_matriculas_tabela = df_matriculas_tabela[
            df_matriculas_tabela["utm_source"].notna() & (df_matriculas_tabela["utm_source"] != "")
        ].copy()
    
    filtro_utm_campaign = st.sidebar.checkbox("Apenas com UTM Campaign", value=False)
    if filtro_utm_campaign:
        df_matriculas_tabela = df_matriculas_tabela[
            df_matriculas_tabela["utm_campaign"].notna() & (df_matriculas_tabela["utm_campaign"] != "")
        ].copy()
    
    filtro_utm_medium = st.sidebar.checkbox("Apenas com UTM Medium", value=False)
    if filtro_utm_medium:
        df_matriculas_tabela = df_matriculas_tabela[
            df_matriculas_tabela["utm_medium"].notna() & (df_matriculas_tabela["utm_medium"] != "")
        ].copy()

    # ========== PREPARAÇÃO DOS DADOS PARA A TABELA ==========
    
    # Criar coluna de data (dia) para agrupamento
    df_orders_filtrado['dia'] = df_orders_filtrado['data_pagamento'].dt.date
    df_oportunidades_filtrado['dia'] = df_oportunidades_filtrado['criacao'].dt.date

    # Criar classificação de modalidade para orders baseado em categoria
    def classificar_modalidade_order(categoria):
        if pd.isna(categoria):
            return 'Outros'
        categoria = str(categoria).lower()
        if 'presencial' in categoria:
            return 'Presencial'
        elif 'live' in categoria:
            return 'Live'
        elif 'online' in categoria or 'ead' in categoria:
            return 'Online'
        elif 'passaporte' in categoria:
            return 'Passaporte'
        elif 'smart' in categoria:
            return 'Smart'
        elif 'apostila' in categoria:
            return 'Apostila'
        else:
            return 'Outros'
    
    df_orders_filtrado['tipo_modalidade'] = df_orders_filtrado['categoria'].apply(classificar_modalidade_order)

    # Classificar modalidade para oportunidades
    def classificar_modalidade_oportunidade(modalidade):
        if pd.isna(modalidade):
            return 'Outros'
        modalidade = str(modalidade).lower()
        if 'presencial' in modalidade:
            return 'Presencial'
        elif 'live' in modalidade:
            return 'Live'
        elif 'online' in modalidade or 'ead' in modalidade:
            return 'Online'
        elif 'passaporte' in modalidade:
            return 'Passaporte'
        elif 'smart' in modalidade:
            return 'Smart'
        elif 'apostila' in modalidade:
            return 'Apostila'
        else:
            return 'Outros'
    
    df_oportunidades_filtrado['tipo_modalidade'] = df_oportunidades_filtrado['modalidade'].apply(classificar_modalidade_oportunidade)

    # ========== AGREGAÇÃO DOS DADOS ==========
    
    # Agregar matrículas por dia e modalidade (SOMA DOS VALORES)
    matriculas_por_dia = df_orders_filtrado.groupby(['dia', 'tipo_modalidade'])['total_pedido'].sum().reset_index(name='valor')
    matriculas_pivot = matriculas_por_dia.pivot(index='dia', columns='tipo_modalidade', values='valor').fillna(0)

    # Criar coluna de Matrículas e Apostilas (todas exceto Passaporte)
    colunas_matriculas = [col for col in matriculas_pivot.columns if col != 'Passaporte']
    matriculas_pivot['Matrículas e Apostilas'] = matriculas_pivot[colunas_matriculas].sum(axis=1)
    
    # Renomear coluna Passaporte se existir
    if 'Passaporte' in matriculas_pivot.columns:
        matriculas_pivot['Passaporte'] = matriculas_pivot['Passaporte']
    else:
        matriculas_pivot['Passaporte'] = 0
    
    # Manter apenas as colunas agregadas
    matriculas_pivot = matriculas_pivot[['Matrículas e Apostilas', 'Passaporte']]
    
    # Agregar oportunidades por dia e modalidade (QUANTIDADE)
    oportunidades_por_dia = df_oportunidades_filtrado.groupby(['dia', 'tipo_modalidade']).size().reset_index(name='quantidade')
    oportunidades_pivot = oportunidades_por_dia.pivot(index='dia', columns='tipo_modalidade', values='quantidade').fillna(0)

    # Criar coluna Leads Totais (soma de todas as oportunidades)
    oportunidades_pivot['Leads Totais'] = oportunidades_pivot.sum(axis=1)
    
    # Renomear colunas de oportunidades
    oportunidades_pivot.columns = [f'Oportunidades {col}' if col != 'Leads Totais' else col for col in oportunidades_pivot.columns]
    
    # ========== CRIAR TABELA COMPLETA ==========
    
    # Criar range de todas as datas do mês
    todas_datas = pd.date_range(start=primeiro_dia, end=ultimo_dia, freq='D', tz=TIMEZONE).date
    df_completo = pd.DataFrame({'dia': todas_datas})
    
    # Merge com matrículas e oportunidades
    df_completo = df_completo.merge(matriculas_pivot, on='dia', how='left')
    df_completo = df_completo.merge(oportunidades_pivot, on='dia', how='left')
    
    # Preencher valores nulos com 0
    df_completo = df_completo.fillna(0)
    
    # Ordenar colunas na ordem desejada: Matrículas primeiro, depois Oportunidades
    colunas_ordenadas = ['dia', 'Matrículas e Apostilas', 'Passaporte']
    
    # Adicionar coluna Leads Totais
    if 'Leads Totais' in df_completo.columns:
        colunas_ordenadas.append('Leads Totais')
    
    # Adicionar colunas de oportunidades na ordem: Presencial, Live, Online, etc
    for modalidade in ['Presencial', 'Live', 'Online', 'Smart', 'Apostila', 'Outros']:
        col_oportunidade = f'Oportunidades {modalidade}'
        if col_oportunidade in df_completo.columns:
            colunas_ordenadas.append(col_oportunidade)
    
    # Adicionar outras colunas que possam existir
    for col in df_completo.columns:
        if col not in colunas_ordenadas:
            colunas_ordenadas.append(col)
    
    df_completo = df_completo[colunas_ordenadas]
    
    # Função para formatar valores em reais
    def formatar_reais(valor):
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
    # Formatar a coluna de data
    df_completo['Data'] = pd.to_datetime(df_completo['dia']).dt.strftime('%d/%m/%Y')
    
    # Calcular totais para cada coluna
    totais = {}
    totais['Data'] = 'TOTAL'
    for col in df_completo.columns:
        if col not in ['dia', 'Data']:
            totais[col] = df_completo[col].sum()
    
    # Criar DataFrame com a linha de totais
    df_totais = pd.DataFrame([totais])
    
    # Calcular apontamentos (projeção baseada em média de dias com dados)
    apontamentos = {}
    apontamentos['Data'] = 'APONTAMENTOS'
    
    # Contar dias do mês total e dias com dados até hoje
    total_dias_mes = ultimo_dia_mes
    hoje = pd.Timestamp.now(tz=TIMEZONE)
    
    # Se estamos no mês selecionado, usar o dia atual, senão usar o total de dias do mês
    if ano_selecionado == hoje.year and mes_selecionado == hoje.month:
        dias_com_dados = hoje.day
    else:
        # Se for mês passado, usar todos os dias do mês
        dias_com_dados = total_dias_mes
    
    for col in df_completo.columns:
        if col not in ['dia', 'Data']:
            # Calcula a média dos valores dividida pelo número de dias com dados, multiplicada pelo total de dias
            media_por_dia = totais[col] / dias_com_dados if dias_com_dados > 0 else 0
            apontamentos[col] = media_por_dia * total_dias_mes
    
    # Criar DataFrame com a linha de apontamentos
    df_apontamentos = pd.DataFrame([apontamentos])
    
    # Criar uma cópia para exibição com valores formatados
    df_exibicao = df_completo.copy()
    
    # Formatar colunas de matrículas (valores em R$)
    for col in df_exibicao.columns:
        if col in ['Matrículas e Apostilas', 'Passaporte']:
            df_exibicao[col] = df_exibicao[col].apply(formatar_reais)
        elif col not in ['dia', 'Data']:
            # Oportunidades ficam como inteiros
            df_exibicao[col] = df_exibicao[col].astype(int)
    
    # Formatar totais
    for col in df_totais.columns:
        if col in ['Matrículas e Apostilas', 'Passaporte']:
            df_totais[col] = df_totais[col].apply(formatar_reais)
        elif col not in ['Data']:
            df_totais[col] = df_totais[col].astype(int)
    
    # Formatar apontamentos
    for col in df_apontamentos.columns:
        if col in ['Matrículas e Apostilas', 'Passaporte']:
            df_apontamentos[col] = df_apontamentos[col].apply(formatar_reais)
        elif col not in ['Data']:
            # Arredondar para inteiro mais próximo
            df_apontamentos[col] = df_apontamentos[col].round(0).astype(int)
    
    df_exibicao = df_exibicao.drop('dia', axis=1)
    
    # Reordenar para Data ficar primeira
    cols = ['Data'] + [col for col in df_exibicao.columns if col != 'Data']
    df_exibicao = df_exibicao[cols]
    df_totais = df_totais[cols]
    df_apontamentos = df_apontamentos[cols]
    
    # Concatenar tabela com totais e apontamentos
    df_exibicao_com_total = pd.concat([df_exibicao, df_totais, df_apontamentos], ignore_index=True)

    # ========== EXIBIÇÃO ==========
    
    st.subheader(f"Desempenho de {meses[mes_selecionado]} de {ano_selecionado} - {empresa_selecionada}")
    
    # Calcular valores para as métricas
    total_oportunidades = df_oportunidades_filtrado.shape[0]
    qtd_matriculas = df_orders_filtrado.shape[0]
    
    # Separar valores de Passaporte e Matrículas/Apostilas
    valor_passaporte = df_orders_filtrado[df_orders_filtrado['tipo_modalidade'] == 'Passaporte']['total_pedido'].sum()
    valor_matriculas_apostilas = df_orders_filtrado[df_orders_filtrado['tipo_modalidade'] != 'Passaporte']['total_pedido'].sum()
    
    # Métricas resumidas
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total de Oportunidades", f"{total_oportunidades:,}")
    
    with col2:
        st.metric("Matrículas e Apostilas", formatar_reais(valor_matriculas_apostilas))
    
    with col3:
        st.metric("Passaporte", formatar_reais(valor_passaporte))
    
    with col4:
        taxa_conversao = (qtd_matriculas / total_oportunidades * 100) if total_oportunidades > 0 else 0
        st.metric("Taxa de Conversão", f"{taxa_conversao:.1f}%")
    
    # Tabela detalhada
    st.subheader("Detalhamento Diário")
    st.dataframe(df_exibicao_com_total, use_container_width=True, hide_index=True)

    # Tabela de matrículas por cliente (período independente)
    st.subheader("Matrículas por Origem")
    origem_chart = (
        df_matriculas_tabela.groupby("origem_exibicao").size().reset_index(name="qtd")
    )
    fig_origem = px.pie(
        origem_chart,
        names="origem_exibicao",
        values="qtd",
        title="Matrículas por Origem"
    )
    fig_origem.update_traces(textinfo="value+percent")
    st.plotly_chart(fig_origem, use_container_width=True)

    st.subheader("Matrículas no Período (por Cliente)")
    
    # Métricas do período de matrículas
    col1, col2, col3 = st.columns(3)
    
    with col1:
        qtd_total_matriculas = len(df_matriculas_tabela)
        st.metric("Total de Matrículas", f"{qtd_total_matriculas:,}")
        
        qtd_com_oportunidade = len(df_matriculas_tabela[df_matriculas_tabela["qtd_oportunidades"] > 0])
        st.metric("Com Oportunidade", f"{qtd_com_oportunidade:,}")
    
    with col2:
        qtd_com_gclid = len(df_matriculas_tabela[
            df_matriculas_tabela["gclid"].notna() & (df_matriculas_tabela["gclid"] != "")
        ])
        st.metric("Com GCLID", f"{qtd_com_gclid:,}")
        
        qtd_com_fbclid = len(df_matriculas_tabela[
            df_matriculas_tabela["fbclid"].notna() & (df_matriculas_tabela["fbclid"] != "")
        ])
        st.metric("Com FBCLID", f"{qtd_com_fbclid:,}")
    
    with col3:
        valor_total_periodo = df_matriculas_tabela["total_pedido"].sum()
        st.metric("Valor Total do Período", formatar_reais(valor_total_periodo))
    
    # Métricas por categoria
    st.markdown("**Quantidade por Categoria:**")
    categorias_metricas = df_matriculas_tabela.groupby("categoria").agg({
        "cliente_id": "count",
        "total_pedido": "sum"
    }).reset_index()
    categorias_metricas.columns = ["Categoria", "Quantidade", "Valor Total"]
    categorias_metricas = categorias_metricas.sort_values("Quantidade", ascending=False)
    
    # Exibir categorias em colunas
    num_categorias = len(categorias_metricas)
    if num_categorias > 0:
        cols_categorias = st.columns(min(4, num_categorias))
        for idx, row in categorias_metricas.iterrows():
            col_idx = idx % len(cols_categorias)
            with cols_categorias[col_idx]:
                st.metric(
                    row["Categoria"],
                    f"{int(row['Quantidade'])}",
                    delta=formatar_reais(row["Valor Total"])
                )
    
    st.markdown("---")
    
    tabela_matriculas = df_matriculas_tabela[[
        "cliente_id",
        "nome_cliente",
        "email_cliente",
        "data_pagamento",
        "categoria",
        "total_pedido",
        "qtd_oportunidades",
        "origem_ult_1_15",
        "concurso",
        "gclid",
        "fbclid",
        "utm_source",
        "utm_campaign",
        "utm_medium"
    ]].copy()
    tabela_matriculas.rename(columns={
        "cliente_id": "ID do Cliente",
        "nome_cliente": "Nome",
        "email_cliente": "Email",
        "data_pagamento": "Data da Matrícula",
        "categoria": "Categoria",
        "total_pedido": "Valor do Pedido",
        "qtd_oportunidades": "Qtd. Oportunidades",
        "origem_ult_1_15": "Origem (etapa 1 ou 15)",
        "concurso": "Concurso",
        "gclid": "GCLID",
        "fbclid": "FBCLID",
        "utm_source": "UTM Source",
        "utm_campaign": "UTM Campaign",
        "utm_medium": "UTM Medium"
    }, inplace=True)
    tabela_matriculas["Data da Matrícula"] = pd.to_datetime(
        tabela_matriculas["Data da Matrícula"]
    ).dt.strftime('%d/%m/%Y')
    tabela_matriculas = tabela_matriculas.sort_values(by="Valor do Pedido", ascending=False)
    tabela_matriculas["Valor do Pedido"] = tabela_matriculas["Valor do Pedido"].apply(formatar_reais)
    st.dataframe(tabela_matriculas, use_container_width=True, hide_index=True)
    
    # Preparar dados para exportação (com valores numéricos)
    df_exportacao = df_completo.copy()
    df_exportacao['Data'] = pd.to_datetime(df_exportacao['dia']).dt.strftime('%d/%m/%Y')
    df_exportacao = df_exportacao.drop('dia', axis=1)
    cols_export = ['Data'] + [col for col in df_exportacao.columns if col != 'Data']
    df_exportacao = df_exportacao[cols_export]
    
    # Botão de download
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df_exportacao.to_excel(writer, index=False, sheet_name='Desempenho Mensal')
    buffer.seek(0)
    
    st.download_button(
        label="📥 Baixar Relatório em Excel",
        data=buffer,
        file_name=f"desempenho_mensal_{empresa_selecionada}_{ano_selecionado}_{mes_selecionado:02d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )