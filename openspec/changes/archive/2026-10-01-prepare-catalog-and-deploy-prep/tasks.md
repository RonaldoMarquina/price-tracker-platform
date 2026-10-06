# Tareas: Preparación del Catálogo y Listos para el Despliegue

## 1. Catálogo Canónico e Integridad del Backend

- [x] 1.1 Consolidar el catálogo de componentes en `backend/app/db/seed.py` (32 productos, 44 ofertas en tiendas, URLs reales de imágenes en CDN) y verificar conteos AST
- [x] 1.2 Ejecutar las pruebas del seed y de la API de productos (`pytest tests/test_seed_integrity.py tests/test_api_products.py`) y verificar que pasen al 100%

## 2. Alineación de Gráficos y Enrutamiento en el Frontend

- [x] 2.1 Consolidar la agrupación por día calendario en `frontend/src/components/chart/PriceChart.tsx` y verificar que las pruebas pasen con `PriceChart.test.tsx`
- [x] 2.2 Crear el archivo `frontend/vercel.json` con reglas de reescritura hacia `/index.html` para asegurar que las rutas SPA no den 404 en el servidor

## 3. Validación de Extremo a Extremo y Semilla Local

- [x] 3.1 Ejecutar la siembra canónica en la base de datos PostgreSQL local y verificar que los 32 productos aparezcan en `GET /api/v1/products`
- [x] 3.2 Ejecutar la suite completa de pruebas del frontend (`npm test`) y la compilación de producción (`npm run build`) para certificar que está listo para desplegar
