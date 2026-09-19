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

## Reglas

- Validar límites de paginación.
- Usar códigos HTTP correctos.
- No devolver trazas internas al cliente.
- Mantener compatibilidad dentro de `/api/v1`.
- Documentar automáticamente el contrato mediante OpenAPI.

