import pandas as pd
import streamlit as st
from datetime import datetime
from utils.sql_loader import carregar_sql
from conexao.mysql_connector import conectar_mysql
import io
import re
import html
from pandas import ExcelWriter
import zipfile
import requests
import json


# Cache dedicado desta página: 60s (a query é pequena/leve e precisa de dados mais frescos).
# O carregar_dados global continua com TTL de 10 min para as demais análises.
@st.cache_data(ttl=60)
def carregar_dados_notas(caminho_sql):
    query = carregar_sql(caminho_sql)
    engine = conectar_mysql()
    if engine:
        try:
            return pd.read_sql(query, engine)
        except Exception as e:
            st.error(f"Erro ao executar a consulta: {e}")
            return pd.DataFrame()
    else:
        st.error("Erro ao conectar ao banco de dados.")
        return pd.DataFrame()


def run_page():

    st.title("Notas Fiscais - SP")

    # --- 1. DEFINIÇÃO DO FUSO HORÁRIO ---
    TIMEZONE = 'America/Sao_Paulo'

    # --- Funções Auxiliares ---
    def formatar_reais(valor):
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def slug(texto):
        return re.sub(r'[^A-Za-z0-9_-]', '_', str(texto or ''))

    # --- Carregamento e Preparação dos Dados ---
    df = carregar_dados_notas("consultas/notas/notas.sql")

    # Verificar se o DataFrame está vazio ou não tem as colunas necessárias
    if df.empty:
        st.warning("Nenhum dado encontrado na consulta.")
        st.stop()

    # Verificar se as colunas necessárias existem
    colunas_necessarias = ['data_emissao', 'valor_total_nota', 'tipo', 'empresa']
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

    # --- 2. FILTROS ---
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

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        empresas_disponiveis = sorted(df['empresa'].dropna().unique().tolist())
        empresa_sel = st.selectbox("Empresa", options=["Todas"] + empresas_disponiveis)
    with col_f2:
        tipos_disponiveis = sorted(df['tipo'].dropna().unique().tolist())
        tipo_sel = st.selectbox("Tipo da Nota", options=["Todos"] + tipos_disponiveis)

    # Filtrar dados pela data
    df_filtrado = df[
        (df['data_emissao'].dt.date >= data_inicio) &
        (df['data_emissao'].dt.date <= data_fim)
    ].copy()

    # Filtrar por empresa e tipo
    if empresa_sel != "Todas":
        df_filtrado = df_filtrado[df_filtrado['empresa'] == empresa_sel]
    if tipo_sel != "Todos":
        df_filtrado = df_filtrado[df_filtrado['tipo'] == tipo_sel]

    # --- 3. KPIs ---
    st.subheader("Resumo")
    valor_total = df_filtrado['valor_total_nota'].sum()

    col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
    with col_kpi1:
        st.metric("Valor Total de Notas Emitidas", formatar_reais(valor_total))
    with col_kpi2:
        st.metric("Quantidade de Notas", len(df_filtrado))
    with col_kpi3:
        qtd_produto = (df_filtrado['tipo'] == 'NFe').sum()
        qtd_servico = (df_filtrado['tipo'] == 'NFSe').sum()
        st.metric("NFe / NFSe", f"{qtd_produto} / {qtd_servico}")

    # Resumo por empresa e tipo
    if len(df_filtrado) > 0:
        resumo = (
            df_filtrado
            .groupby(['empresa', 'tipo'])
            .agg(Quantidade=('id', 'count'), Valor=('valor_total_nota', 'sum'))
            .reset_index()
        )
        resumo['Valor'] = resumo['Valor'].apply(formatar_reais)
        resumo = resumo.rename(columns={'empresa': 'Empresa', 'tipo': 'Tipo'})
        st.dataframe(resumo, use_container_width=True, hide_index=True)

    st.markdown("---")

    # --- 4. TABELA COM NOTAS ---
    st.subheader("Notas Fiscais Emitidas")

    if len(df_filtrado) == 0:
        st.warning("Nenhuma nota fiscal encontrada para os filtros selecionados.")
        return

    # Preparar dados para exibição
    df_display = df_filtrado.copy()
    df_display['data_emissao'] = df_display['data_emissao'].dt.strftime('%d/%m/%Y %H:%M')
    df_display['valor_formatado'] = df_display['valor_total_nota'].apply(formatar_reais)

    # Criar link para PDF (URL escapada para não quebrar o href — a URL da NFSe-SP tem vários "&")
    df_display['link_pdf'] = df_display['link_nota'].apply(
        lambda x: f'<a href="{html.escape(str(x), quote=True)}" target="_blank">📄 Ver PDF</a>'
        if pd.notna(x) and x else ''
    )

    # Selecionar e renomear colunas
    colunas_display = {
        'empresa': 'Empresa',
        'tipo': 'Tipo',
        'numero': 'Número',
        'data_emissao': 'Data Emissão',
        'xNome': 'Cliente',
        'cpf': 'CPF/CNPJ',
        'produtos': 'Produtos/Serviço',
        'valor_formatado': 'Valor Total',
        'link_pdf': 'PDF'
    }

    df_tabela = df_display[list(colunas_display.keys())].rename(columns=colunas_display)

    # Escapar HTML das colunas de texto (a coluna PDF já contém HTML intencional e seguro)
    for col in df_tabela.columns:
        if col != 'PDF':
            df_tabela[col] = df_tabela[col].apply(lambda v: html.escape(str(v)) if pd.notna(v) else '')

    # Adicionar linha de total
    linha_total = pd.DataFrame([{
        'Empresa': '',
        'Tipo': '',
        'Número': '',
        'Data Emissão': '',
        'Cliente': '',
        'CPF/CNPJ': '',
        'Produtos/Serviço': 'TOTAL',
        'Valor Total': formatar_reais(valor_total),
        'PDF': ''
    }])

    df_tabela_com_total = pd.concat([df_tabela, linha_total], ignore_index=True)

    # Exibir tabela com links HTML
    st.write(df_tabela_com_total.to_html(escape=False, index=False), unsafe_allow_html=True)

    st.markdown("---")

    # --- 5. DOWNLOADS ---
    # Botão de download Excel
    buffer = io.BytesIO()
    df_export = df_display[['empresa', 'tipo', 'numero', 'data_emissao', 'xNome', 'cpf', 'produtos', 'valor_formatado', 'link_nota']]
    df_export.columns = ['Empresa', 'Tipo', 'Número', 'Data Emissão', 'Cliente', 'CPF/CNPJ', 'Produtos/Serviço', 'Valor Total', 'Link PDF']
    with ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df_export.to_excel(writer, index=False, sheet_name='Notas Fiscais')

    st.download_button(
        label="📥 Baixar Excel",
        data=buffer.getvalue(),
        file_name=f"notas_fiscais_{data_inicio.strftime('%Y%m%d')}_{data_fim.strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.markdown("---")

    # --- 6. XML PARA CONTABILIDADE (ZIP separado por empresa) ---
    st.subheader("XMLs para Contabilidade")
    st.caption("Gera um arquivo ZIP separado por empresa, contendo os XMLs de NFe e NFSe do período/filtros selecionados.")

    def construir_zip(subset):
        """Monta o ZIP de XMLs (NFe via S3 + NFSe direto do banco) para um subconjunto de notas."""
        zip_buffer = io.BytesIO()
        contador = 0
        erros = []
        usados = set()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for _, row in subset.iterrows():
                numero = row.get('numero', '')
                tipo = row.get('tipo', '')
                try:
                    if tipo == 'NFe':
                        # XML da NFe está hospedado no S3 (resultado_json.xmlProcS3Url)
                        rj = row['resultado_json']
                        rj = json.loads(rj) if isinstance(rj, str) else rj
                        rj = rj or {}
                        xml_url = rj.get('xmlProcS3Url')
                        if not xml_url:
                            erros.append(f"NFe {numero}: URL do XML não encontrada")
                            continue
                        response = requests.get(xml_url, timeout=30)
                        if response.status_code != 200:
                            erros.append(f"NFe {numero}: Erro HTTP {response.status_code}")
                            continue
                        chave = row.get('chave_acesso') or rj.get('chaveAcesso') or f"nfe_{numero}_{row['id']}"
                        nome_arquivo = f"NFe/{slug(chave)}.xml"
                        conteudo = response.content
                    else:
                        # XML da NFSe já está guardado no banco (coluna xml_resposta)
                        xml_resp = row.get('xml_resposta')
                        if not xml_resp:
                            erros.append(f"NFSe {numero}: XML não disponível")
                            continue
                        if isinstance(xml_resp, bytes):
                            conteudo = xml_resp
                        else:
                            conteudo = str(xml_resp).encode('utf-8')
                        chave = row.get('chave_acesso') or f"{slug(numero)}_{row['id']}"
                        nome_arquivo = f"NFSe/nfse_{slug(chave)}.xml"

                    # Garantir nome único dentro do ZIP
                    base = nome_arquivo
                    n = 1
                    while nome_arquivo in usados:
                        nome_arquivo = base.replace('.xml', f'_{n}.xml')
                        n += 1
                    usados.add(nome_arquivo)

                    zip_file.writestr(nome_arquivo, conteudo)
                    contador += 1
                except Exception as e:
                    erros.append(f"{tipo} {numero}: {str(e)}")
                    continue

        zip_buffer.seek(0)
        return zip_buffer.getvalue(), contador, erros

    if st.button("📦 Preparar XMLs (ZIP por empresa)"):
        empresas = sorted(df_filtrado['empresa'].dropna().unique().tolist())
        with st.spinner("Baixando e compactando XMLs..."):
            for emp in empresas:
                subset = df_filtrado[df_filtrado['empresa'] == emp]
                dados_zip, contador, erros = construir_zip(subset)

                st.markdown(f"**{emp}** — {contador} de {len(subset)} XMLs")
                if contador > 0:
                    st.download_button(
                        label=f"⬇️ Baixar ZIP {emp} ({contador} XMLs)",
                        data=dados_zip,
                        file_name=f"xmls_{slug(emp).lower()}_{data_inicio.strftime('%Y%m%d')}_{data_fim.strftime('%Y%m%d')}.zip",
                        mime="application/zip",
                        key=f"download_zip_{slug(emp)}"
                    )
                else:
                    st.error(f"Nenhum XML foi adicionado ao ZIP de {emp}.")

                if erros:
                    with st.expander(f"Ver erros ({emp})"):
                        for erro in erros:
                            st.warning(erro)
