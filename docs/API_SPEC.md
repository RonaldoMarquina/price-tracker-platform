# Contrato de API

Prefijo: `/api/v1`

Formato de intercambio: JSON.

## Listar productos

```http
GET /api/v1/products?q=ryzen&category=processors&page=1&page_size=20
```

Respuesta `200 OK`:

```json
{
  "items": [
    {
      "id": "uuid",
      "name": "AMD Ryzen 7 5800X",
      "brand": "AMD",
      "category": "Procesadores",
      "image_url": null,
      "latest_price": {
        "amount": "799.90",
        "currency": "PEN",
        "store": "Tienda ejemplo"
      }
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

## Obtener producto

```http
GET /api/v1/products/{product_id}
```

Respuestas: `200 OK` o `404 Not Found`.

## Obtener historial

```http
GET /api/v1/products/{product_id}/price-history?store_id={uuid}&from=2026-01-01&to=2026-09-19
```

Respuesta `200 OK`:

```json
{
  "product_id": "uuid",
  "series": [
    {
      "store_id": "uuid",
      "store_name": "Tienda ejemplo",
      "currency": "PEN",
      "points": [
        {"captured_at": "2026-09-19T10:00:00Z", "price": "799.90"}
      ]
    }
  ]
}
```

## Crear trabajo manual

```http
POST /api/v1/scraping/jobs
Authorization: Bearer {token-interno}
Content-Type: application/json

{
  "store_id": "uuid",
  "product_ids": ["uuid"]
}
```

Respuesta `202 Accepted`:

```json
{
  "job_id": "uuid",
  "status": "queued"
}
```

## Endpoints operativos y de supervisión (Incremento 7)

Todos los endpoints bajo `/api/v1/scraping/` (excepto los de lectura pública si existieran) exigen autenticación estricta:
`Authorization: Bearer <INTERNAL_API_KEY>` (401 si falta o es inválido).

### Listar trabajos de scraping
```http
GET /api/v1/scraping/jobs?page=1&page_size=20&status=completed&store_id={uuid}&from_date=2026-09-21T00:00:00Z&to_date=2026-09-21T23:59:59Z
```
Respuesta `200 OK` paginada con items, total, page, page_size y total_pages.

### Detalle de trabajo de scraping
```http
GET /api/v1/scraping/jobs/{job_id}
```
Respuesta `200 OK` con trazabilidad completa: estado, intentos, fechas (`created_at`, `started_at`, `finished_at`, `sent_to_dlq_at`), `observations_created`, `error_reason`, `last_dlq_reason` y `replay_count`. (404 si no existe).

### Métricas de colas y rendimiento
```http
GET /api/v1/scraping/queue/metrics?window_hours=24
```
Respuesta `200 OK` con conteos vivos de mensajes (`pending`, `processing`, `retrying`, `dlq`), desglose de trabajos por estado y tasa de éxito en la ventana.

### Disparo manual por lotes
```http
POST /api/v1/scraping/dispatch
Content-Type: application/json

{"store_id": "uuid"}  // Opcional; si se omite, despacha todas las tiendas activas
```
Respuesta `202 Accepted` con `jobs_created`, `job_ids`, `skipped_stores` y `failed_stores`. Protegido contra concurrencia distribuida vía PostgreSQL advisory lock (409 Conflict si ya hay otro despacho en ejecución).

### Inspección sanitizada de Dead Letter Queue (DLQ)
```http
GET /api/v1/scraping/dlq?page=1&page_size=20&store_id={uuid}&from_date={iso}&to_date={iso}
```
Respuesta `200 OK` con 13 campos canónicos por item (`message_id`, `job_id`, `store_id`, `store_name`, `products_count`, `attempts`, `error_reason`, `created_at`, `sent_to_dlq_at`, `replay_count`, `replayed_at`, `replayable`, `replay_block_reason`).
- `error_reason` truncado a 500 caracteres, saltos de línea eliminados, tokens y trazas redactados.
- Nunca expone `payload` ni `receipt_handle`.
- Payloads corruptos/antiguos reportan `job_id=null`, `products_count=0`, `replayable=false` y motivo sin causar error 500.

### Replay transaccional de mensajes DLQ
```http
POST /api/v1/scraping/dlq/replay
Content-Type: application/json

{"message_ids": ["uuid-1", "uuid-2"]}
```
Respuesta `202 Accepted` (`replayed_count`, `message_ids`, `job_ids`, `status: accepted`).
- Bloqueo determinista SQL `ORDER BY id ASC FOR UPDATE`.
- All-or-nothing: ante fallo de 1 mensaje (ej. estado no `dead_letter` o payload malformado), rollback total (409 Conflict).
- Reinicio atómico de intentos (`attempts = 0`, `payload.attempt = 1`, `job.status = 'queued'`) y conservación de observaciones acumuladas.

## Formato de error

```json
{
  "error": {
    "code": "PRODUCT_NOT_FOUND",
    "message": "El producto solicitado no existe.",
    "request_id": "uuid"
  }
}
```

## Reglas de seguridad y operación administrativa

- **Credencial M2M**: `INTERNAL_API_KEY` es una clave de comunicación máquina-a-máquina y para administración local controlada.
- **Prohibición en Frontend**: Nunca debe incrustarse en el bundle de Vite, ni en variables `VITE_*`, ni guardarse en `localStorage` o `sessionStorage`.
- **Entorno Productivo**: En despliegues públicos, la documentación interactiva (`/docs`, `/redoc`, `/openapi.json`) debe deshabilitarse o restringirse por red.
- **Auditoría Limpia**: Los secretos, contraseñas y encabezados Authorization nunca deben registrarse en logs, URLs ni respuestas de error.
- **Futura Autenticación**: En AWS, el acceso de operadores humanos se implementará con Amazon Cognito, OIDC en ALB o VPN privada antes de considerar cualquier panel web visual.

