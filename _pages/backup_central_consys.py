import sys
import os
import io
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pandas as pd
import streamlit as st
import json
from datetime import datetime
from pathlib import Path


# Diretório dos arquivos Parquet particionados
CACHE_DIR = Path(__file__).parent.parent / "data_cache" / "central_backup"


@st.cache_data(show_spinner=False)
def carregar_anos_disponiveis():
    """Lista os anos disponíveis nos arquivos Parquet"""
    if not CACHE_DIR.exists():
        return []
    
    arquivos = list(CACHE_DIR.glob("*.parquet"))
    anos = sorted([int(f.stem) for f in arquivos])
    return anos


@st.cache_data(show_spinner=False)
def carregar_dados_ano(ano):
    """Carrega dados de um ano específico do arquivo Parquet"""
    arquivo = CACHE_DIR / f"{ano}.parquet"
    
    if not arquivo.exists():
        return pd.DataFrame()
    
    df = pd.read_parquet(arquivo)
    # Converte data de volta para datetime
    df['data'] = pd.to_datetime(df['data'], errors='coerce')
    return df


@st.cache_data(show_spinner=False)
def carregar_todos_dados():
    """Carrega todos os anos em um único DataFrame (quando necessário)"""
    anos = carregar_anos_disponiveis()
    
    if not anos:
        return pd.DataFrame()
    
    dfs = [carregar_dados_ano(ano) for ano in anos]
    return pd.concat(dfs, ignore_index=True)


def exibir_parcelas(json_parcelas):
    """Converte JSON de parcelas em DataFrame e exibe tabela formatada"""
    if pd.isna(json_parcelas) or json_parcelas is None:
        st.info("Sem parcelas cadastradas")
        return
    
    try:
        parcelas = json.loads(json_parcelas)
        if not parcelas:
            st.info("Sem parcelas cadastradas")
            return
            
        df_parcelas = pd.DataFrame(parcelas)
        df_parcelas.columns = ['Parcela', 'Valor', 'Vencimento']
        df_parcelas['Valor'] = df_parcelas['Valor'].apply(lambda x: f"R$ {x:,.2f}".replace(',', '_').replace('.', ',').replace('_', '.'))
        
        st.dataframe(df_parcelas, use_container_width=True, hide_index=True)
        
    except json.JSONDecodeError:
        st.error("Erro ao processar JSON de parcelas")


def exibir_detalhes_matricula(row):
    """Exibe detalhes completos de uma matrícula"""
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### 📋 Dados Cadastrais")
        st.write(f"**Código:** {row['codigo']}")
        st.write(f"**Matrícula:** {row['matricula']}")
        st.write(f"**Nome:** {row['nome']}")
        st.write(f"**CPF:** {row['cpf']}")
        st.write(f"**Email:** {row['email']}")
        st.write(f"**Telefone:** {row['telefone']}")
    
    with col2:
        st.markdown("### 🏫 Dados do Curso")
        st.write(f"**Unidade:** {row['unidade_central']}")
        st.write(f"**Turma:** {row['turma']}")
        st.write(f"**Curso:** {row['desc_curso']}")
        st.write(f"**Data Cadastro:** {row['data']}")
        st.write(f"**Status:** {row['status']}")
    
    with col3:
        st.markdown("### 💰 Dados Financeiros")
        st.write(f"**Valor Produto:** R$ {row['valor_produto']:,.2f}".replace(',', '_').replace('.', ',').replace('_', '.'))
        st.write(f"**Desconto:** R$ {row['desconto']:,.2f}".replace(',', '_').replace('.', ',').replace('_', '.'))
        st.write(f"**Valor Pagamento:** R$ {row['valor_pagamento']:,.2f}".replace(',', '_').replace('.', ',').replace('_', '.'))
        st.write(f"**Forma Pagamento:** {row['forma']}")
        st.write(f"**Qtd. Parcelas:** {row['parcelas']}")
        if row['motivo_desconto']:
            st.write(f"**Motivo Desconto:** {row['motivo_desconto']}")
    
    # Dados de endereço
    if row['endereco'] or row['cidade'] or row['cep']:
        st.markdown("### 📍 Endereço")
        endereco_completo = f"{row['endereco']}, {row['cidade']} - CEP: {row['cep']}"
        st.write(endereco_completo)
    
    # Parcelas
    st.markdown("### 💳 Parcelas")
    exibir_parcelas(row['json_parcelas'])


