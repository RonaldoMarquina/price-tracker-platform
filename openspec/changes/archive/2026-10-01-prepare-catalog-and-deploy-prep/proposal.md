# Proposal: Prepare Curated Catalog and Deployment Readiness

## Why

To prepare Price Tracker Platform for public deployment behind Cloudflare (with Vercel and Render), the system requires a rock-solid, verified canonical catalog with clean store URLs and high-definition product images, chart time-alignment for accurate multi-store price comparisons, and SPA edge rewrites to eliminate HTTP 404 errors during client-side navigation.

## What Changes

- Consolidate the curated canonical catalog in `backend/app/db/seed.py` with 32 canonical components across 8 core categories and 44 verified store associations across 4 authorized stores.
- Update canonical product and store associations to reference validated image URLs from authorized merchant CDNs, replacing placeholders and broken endpoints.
- Align multi-store price observations captured at slightly different minutes on the same calendar day within `frontend/src/components/chart/PriceChart.tsx` to ensure smooth comparative line graphs.
- Add `frontend/vercel.json` SPA rewrite configuration (`/(.*)` -> `/index.html`) to support client-side routing for catalog, detail, and analytics routes.
- Verify that automated test suites for both backend and frontend pass completely before production deployment.

## Capabilities

### New Capabilities
- `catalog-and-deployment-readiness`: Defines the requirements for canonical product and store association curation, time-series chart alignment for concurrent observations, and SPA client routing fallbacks for edge hosting.

### Modified Capabilities
<!-- None: No existing specs exist in the repository inventory. -->

## Impact

- **Backend**: `backend/app/db/seed.py`, `backend/tests/test_seed_integrity.py`, `backend/tests/test_api_products.py`.
- **Frontend**: `frontend/src/components/chart/PriceChart.tsx`, `frontend/src/components/chart/PriceChart.test.tsx`, `frontend/vercel.json`.
- **Infrastructure / Hosting**: Edge routing compatibility with Vercel and Cloudflare CDN proxying.
