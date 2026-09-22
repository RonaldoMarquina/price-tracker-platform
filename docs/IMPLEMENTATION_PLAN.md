# Plan de implementación

Este plan describe incrementos de construcción. No autoriza al agente a ejecutar todos los pasos en una sola tarea.

## Incremento 0 Preparación

- Crear el monorepo y archivos de configuración.
- Configurar `.gitignore` y `.env.example`.
- Agregar Docker Compose con PostgreSQL.
- Definir comandos de formato, análisis y pruebas.

Resultado verificable: PostgreSQL inicia y los proyectos vacíos ejecutan sus pruebas base.

## Incremento 1 Persistencia

- Crear modelos SQLAlchemy.
- Configurar Alembic.
- Crear la migración inicial.
- Insertar datos mínimos de desarrollo.

Resultado verificable: la migración se aplica desde una base vacía.

## Incremento 2 API de lectura

- Implementar catálogo paginado.
- Implementar detalle del producto.
- Implementar historial de precios.
- Agregar pruebas de integración.

Resultado verificable: OpenAPI muestra los endpoints y las pruebas pasan.

## Incremento 3 Frontend mínimo

- Crear layout y rutas.
- Crear búsqueda y filtro.
- Crear página de detalle.
- Mostrar gráfico histórico.
- Manejar carga, vacío y error.

Resultado verificable: el usuario completa el flujo catálogo → detalle → historial.

## Incremento 4 Procesamiento asíncrono local

- Definir el esquema del mensaje.
- Implementar una abstracción de cola.
- Crear un consumidor local o simulado.
- Asegurar idempotencia.

Resultado verificable: un mensaje de prueba genera una observación sin duplicarla al repetirse.

## Incremento 5 Scraping

- Definir la interfaz `StoreAdapter`.
- Implementar un adaptador con HTML de prueba.
- Añadir una tienda real autorizada.
- Incorporar reintentos y límites de frecuencia.

Resultado verificable: el adaptador transforma una página en un resultado normalizado.

## Incremento 6 Analítica de mercado

- Implementar agregaciones analíticas de catálogo y tendencias de precios.
- Endpoints analíticos (`/overview`, `/price-trends`, `/price-drops`, `/filters`).
- Dashboard analítico responsive en frontend con KPIs, gráficos y filtros.

Resultado verificable: 4 módulos analíticos funcionales con 76 pruebas en frontend.

## Incremento 7 Supervisión, trazabilidad y control operativo del scraping

- **Subincremento 7A: Persistencia y ciclo de vida de `ScrapingJob`** (Commit `573107b`):
  - Modelo `ScrapingJob` con clave foránea restrictiva y máquina de estados: `queued`, `processing`, `retrying`, `completed`, `skipped`, `failed`, `dead_letter`.
  - Migración Alembic `005_create_scraping_jobs`.
  - Trazabilidad en `ScrapingConsumer`: actualización atómica de estados, `started_at`, `finished_at`, `attempts` y `observations_created`.
  - Idempotencia y recuperación de trabajos abandonados por timeout de visibilidad.

- **Subincremento 7B: Dispatcher independiente y API operativa** (Commit `98fbd70`):
  - Proceso `python -m app.dispatcher` independiente del worker y de la API web.
  - Exclusión mutua distribuida mediante PostgreSQL Advisory Lock (`pg_try_advisory_lock`).
  - Normalización determinista de ventana horaria `dispatch_slot` (ej. `2026-09-21T18:00:00Z`).
  - Constraint de coherencia `ck_scraping_jobs_dispatch_slot_coherence` y restricción única `(store_id, dispatch_slot)`.
  - Migración Alembic `006_dispatch_slot_trigger_type`.
  - Endpoints protegidos (`INTERNAL_API_KEY`): `GET /jobs`, `GET /jobs/{id}`, `GET /queue/metrics`, `POST /dispatch`.

- **Subincremento 7C: Inspección sanitizada y replay transaccional de DLQ** (Commit `0bce133`):
  - Migración Alembic `007_dlq_audit_and_replay`: campos `sent_to_dlq_at`, `replay_count`, `replayed_at`, `last_dlq_reason` e índices de consulta.
  - Endpoint `GET /api/v1/scraping/dlq`: paginado, ordenado, sanitizado (sin payload ni receipt_handle, error truncado a 500 caracteres, tokens y trazas redactados) y evaluación dinámica de `replayable`.
  - Endpoint `POST /api/v1/scraping/dlq/replay`: bloqueo SQL determinista `ORDER BY id ASC FOR UPDATE`, all-or-nothing rollback en try/except, reinicio atómico de contadores (`attempts = 0`, `payload["attempt"] = 1`, `job.status = 'queued'`).
  - Semántica acumulativa de `observations_created` e idempotencia vía `source_hash`.

- **Subincremento 7D: Panel web `/operations` en React — POSPUESTO**:
  - **Decisión de seguridad**: Se pospone formalmente la creación del panel visual web en el frontend público de Vite para evitar introducir sesiones provisionales con cookies HMAC, CSRF en memoria o riesgo de exposición de credenciales en el cliente.
  - **Operación administrativa provisional**: La supervisión y control operativo se gestiona exclusivamente en entorno local o red privada controlada mediante Swagger UI (`/docs`) y llamadas REST directas utilizando `INTERNAL_API_KEY`.
  - **Restricción de exposición**: Los endpoints `/docs`, `/redoc` y `/openapi.json` permanecen prohibidos de exposición pública en producción.
  - **Evolución futura**: La autenticación de operadores humanos se diseñará en AWS mediante Amazon Cognito, OIDC en ALB o red privada antes de habilitar un panel web visual.

Resultado verificable: 287 pruebas aprobadas (Backend: 104, Worker: 107, Frontend: 76), migración activa `007_dlq_audit_and_replay`.

## Incremento 8 Integración y Despliegue en AWS (Fase posterior)

- Configurar SQS y DLQ nativas en AWS.
- Configurar EventBridge para ejecución programada.
- Crear tareas ECS Fargate para API FastAPI, worker y dispatcher.
- Configurar RDS PostgreSQL, S3, CloudFront y Application Load Balancer (ALB).
- Autenticación administrativa segura (Cognito / OIDC) y métricas en CloudWatch.

## Orden para pedir tareas a la IA

Utilizar solicitudes pequeñas, por ejemplo:

1. “Crea únicamente la estructura del backend y una prueba de salud”.
2. “Agrega PostgreSQL y Alembic siguiendo `DATA_MODEL.md`”.
3. “Implementa `GET /api/v1/products` siguiendo `API_SPEC.md`”.
4. “Crea el catálogo de React consumiendo el endpoint existente”.

Evitar solicitudes como “construye toda la plataforma” porque dificultan revisar y corregir cada incremento.

