# Tareas: Automatización del Scraping Diario

## 1. Automatización con GitHub Actions y Cron Diario

- [x] 1.1 Crear el flujo `.github/workflows/daily-scraping.yml` configurado con cron diario (`0 11 * * *`) y activación manual (`workflow_dispatch`), incluyendo precalentamiento con `GET /health` y llamada autenticada a `POST /api/v1/scraping/dispatch`
- [x] 1.2 Validar la sintaxis y estructura del archivo YAML del workflow asegurando el manejo seguro de secretos (`API_BASE_URL` e `INTERNAL_API_KEY`)

## 2. Script de Despacho Local y Validación Operativa

- [x] 2.1 Crear el script ejecutable `scripts/trigger_daily_scraping.sh` para invocar el endpoint de scraping localmente o en remoto leyendo variables de entorno
- [x] 2.2 Probar la ejecución del script contra la API local de FastAPI y verificar la respuesta de despacho y métricas en `GET /api/v1/scraping/queue/metrics`
