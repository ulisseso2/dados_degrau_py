import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder
from st_aggrid.shared import JsCode
from datetime import datetime
from utils.sql_loader import carregar_dados
import plotly.express as px
import io
from pandas import ExcelWriter
import zipfile
import requests
import json

def run_page():

    st.title("Notas Fiscais de Produtos - SP")

    # --- 1. DEFINIÇÃO DO FUSO HORÁRIO ---
    TIMEZONE = 'America/Sao_Paulo'

    # --- Função Auxiliar ---
    def formatar_reais(valor):
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    # --- Carregamento e Preparação dos Dados ---
    df = carregar_dados("consultas/notas/notas.sql")
    
    # Verificar se o DataFrame está vazio ou não tem as colunas necessárias
    if df.empty:
        st.warning("Nenhum dado encontrado na consulta.")
        st.stop()
    
    # Verificar se as colunas necessárias existem
    colunas_necessarias = ['data_emissao', 'valor_total_nota']
    colunas_faltantes = [col for col in colunas_necessarias if col not in df.columns]
    
    if colunas_faltantes:
        st.error(f"❌ Colunas faltantes no banco de dados: {', '.join(colunas_faltantes)}")
        st.info("Colunas disponíveis: " + ", ".join(df.columns.tolist()))
        st.stop()
    
    # Converter data_emissao
    df['data_emissao'] = pd.to_datetime(df['data_emissao'], errors='coerce')
    
    # Remover linhas com data inválida
    df = df.dropna(subset=['data_emissao'])
    
    if df.empty:
        st.warning("Nenhuma nota com data válida encontrada.")
        st.stop()
    
    df['data_emissao'] = df['data_emissao'].dt.tz_localize('UTC').dt.tz_convert(TIMEZONE)
    
    # Converter valor_total_nota para numérico
    df['valor_total_nota'] = pd.to_numeric(df['valor_total_nota'], errors='coerce').fillna(0)
    
    # --- 2. FILTRO DE DATA (MÊS ATUAL) ---
    st.subheader("Filtros")
    
    # Obter primeiro e último dia do mês atual
    hoje = datetime.now()
    primeiro_dia = datetime(hoje.year, hoje.month, 1)
    # Último dia do mês
    if hoje.month == 12:
        ultimo_dia = datetime(hoje.year, 12, 31)
    else:
        ultimo_dia = datetime(hoje.year, hoje.month + 1, 1) - pd.Timedelta(days=1)
    
    col1, col2 = st.columns(2)
    with col1:
        data_inicio = st.date_input("Data Inicial", value=primeiro_dia, format="DD/MM/YYYY")
    with col2:
        data_fim = st.date_input("Data Final", value=ultimo_dia, format="DD/MM/YYYY")
    
    # Filtrar dados pela data
    df_filtrado = df[
        (df['data_emissao'].dt.date >= data_inicio) & 
        (df['data_emissao'].dt.date <= data_fim)
    ].copy()
    
    # --- 3. KPI - VALOR TOTAL ---
    st.subheader("Resumo")
    valor_total = df_filtrado['valor_total_nota'].sum()
    
    col_kpi1, col_kpi2 = st.columns(2)
    with col_kpi1:
        st.metric("Valor Total de Notas Emitidas", formatar_reais(valor_total))
    with col_kpi2:
        st.metric("Quantidade de Notas", len(df_filtrado))
    
    st.markdown("---")
    
    # --- 4. TABELA COM NOTAS ---
    st.subheader("Notas Fiscais Emitidas")
    
    if len(df_filtrado) > 0:
        # Preparar dados para exibição
        df_display = df_filtrado.copy()
        df_display['data_emissao'] = df_display['data_emissao'].dt.strftime('%d/%m/%Y %H:%M')
        df_display['valor_formatado'] = df_display['valor_total_nota'].apply(formatar_reais)
        
        # Criar link para PDF
        df_display['link_pdf'] = df_display['link_nota'].apply(
            lambda x: f'<a href="{x}" target="_blank">📄 Ver PDF</a>' if pd.notna(x) and x else ''
        )
        
        # Selecionar e renomear colunas
        colunas_display = {
            'numero': 'Número NF',
            'data_emissao': 'Data Emissão',
            'xNome': 'Cliente',
            'cpf': 'CPF',
            'produtos': 'Produtos',
            'valor_formatado': 'Valor Total',
            'link_pdf': 'PDF'
        }
        
        df_tabela = df_display[list(colunas_display.keys())].rename(columns=colunas_display)
        
        # Adicionar linha de total
        linha_total = pd.DataFrame([{
            'Número NF': '',
            'Data Emissão': '',
            'Cliente': '',
            'CPF': '',
            'Produtos': 'TOTAL',
            'Valor Total': formatar_reais(valor_total),
            'PDF': ''
        }])
        
        df_tabela_com_total = pd.concat([df_tabela, linha_total], ignore_index=True)
        
        # Exibir tabela com links HTML
        st.write(df_tabela_com_total.to_html(escape=False, index=False), unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Botões de download
        col_download1, col_download2 = st.columns(2)
        
        with col_download1:
            # Botão de download Excel
            buffer = io.BytesIO()
            df_export = df_display[['numero', 'data_emissao', 'xNome', 'cpf', 'produtos', 'valor_formatado', 'link_nota']]
            df_export.columns = ['Número NF', 'Data Emissão', 'Cliente', 'CPF', 'Produtos', 'Valor Total', 'Link PDF']
            with ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_export.to_excel(writer, index=False, sheet_name='Notas Fiscais')
            
            st.download_button(
                label="📥 Baixar Excel",
                data=buffer.getvalue(),
                file_name=f"notas_fiscais_{data_inicio.strftime('%Y%m%d')}_{data_fim.strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        with col_download2:
            # Botão para baixar XMLs em ZIP
            if st.button("📦 Baixar XMLs (ZIP para Contabilidade)"):
                with st.spinner("Preparando XMLs..."):
                    try:
                        zip_buffer = io.BytesIO()
                        contador = 0
                        erros = []
                        
                        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                            for idx, row in df_filtrado.iterrows():
                                try:
                                    # Extrair URL do XML do campo resultado_json
                                    resultado_json = json.loads(row['resultado_json']) if isinstance(row['resultado_json'], str) else row['resultado_json']
                                    xml_url = resultado_json.get('xmlProcS3Url')
                                    
                                    if not xml_url:
                                        erros.append(f"Nota {row['numero']}: URL do XML não encontrada")
                                        continue
                                    
                                    # Baixar XML
                                    response = requests.get(xml_url, timeout=30)
                                    if response.status_code == 200:
                                        # Nome do arquivo: chave_acesso.xml
                                        chave = row.get('chave_acesso', resultado_json.get('chaveAcesso', ''))
                                        if chave:
                                            xml_filename = f"{chave}.xml"
                                            zip_file.writestr(xml_filename, response.content)
                                            contador += 1
                                        else:
                                            erros.append(f"Nota {row['numero']}: Chave de acesso não encontrada")
                                    else:
                                        erros.append(f"Nota {row['numero']}: Erro HTTP {response.status_code}")
                                except Exception as e:
                                    erros.append(f"Nota {row['numero']}: {str(e)}")
                                    continue
                        
                        zip_buffer.seek(0)
                        
                        if contador > 0:
                            st.download_button(
                                label=f"✅ Download ZIP Pronto ({contador} XMLs)",
                                data=zip_buffer.getvalue(),
                                file_name=f"xmls_notas_fiscais_{data_inicio.strftime('%Y%m%d')}_{data_fim.strftime('%Y%m%d')}.zip",
                                mime="application/zip",
                                key="download_zip"
                            )
                            st.success(f"ZIP criado com {contador} de {len(df_filtrado)} XMLs.")
                        else:
                            st.error("Nenhum XML foi adicionado ao ZIP.")
                        
                        if erros:
                            with st.expander("Ver erros"):
                                for erro in erros:
                                    st.warning(erro)
                    except Exception as e:
                        st.error(f"Erro ao criar ZIP: {str(e)}")
    else:
        st.warning("Nenhuma nota fiscal encontrada no período selecionado.")