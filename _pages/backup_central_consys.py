import sys
import os
import io
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pandas as pd
import streamlit as st
import json
import pickle
from datetime import datetime
from pathlib import Path
from utils.sql_loader import carregar_dados_secundario


# Caminho do cache
CACHE_DIR = Path(__file__).parent.parent / ".cache"
CACHE_FILE = CACHE_DIR / "central_backup.pkl"


def carregar_dados_central():
    """
    Carrega dados do banco Central com cache persistente em disco.
    Como os dados são estáticos, usa sempre o cache se existir.
    """
    # Cria diretório de cache se não existir
    CACHE_DIR.mkdir(exist_ok=True)
    
    # Verifica se existe cache
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'rb') as f:
                df = pickle.load(f)
                st.info(f"✅ Dados carregados do cache local ({len(df):,} registros)")
                return df
        except Exception as e:
            st.warning(f"⚠️ Erro ao ler cache, carregando do banco: {e}")
    
    # Se não tem cache ou deu erro, carrega do banco
    st.info("🔄 Carregando dados do banco (primeira vez)...")
    df = carregar_dados_secundario("consultas/consys/central_backup.sql")
    
    # Salva no cache
    if not df.empty:
        try:
            with open(CACHE_FILE, 'wb') as f:
                pickle.dump(df, f)
            st.success(f"💾 Cache criado com sucesso! ({len(df):,} registros)")
        except Exception as e:
            st.warning(f"⚠️ Não foi possível salvar cache: {e}")
    
    return df


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
    
    # Botão para atualizar cache apenas em ambiente local
    is_local = Path(__file__).parent.parent / ".env"
    if is_local.exists():
        col_titulo1, col_titulo2 = st.columns([4, 1])
        with col_titulo2:
            if st.button("🔄 Atualizar Cache"):
                if CACHE_FILE.exists():
                    CACHE_FILE.unlink()
                    st.success("Cache limpo! Recarregando...")
                    st.rerun()
    
    # Carrega dados com cache persistente
    df = carregar_dados_central()
    
    if df.empty:
        st.error("Não foi possível carregar os dados")
        return
    
    # Converte data para datetime se necessário
    if 'data' in df.columns and df['data'].dtype == 'object':
        df['data'] = pd.to_datetime(df['data'], errors='coerce')
    
    st.write(f"**Total de registros:** {len(df):,}")
    
    # Filtros de busca
    st.markdown("## 🔍 Filtros de Busca")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        tipo_busca = st.selectbox(
            "Tipo de Busca",
            ["Selecione...", "CPF", "Email", "Telefone", "Data", "Turma"]
        )
    
    df_filtrado = df.copy()
    
    if tipo_busca == "CPF":
        with col2:
            cpf_busca = st.text_input("Digite o CPF")
        if cpf_busca:
            df_filtrado = df_filtrado[df_filtrado['cpf'].astype(str).str.contains(cpf_busca, case=False, na=False)]
    
    elif tipo_busca == "Email":
        with col2:
            email_busca = st.text_input("Digite o Email")
        if email_busca:
            df_filtrado = df_filtrado[df_filtrado['email'].astype(str).str.contains(email_busca, case=False, na=False)]
    
    elif tipo_busca == "Telefone":
        with col2:
            telefone_busca = st.text_input("Digite o Telefone")
        if telefone_busca:
            df_filtrado = df_filtrado[df_filtrado['telefone'].astype(str).str.contains(telefone_busca, case=False, na=False)]
    
    elif tipo_busca == "Data":
        with col2:
            data_inicio = st.date_input("Data Início")
        with col3:
            data_fim = st.date_input("Data Fim")
        if data_inicio and data_fim:
            df_filtrado = df_filtrado[
                (df_filtrado['data'] >= pd.to_datetime(data_inicio)) & 
                (df_filtrado['data'] <= pd.to_datetime(data_fim))
            ]
    
    elif tipo_busca == "Turma":
        with col2:
            turmas_disponiveis = sorted(df['turma'].dropna().unique())
            turma_selecionada = st.selectbox("Selecione a Turma", ["Todas"] + list(turmas_disponiveis))
        
        if turma_selecionada != "Todas":
            df_filtrado = df_filtrado[df_filtrado['turma'] == turma_selecionada]
    
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