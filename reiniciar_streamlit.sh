#!/bin/bash

echo "🔄 Reiniciando aplicação Streamlit..."
echo ""

# Procura processos do Streamlit
PIDS=$(pgrep -f "streamlit run")

if [ -z "$PIDS" ]; then
    echo "ℹ️  Nenhum processo Streamlit encontrado em execução."
    echo ""
    echo "Para iniciar o Streamlit, execute:"
    echo "  streamlit run main.py"
else
    echo "🛑 Encerrando processos Streamlit existentes..."
    echo "   PIDs: $PIDS"
    
    # Encerra os processos
    kill $PIDS 2>/dev/null
    
    # Aguarda um momento
    sleep 2
    
    # Verifica se ainda existem processos
    REMAINING=$(pgrep -f "streamlit run")
    if [ -n "$REMAINING" ]; then
        echo "⚠️  Alguns processos ainda estão ativos. Forçando encerramento..."
        kill -9 $REMAINING 2>/dev/null
    fi
    
    echo "✅ Processos encerrados com sucesso!"
    echo ""
    echo "Para iniciar o Streamlit novamente, execute:"
    echo "  streamlit run main.py"
fi

echo ""
echo "💡 Dica: O novo token do Facebook foi carregado."
echo "   A aplicação agora usará o token válido até 17/01/2026."
