# Requisitos

## Requisitos funcionales

| Código | Requisito | Criterio de aceptación |
|---|---|---|
| RF01 | Catálogo | Se pueden listar productos con paginación. |
| RF02 | Búsqueda | Se puede buscar por nombre y filtrar por categoría. |
| RF03 | Detalle | Se muestra información del producto y el último precio por tienda. |
| RF04 | Historial | Se obtiene una serie temporal filtrable por tienda y fechas. |
| RF05 | Extracción | Un worker actualiza precios desde al menos dos tiendas. |
| RF06 | Programación | EventBridge puede crear trabajos periódicos. |
| RF07 | Ejecución manual | Un operador autorizado puede publicar un trabajo y recibe HTTP 202. |
| RF08 | Fallos | Un trabajo que excede los reintentos se dirige a una DLQ. |

## Requisitos no funcionales

| Código | Atributo | Criterio |
|---|---|---|
| RNF01 | Desacoplamiento | El scraping no se ejecuta dentro del proceso de una petición web. |
| RNF02 | Escalabilidad | API y workers pueden aumentar sus réplicas independientemente. |
| RNF03 | Rendimiento | El catálogo usa paginación y el historial cuenta con índices apropiados. |
| RNF04 | Resiliencia | Los trabajos admiten reintentos, idempotencia y DLQ. |
| RNF05 | Seguridad | HTTPS en producción, secretos fuera del código y RDS en red privada. |
| RNF06 | Observabilidad | La API y los workers generan logs estructurados con identificadores de correlación. |
| RNF07 | Costo | El MVP utiliza recursos mínimos y límites de escalamiento. |

## Reglas de negocio

- Un producto puede aparecer en varias tiendas.
- Una tienda puede ofrecer varios productos.
- Cada observación debe tener precio positivo, moneda, URL y fecha de captura.
- Guardar dinero con tipo decimal; nunca usar `float`.
- Cuando una tienda diferencie el precio según la forma de pago (por ejemplo, efectivo/transferencia frente a recargo por tarjeta), se extrae únicamente el precio base (`base_price`, condición `cash_or_bank_transfer`). El recargo de tarjeta no se almacena como segunda observación. El frontend deberá mostrar "Precio en efectivo o transferencia" cuando la tienda publique esa condición.
- Los productos agotados (`out_of_stock`) o con disponibilidad indeterminada (`unknown`) se conservan para historial y auditoría, pero no compiten como mejor precio, se muestran como no disponibles y no cuentan como comparación activa.
- Los trabajos pueden entregarse más de una vez, por lo que el worker debe ser idempotente.
- Un error de una tienda no debe impedir procesar otras tiendas.
- El sistema no debe intentar evadir autenticación, CAPTCHA ni restricciones explícitas de los sitios externos.

## Criterios de aceptación del MVP

- El entorno local inicia con un solo comando documentado.
- La API expone documentación OpenAPI.
- El frontend puede listar, buscar y mostrar el historial de un producto.
- Existe al menos una prueba de integración para cada endpoint principal.
- Los workers procesan mensajes simulados antes de conectar servicios AWS reales.
- No hay secretos versionados.

