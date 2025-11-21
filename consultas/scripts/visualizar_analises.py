import pandas as pd
import streamlit as st
import os

def carregar_dados(caminho_csv):
    """
    Carrega os dados estruturados de um arquivo CSV.

    Args:
        caminho_csv (str): Caminho para o arquivo CSV.

    Returns:
        DataFrame: Dados carregados em um DataFrame.
    """
    if not os.path.exists(caminho_csv):
        return None
    
    try:
        df = pd.read_csv(caminho_csv)
        # Substituir valores None/null por "Não identificado"
        df = df.fillna("Não identificado")
        return df
    except pd.errors.EmptyDataError:
        return None

def main():
    st.set_page_config(page_title="Análise de Transcrições", page_icon="📞", layout="wide")
    
    st.title("📞 Análise de Transcrições de Telefonia")
    st.markdown("---")

    caminho_csv = "consultas/resultados/analises.csv"

    # Carregar dados
    dados = carregar_dados(caminho_csv)
    
    if dados is None or dados.empty:
        st.warning("⚠️ Nenhum dado encontrado. Execute o pipeline primeiro:")
        st.code("python consultas/scripts/main.py")
        return

    # Métricas gerais
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total de Conversas", len(dados))
    
    with col2:
        consultores_unicos = dados[dados['consultor'] != "Não identificado"]['consultor'].nunique()
        st.metric("Consultores", consultores_unicos)
    
    with col3:
        concursos_unicos = dados[dados['concurso_interesse'] != "Não identificado"]['concurso_interesse'].nunique()
        st.metric("Concursos Identificados", concursos_unicos)
    
    with col4:
        com_objecao = len(dados[dados['objecao'] != "Não identificado"])
        st.metric("Conversas com Objeções", com_objecao)

    st.markdown("---")

    # Filtros laterais
    st.sidebar.header("🔍 Filtros")
    
    # Filtro por consultor
    consultores = ["Todos"] + sorted(dados[dados['consultor'] != "Não identificado"]['consultor'].unique().tolist())
    consultor_selecionado = st.sidebar.selectbox("Consultor", consultores)
    
    # Filtro por concurso
    concursos = ["Todos"] + sorted(dados[dados['concurso_interesse'] != "Não identificado"]['concurso_interesse'].unique().tolist())
    concurso_selecionado = st.sidebar.selectbox("Concurso de Interesse", concursos)
    
    # Filtro por objeção
    tem_objecao = st.sidebar.radio("Tem Objeção?", ["Todos", "Sim", "Não"])
    
    # Aplicar filtros
    dados_filtrados = dados.copy()
    
    if consultor_selecionado != "Todos":
        dados_filtrados = dados_filtrados[dados_filtrados['consultor'] == consultor_selecionado]
    
    if concurso_selecionado != "Todos":
        dados_filtrados = dados_filtrados[dados_filtrados['concurso_interesse'] == concurso_selecionado]
    
    if tem_objecao == "Sim":
        dados_filtrados = dados_filtrados[dados_filtrados['objecao'] != "Não identificado"]
    elif tem_objecao == "Não":
        dados_filtrados = dados_filtrados[dados_filtrados['objecao'] == "Não identificado"]

    # Exibir dados filtrados
    st.subheader(f"📊 Dados Filtrados ({len(dados_filtrados)} conversas)")
    
    # Ordenar colunas para melhor visualização
    colunas_ordem = ['arquivo', 'consultor', 'interlocutor', 'concurso_interesse', 
                     'oferta_proposta', 'objecao', 'resposta_consultor', 'assunto']
    dados_filtrados = dados_filtrados[colunas_ordem]
    
    st.dataframe(dados_filtrados, use_container_width=True, height=400)

    # Análises e visualizações
    st.markdown("---")
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 Top 5 Consultores")
        top_consultores = dados[dados['consultor'] != "Não identificado"]['consultor'].value_counts().head(5)
        if not top_consultores.empty:
            st.bar_chart(top_consultores)
        else:
            st.info("Sem dados suficientes")
    
    with col2:
        st.subheader("📈 Top 5 Concursos de Interesse")
        top_concursos = dados[dados['concurso_interesse'] != "Não identificado"]['concurso_interesse'].value_counts().head(5)
        if not top_concursos.empty:
            st.bar_chart(top_concursos)
        else:
            st.info("Sem dados suficientes")

    # Tabela de objeções mais comuns
    st.markdown("---")
    st.subheader("🚫 Objeções Mais Comuns")
    objecoes = dados[dados['objecao'] != "Não identificado"]['objecao'].value_counts().head(10)
    if not objecoes.empty:
        st.dataframe(objecoes.reset_index().rename(columns={'index': 'Objeção', 'objecao': 'Quantidade'}), 
                     use_container_width=True)
    else:
        st.info("Nenhuma objeção identificada nos dados")

    # Download dos dados
    st.markdown("---")
    st.download_button(
        label="📥 Download CSV",
        data=dados_filtrados.to_csv(index=False).encode('utf-8'),
        file_name="analise_transcricoes.csv",
        mime="text/csv"
    )

if __name__ == "__main__":
    main()