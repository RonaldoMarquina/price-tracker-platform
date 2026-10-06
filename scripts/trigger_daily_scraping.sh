#!/usr/bin/env bash
# ==============================================================================
# Price Tracker Platform - Trigger Daily Scraping Script
# ==============================================================================
# Usage:
#   ./scripts/trigger_daily_scraping.sh [options]
#
# Options:
#   -u, --url <URL>    Base URL of the API (default: from .env or http://localhost:8000/api/v1)
#   -k, --key <KEY>    Internal API key (default: from .env)
#   -c, --check        Check health and queue metrics only, without dispatching
#   -h, --help         Show this help message
# ==============================================================================

set -euo pipefail

# ANSI Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Determine script directory and repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

API_URL="http://localhost:8000/api/v1"
API_KEY=""
CHECK_ONLY=false

# Safely extract variables from .env without executing/sourcing shell syntax
if [ -f "$REPO_ROOT/.env" ]; then
    while IFS='=' read -r key val || [ -n "$key" ]; do
        [[ "$key" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$key" ]] && continue
        key="$(echo "$key" | tr -d ' ')"
        val="${val%\"}"
        val="${val#\"}"
        val="${val%\'}"
        val="${val#\'}"
        if [ "$key" = "INTERNAL_API_KEY" ]; then
            API_KEY="$val"
        elif [ "$key" = "VITE_API_BASE_URL" ]; then
            API_URL="$val"
        fi
    done < "$REPO_ROOT/.env"
fi

# Override with environment variables if present
API_URL="${VITE_API_BASE_URL:-$API_URL}"
API_KEY="${INTERNAL_API_KEY:-$API_KEY}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -u|--url)
            API_URL="$2"
            shift 2
            ;;
        -k|--key)
            API_KEY="$2"
            shift 2
            ;;
        -c|--check)
            CHECK_ONLY=true
            shift
            ;;
        -h|--help)
            echo "Uso: $0 [opciones]"
            echo "  -u, --url <URL>    URL base de la API (ej: http://localhost:8000/api/v1)"
            echo "  -k, --key <KEY>    INTERNAL_API_KEY para autenticación de operador"
            echo "  -c, --check        Solo consulta salud y métricas de cola sin disparar"
            echo "  -h, --help         Muestra esta ayuda"
            exit 0
            ;;
        *)
            echo -e "${RED}Error: Opción desconocida: $1${NC}"
            exit 1
            ;;
    esac
done

# Strip trailing slash
API_URL="${API_URL%/}"

# Derive root URL for health check
ROOT_URL="${API_URL%/api/v1}"

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}  Price Tracker Platform - Operación de Scraping Diario${NC}"
echo -e "${BLUE}======================================================${NC}"
echo -e "API Base URL:  ${GREEN}$API_URL${NC}"

# 1. Health Check
echo -e "\n${YELLOW}[1/3] Verificando salud del backend...${NC}"
HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$ROOT_URL/health" || echo "000")

if [ "$HEALTH_STATUS" = "200" ]; then
    HEALTH_BODY=$(curl -s --max-time 10 "$ROOT_URL/health")
    echo -e "${GREEN}✓ Backend saludable (HTTP 200): $HEALTH_BODY${NC}"
else
    echo -e "${RED}✗ Error: Backend no responde en $ROOT_URL/health (HTTP $HEALTH_STATUS)${NC}"
    exit 1
fi

# 2. Queue Metrics Check
if [ -n "$API_KEY" ]; then
    echo -e "\n${YELLOW}[2/3] Consultando métricas de cola...${NC}"
    METRICS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
        -H "Authorization: Bearer $API_KEY" \
        -H "X-Internal-API-Key: $API_KEY" \
        "$API_URL/scraping/queue/metrics" || echo "000")
        
    if [ "$METRICS_STATUS" = "200" ]; then
        curl -s --max-time 10 \
            -H "Authorization: Bearer $API_KEY" \
            -H "X-Internal-API-Key: $API_KEY" \
            "$API_URL/scraping/queue/metrics" | jq . || true
    else
        echo -e "${YELLOW}! Métricas no disponibles o clave no autorizada (HTTP $METRICS_STATUS)${NC}"
    fi
fi

if [ "$CHECK_ONLY" = true ]; then
    echo -e "\n${GREEN}Modo check completado.${NC}"
    exit 0
fi

# 3. Trigger Scraping Dispatch
echo -e "\n${YELLOW}[3/3] Ejecutando disparo de scraping diario...${NC}"

if [ -z "$API_KEY" ]; then
    echo -e "${RED}✗ Error: INTERNAL_API_KEY es obligatorio para disparar el scraping.${NC}"
    exit 1
fi

DISPATCH_RESPONSE=$(mktemp)
HTTP_CODE=$(curl -s -w "%{http_code}" -o "$DISPATCH_RESPONSE" \
    -X POST "$API_URL/scraping/dispatch" \
    -H "Authorization: Bearer $API_KEY" \
    -H "X-Internal-API-Key: $API_KEY" \
    -H "Content-Type: application/json" \
    --max-time 60)

RESPONSE_CONTENT=$(cat "$DISPATCH_RESPONSE")
rm -f "$DISPATCH_RESPONSE"

if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
    echo -e "${GREEN}✓ Disparo ejecutado exitosamente (HTTP $HTTP_CODE):${NC}"
    echo "$RESPONSE_CONTENT" | jq . || echo "$RESPONSE_CONTENT"
elif [ "$HTTP_CODE" = "409" ]; then
    echo -e "${YELLOW}! Disparo omitido: otra instancia tiene el cerrojo o ya se ejecutó este slot (HTTP 409).${NC}"
    echo "$RESPONSE_CONTENT" | jq . || echo "$RESPONSE_CONTENT"
else
    echo -e "${RED}✗ Error al disparar scraping (HTTP $HTTP_CODE):${NC}"
    echo "$RESPONSE_CONTENT"
    exit 1
fi

echo -e "\n${GREEN}Operación finalizada.${NC}"
