# Price Tracker Platform

Portal web para consultar el precio actual y el historial de precios de componentes tecnológicos en diferentes tiendas.

## Objetivo

Permitir que una persona busque un producto, consulte su evolución de precio y compare las tiendas disponibles. La extracción de precios debe ejecutarse de forma independiente de la API para que un fallo o retraso del scraping no interrumpa la navegación.

## Estado actual

Incremento 0 (Preparación) e Incremento 1 (Persistencia y modelos SQLAlchemy con Alembic) completados y verificados.

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
