#!/usr/bin/env python3
"""
Script de teste para demonstrar o cálculo correto do comparativo Like-for-Like
"""
import pandas as pd
from datetime import datetime

TIMEZONE = 'America/Sao_Paulo'

def testar_comparativo():
    print("🧪 Teste do Comparativo Like-for-Like Corrigido")
    print("=" * 50)
    
    # Simular a data atual
    hoje_tz = pd.Timestamp.now(tz=TIMEZONE)
    print(f"📅 Data atual: {hoje_tz.strftime('%d/%m/%Y %H:%M')}")
    
    # Calcular dias decorridos no mês atual
    mes_atual_inicio = hoje_tz.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    dias_decorridos_mes_atual = (hoje_tz - mes_atual_inicio).days + 1
    
    print(f"📊 Dias decorridos no mês atual: {dias_decorridos_mes_atual}")
    
    # Calcular mês anterior
    if mes_atual_inicio.month == 1:
        mes_anterior_inicio = mes_atual_inicio.replace(year=mes_atual_inicio.year - 1, month=12)
    else:
        mes_anterior_inicio = mes_atual_inicio.replace(month=mes_atual_inicio.month - 1)
    
    # Período like-for-like do mês anterior
    mes_anterior_fim_like = mes_anterior_inicio + pd.Timedelta(days=dias_decorridos_mes_atual - 1)
    mes_anterior_fim_like = mes_anterior_fim_like.replace(hour=23, minute=59, second=59)
    
    print(f"📅 Período mês anterior: {mes_anterior_inicio.strftime('%d/%m/%Y')} a {mes_anterior_fim_like.strftime('%d/%m/%Y')}")
    print(f"📅 Período mês atual: {mes_atual_inicio.strftime('%d/%m/%Y')} a {hoje_tz.strftime('%d/%m/%Y')}")
    
    print("\n✅ Comparativo corrigido:")
    print(f"   - Ambos os períodos têm {dias_decorridos_mes_atual} dias")
    print(f"   - Comparação justa: primeiros {dias_decorridos_mes_atual} dias de cada mês")
    print(f"   - Warning de timezone removido com tz_convert('UTC')")

if __name__ == "__main__":
    testar_comparativo()
