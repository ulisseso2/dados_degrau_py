import streamlit as st
import os
import json
import ast

# Configuração da página (deve ser o primeiro comando Streamlit)
st.set_page_config(layout="wide", page_title="Dashboard Seducar")

# Importa os módulos de cada página da aplicação com tratamento de erro
try:
    from _pages import (
        oportunidades, financeiro, tendencias, cancelamentos, matriculas, 
        vendedores, madureira, madureira_cancelamento, campogrande, 
        campogrande_cancelamento, niteroi, niteroi_cancelamento, centro, 
        centro_cancelamento, analise_ga, analise_facebook, gads_face_combinado, 
        octadesk, custo_aula, analise_ga_central, analise_disciplinas, oportunidades_sp
    )
except ImportError as e:
    st.error(f"Erro ao importar módulos: {e}")
    st.info("Tentando importação individual...")
    
    # Importação individual com fallback
    import importlib
    import sys
    
    modules = [
        'oportunidades', 'financeiro', 'tendencias', 'cancelamentos', 'matriculas',
        'vendedores', 'madureira', 'madureira_cancelamento', 'campogrande',
        'campogrande_cancelamento', 'niteroi', 'niteroi_cancelamento', 'centro',
        'centro_cancelamento', 'analise_ga', 'analise_facebook', 'gads_face_combinado',
        'octadesk', 'custo_aula', 'analise_ga_central', 'analise_disciplinas', 'oportunidades_sp'
    ]
    
    for module_name in modules:
        try:
            module = importlib.import_module(f'_pages.{module_name}')
            globals()[module_name] = module
        except ImportError as module_error:
            st.warning(f"Não foi possível importar {module_name}: {module_error}")
            # Criar um módulo dummy para evitar erros
            class DummyModule:
                def run_page(self):
                    st.error(f"Módulo {module_name} não disponível")
            globals()[module_name] = DummyModule()
st.set_page_config(layout="wide", page_title="Dashboard Seducar")

# 1. MAPEAMENTO E AUTENTICAÇÃO

PAGES = {
    "Oportunidades": oportunidades,
    "Oportunidades SP": oportunidades_sp,
    "Tendências": tendencias,
    "Financeiro": financeiro,
    "Cancelamentos": cancelamentos,
    "Matriculas": matriculas,
    "Vendedores": vendedores,
    "Análise Combinada MKT":gads_face_combinado,
    "Análise GA Degrau": analise_ga,
    "Análise GA Central": analise_ga_central,
    "Análise Facebook": analise_facebook,
    "Análise Disciplinas": analise_disciplinas,
    "Previsão Custo Pedagógico": custo_aula,
    "Matriculas Madureira": madureira,
    "Cancelamentos Madureira": madureira_cancelamento,
    "Matriculas Campo Grande": campogrande,
    "Cancelamentos Campo Grande": campogrande_cancelamento,
    "Matriculas Niterói": niteroi,
    "Cancelamentos Niterói": niteroi_cancelamento,
    "Matriculas Centro": centro,
    "Cancelamentos Centro": centro_cancelamento,
    "Mensagens Octadesk": octadesk
}

def check_credentials(username, password):
    """
    Verifica as credenciais de forma híbrida, lidando com
    diferentes tipos de dados de 'pages'.
    """
    users_db = {}
    try:
        users_db = st.secrets["users"]
    except st.errors.StreamlitAPIException:
        users_json_str = os.getenv("LOCAL_USERS_DB")
        if users_json_str:
            users_db = json.loads(users_json_str)
        else:
            st.error("Credenciais de usuário locais não encontradas.")
            return False, None

    try:
        user_data = users_db.get(username.lower(), {})
        stored_password = user_data.get("password")
        
        if stored_password == password:
            pages_value = user_data.get("pages", [])
            
            # Se o valor for uma string (vem do st.secrets), converte para lista
            if isinstance(pages_value, str):
                allowed_pages = ast.literal_eval(pages_value)
            # Se já for uma lista (vem do .env/json), usa diretamente para ser possível o acesso local
            elif isinstance(pages_value, list):
                allowed_pages = pages_value
            # Caso contrário, fallback para uma lista vazia
            else:
                allowed_pages = []
                
            return True, allowed_pages
            
    except Exception as e:
        st.error(f"Erro ao processar credenciais: {e}")
        return False, None
        
    return False, None # Senha incorreta

# 2. LÓGICA DE INTERFACE (UI) E SESSÃO

# Inicializa o estado da sessão se ainda não existir
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False
    st.session_state['username'] = ''
    st.session_state['allowed_pages'] = []

def show_login_screen():
    """Mostra o formulário de login."""
    st.title("Login - Dashboard Seducar")
    with st.form("login_form"):
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar")

        if submitted:
            is_authenticated, allowed_pages = check_credentials(username, password)
            if is_authenticated:
                st.session_state['authenticated'] = True
                st.session_state['username'] = username
                st.session_state['allowed_pages'] = allowed_pages
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")

# --- Lógica Principal de Renderização ---
# Se o usuário NÃO estiver autenticado, mostra a tela de login
if not st.session_state['authenticated']:
    show_login_screen()

# Se ESTIVER autenticado, mostra o aplicativo completo
else:
    # --- Construção da Barra Lateral ---
    st.sidebar.title(f"Bem-vindo(a), {st.session_state['username'].capitalize()}!")
    if st.sidebar.button("Logout"):
        for key in st.session_state.keys():
            del st.session_state[key]
        st.rerun()
        
    st.sidebar.divider()
    st.sidebar.header("Navegação")

    allowed_pages_names = st.session_state['allowed_pages']

    if "all" in allowed_pages_names:
        pages_to_show = list(PAGES.keys())
    else:
        pages_to_show = [page for page in allowed_pages_names if page in PAGES]
    
    if pages_to_show:
        selected_page = st.sidebar.radio("Menu", pages_to_show)
        
        # --- Roteador que renderiza a página selecionada ---
        PAGES[selected_page].run_page()
    else:
        st.warning("Você não tem acesso a nenhuma página. Por favor, contate o administrador.")