def run_page():
    st.title("🎓 Consulta de Matrículas - Central Backup")
    
    # Verifica se os arquivos existem
    anos_disponiveis = carregar_anos_disponiveis()
    
    if not anos_disponiveis:
        st.error("❌ Cache não encontrado!")
        st.info("Execute o script `utils/central_backup_generator.py` para gerar o cache.")
        return
    
    st.success(f"✅ Cache disponível: {len(anos_disponiveis)} anos ({min(anos_disponiveis)} - {max(anos_disponiveis)})")
    
    # Filtros de busca
    st.markdown("## 🔍 Filtros de Busca")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        tipo_busca = st.selectbox(
            "Tipo de Busca",
            ["Selecione...", "CPF", "Email", "Telefone", "Data", "Turma"]
        )
    
    df_filtrado = pd.DataFrame()
    
    if tipo_busca == "CPF":
        with col2:
            cpf_busca = st.text_input("Digite o CPF")
        if cpf_busca:
            with st.spinner("Buscando..."):
                df = carregar_todos_dados()
                df_filtrado = df[df['cpf'].astype(str).str.contains(cpf_busca, case=False, na=False)]
    
    elif tipo_busca == "Email":
        with col2:
            email_busca = st.text_input("Digite o Email")
        if email_busca:
            with st.spinner("Buscando..."):
                df = carregar_todos_dados()
                df_filtrado = df[df['email'].astype(str).str.contains(email_busca, case=False, na=False)]
    
    elif tipo_busca == "Telefone":
        with col2:
            telefone_busca = st.text_input("Digite o Telefone")
        if telefone_busca:
            with st.spinner("Buscando..."):
                df = carregar_todos_dados()
                df_filtrado = df[df['telefone'].astype(str).str.contains(telefone_busca, case=False, na=False)]
    
    elif tipo_busca == "Data":
        with col2:
            data_inicio = st.date_input("Data Início")
        with col3:
            data_fim = st.date_input("Data Fim")
        if data_inicio and data_fim:
            with st.spinner("Buscando..."):
                # Carrega apenas os anos necessários
                ano_inicio = data_inicio.year
                ano_fim = data_fim.year
                anos_necessarios = [ano for ano in anos_disponiveis if ano_inicio <= ano <= ano_fim]
                
                dfs = [carregar_dados_ano(ano) for ano in anos_necessarios]
                df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
                
                df_filtrado = df[
                    (df['data'] >= pd.to_datetime(data_inicio)) & 
                    (df['data'] <= pd.to_datetime(data_fim))
                ]
    
    elif tipo_busca == "Turma":
        with col2:
            df_todas = carregar_todos_dados()
            turmas_disponiveis = sorted(df_todas['turma'].dropna().unique())
            turma_selecionada = st.selectbox("Selecione a Turma", ["Todas"] + list(turmas_disponiveis))
        
        if turma_selecionada != "Todas":
            with st.spinner("Buscando..."):
                df_filtrado = df_todas[df_todas['turma'] == turma_selecionada]
    
    # Exibição dos resultados
    if tipo_busca != "Selecione...":
        st.markdown("---")
        st.markdown(f"## 📊 Resultados ({len(df_filtrado)} registros)")
        
        if df_filtrado.empty:
            st.warning("Nenhum registro encontrado com os filtros aplicados")
        else:
            # Todas as buscas agora exibem em formato de lista com expander
            for idx, row in df_filtrado.iterrows():
                # Formata valores para exibição
                valor_fmt = f"R$ {row['valor_pagamento']:,.2f}".replace(',', '_').replace('.', ',').replace('_', '.')
                data_fmt = row['data'].strftime('%d/%m/%Y') if pd.notna(row['data']) else 'N/A'
                
                # Título do expander com informações básicas
                titulo = f"📋 {row['matricula']} - {row['nome']} | 📅 {data_fmt} | 🏫 {row['turma']} | 💰 {valor_fmt} | 📊 {row['parcelas']}x | Status: {row['status']}"
                
                with st.expander(titulo):
                    exibir_detalhes_matricula(row)