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
from gclid_db import get_campaign_for_gclid as get_campaign_degrau
from gclid_db_central import get_campaign_for_gclid as get_campaign_central

def run_page():
    st.title("📊 Relatório de Desempenho Mensal de Vendas")
    TIMEZONE = 'America/Sao_Paulo'

    # ✅ Carrega os dados com cache (10 min por padrão, pode ajustar no sql_loader.py)
    dfo = carregar_dados("consultas/orders/orders.sql")
    dfi = carregar_dados("consultas/oportunidades/oportunidades.sql")
    dft = carregar_dados("consultas/transcricoes/transcricoes.sql")

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
    #etapa 1 = 
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

    # Buscar campanha vinculada ao GCLID no cache SQLite (banco específico por empresa)
    def buscar_campanha_gclid(row):
        gclid = row.get("gclid")
        if pd.isna(gclid) or gclid == "":
            return None
        if empresa_selecionada == "Central":
            return get_campaign_central(gclid)
        else:
            return get_campaign_degrau(gclid)

    df_matriculas_tabela["Campanha_Gclid"] = df_matriculas_tabela.apply(buscar_campanha_gclid, axis=1)

    # Buscar dados de ligação (transcrições) vinculadas ao cliente via oportunidade
    if not dft.empty and "oportunidade" in dft.columns and "oportunidade" in dfi.columns:
        # Mapa oportunidade → cliente_id (usando todas as oportunidades da empresa)
        oport_cliente_map = dfi.loc[
            dfi["empresa"] == empresa_selecionada,
            ["oportunidade", "cliente_id"]
        ].drop_duplicates()

        # Filtra transcrições da empresa e cruza com oportunidades para obter cliente_id
        dft_empresa = dft[dft["empresa"] == empresa_selecionada].copy()
        dft_empresa["data_ligacao"] = pd.to_datetime(dft_empresa["data_ligacao"], errors="coerce")
        dft_com_cliente = dft_empresa.merge(oport_cliente_map, on="oportunidade", how="inner")

        if not dft_com_cliente.empty:
            # Pega a transcrição mais recente por cliente
            dft_mais_recente = (
                dft_com_cliente
                .sort_values("data_ligacao", ascending=False)
                .groupby("cliente_id")
                .first()
                .reset_index()
            )
            ligacao_data = dft_mais_recente[["cliente_id"]].copy()
            ligacao_data["Ligação"] = "Sim"
            ligacao_data["Lead_Score"] = pd.to_numeric(
                dft_mais_recente["lead_score"], errors="coerce"
            )
            df_matriculas_tabela = df_matriculas_tabela.merge(
                ligacao_data[["cliente_id", "Ligação", "Lead_Score"]],
                on="cliente_id",
                how="left"
            )
        else:
            df_matriculas_tabela["Ligação"] = None
            df_matriculas_tabela["Lead_Score"] = None
    else:
        df_matriculas_tabela["Ligação"] = None
        df_matriculas_tabela["Lead_Score"] = None

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
    
    # --- Filtros de rastreamento (checkboxes AND) ---
    st.markdown("**🔎 Filtrar por rastreamento:**")
    chk_cols = st.columns(4)
    with chk_cols[0]:
        filtro_gclid = st.checkbox("Com GCLID", value=False, key="chk_gclid")
    with chk_cols[1]:
        filtro_fbclid = st.checkbox("Com FBCLID", value=False, key="chk_fbclid")
    with chk_cols[2]:
        filtro_utm = st.checkbox("Com UTM Source", value=False, key="chk_utm")
    with chk_cols[3]:
        filtro_ligacao = st.checkbox("Com Ligação", value=False, key="chk_ligacao_filtro")

    df_matriculas_filtrado = df_matriculas_tabela.copy()

    if filtro_gclid:
        df_matriculas_filtrado = df_matriculas_filtrado[
            df_matriculas_filtrado["gclid"].notna() & (df_matriculas_filtrado["gclid"] != "")
        ]
    if filtro_fbclid:
        df_matriculas_filtrado = df_matriculas_filtrado[
            df_matriculas_filtrado["fbclid"].notna() & (df_matriculas_filtrado["fbclid"] != "")
        ]
    if filtro_utm:
        df_matriculas_filtrado = df_matriculas_filtrado[
            df_matriculas_filtrado["utm_source"].notna() & (df_matriculas_filtrado["utm_source"] != "")
        ]
    if filtro_ligacao:
        df_matriculas_filtrado = df_matriculas_filtrado[
            df_matriculas_filtrado["Ligação"] == "Sim"
        ]

    filtros_ativos = sum([filtro_gclid, filtro_fbclid, filtro_utm, filtro_ligacao])
    if filtros_ativos > 0:
        st.caption(
            f"🔽 Exibindo **{len(df_matriculas_filtrado)}** de {len(df_matriculas_tabela)} matrículas "
            f"({filtros_ativos} filtro{'s' if filtros_ativos > 1 else ''} ativo{'s' if filtros_ativos > 1 else ''})"
        )

    st.markdown("---")
    
    tabela_matriculas = df_matriculas_filtrado[[
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
        "Campanha_Gclid",
        "Ligação",
        "Lead_Score",
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
        "Campanha_Gclid": "Campanha_Gclid",
        "Ligação": "Ligação",
        "Lead_Score": "Lead_Score",
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

    # Preparar tabela de matrículas detalhada para exportação
    df_matriculas_export = df_matriculas_tabela[[
        "cliente_id", "nome_cliente", "email_cliente", "data_pagamento",
        "categoria", "total_pedido", "qtd_oportunidades", "origem_ult_1_15",
        "concurso", "gclid", "Campanha_Gclid", "Ligação", "Lead_Score",
        "fbclid", "utm_source", "utm_campaign", "utm_medium"
    ]].copy()
    df_matriculas_export.rename(columns={
        "cliente_id": "ID do Cliente", "nome_cliente": "Nome",
        "email_cliente": "Email", "data_pagamento": "Data da Matrícula",
        "categoria": "Categoria", "total_pedido": "Valor do Pedido",
        "qtd_oportunidades": "Qtd. Oportunidades",
        "origem_ult_1_15": "Origem (etapa 1 ou 15)",
        "concurso": "Concurso", "gclid": "GCLID",
        "Campanha_Gclid": "Campanha_Gclid",
        "Ligação": "Ligação", "Lead_Score": "Lead_Score",
        "fbclid": "FBCLID", "utm_source": "UTM Source",
        "utm_campaign": "UTM Campaign", "utm_medium": "UTM Medium"
    }, inplace=True)
    df_matriculas_export["Data da Matrícula"] = pd.to_datetime(
        df_matriculas_export["Data da Matrícula"]
    ).dt.strftime('%d/%m/%Y')
    df_matriculas_export = df_matriculas_export.sort_values(by="Valor do Pedido", ascending=False)
    
    # Botão de download com ambas as abas
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df_exportacao.to_excel(writer, index=False, sheet_name='Desempenho Mensal')
        df_matriculas_export.to_excel(writer, index=False, sheet_name='Matrículas Detalhado')
    buffer.seek(0)
    
    st.download_button(
        label="📥 Baixar Relatório em Excel",
        data=buffer,
        file_name=f"desempenho_mensal_{empresa_selecionada}_{ano_selecionado}_{mes_selecionado:02d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # ==============================================================================
    # ANÁLISES DE RASTREAMENTO E COMPORTAMENTO DO MATRICULADO
    # ==============================================================================
    st.divider()
    st.header("🔎 Análise de Rastreamento e Comportamento dos Matriculados")

    # --- Métricas de rastreamento ---
    total_mat = len(df_matriculas_tabela)

    _tem_gclid = df_matriculas_tabela["gclid"].notna() & (df_matriculas_tabela["gclid"] != "")
    _tem_fbclid = df_matriculas_tabela["fbclid"].notna() & (df_matriculas_tabela["fbclid"] != "")
    _tem_ligacao = df_matriculas_tabela["Ligação"] == "Sim"
    _tem_utm = (
        (df_matriculas_tabela["utm_source"].notna() & (df_matriculas_tabela["utm_source"] != "")) |
        (df_matriculas_tabela["utm_campaign"].notna() & (df_matriculas_tabela["utm_campaign"] != "")) |
        (df_matriculas_tabela["utm_medium"].notna() & (df_matriculas_tabela["utm_medium"] != ""))
    )
    _tem_campanha = df_matriculas_tabela["Campanha_Gclid"].notna() & (df_matriculas_tabela["Campanha_Gclid"] != "") & (df_matriculas_tabela["Campanha_Gclid"] != "Não encontrado")
    _tem_lead_score = df_matriculas_tabela["Lead_Score"].notna()

    qtd_gclid = int(_tem_gclid.sum())
    qtd_fbclid = int(_tem_fbclid.sum())
    qtd_ligacao = int(_tem_ligacao.sum())
    qtd_utm = int(_tem_utm.sum())
    qtd_campanha = int(_tem_campanha.sum())
    qtd_lead_score = int(_tem_lead_score.sum())

    st.subheader("📌 Cobertura de Rastreamento")

    mc1, mc2, mc3 = st.columns(3)
    mc4, mc5, mc6 = st.columns(3)

    def _pct(n):
        return f"{n / total_mat * 100:.1f}%" if total_mat > 0 else "0%"

    mc1.metric("Com GCLID (Google Ads)", f"{qtd_gclid}", delta=_pct(qtd_gclid))
    mc2.metric("Com FBCLID (Meta Ads)", f"{qtd_fbclid}", delta=_pct(qtd_fbclid))
    mc3.metric("Com Ligação Registrada", f"{qtd_ligacao}", delta=_pct(qtd_ligacao))
    mc4.metric("Com UTM (qualquer)", f"{qtd_utm}", delta=_pct(qtd_utm))
    mc5.metric("Campanha Google Identificada", f"{qtd_campanha}", delta=_pct(qtd_campanha))
    mc6.metric("Com Lead Score", f"{qtd_lead_score}", delta=_pct(qtd_lead_score))

    # --- Gráfico de cobertura de rastreamento (rosca) ---
    _sem_rastreio = total_mat - int((_tem_gclid | _tem_fbclid | _tem_utm).sum())
    df_cobertura = pd.DataFrame({
        "Tipo": ["GCLID", "FBCLID", "UTM (sem GCLID/FBCLID)", "Sem rastreamento"],
        "Qtd": [
            qtd_gclid,
            int((_tem_fbclid & ~_tem_gclid).sum()),
            int((_tem_utm & ~_tem_gclid & ~_tem_fbclid).sum()),
            _sem_rastreio
        ]
    })
    df_cobertura = df_cobertura[df_cobertura["Qtd"] > 0]

    if not df_cobertura.empty:
        fig_cob = px.pie(
            df_cobertura, names="Tipo", values="Qtd",
            title="Distribuição por Tipo de Rastreamento",
            hole=0.4,
            color_discrete_sequence=px.colors.qualitative.Set2
        )
        fig_cob.update_traces(textinfo="value+percent")
        st.plotly_chart(fig_cob, use_container_width=True)

    st.divider()

    # --- Campanhas Google Ads identificadas (barras horizontais) ---
    st.subheader("📊 Campanhas Google Ads Identificadas (via GCLID)")

    df_camp = df_matriculas_tabela[_tem_campanha].copy()
    if not df_camp.empty:
        camp_counts = (
            df_camp.groupby("Campanha_Gclid")
            .agg(Matrículas=("cliente_id", "count"), Receita=("total_pedido", "sum"))
            .reset_index()
            .sort_values("Matrículas", ascending=True)
        )

        fig_camp = px.bar(
            camp_counts, x="Matrículas", y="Campanha_Gclid",
            orientation="h",
            text="Matrículas",
            title="Matrículas por Campanha Google Ads",
            color="Receita",
            color_continuous_scale="Blues",
            labels={"Campanha_Gclid": "Campanha", "Matrículas": "Qtd. Matrículas"}
        )
        fig_camp.update_layout(height=max(300, len(camp_counts) * 35), margin=dict(l=10))
        fig_camp.update_traces(textposition="outside")
        st.plotly_chart(fig_camp, use_container_width=True)

        # Tabela resumo por campanha
        camp_resumo = camp_counts.sort_values("Matrículas", ascending=False).copy()
        camp_resumo["Ticket Médio"] = camp_resumo["Receita"] / camp_resumo["Matrículas"]
        camp_resumo["Receita"] = camp_resumo["Receita"].apply(formatar_reais)
        camp_resumo["Ticket Médio"] = camp_resumo["Ticket Médio"].apply(formatar_reais)
        camp_resumo.rename(columns={"Campanha_Gclid": "Campanha"}, inplace=True)
        st.dataframe(camp_resumo, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma campanha Google Ads identificada no período.")

    st.divider()

    # --- Análise: Ligação vs Ticket Médio ---
    st.subheader("📞 Impacto da Ligação na Conversão")

    col_lig1, col_lig2 = st.columns(2)

    with col_lig1:
        df_com_lig = df_matriculas_tabela[_tem_ligacao]
        df_sem_lig = df_matriculas_tabela[~_tem_ligacao]
        ticket_com = df_com_lig["total_pedido"].mean() if len(df_com_lig) > 0 else 0
        ticket_sem = df_sem_lig["total_pedido"].mean() if len(df_sem_lig) > 0 else 0

        df_lig_comp = pd.DataFrame({
            "Situação": ["Com Ligação", "Sem Ligação"],
            "Ticket Médio": [ticket_com, ticket_sem],
            "Qtd. Matrículas": [len(df_com_lig), len(df_sem_lig)],
            "Receita Total": [df_com_lig["total_pedido"].sum(), df_sem_lig["total_pedido"].sum()]
        })

        fig_lig = px.bar(
            df_lig_comp, x="Situação", y="Ticket Médio",
            text=df_lig_comp["Ticket Médio"].apply(formatar_reais),
            color="Situação",
            color_discrete_map={"Com Ligação": "#00CC96", "Sem Ligação": "#EF553B"},
            title="Ticket Médio: Com vs Sem Ligação"
        )
        fig_lig.update_layout(showlegend=False)
        st.plotly_chart(fig_lig, use_container_width=True)

    with col_lig2:
        fig_lig_receita = px.bar(
            df_lig_comp, x="Situação", y="Receita Total",
            text=df_lig_comp["Receita Total"].apply(formatar_reais),
            color="Situação",
            color_discrete_map={"Com Ligação": "#00CC96", "Sem Ligação": "#EF553B"},
            title="Receita Total: Com vs Sem Ligação"
        )
        fig_lig_receita.update_layout(showlegend=False)
        st.plotly_chart(fig_lig_receita, use_container_width=True)

    st.divider()

    # --- Distribuição de Lead Score dos matriculados ---
    st.subheader("🎯 Distribuição de Lead Score dos Matriculados")

    df_com_score = df_matriculas_tabela[_tem_lead_score].copy()
    if not df_com_score.empty:
        col_ls1, col_ls2 = st.columns(2)

        with col_ls1:
            media_score = df_com_score["Lead_Score"].mean()
            mediana_score = df_com_score["Lead_Score"].median()

            fig_hist = px.histogram(
                df_com_score, x="Lead_Score", nbins=20,
                title="Histograma de Lead Score",
                labels={"Lead_Score": "Lead Score"},
                color_discrete_sequence=["#636EFA"]
            )
            fig_hist.add_vline(
                x=media_score, line_dash="dash", line_color="red",
                annotation_text=f"Média: {media_score:.1f}"
            )
            fig_hist.update_layout(height=350)
            st.plotly_chart(fig_hist, use_container_width=True)

        with col_ls2:
            # Classificação do lead score em faixas
            def classificar_lead(score):
                if pd.isna(score):
                    return "Sem score"
                if score >= 75:
                    return "A (≥75)"
                if score >= 50:
                    return "B (50-74)"
                if score >= 25:
                    return "C (25-49)"
                return "D (<25)"

            df_com_score["Faixa_Score"] = df_com_score["Lead_Score"].apply(classificar_lead)
            faixa_counts = df_com_score["Faixa_Score"].value_counts().reset_index()
            faixa_counts.columns = ["Faixa", "Qtd"]
            ordem_faixas = ["A (≥75)", "B (50-74)", "C (25-49)", "D (<25)"]
            faixa_counts["Faixa"] = pd.Categorical(faixa_counts["Faixa"], categories=ordem_faixas, ordered=True)
            faixa_counts = faixa_counts.sort_values("Faixa")

            fig_faixa = px.bar(
                faixa_counts, x="Faixa", y="Qtd",
                text="Qtd",
                title="Matrículas por Faixa de Lead Score",
                color="Faixa",
                color_discrete_map={
                    "A (≥75)": "#00CC96", "B (50-74)": "#636EFA",
                    "C (25-49)": "#FFA15A", "D (<25)": "#EF553B"
                }
            )
            fig_faixa.update_layout(showlegend=False, height=350)
            st.plotly_chart(fig_faixa, use_container_width=True)

        # Ticket médio por faixa de lead score
        score_ticket = df_com_score.groupby("Faixa_Score").agg(
            Matrículas=("cliente_id", "count"),
            Receita=("total_pedido", "sum")
        ).reset_index()
        score_ticket["Ticket Médio"] = score_ticket["Receita"] / score_ticket["Matrículas"]
        score_ticket["Faixa_Score"] = pd.Categorical(score_ticket["Faixa_Score"], categories=ordem_faixas, ordered=True)
        score_ticket = score_ticket.sort_values("Faixa_Score")
        score_ticket["Receita"] = score_ticket["Receita"].apply(formatar_reais)
        score_ticket["Ticket Médio"] = score_ticket["Ticket Médio"].apply(formatar_reais)
        score_ticket.rename(columns={"Faixa_Score": "Faixa de Lead Score"}, inplace=True)
        st.dataframe(score_ticket, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum lead score disponível para os matriculados no período.")

    st.divider()

    # --- Origem vs Receita e Ticket Médio ---
    st.subheader("🏷️ Performance por Origem de Aquisição")

    df_origem_perf = df_matriculas_tabela.groupby("origem_exibicao").agg(
        Matrículas=("cliente_id", "count"),
        Receita=("total_pedido", "sum"),
        Com_GCLID=("gclid", lambda x: int((x.notna() & (x != "")).sum())),
        Com_Ligação=("Ligação", lambda x: int((x == "Sim").sum()))
    ).reset_index().sort_values("Receita", ascending=False)
    df_origem_perf["Ticket Médio"] = df_origem_perf["Receita"] / df_origem_perf["Matrículas"]
    df_origem_perf["% Ligação"] = (df_origem_perf["Com_Ligação"] / df_origem_perf["Matrículas"] * 100).round(1)

    col_or1, col_or2 = st.columns(2)

    with col_or1:
        fig_or_receita = px.bar(
            df_origem_perf.sort_values("Receita", ascending=True),
            x="Receita", y="origem_exibicao",
            orientation="h", text=df_origem_perf.sort_values("Receita", ascending=True)["Receita"].apply(formatar_reais),
            title="Receita por Origem",
            labels={"origem_exibicao": "Origem", "Receita": "Receita Total"},
            color_discrete_sequence=["#636EFA"]
        )
        fig_or_receita.update_layout(height=max(300, len(df_origem_perf) * 30))
        st.plotly_chart(fig_or_receita, use_container_width=True)

    with col_or2:
        fig_or_ticket = px.bar(
            df_origem_perf.sort_values("Ticket Médio", ascending=True),
            x="Ticket Médio", y="origem_exibicao",
            orientation="h", text=df_origem_perf.sort_values("Ticket Médio", ascending=True)["Ticket Médio"].apply(formatar_reais),
            title="Ticket Médio por Origem",
            labels={"origem_exibicao": "Origem", "Ticket Médio": "Ticket Médio"},
            color_discrete_sequence=["#00CC96"]
        )
        fig_or_ticket.update_layout(height=max(300, len(df_origem_perf) * 30))
        st.plotly_chart(fig_or_ticket, use_container_width=True)

    # Tabela consolidada por origem
    df_origem_exib = df_origem_perf.copy()
    df_origem_exib["Receita"] = df_origem_exib["Receita"].apply(formatar_reais)
    df_origem_exib["Ticket Médio"] = df_origem_exib["Ticket Médio"].apply(formatar_reais)
    df_origem_exib.rename(columns={
        "origem_exibicao": "Origem",
        "Com_GCLID": "Com GCLID",
        "Com_Ligação": "Com Ligação",
        "% Ligação": "% com Ligação"
    }, inplace=True)
    st.dataframe(df_origem_exib, use_container_width=True, hide_index=True)

    st.divider()

    # --- UTM Source / Medium / Campaign ---
    st.subheader("🔗 Análise de UTMs dos Matriculados")

    df_utm_source = df_matriculas_tabela[
        df_matriculas_tabela["utm_source"].notna() & (df_matriculas_tabela["utm_source"] != "")
    ].copy()

    if not df_utm_source.empty:
        col_utm1, col_utm2 = st.columns(2)

        with col_utm1:
            src_counts = df_utm_source["utm_source"].value_counts().reset_index()
            src_counts.columns = ["UTM Source", "Matrículas"]
            fig_src = px.bar(
                src_counts.sort_values("Matrículas", ascending=True).tail(15),
                x="Matrículas", y="UTM Source",
                orientation="h", text="Matrículas",
                title="Top 15 UTM Source",
                color_discrete_sequence=["#AB63FA"]
            )
            fig_src.update_layout(height=400)
            st.plotly_chart(fig_src, use_container_width=True)

        with col_utm2:
            med_counts = df_utm_source["utm_medium"].value_counts().dropna().reset_index()
            med_counts.columns = ["UTM Medium", "Matrículas"]
            if not med_counts.empty:
                fig_med = px.pie(
                    med_counts, names="UTM Medium", values="Matrículas",
                    title="Distribuição por UTM Medium",
                    hole=0.35,
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                fig_med.update_traces(textinfo="value+percent")
                st.plotly_chart(fig_med, use_container_width=True)

        # Top campanhas UTM
        df_utm_camp = df_utm_source[
            df_utm_source["utm_campaign"].notna() & (df_utm_source["utm_campaign"] != "")
        ]
        if not df_utm_camp.empty:
            camp_utm_counts = (
                df_utm_camp.groupby("utm_campaign")
                .agg(Matrículas=("cliente_id", "count"), Receita=("total_pedido", "sum"))
                .reset_index()
                .sort_values("Matrículas", ascending=False)
                .head(15)
            )
            camp_utm_counts["Ticket Médio"] = camp_utm_counts["Receita"] / camp_utm_counts["Matrículas"]

            fig_utm_camp = px.bar(
                camp_utm_counts.sort_values("Matrículas", ascending=True),
                x="Matrículas", y="utm_campaign",
                orientation="h", text="Matrículas",
                title="Top 15 UTM Campaign",
                color="Receita",
                color_continuous_scale="Purples",
                labels={"utm_campaign": "Campanha UTM"}
            )
            fig_utm_camp.update_layout(height=max(300, len(camp_utm_counts) * 30))
            st.plotly_chart(fig_utm_camp, use_container_width=True)
    else:
        st.info("Nenhum parâmetro UTM encontrado nos matriculados do período.")

    st.divider()

    # --- Resumo executivo ---
    st.subheader("📋 Resumo Executivo do Período")

    _pct_rastreado = ((qtd_gclid + int((_tem_fbclid & ~_tem_gclid).sum()) + int((_tem_utm & ~_tem_gclid & ~_tem_fbclid).sum())) / total_mat * 100) if total_mat > 0 else 0
    _pct_ligacao = (qtd_ligacao / total_mat * 100) if total_mat > 0 else 0

    insights = []
    insights.append(f"**{total_mat}** matrículas no período, totalizando **{formatar_reais(df_matriculas_tabela['total_pedido'].sum())}** em receita.")
    insights.append(f"**{_pct_rastreado:.1f}%** das matrículas possuem algum rastreamento digital (GCLID, FBCLID ou UTM).")
    insights.append(f"**{_pct_ligacao:.1f}%** dos matriculados receberam pelo menos uma ligação comercial registrada.")

    if ticket_com > 0 and ticket_sem > 0:
        diff_ticket = ((ticket_com - ticket_sem) / ticket_sem * 100)
        if diff_ticket > 0:
            insights.append(f"Matriculados que receberam ligação têm ticket médio **{diff_ticket:.1f}% maior** ({formatar_reais(ticket_com)} vs {formatar_reais(ticket_sem)}).")
        else:
            insights.append(f"Matriculados sem ligação têm ticket médio **{abs(diff_ticket):.1f}% maior** ({formatar_reais(ticket_sem)} vs {formatar_reais(ticket_com)}).")

    if qtd_campanha > 0:
        top_camp = df_camp.groupby("Campanha_Gclid")["total_pedido"].sum().idxmax()
        insights.append(f"A campanha Google Ads com maior receita é **{top_camp}**.")

    for insight in insights:
        st.markdown(f"- {insight}")