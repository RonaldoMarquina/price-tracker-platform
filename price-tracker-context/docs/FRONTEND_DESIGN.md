# Propuesta de Diseño Visual y Frontend (PriceTrack)

Documento de especificación de diseño visual, interfaz y arquitectura de componentes para el frontend de la plataforma **PriceTrack**, alineado estrictamente con los contratos de la API ([`docs/API_SPEC.md`](API_SPEC.md) y `/openapi.json`) y los requisitos del **Incremento 3 (Frontend mínimo)**.

---

## 1. Concepto y Filosofía Visual

El comparador de precios de componentes de PC adopta una estética **clean-tech**: moderna, limpia, de alta densidad informativa y con contraste optimizado para la lectura de precios y comparativas técnicas entre tiendas. La interfaz consume **exclusivamente la API REST** sin datos simulados en producción.

---

## 2. Sistema de Diseño (Design Tokens)

### 2.1. Paleta de Colores

| Token CSS | Valor HEX | Uso |
|---|---|---|
| `--color-bg` | `#F8FAFC` | Fondo principal de la aplicación (Slate 50) |
| `--color-surface` | `#FFFFFF` | Superficies de tarjetas, paneles, inputs y barras |
| `--color-primary` | `#2563EB` | Color principal (Blue 600), botones primarios y acentos |
| `--color-primary-hover` | `#1D4ED8` | Estado hover de botones y elementos interactivos |
| `--color-text-dark` | `#0F172A` | Títulos, encabezados, precios destacados y texto base |
| `--color-text-secondary`| `#64748B` | Marcas, etiquetas, placeholders y breadcrumbs |
| `--color-border` | `#E2E8F0` | Líneas divisorias, bordes de tarjetas y contenedores |
| `--color-price-down` | `#16A34A` | Mejor precio, caídas de precio y stock disponible |
| `--color-price-up` | `#DC2626` | Aumentos de precio, mensajes de error y falta de stock |

### 2.2. Tipografía
- **Familia principal**: `Inter`, `system-ui`, `sans-serif`.
- **Escala tipográfica**:
  - `Hero Display`: 32px / Bold (700)
  - `H1 (Títulos de página)`: 24px / SemiBold (600)
  - `H2 (Encabezados de sección)`: 20px / SemiBold (600)
  - `H3 (Nombre en tarjetas)`: 16px / Medium (500)
  - `Body`: 15px / Regular (400)
  - `Small (Badges y metadatos)`: 13px / Medium (500)
  - `Tiny (SKUs y referencias)`: 11px / Regular (400)

### 2.3. Espaciado, Sombras y Radios
- **Radio de esquinas**:
  - Elementos pequeños (botones, badges, inputs): `8px` (`rounded-md`).
  - Superficies grandes (tarjetas, contenedores): `12px` (`rounded-lg`).
- **Sombras**:
  - Reposo: `box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.07), 0 1px 2px -1px rgba(0, 0, 0, 0.05);`
  - Hover: `box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -4px rgba(0, 0, 0, 0.04); transform: translateY(-2px);`

---

## 3. Especificación de Vistas y Mapeo Estricto con la API

### 3.1. Página Principal (`/`)
- **Header Global**:
  - Logotipo interactivo `PriceTrack` con enlace al inicio.
  - Enlace de navegación a "Catálogo".
  *(Nota: Se excluye el indicador técnico "API en línea" ya que `/health` es de monitoreo operativo y no aporta valor al usuario final).*
- **Sección Hero**:
  - Título: *"Encuentra el mejor precio para tu próxima PC"*.
  - Subtítulo enfocado en comparar opciones y ahorro.
  - **Buscador Destacado**: Campo central amplio con icono de lupa que redirige a `/products?q=...`.
- **Accesos Rápidos por Categoría**:
  - Chips interactivos (`Procesadores`, `Tarjetas de Video`, `Memorias RAM`) para filtrar el catálogo en un clic.
- **Primeros Componentes del Catálogo**:
  - Grilla que consume los primeros resultados de `GET /api/v1/products?page=1&page_size=4` como muestra inicial.

