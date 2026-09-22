# Price Tracker Platform

Portal web para consultar el precio actual y el historial de precios de componentes tecnológicos en diferentes tiendas.

## Objetivo

Permitir que una persona busque un producto, consulte su evolución de precio y compare las tiendas disponibles. La extracción de precios debe ejecutarse de forma independiente de la API para que un fallo o retraso del scraping no interrumpa la navegación.

## Estado actual

- **Incrementos completados**:
  - Incremento 0: Preparación y entorno Docker Compose.
  - Incremento 1: Persistencia base y migraciones Alembic.
  - Incremento 2: API de lectura del catálogo e historial.
  - Incremento 3: Frontend mínimo en React con catálogo e historial.
  - Incremento 4: Procesamiento asíncrono local con colas en PostgreSQL.
  - Incremento 5: Adaptadores reales de scraping y canalizaciones de extracción.
  - Incremento 6: Módulo analítico de mercado y dashboard de tendencias.
  - Incremento 7: Supervisión, trazabilidad y control operativo del scraping:
    - **7A**: Persistencia y ciclo de vida de `ScrapingJob` (Commit `573107b`).
    - **7B**: Dispatcher local independiente y API operativa protegida (Commit `98fbd70`).
    - **7C**: Inspección sanitizada y replay transaccional de DLQ (Commit `0bce133`).
    - **7D**: Panel web `/operations` pospuesto por decisión de seguridad arquitectónica.
- **Operación administrativa provisional**: Exclusivamente local mediante Swagger UI (`/docs`) y endpoints REST protegidos con `INTERNAL_API_KEY`.
- **Regla de seguridad**: `/docs`, `/redoc` y `/openapi.json` permanecen restringidos de la exposición pública en producción.
- **Pruebas automatizadas**: 287 pruebas aprobadas (Backend: 104, Worker: 107, Frontend: 76).
- **Migración activa**: `007_dlq_audit_and_replay`.

## Estructura del Proyecto

```text
price-tracker-platform/
├── frontend/          # React con Vite y TypeScript
├── backend/           # API FastAPI, Pydantic y SQLAlchemy
├── worker/            # Workers de scraping asíncrono
├── database/          # Migraciones y scripts PostgreSQL
├── infrastructure/    # Docker y configuración de despliegue
├── docs/              # Documentación técnica y de arquitectura
├── AGENTS.md          # Instrucciones para agentes de IA
├── GEMINI.md          # Contexto y directrices de Antigravity
├── docker-compose.yml # Orquestación de servicios locales (PostgreSQL)
├── .env.example       # Plantilla de variables de entorno
└── README.md          # Este documento
```

## Tecnologías aprobadas

- **Frontend**: React con Vite y TypeScript.
- **Backend**: Python 3.11+, FastAPI, Pydantic y SQLAlchemy.
- **Base de datos**: PostgreSQL 16.
- **Worker / Scraping**: Python; `httpx` y BeautifulSoup (Playwright únicamente cuando se requiera JavaScript).
- **Desarrollo local**: Docker Compose.
- **Nube objetivo (Fases posteriores)**: AWS S3, CloudFront, ALB, ECS Fargate, SQS, EventBridge y RDS PostgreSQL.

## Documentación

- [Contexto del proyecto](docs/PROJECT_CONTEXT.md)
- [Requisitos](docs/REQUIREMENTS.md)
- [Arquitectura](docs/ARCHITECTURE.md)
- [Modelo de datos](docs/DATA_MODEL.md)
- [Contrato de API](docs/API_SPEC.md)
- [Plan de implementación](docs/IMPLEMENTATION_PLAN.md)
