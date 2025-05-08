import sys
import os
import io
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime
from utils.sql_loader import carregar_dados  # agora usamos a função com cache

st.title("Dashboard Financeiro")

# ✅ Carrega os dados com cache (1h por padrão, pode ajustar no sql_loader.py)
df = carregar_dados("consultas/contas_a_pagar/contas_a_pagar.sql")