---

### 3.2. Catálogo de Componentes (`/products`)
- **Barra Superior**:
  - Migas de pan: `Inicio > Catálogo`.
  - Contador de resultados según campo `total` de la respuesta: *"X productos encontrados"*.
  - Buscador en vivo con debounce de 350-400ms conectado al parámetro `q`.
- **Filtros por Categoría**:
  - Botones tipo píldora (`Todos`, `Procesadores`, `Tarjetas de Video`, `Memorias RAM`) conectados al parámetro `category`.
- **Grilla de Resultados**:
  - Cuadrícula responsive de tarjetas de productos.
- **Paginador Numérico**:
  - Botones `Anterior`, números de página (`1`, `2`, `3`...) y `Siguiente` sincronizados con `page` y `page_size`.

---

### 3.3. Anatomía de la Tarjeta de Producto (`ProductCard`)

Refleja **única y exclusivamente** los campos devueltos por `ProductListItemOut` en `GET /api/v1/products`:

```text
┌─────────────────────────────────────────────────────────┐
│ [ Badge: {category} ]                                   │
│                                                         │
│                   [ Imagen del Producto ]               │
│               (con fallback SVG si es null)             │
│                                                         │
├─────────────────────────────────────────────────────────┤
│ {brand} (si está presente)                              │
│ {name}                                                  │
│                                                         │
│ Desde                                                   │
│ {latest_price.currency} {latest_price.amount}           │
│ En {latest_price.store}                                 │
│ (o "Sin precio registrado" si latest_price es null)     │
│                                                         │
│ [ Botón: Ver historial → ]                              │
└─────────────────────────────────────────────────────────┘
```

*Ajuste obligatorio aplicado: Se omite cualquier fecha inventada de "actualizado hace X horas", dado que `ProductListItemOut` no provee timestamp en la lista.*

---

### 3.4. Página de Detalle (`/products/:id`)

Consume `GET /api/v1/products/{product_id}` y `GET /api/v1/products/{product_id}/price-history`:

1. **Ficha Principal**:
   - Miga de pan: `Inicio > Catálogo > {category.name} > {name}`.
   - Imagen del producto (o fallback).
   - Nombre (`name`), Marca (`brand`, si existe), Modelo (`model`, si existe).
   - Badge con el **Precio Más Bajo** entre las tiendas listadas.
2. **Tabla Comparativa de Tiendas (`stores`)**:
   - Columnas:
     - Tienda (`store_name`).
     - Disponibilidad (`availability`, si la tienda lo reporta).
     - Precio actual (`latest_price.currency` `latest_price.amount`).
     - Fecha de observación (`latest_price.captured_at` formateada en fecha local).
     - Enlace externo: Botón `"Ir a la tienda"` **se muestra únicamente si `product_url` es una URL válida**. Se abre con `target="_blank"` y `rel="noopener noreferrer"`.
3. **Gráfico Histórico de Precios**:
   - Implementado mediante **Recharts** consumiendo `series` de `/price-history`.
   - Una curva por tienda con color diferenciado.
   - Ejes: Fecha (`captured_at`) y Precio (`price`).
   - **Filtros de tiempo**: Botones de rango que calculan fechas y llaman a la API con sus parámetros reales:
     - Último mes: `?from={hace_30_días}&to={hoy}`
     - Últimos 3 meses: `?from={hace_90_días}&to={hoy}`
     - Todo: sin parámetros de fecha.
     - Selector opcional de tienda: `?store_id={uuid}`.

---

## 4. Estados Visuales del Sistema

1. **Estado de Carga (Skeletons)**:
   - Siluetas con gradiente animado (*shimmer effect*) del mismo tamaño que las tarjetas, filtros y gráficos finales.
   - Evita saltos acumulativos de diseño (*Cumulative Layout Shift - CLS*).
2. **Estado Sin Resultados (Empty State)**:
   - Icono `SearchX` de Lucide.
   - Mensaje: *"No se encontraron productos para los filtros seleccionados"*.
   - Botón `"Restablecer filtros"` para volver al catálogo inicial.
