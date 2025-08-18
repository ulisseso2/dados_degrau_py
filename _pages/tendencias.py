import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils.sql_loader import carregar_dados
from datetime import datetime
import plotly.express as px

def run_page():
    TIMEZONE = 'America/Sao_Paulo'

    st.title("📈 Análise de Tendências de Oportunidades")

    # --- Carregamento e Filtros ---
    df = carregar_dados("consultas/oportunidades/oportunidades.sql")

    empresas = df["empresa"].dropna().unique().tolist()
    empresa_selecionada = st.sidebar.radio("Selecione uma empresa:", empresas)
    df_filtrado_empresa = df[df["empresa"] == empresa_selecionada]

    # Filtro utilizando data de criação da oportunidade
    df_filtrado_empresa["criacao"] = pd.to_datetime(df_filtrado_empresa["criacao"]).dt.tz_localize(TIMEZONE, ambiguous='infer').copy()

    # Limita a busca para dados a partir de Jan/2024
    data_minima_aware = pd.Timestamp('2024-01-01', tz=TIMEZONE)
    df_filtrado_empresa = df_filtrado_empresa[df_filtrado_empresa['criacao'] >= data_minima_aware]

    min_date_para_filtro = df_filtrado_empresa['criacao'].min().date()
    max_date_para_filtro = df_filtrado_empresa['criacao'].max().date()

    periodo = [min_date_para_filtro, max_date_para_filtro]

    # Verificamos se o usuário selecionou um período válido
    if len(periodo) == 2:
        # Convertemos as datas puras em Timestamps precisos com fuso horário
        data_inicio_aware = pd.Timestamp(periodo[0], tz=TIMEZONE)
        # Adicionamos 1 dia ao fim e usamos '<' para incluir o dia final inteiro
        data_fim_aware = pd.Timestamp(periodo[1], tz=TIMEZONE) + pd.Timedelta(days=1)

        # Filtrar o DataFrame usando os Timestamps 'aware'
        df_filtrado = df_filtrado_empresa[
            (df_filtrado_empresa['criacao'] >= data_inicio_aware) & 
            (df_filtrado_empresa['criacao'] < data_fim_aware)
        ]
    else:
        # Se o usuário limpar o filtro de data, usamos o DataFrame completo
        df_filtrado = df.copy()

    # --- INÍCIO DA ANÁLISE MENSAL
    st.header("Análise Mensal de Oportunidades")
    st.markdown("Comparativo do desempenho mensal e a tendência ao longo do tempo.")

    # --- Lógica de cálculo Like-for-Like ---
    hoje = pd.Timestamp.now(tz=TIMEZONE)
    dia_corrente = hoje.day

    # Períodos do Mês Atual (Mês-a-Data)
    mes_atual_inicio = hoje.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    df_mes_atual_mtd = df_filtrado[(df_filtrado['criacao'] >= mes_atual_inicio) & (df_filtrado['criacao'] <= hoje)]
    total_mes_atual_mtd = df_mes_atual_mtd.shape[0]

    # Períodos do Mês Anterior
    mes_anterior_fim_total = mes_atual_inicio - pd.Timedelta(seconds=1)
    mes_anterior_inicio = mes_anterior_fim_total.replace(day=1)
    # Período "Like-for-Like" do mês anterior
    mes_anterior_fim_like = (mes_anterior_inicio + pd.DateOffset(days=dia_corrente - 1)).replace(hour=23, minute=59, second=59)

    df_mes_anterior_total = df_filtrado[(df_filtrado['criacao'] >= mes_anterior_inicio) & (df_filtrado['criacao'] <= mes_anterior_fim_total)]
    df_mes_anterior_like = df_mes_anterior_total[df_mes_anterior_total['criacao'] <= mes_anterior_fim_like]

    total_mes_anterior_completo = df_mes_anterior_total.shape[0]
    total_mes_anterior_like = df_mes_anterior_like.shape[0]

    # Cálculo da tendência "Like-for-Like"
    delta_like_for_like = 0
    if total_mes_anterior_like > 0:
        delta_like_for_like = ((total_mes_atual_mtd - total_mes_anterior_like) / total_mes_anterior_like) * 100

    # --- Apresentação das Métricas ---
    st.subheader(f"Comparativo Mês a Data: Primeiros {dia_corrente} dias")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            label=f"Mês Atual (Até Dia {dia_corrente})",
            value=f"{total_mes_atual_mtd}",
            delta=f"{delta_like_for_like:.1f}%",
            help=f"Comparado com os primeiros {dia_corrente} dias do mês anterior."
        )

    with col2:
        st.metric(
            label=f"Mês Anterior (Primeiros {dia_corrente} dias)",
            value=f"{total_mes_anterior_like}"
        )

    with col3:
        st.metric(
            label=f"Total do Mês Anterior Completo",
            value=f"{total_mes_anterior_completo}",
            help="Valor total do mês anterior para referência."
        )

    st.divider()

    # --- Gráfico de Barras Mensal ---
    st.subheader("Evolução Mensal de Oportunidades")
    df_mensal = df_filtrado.groupby(df_filtrado['criacao'].dt.tz_convert(None).dt.to_period('M')).agg(
        Quantidade=('oportunidade', 'count')
    ).reset_index()
    df_mensal['Mes'] = df_mensal['criacao'].dt.strftime('%Y-%m')

    if not df_mensal.empty:
        fig_mensal = go.Figure(go.Bar(
            x=df_mensal['Mes'], y=df_mensal['Quantidade'], text=df_mensal['Quantidade'],
            textposition='outside', marker_color='#1f77b4'
        ))
        fig_mensal.update_layout(
            title_text='Total de Oportunidades por Mês', xaxis_title='Mês',
            yaxis_title='Quantidade', xaxis_type='category'
        )
        st.plotly_chart(fig_mensal, use_container_width=True)
    else:
        st.warning("Não há dados mensais para exibir no período selecionado.")

    st.divider()
    st.header("🔬 Zoom na Tendência de Concursos (Janela de 7 dias)")

    # --- 1. CONTROLE DE DATA INDEPENDENTE ---
    data_max_analise = periodo[1]
    data_min_analise = periodo[0]

    data_final_selecionada = st.date_input(
        "Selecione a data FINAL da sua análise de 7 dias:",
        value=data_max_analise,
        min_value=data_min_analise,
        max_value=data_max_analise,
        help="A análise considerará os 7 dias que terminam nesta data."
    )

    if data_final_selecionada:
        # Define a janela de 7 dias selecionada pelo usuário
        data_fim_janela = pd.Timestamp(data_final_selecionada, tz=TIMEZONE)
        data_inicio_janela = data_fim_janela - pd.Timedelta(days=6)
        limite_superior = data_fim_janela + pd.Timedelta(days=1)
        
        df_7dias = df_filtrado[
            (df_filtrado['criacao'] >= data_inicio_janela) & 
            (df_filtrado['criacao'] < limite_superior)
        ]

        if not df_7dias.empty:
            # Identifica os Top 6 concursos na janela selecionada
            top_6_concursos = df_7dias['concurso'].value_counts().nlargest(6).index.tolist()
            
            # Filtra os dados da janela atual para conter apenas os Top 6
            df_top6_atuais = df_7dias[df_7dias['concurso'].isin(top_6_concursos)]
            total_dias_atuais = df_top6_atuais.shape[0]

            # --- 2a. CÁLCULO PARA AS MÉTRICAS DE COMPARAÇÃO ---
            # Define a janela dos 7 dias anteriores
            fim_periodo_anterior = data_inicio_janela - pd.Timedelta(days=1)
            inicio_periodo_anterior = fim_periodo_anterior - pd.Timedelta(days=6)
            
            # Filtra os dados para o período anterior, USANDO A MESMA LISTA DE TOP 6 CONCURSOS
            df_7dias_anteriores = df_filtrado[
                (df_filtrado['criacao'] >= inicio_periodo_anterior) &
                (df_filtrado['criacao'] <= fim_periodo_anterior) &
                (df_filtrado['concurso'].isin(top_6_concursos)) # Importante para uma comparação justa
            ]
            total_dias_anteriores = df_7dias_anteriores.shape[0]

            # Calcula a variação
            delta_semanal = 0
            if total_dias_anteriores > 0:
                delta_semanal = ((total_dias_atuais - total_dias_anteriores) / total_dias_anteriores) * 100

            # --- 2b. EXIBIÇÃO DAS MÉTRICAS ---
            st.subheader("Comparativo de Desempenho (Semana a Semana)")
            col1, col2 = st.columns(2)
            col1.metric(
                label=f"Oportunidades nos 7 dias selecionados",
                value=total_dias_atuais,
                delta=f"{delta_semanal:.1f}% vs. semana anterior"
            )
            col2.metric(
                label=f"Oportunidades nos 7 dias anteriores",
                value=total_dias_anteriores
            )
            
            # --- 3. EXIBIÇÃO DO GRÁFICO DE COLUNAS ---
            st.subheader(f"Oportunidades Diárias para os Top 6 Concursos")
            df_grafico_7d = df_top6_atuais.groupby([df_top6_atuais['criacao'].dt.date, 'concurso']) \
                                        .agg(Quantidade=('oportunidade', 'count')).reset_index()
            df_grafico_7d.rename(columns={'criacao': 'Data'}, inplace=True)

            fig_7d = px.bar(
                df_grafico_7d,
                x='Data', y='Quantidade', color='concurso',
                title=f"Volume de Oportunidades de {data_inicio_janela.strftime('%d/%m')} a {data_fim_janela.strftime('%d/%m')}",
                labels={'Quantidade': 'Nº de Oportunidades', 'Data': 'Dia'},
                barmode='group', text_auto='.0f'
            )
            fig_7d.update_layout(xaxis={'type': 'category', 'categoryorder':'category ascending'})
            st.plotly_chart(fig_7d, use_container_width=True)

        else:
            st.info("Não há dados de oportunidades na janela de 7 dias selecionada.")