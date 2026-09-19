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

## Incremento 6 Integración AWS

- Configurar SQS y DLQ.
- Configurar EventBridge.
- Crear servicios ECS Fargate para API y workers.
- Configurar RDS, S3, CloudFront y ALB.
- Añadir métricas, logs y alertas de costo.

Resultado verificable: el despliegue reproduce el flujo probado localmente.

## Orden para pedir tareas a la IA

Utilizar solicitudes pequeñas, por ejemplo:

1. “Crea únicamente la estructura del backend y una prueba de salud”.
2. “Agrega PostgreSQL y Alembic siguiendo `DATA_MODEL.md`”.
3. “Implementa `GET /api/v1/products` siguiendo `API_SPEC.md`”.
4. “Crea el catálogo de React consumiendo el endpoint existente”.

Evitar solicitudes como “construye toda la plataforma” porque dificultan revisar y corregir cada incremento.

