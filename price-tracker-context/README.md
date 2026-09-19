# Price Tracker Platform

Portal web para consultar el precio actual y el historial de precios de componentes tecnológicos en diferentes tiendas.

## Objetivo

Permitir que una persona busque un producto, consulte su evolución de precio y compare las tiendas disponibles. La extracción de precios debe ejecutarse de forma independiente de la API para que un fallo o retraso del scraping no interrumpa la navegación.

## Estado actual

El proyecto se encuentra al inicio de la construcción. Las fases de planificación y diseño ya fueron definidas. La implementación debe realizarse por incrementos pequeños y verificables.

## Estructura prevista

```text
price-tracker-platform/
├── frontend/          # React
├── backend/           # FastAPI
├── worker/            # Workers de scraping
├── database/          # Migraciones y scripts PostgreSQL
├── infrastructure/    # Docker y configuración de despliegue
├── docs/              # Documentación del proyecto
├── AGENTS.md
├── GEMINI.md
├── docker-compose.yml
├── .env.example
└── README.md
```

## Tecnologías aprobadas

- Frontend: React con Vite y TypeScript.
- Backend: Python, FastAPI, Pydantic y SQLAlchemy.
- Base de datos: PostgreSQL.
- Scraping: Python; usar `httpx` y BeautifulSoup cuando sea suficiente. Usar Playwright solamente cuando el sitio requiera JavaScript.
- Desarrollo local: Docker Compose.
- Nube objetivo: AWS S3, CloudFront, ALB, ECS Fargate, SQS, EventBridge y RDS PostgreSQL.

## Documentación

- [Contexto del proyecto](docs/PROJECT_CONTEXT.md)
- [Requisitos](docs/REQUIREMENTS.md)
- [Arquitectura](docs/ARCHITECTURE.md)
- [Modelo de datos](docs/DATA_MODEL.md)
- [Contrato de API](docs/API_SPEC.md)
- [Plan de implementación](docs/IMPLEMENTATION_PLAN.md)

