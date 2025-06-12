import streamlit as st
from _pages import oportunidades, financeiro, tendencias , cancelamentos, matriculas
# =====================================================================
# 1. CONFIGURAÇÃO DE ACESSO
#    - Mapeia emails a uma lista de páginas permitidas.
#    - Use ["all"] para dar acesso a todas as páginas.
# =====================================================================
ACCESS_CONTROL = {
    # 🚨 IMPORTANTE: Coloque seu email aqui para testar localmente
    "ulissesrce@gmail.com": ["all"],
    "igor.velazquez@degraucultural.com.br": ["all"],
    "eduardo.lopes@degraucultural.com.br": ["all"],
    # --- Exemplos de outros perfis ---
    "ulisses@maisquestoes.com.br": ["Oportunidades", "Matrículas", "Tendencias"],
    "andrea.zanardi@degraucultural.com.br": ["Oportunidades", "Cancelamentos", "Tendencias", "Matriculas"],
}

# =====================================================================
# 2. MAPEAMENTO DAS PÁGINAS
#    - Mapeia o nome amigável da página ao caminho real do arquivo.
# =====================================================================
PAGES = {
    "Oportunidades": oportunidades,
    "Tendencias": tendencias,
    "Financeiro": financeiro,
    "Cancelamentos": cancelamentos,
    "Matriculas": matriculas,
}

# --- Função para obter o email do usuário ---
def get_user_email():
    """
    Retorna o email do usuário logado de forma segura.
    Se não estiver em produção ou o usuário não estiver logado,
    retorna um email de teste.
    """
    # hasattr() checa de forma segura se o atributo 'user' existe em 'st'
    if hasattr(st, 'user'):
        # Se existir, verificamos se o email não é nulo
        if st.user and st.user.email:
            return st.user.email
    
    # Se qualquer uma das checagens acima falhar, estamos em modo local
    # ou o usuário não está logado. Retornamos o email de teste.
    return list(ACCESS_CONTROL.keys())[0]

# =====================================================================
# LÓGICA PRINCIPAL DO APP
# =====================================================================
st.set_page_config(layout="wide", page_title="Dashboard Seducar")

user_email = get_user_email()
allowed_pages_names = ACCESS_CONTROL.get(user_email)

if not allowed_pages_names:
    st.error("🚫 Acesso Negado.")
    st.stop()

# --- Construção da Barra Lateral com st.radio ---
st.sidebar.title("Bem-vindo(a)!")
st.sidebar.write(f"{user_email}")
st.sidebar.divider()

# Cria a lista de páginas permitidas para o usuário
if "all" in allowed_pages_names:
    pages_to_show = list(PAGES.keys())
else:
    pages_to_show = [page for page in allowed_pages_names if page in PAGES]

# O st.radio funciona como nosso menu de navegação
selected_page = st.sidebar.radio("Navegação", pages_to_show)


# --- Roteador: Executa a página selecionada ---
if selected_page:
    # Chama a função run_page() do módulo correspondente
    PAGES[selected_page].run_page()
else:
    st.title("📊 Bem-vindo ao Dashboard Seducar")
    st.markdown("Utilize o menu na barra lateral para navegar.")