3. **Estado de Error con Reintento**:
   - Mensaje legible en español explicando la incidencia.
   - Botón `"Reintentar"` que reejecuta la llamada a la API.

---

## 5. Diseño Responsive (Puntos de Quiebre)

- **Móvil (`< 640px`)**:
  - Grilla de 1 columna para tarjetas.
  - Buscador al 100% de ancho y categorías en barra deslizante horizontal.
  - Gráfico a altura de 260px adaptado a pantallas compactas.
- **Tablet (`640px - 1024px`)**:
  - Grilla de 2 columnas de productos.
- **Escritorio (`> 1024px`)**:
  - Grilla de 3 o 4 columnas.
  - Detalle en 2 columnas principales con gráfico a 380px de alto.

---

## 6. Arquitectura de Componentes y Código (`frontend/src/`)

```text
frontend/src/
├── api/
│   ├── client.ts              # Fetch tipado leyendo VITE_API_BASE_URL (sin hardcodeo)
│   └── products.ts            # getProducts, getProductById, getPriceHistory
├── components/
│   ├── common/
│   │   ├── Navbar.tsx         # Encabezado (Logo + enlaces)
│   │   ├── Footer.tsx         # Pie de página
│   │   ├── Badge.tsx          # Badges de categoría y disponibilidad
│   │   ├── Skeleton.tsx       # Esqueletos de carga
│   │   ├── EmptyState.tsx     # Estado sin resultados
│   │   └── ErrorAlert.tsx     # Mensaje de error con botón de reintento
│   ├── product/
│   │   ├── ProductCard.tsx    # Tarjeta de producto conforme al esquema
│   │   ├── ProductGrid.tsx    # Cuadrícula responsive
│   │   └── StoreTable.tsx     # Comparativa de tiendas (valida product_url)
│   └── chart/
│       └── PriceChart.tsx     # Gráfico con Recharts conectado a from/to/store_id
├── features/
│   ├── SearchBar.tsx          # Buscador con debounce
│   ├── CategoryFilter.tsx     # Botones de categoría
│   └── Pagination.tsx         # Paginación numérica
├── pages/
│   ├── HomePage.tsx           # Vista principal
│   ├── CatalogPage.tsx        # Vista catálogo
│   └── ProductDetailPage.tsx  # Vista detalle
├── types/
│   └── api.ts                 # Tipos TypeScript reflejando OpenAPI
├── index.css                  # Variables CSS, Inter y estilos base
├── App.tsx                    # Enrutador cliente y layout general
└── main.tsx                   # Punto de montaje
```

---

## 7. Tecnologías y Dependencias Autorizadas

- **React 18.2.0** y **TypeScript 5**: Se conserva la versión instalada en el Incremento 0.
- **Variables de Entorno**: Acceso a la API mediante `import.meta.env.VITE_API_BASE_URL` (por defecto `http://localhost:8000/api/v1`), nunca localhost fijo en componentes.
- **Librerías autorizadas**:
  - `recharts`: Exclusivamente para el gráfico temporal de precios.
  - `lucide-react`: Iconos SVG ligeros.
- **Estilos**: Vanilla CSS con tokens y clases reutilizables (sin librerías completas de UI pesadas).

---

## 8. Estrategia de Pruebas (Vitest)

Pruebas automatizadas requeridas:
1. **Estado de Carga**: Verifica que los esqueletos se muestren mientras la petición está pendiente.
2. **Carga Exitosa**: Renderizado correcto de tarjetas y campos desde la API.
3. **Lista Vacía**: Renderizado del componente `EmptyState` cuando `total == 0`.
4. **Manejo de Errores**: Despliegue de `ErrorAlert` con botón funcional de reintento ante fallos HTTP.
5. **Búsqueda y Filtros**: Cambio de parámetros `q` y `category`.
6. **Navegación al Detalle**: Clic en una tarjeta lleva a la vista del producto correspondiente.
