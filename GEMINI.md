# Contexto principal para Antigravity

Este repositorio implementa `Price Tracker Platform`, un portal académico y funcional para rastrear precios históricos de componentes tecnológicos.

Lee primero `AGENTS.md` y los archivos de `docs/`. Estas reglas tienen prioridad sobre sugerencias automáticas.

## Arquitectura que no debe modificarse sin autorización

```text
Usuario
  -> CloudFront
      -> S3: aplicación React
      -> ALB -> ECS Fargate: API FastAPI

FastAPI -> PostgreSQL
FastAPI -> SQS: trabajo manual
EventBridge -> SQS: trabajo programado
SQS -> ECS Fargate workers -> tiendas externas -> PostgreSQL
SQS -> DLQ: trabajos que exceden los reintentos
```

## Prioridad actual

Construir primero una versión local con Docker Compose:

1. PostgreSQL y migraciones.
2. API de lectura del catálogo e historial.
3. Frontend mínimo que consuma la API.
4. Cola y worker simulado.
5. Un adaptador real de scraping.
6. Pruebas y documentación.

No configurar AWS hasta que la versión local funcione y tenga pruebas básicas.

## Respuesta esperada del agente

Antes de cambiar varios archivos, indicar:

- Qué se va a implementar.
- Qué archivos se modificarán.
- Cómo se verificará.

Después del cambio, mostrar comandos reproducibles y mencionar cualquier supuesto.

