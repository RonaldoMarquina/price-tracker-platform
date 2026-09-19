# Contexto del proyecto

## Problema

Los precios de componentes tecnológicos cambian por la oferta, la demanda, el tipo de cambio y los costos de importación. Las tiendas muestran el precio actual, pero el comprador no dispone fácilmente de un historial consolidado para reconocer tendencias y comparar opciones.

## Solución

Una aplicación web que centraliza productos, tiendas y observaciones de precio. El usuario puede buscar productos, abrir un detalle y visualizar una serie histórica por tienda.

## Decisión principal

La navegación y el scraping son cargas diferentes. La API atiende consultas rápidas; los workers ejecutan extracciones lentas de manera asíncrona. Amazon SQS desacopla ambos procesos y absorbe picos de trabajos pendientes.

## Usuarios

### Visitante

- Busca componentes.
- Filtra por categoría.
- Consulta el precio más reciente.
- Visualiza el historial por tienda.
- Abre el enlace original del producto.

### Operador interno

- Puede solicitar una actualización manual de precios mediante un endpoint protegido.
- Revisa registros y trabajos fallidos.

No se requiere registro público de usuarios durante el MVP.

## Alcance del MVP

- Catálogo de componentes tecnológicos.
- Búsqueda por nombre y filtro por categoría.
- Detalle del producto.
- Historial de precios por tienda y rango de fechas.
- Extracción programada desde al menos dos tiendas.
- Reintentos controlados y cola de mensajes fallidos.

## Fuera de alcance

- Marketplace o venta directa.
- Pagos.
- Aplicación móvil nativa.
- Recomendaciones con inteligencia artificial.
- Alertas personales de precio.
- Panel administrativo completo.
- Kubernetes, Redis y arquitectura multirregión durante el MVP.

## Glosario

- **Producto:** componente tecnológico incluido en el catálogo.
- **Tienda:** comercio electrónico del que se obtiene un precio público.
- **Observación de precio:** precio capturado para un producto y una tienda en una fecha determinada.
- **Trabajo de scraping:** mensaje que solicita extraer uno o varios precios.
- **Worker:** proceso que consume trabajos de la cola y ejecuta la extracción.
- **DLQ:** cola que conserva trabajos que excedieron el máximo de reintentos.

