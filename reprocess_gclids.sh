#!/bin/bash

# Script para facilitar o reprocessamento de GCLIDs
# Uso: ./reprocess_gclids.sh [opcoes]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/reprocess_gclids.py"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Função para mostrar ajuda
show_help() {
    echo -e "${GREEN}🔄 Script de Reprocessamento de GCLIDs${NC}"
    echo ""
    echo "Uso:"
    echo "  $0 count              - Mostra quantos GCLIDs não foram encontrados"
    echo "  $0 period [dias]      - Reprocessa GCLIDs dos últimos N dias (padrão: 30)"
    echo "  $0 all                - Reprocessa TODOS os GCLIDs não encontrados"
    echo ""
    echo "Exemplos:"
    echo "  $0 count"
    echo "  $0 period 7"
    echo "  $0 period 30"
    echo "  $0 all"
    echo ""
}

# Verifica se o Python está disponível
check_python() {
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}❌ Python3 não encontrado. Por favor, instale o Python3.${NC}"
        exit 1
    fi
}

# Verifica se o script Python existe
check_script() {
    if [ ! -f "$PYTHON_SCRIPT" ]; then
        echo -e "${RED}❌ Script Python não encontrado: $PYTHON_SCRIPT${NC}"
        exit 1
    fi
}

# Função principal
main() {
    check_python
    check_script
    
    case "$1" in
        "count")
            echo -e "${YELLOW}📊 Contando GCLIDs não encontrados...${NC}"
            python3 "$PYTHON_SCRIPT" --count
            ;;
        "period")
            DAYS=${2:-30}
            echo -e "${YELLOW}🔄 Reprocessando GCLIDs dos últimos $DAYS dias...${NC}"
            python3 "$PYTHON_SCRIPT" --period "$DAYS"
            ;;
        "all")
            echo -e "${YELLOW}🔄 Reprocessando TODOS os GCLIDs não encontrados...${NC}"
            echo -e "${RED}⚠️  ATENÇÃO: Isso pode demorar muito tempo!${NC}"
            read -p "Continuar? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                python3 "$PYTHON_SCRIPT" --all
            else
                echo "Operação cancelada."
            fi
            ;;
        "help"|"-h"|"--help"|"")
            show_help
            ;;
        *)
            echo -e "${RED}❌ Opção inválida: $1${NC}"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

main "$@"