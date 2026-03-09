import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from utils.sql_loader import carregar_dados
from datetime import datetime, timedelta
import plotly.express as px
import numpy as np

def run_page():
    TIMEZONE = 'America/Sao_Paulo'

    st.title("📈 Análise de Tendências e Performance")
    st.markdown("*Dashboard avançado para análise de oportunidades, conversões e tendências de mercado*")

    # --- Carregamento e Preparação dos Dados ---
    with st.spinner("Carregando dados..."):
        df_oportunidades = carregar_dados("consultas/oportunidades/oportunidades.sql")
        df_matriculas = carregar_dados("consultas/orders/orders.sql")

    # Pré-processamento dos dados de oportunidades
    df = df_oportunidades.copy()
    df["criacao"] = pd.to_datetime(df["criacao"]).dt.tz_localize(TIMEZONE, ambiguous=False, nonexistent='shift_forward')
    df["data"] = df["criacao"].dt.date
    # Remover timezone antes de converter para period para evitar warning
    df["mes_ano"] = df["criacao"].dt.tz_localize(None).dt.to_period('M')
    df["semana"] = df["criacao"].dt.isocalendar().week
    df["dia_semana"] = df["criacao"].dt.day_name()
    df["hora"] = df["criacao"].dt.hour
    
    # Pré-processamento dos dados de matrículas para conversões
    df_matriculas["data_pagamento"] = pd.to_datetime(df_matriculas["data_pagamento"]).dt.tz_localize(TIMEZONE, ambiguous=False, nonexistent='shift_forward')
    df_matriculas["data"] = df_matriculas["data_pagamento"].dt.date
    
    # ===============================================================================
    # SIDEBAR - FILTROS GLOBAIS
    # ===============================================================================
    st.sidebar.header("🎛️ Filtros Globais")
    
    # Filtro de Empresa (principal) - usando radio conforme solicitado
    # Filtro: empresa
    empresa_selecionada = "Central"
    df_filtrado_empresa = df[df["empresa"] == empresa_selecionada]
    
    # Aplicar filtro de empresa
    if empresa_selecionada:
        df_empresa = df_filtrado_empresa
    else:
        df_empresa = df.copy()

    # Filtros de período melhorados
    st.sidebar.subheader("📅 Período de Análise")
    
    # Limita a busca para dados a partir de Jan/2024
    data_minima_aware = pd.Timestamp('2024-01-01', tz=TIMEZONE)
    df_empresa = df_empresa[df_empresa['criacao'] >= data_minima_aware]

    min_date_para_filtro = df_empresa['criacao'].min().date()
    max_date_para_filtro = df_empresa['criacao'].max().date()
    
    # Opções de período pré-definidas
    periodo_opcoes = {
        "Últimos 30 dias": 30,
        "Últimos 60 dias": 60,
        "Últimos 90 dias": 90,
        "Desde Janeiro 2024": None,
        "Personalizado": "custom"
    }
    
    periodo_escolha = st.sidebar.selectbox("Selecione o período:", list(periodo_opcoes.keys()))
    
    hoje = datetime.now(tz=pd.Timestamp.now(tz=TIMEZONE).tz).date()
    
    if periodo_escolha == "Personalizado":
        periodo = st.sidebar.date_input(
            "Período personalizado:",
            [min_date_para_filtro, max_date_para_filtro],
            min_value=min_date_para_filtro,
            max_value=max_date_para_filtro,
            key="periodo_tendencias"
        )
        if len(periodo) != 2:
            st.warning("Selecione um período válido")
            st.stop()
        data_inicio, data_fim = periodo
    elif periodo_escolha == "Desde Janeiro 2024":
        data_inicio = min_date_para_filtro
        data_fim = max_date_para_filtro
    else:
        dias = periodo_opcoes[periodo_escolha]
        data_inicio = hoje - timedelta(days=dias)
        data_fim = hoje
        st.sidebar.info(f"📊 Analisando: {data_inicio.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')}")

    # Aplicar filtro de data
    data_inicio_aware = pd.Timestamp(data_inicio, tz=TIMEZONE)
    data_fim_aware = pd.Timestamp(data_fim, tz=TIMEZONE) + pd.Timedelta(days=1)
    
    df_filtrado = df_empresa[
        (df_empresa["criacao"] >= data_inicio_aware) &
        (df_empresa["criacao"] < data_fim_aware)
    ]
    
    # Filtros adicionais (expandidos)
    with st.sidebar.expander("🔧 Filtros Avançados", expanded=False):
        # Filtro de Unidades
        unidades = sorted(df_filtrado["unidade"].dropna().unique())
        if unidades:
            unidades_selecionadas = st.multiselect(
                "🏫 Unidades:", 
                unidades, 
                default=unidades,
                help="Selecione as unidades para análise"
            )
            if unidades_selecionadas:
                df_filtrado = df_filtrado[
                    df_filtrado["unidade"].isin(unidades_selecionadas) | 
                    df_filtrado["unidade"].isna()
                ]
        
        # Filtro de Etapas
        etapas = sorted(df_filtrado["etapa"].dropna().unique())
        if etapas:
            etapas_selecionadas = st.multiselect(
                "🎯 Etapas:", 
                etapas, 
                default=etapas,
                help="Selecione as etapas do funil"
            )
            if etapas_selecionadas:
                df_filtrado = df_filtrado[
                    df_filtrado["etapa"].isin(etapas_selecionadas) | 
                    df_filtrado["etapa"].isna()
                ]
    
    # Verificação de dados
    if df_filtrado.empty:
        st.error("❌ Nenhum dado encontrado para os filtros selecionados.")
        st.stop()

    # ===============================================================================
    # MÉTRICAS PRINCIPAIS COM COMPARAÇÃO
    # ===============================================================================
    st.header("📊 Visão Geral e Comparativos")
    
    # Calcular métricas comparativas
    dias_periodo = (data_fim - data_inicio).days
    periodo_anterior_inicio = data_inicio - timedelta(days=dias_periodo)
    periodo_anterior_fim = data_inicio
    
    df_periodo_anterior = df_empresa[
        (df_empresa["criacao"] >= pd.Timestamp(periodo_anterior_inicio, tz=TIMEZONE)) &
        (df_empresa["criacao"] < pd.Timestamp(periodo_anterior_fim, tz=TIMEZONE))
    ]
    
    # Aplicar os mesmos filtros ao período anterior
    if 'unidades_selecionadas' in locals() and unidades_selecionadas:
        df_periodo_anterior = df_periodo_anterior[
            df_periodo_anterior["unidade"].isin(unidades_selecionadas) | 
            df_periodo_anterior["unidade"].isna()
        ]
    if 'etapas_selecionadas' in locals() and etapas_selecionadas:
        df_periodo_anterior = df_periodo_anterior[
            df_periodo_anterior["etapa"].isin(etapas_selecionadas) | 
            df_periodo_anterior["etapa"].isna()
        ]
    
    col1, col2, col3, col4 = st.columns(4)
    
    # Total de Oportunidades
    total_atual = len(df_filtrado)
    total_anterior = len(df_periodo_anterior)
    delta_total = total_atual - total_anterior
    delta_pct_total = (delta_total / total_anterior * 100) if total_anterior > 0 else 0
    
    col1.metric(
        "🎯 Total de Oportunidades", 
        f"{total_atual:,}",
        delta=f"{delta_total:+,} ({delta_pct_total:+.1f}%)"
    )
    
    # Média Diária
    media_diaria_atual = total_atual / dias_periodo if dias_periodo > 0 else 0
    media_diaria_anterior = total_anterior / dias_periodo if dias_periodo > 0 else 0
    delta_media = media_diaria_atual - media_diaria_anterior
    
    col2.metric(
        "📈 Média Diária", 
        f"{media_diaria_atual:.1f}",
        delta=f"{delta_media:+.1f}"
    )
    
    # Conversões (usando dados de matrículas/pedidos)
    # Filtrar matrículas para a empresa selecionada e período
    df_matriculas_empresa = df_matriculas[df_matriculas["empresa"] == empresa_selecionada]
    
    conversoes_atual = len(df_matriculas_empresa[
        (df_matriculas_empresa["data_pagamento"] >= pd.Timestamp(data_inicio, tz=TIMEZONE)) &
        (df_matriculas_empresa["data_pagamento"] < pd.Timestamp(data_fim, tz=TIMEZONE) + pd.Timedelta(days=1)) &
        (df_matriculas_empresa["status_id"].isin([2, 3, 14, 10, 15])) &
        (df_matriculas_empresa["total_pedido"] != 0) &
        (~df_matriculas_empresa["metodo_pagamento"].isin([5, 8, 13]))
    ])  # Status de pagamentos
    
    conversoes_anterior = len(df_matriculas_empresa[
        (df_matriculas_empresa["data_pagamento"] >= pd.Timestamp(periodo_anterior_inicio, tz=TIMEZONE)) &
        (df_matriculas_empresa["data_pagamento"] < pd.Timestamp(periodo_anterior_fim, tz=TIMEZONE)) &
        (df_matriculas_empresa["status_id"].isin([2, 3, 14, 10, 15])) &
        (df_matriculas_empresa["total_pedido"] != 0) &
        (~df_matriculas_empresa["metodo_pagamento"].isin([5, 8, 13]))  # Status de pagamentos
    ])
    
    delta_conversoes = conversoes_atual - conversoes_anterior
    
    col3.metric(
        "✅ Conversões", 
        f"{conversoes_atual:,}",
        delta=f"{delta_conversoes:+,}"
    )
    
    # Taxa de Conversão
    taxa_conversao_atual = (conversoes_atual / total_atual * 100) if total_atual > 0 else 0
    taxa_conversao_anterior = (conversoes_anterior / total_anterior * 100) if total_anterior > 0 else 0
    delta_taxa = taxa_conversao_atual - taxa_conversao_anterior
    
    col4.metric(
        "🎯 Taxa de Conversão", 
        f"{taxa_conversao_atual:.1f}%",
        delta=f"{delta_taxa:+.1f}%"
    )
    
    st.divider()
    # ===============================================================================
    # ANÁLISE MENSAL APRIMORADA
    # ===============================================================================
    st.header("📅 Análise Mensal de Oportunidades")
    st.markdown("Comparativo do desempenho mensal e tendência ao longo do tempo.")
    
    # --- Análise Like-for-Like melhorada ---
    hoje_tz = pd.Timestamp.now(tz=TIMEZONE)
    dia_corrente = hoje_tz.day

    # Períodos do Mês Atual (Mês-a-Data)
    mes_atual_inicio = hoje_tz.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    df_mes_atual_mtd = df_filtrado[(df_filtrado['criacao'] >= mes_atual_inicio) & (df_filtrado['criacao'] <= hoje_tz)]
    total_mes_atual_mtd = df_mes_atual_mtd.shape[0]

    # Períodos do Mês Anterior - Correção para o mês anterior correto
    # Calcular o primeiro dia do mês anterior
    if mes_atual_inicio.month == 1:
        mes_anterior_inicio = mes_atual_inicio.replace(year=mes_atual_inicio.year - 1, month=12)
    else:
        mes_anterior_inicio = mes_atual_inicio.replace(month=mes_atual_inicio.month - 1)
    
    # Calcular o último dia do mês anterior
    mes_anterior_fim_total = mes_atual_inicio - pd.Timedelta(seconds=1)
    
    # Período "Like-for-Like" do mês anterior (primeiros X dias)
    # Calcular quantos dias úteis temos no mês atual até hoje
    dias_decorridos_mes_atual = (hoje_tz - mes_atual_inicio).days + 1  # +1 para incluir o dia atual
    
    # Aplicar o mesmo número de dias no mês anterior
    try:
        # Tentar adicionar o mesmo número de dias ao início do mês anterior
        mes_anterior_fim_like = mes_anterior_inicio + pd.Timedelta(days=dias_decorridos_mes_atual - 1)
        # Garantir que não ultrapasse o último dia do mês anterior
        if mes_anterior_fim_like > mes_anterior_fim_total:
            mes_anterior_fim_like = mes_anterior_fim_total
        # Definir horário para fim do dia
        mes_anterior_fim_like = mes_anterior_fim_like.replace(hour=23, minute=59, second=59)
    except ValueError:
        # Se der erro, usar o último dia disponível do mês anterior
        mes_anterior_fim_like = mes_anterior_fim_total

    df_mes_anterior_total = df_filtrado[(df_filtrado['criacao'] >= mes_anterior_inicio) & (df_filtrado['criacao'] <= mes_anterior_fim_total)]
    df_mes_anterior_like = df_filtrado[(df_filtrado['criacao'] >= mes_anterior_inicio) & (df_filtrado['criacao'] <= mes_anterior_fim_like)]

    total_mes_anterior_completo = df_mes_anterior_total.shape[0]
    total_mes_anterior_like = df_mes_anterior_like.shape[0]

    # Cálculo da tendência "Like-for-Like"
    delta_like_for_like = 0
    if total_mes_anterior_like > 0:
        delta_like_for_like = ((total_mes_atual_mtd - total_mes_anterior_like) / total_mes_anterior_like) * 100

    # --- Apresentação das Métricas ---
    st.subheader(f"📊 Comparativo Mês a Data: Primeiros {dias_decorridos_mes_atual} dias")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            label=f"Mês Atual ({dias_decorridos_mes_atual} dias)",
            value=f"{total_mes_atual_mtd:,}",
            delta=f"{delta_like_for_like:.1f}%",
            help=f"Comparado com os primeiros {dias_decorridos_mes_atual} dias do mês anterior."
        )

    with col2:
        st.metric(
            label=f"Mês Anterior ({dias_decorridos_mes_atual} dias)",
            value=f"{total_mes_anterior_like:,}"
        )

    with col3:
        st.metric(
            label=f"Total do Mês Anterior Completo",
            value=f"{total_mes_anterior_completo:,}",
            help="Valor total do mês anterior para referência."
        )

    # --- Gráficos de Tendência Mensal e Diária ---
    col1, col2 = st.columns(2)
    
    with col1:
        # Gráfico de Barras Mensal
        st.subheader("📊 Evolução Mensal")
        df_mensal = df_filtrado.groupby(df_filtrado['criacao'].dt.tz_convert(None).dt.to_period('M')).agg(
            Quantidade=('oportunidade', 'count')
        ).reset_index()
        df_mensal['Mes'] = df_mensal['criacao'].dt.strftime('%Y-%m')

        if not df_mensal.empty:
            fig_mensal = go.Figure(go.Bar(
                x=df_mensal['Mes'], 
                y=df_mensal['Quantidade'], 
                text=df_mensal['Quantidade'],
                textposition='outside', 
                marker_color='#1f77b4',
                hovertemplate='<b>%{x}</b><br>Oportunidades: %{y}<extra></extra>'
            ))
            fig_mensal.update_layout(
                title_text='Total de Oportunidades por Mês', 
                xaxis_title='Mês',
                yaxis_title='Quantidade', 
                xaxis_type='category',
                height=400
            )
            st.plotly_chart(fig_mensal, use_container_width=True)
        else:
            st.warning("Não há dados mensais para exibir.")
    
    with col2:
        # Gráfico de Tendência Diária
        st.subheader("📈 Tendência Diária")
        df_diario = df_filtrado.groupby("data").agg({
            "oportunidade": "count"
        }).reset_index()
        df_diario.columns = ["Data", "Oportunidades"]
        
        if not df_diario.empty and len(df_diario) > 1:
            # Adicionar linha de tendência
            z = np.polyfit(range(len(df_diario)), df_diario["Oportunidades"], 1)
            p = np.poly1d(z)
            df_diario["Tendencia"] = p(range(len(df_diario)))
            
            fig_diario = go.Figure()
            
            # Linha principal
            fig_diario.add_trace(go.Scatter(
                x=df_diario["Data"], 
                y=df_diario["Oportunidades"],
                mode='lines+markers',
                name='Oportunidades',
                line=dict(color='#ff7f0e', width=2),
                marker=dict(size=4)
            ))
            
            # Linha de tendência
            fig_diario.add_trace(go.Scatter(
                x=df_diario["Data"], 
                y=df_diario["Tendencia"],
                mode='lines',
                name='Tendência',
                line=dict(color='red', width=2, dash='dash')
            ))
            
            fig_diario.update_layout(
                title="Tendência Diária de Oportunidades",
                xaxis_title="Data",
                yaxis_title="Oportunidades",
                height=400,
                hovermode='x unified'
            )
            
            st.plotly_chart(fig_diario, use_container_width=True)
        else:
            st.info("Dados insuficientes para tendência diária.")

    st.divider()
    # ===============================================================================
    # ANÁLISE SEMANAL APRIMORADA
    # ===============================================================================
    st.header("🔬 Análise Semanal Detalhada")
    
    tab1, tab2 = st.tabs(["📊 Janela de 7 Dias", "📈 Padrões Semanais"])
    
    with tab1:
        st.subheader("🎯 Zoom na Tendência de Concursos (Janela de 7 dias)")

        # --- 1. CONTROLE DE DATA INDEPENDENTE ---
        data_max_analise = data_fim
        data_min_analise = data_inicio

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
                # Define a janela dos 7 dias anteriores (corrigindo o cálculo)
                inicio_periodo_anterior = data_inicio_janela - pd.Timedelta(days=7)
                fim_periodo_anterior = data_inicio_janela - pd.Timedelta(seconds=1)
                
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
                st.subheader("📊 Comparativo de Desempenho (Semana a Semana)")
                col1, col2, col3 = st.columns(3)
                
                col1.metric(
                    label=f"Oportunidades nos 7 dias selecionados",
                    value=f"{total_dias_atuais:,}",
                    delta=f"{delta_semanal:.1f}% vs. semana anterior"
                )
                col2.metric(
                    label=f"Oportunidades nos 7 dias anteriores",
                    value=f"{total_dias_anteriores:,}"
                )
                
                # Média diária
                media_diaria_7d = total_dias_atuais / 7
                col3.metric(
                    label="Média Diária (7 dias)",
                    value=f"{media_diaria_7d:.1f}"
                )
                
                # --- 3. EXIBIÇÃO DO GRÁFICO DE COLUNAS ---
                st.subheader(f"📊 Oportunidades Diárias para os Top 6 Concursos")
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
                fig_7d.update_layout(
                    xaxis={'type': 'category', 'categoryorder':'category ascending'},
                    height=500
                )
                st.plotly_chart(fig_7d, use_container_width=True)

                # Lista dos Top 6 concursos
                st.subheader("🏆 Top 6 Concursos do Período")
                df_top6_resumo = df_top6_atuais.groupby('concurso')['oportunidade'].count().sort_values(ascending=False).reset_index()
                df_top6_resumo.columns = ['Concurso', 'Total de Oportunidades']
                st.dataframe(df_top6_resumo, use_container_width=True)

            else:
                st.info("Não há dados de oportunidades na janela de 7 dias selecionada.")
    
    with tab2:
        st.subheader("📈 Padrões e Tendências Semanais")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Análise por dia da semana
            ordem_dias = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            dias_pt = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
            
            df_dia_semana = df_filtrado.groupby("dia_semana")["oportunidade"].count().reset_index()
            df_dia_semana["dia_semana"] = pd.Categorical(df_dia_semana["dia_semana"], categories=ordem_dias, ordered=True)
            df_dia_semana = df_dia_semana.sort_values("dia_semana")
            df_dia_semana["dia_pt"] = dias_pt[:len(df_dia_semana)]
            
            fig_dia_semana = px.bar(
                df_dia_semana,
                x="dia_pt",
                y="oportunidade",
                title="📅 Distribuição por Dia da Semana",
                labels={"dia_pt": "Dia da Semana", "oportunidade": "Oportunidades"},
                color="oportunidade",
                color_continuous_scale="Blues",
                text="oportunidade"
            )
            fig_dia_semana.update_traces(textposition='outside')
            fig_dia_semana.update_layout(showlegend=False, height=400)
            
            st.plotly_chart(fig_dia_semana, use_container_width=True)
        
        with col2:
            # Análise por hora do dia
            df_hora = df_filtrado.groupby("hora")["oportunidade"].count().reset_index()
            
            fig_hora = px.line(
                df_hora,
                x="hora",
                y="oportunidade",
                title="🕐 Distribuição por Hora do Dia",
                labels={"hora": "Hora", "oportunidade": "Oportunidades"},
                markers=True
            )
            fig_hora.update_traces(line=dict(color='#ff6b6b', width=3), marker=dict(size=8))
            fig_hora.update_layout(
                xaxis=dict(tickmode='linear', dtick=2),
                hovermode='x',
                height=400
            )
            
            st.plotly_chart(fig_hora, use_container_width=True)
        
        # Heatmap de oportunidades por hora e dia da semana
        if not df_filtrado.empty:
            st.subheader("🔥 Heatmap: Oportunidades por Dia da Semana e Hora")
            df_heatmap = df_filtrado.groupby(["dia_semana", "hora"])["oportunidade"].count().reset_index()
            df_heatmap_pivot = df_heatmap.pivot(index="dia_semana", columns="hora", values="oportunidade").fillna(0)
            
            # Reordenar dias da semana
            if not df_heatmap_pivot.empty:
                df_heatmap_pivot = df_heatmap_pivot.reindex(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'])
                df_heatmap_pivot.index = dias_pt[:len(df_heatmap_pivot)]
                
                fig_heatmap = px.imshow(
                    df_heatmap_pivot,
                    title="Intensidade de Oportunidades por Dia e Hora",
                    labels=dict(x="Hora", y="Dia da Semana", color="Oportunidades"),
                    color_continuous_scale="YlOrRd",
                    aspect="auto"
                )
                fig_heatmap.update_layout(height=400)
                
                st.plotly_chart(fig_heatmap, use_container_width=True)
    
    # ===============================================================================
    # INSIGHTS E RECOMENDAÇÕES
    # ===============================================================================
    st.divider()
    st.header("💡 Insights e Recomendações Inteligentes")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 Principais Insights")
        
        insights = []
        
        # Insight sobre crescimento
        if delta_pct_total > 10:
            insights.append(f"🚀 **Crescimento Forte**: Aumento de {delta_pct_total:.1f}% nas oportunidades comparado ao período anterior")
        elif delta_pct_total < -10:
            insights.append(f"⚠️ **Atenção**: Queda de {abs(delta_pct_total):.1f}% nas oportunidades comparado ao período anterior")
        else:
            insights.append(f"📊 **Estabilidade**: Variação de {delta_pct_total:.1f}% mantém o desempenho estável")
        
        # Insight sobre conversão
        if taxa_conversao_atual > 15:
            insights.append(f"✅ **Boa Taxa de Conversão**: {taxa_conversao_atual:.1f}% está acima da média")
        elif taxa_conversao_atual < 5:
            insights.append(f"🔴 **Taxa de Conversão Baixa**: {taxa_conversao_atual:.1f}% precisa de atenção")
        else:
            insights.append(f"📊 **Taxa Moderada**: {taxa_conversao_atual:.1f}% de conversão dentro da normalidade")
        
        # Insight sobre melhor dia da semana
        if not df_dia_semana.empty:
            melhor_dia_idx = df_dia_semana["oportunidade"].idxmax()
            melhor_dia = df_dia_semana.loc[melhor_dia_idx, "dia_pt"]
            pior_dia_idx = df_dia_semana["oportunidade"].idxmin()
            pior_dia = df_dia_semana.loc[pior_dia_idx, "dia_pt"]
            insights.append(f"📅 **Padrão Semanal**: {melhor_dia} é o melhor dia, {pior_dia} o mais fraco")
        
        # Insight sobre horário de pico
        if not df_hora.empty:
            hora_pico = df_hora.loc[df_hora["oportunidade"].idxmax(), "hora"]
            insights.append(f"⏰ **Horário de Pico**: {hora_pico}h concentra mais oportunidades")
        
        for insight in insights:
            st.markdown(insight)
    
    with col2:
        st.subheader("🎯 Recomendações Estratégicas")
        
        recomendacoes = []
        
        # Recomendação baseada em conversão
        if taxa_conversao_atual < 10:
            recomendacoes.append("📞 **Otimizar Follow-up**: Revisar processo de qualificação e acompanhamento de leads")
        
        # Recomendação baseada em crescimento
        if delta_pct_total < -5:
            recomendacoes.append("📈 **Ação Urgente**: Implementar estratégias para reverter a queda")
        elif delta_pct_total > 20:
            recomendacoes.append("🚀 **Aproveitar Momentum**: Aumentar investimento para sustentar o crescimento")
        
        # Recomendação baseada em horário
        if not df_hora.empty:
            hora_pico = df_hora.loc[df_hora["oportunidade"].idxmax(), "hora"]
            recomendacoes.append(f"⏰ **Otimizar Recursos**: Reforçar equipe no horário de pico ({hora_pico}h)")
        
        # Recomendação baseada em dia da semana
        if not df_dia_semana.empty:
            melhor_dia = df_dia_semana.loc[df_dia_semana["oportunidade"].idxmax(), "dia_pt"]
            recomendacoes.append(f"📅 **Foco Estratégico**: Intensificar campanhas às {melhor_dia}s")
        
        recomendacoes.append("📊 **Monitoramento Contínuo**: Implementar alertas para variações significativas")
        recomendacoes.append("🎯 **Segmentação**: Criar campanhas específicas por padrões identificados")
        
        for rec in recomendacoes:
            st.markdown(rec)
    
    # ===============================================================================
    # EXPORTAÇÃO DE DADOS
    # ===============================================================================
    st.divider()
    st.subheader("📁 Exportar Dados para Análise")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📊 Exportar Dados Completos", help="Download dos dados filtrados em CSV"):
            csv = df_filtrado.to_csv(index=False)
            st.download_button(
                label="⬇️ Download CSV",
                data=csv,
                file_name=f"tendencias_{empresa_selecionada}_{data_inicio}_{data_fim}.csv",
                mime="text/csv"
            )
    
    with col2:
        if st.button("📈 Exportar Análise Mensal", help="Download da análise mensal"):
            if not df_mensal.empty:
                csv_mensal = df_mensal.to_csv(index=False)
                st.download_button(
                    label="⬇️ Download Mensal CSV",
                    data=csv_mensal,
                    file_name=f"analise_mensal_{empresa_selecionada}_{data_inicio}_{data_fim}.csv",
                    mime="text/csv"
                )
    
    with col3:
        if st.button("🎯 Exportar Padrões Semanais", help="Download dos padrões por dia da semana"):
            if not df_dia_semana.empty:
                csv_semanal = df_dia_semana.to_csv(index=False)
                st.download_button(
                    label="⬇️ Download Semanal CSV",
                    data=csv_semanal,
                    file_name=f"padroes_semanais_{empresa_selecionada}_{data_inicio}_{data_fim}.csv",
                    mime="text/csv"
                )

if __name__ == "__main__":
    run_page()