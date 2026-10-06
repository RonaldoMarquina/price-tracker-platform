# Design: Catalog and Deployment Readiness

## Context

The platform is transitioning from local containerized development to a production topology leveraging Vercel (Frontend), Render (FastAPI + PostgreSQL), and Cloudflare (DNS, SSL, CDN, WAF, AI Bot mitigation). Prior to deployment, catalog data integrity, chart rendering stability, and edge route rewrite rules must be cemented.

## Goals / Non-Goals

**Goals:**
- Provide 32 curated canonical hardware products across 8 categories with 44 verified store associations and real merchant images.
- Group asynchronous multi-store observations by local calendar day in `PriceChart.tsx` to provide seamless comparison in Recharts without time fragmentation.
- Provide declarative `vercel.json` rewrite routing for client-side React routes (`/`, `/products/:id`, `/analytics`).
- Maintain 100% green test suite across backend and frontend suites.

**Non-Goals:**
- Uncontrolled dynamic crawling or automated catalog entity creation (prices remain dynamic, catalog remains curated).
- Modifying database schemas or migrations (schema migration `007_dlq_audit_and_replay` / `009_store_product_image_url` remains standard).
- Executing actual cloud provisioning in this phase (scoped to Step 1 code preparation).

## Decisions

### Decision 1: Curated Canonical Catalog over Open Crawler
- **Rationale**: Retail stores (e.g. Memory Kings vs NECS) format product titles with incompatible naming conventions and punctuation. Without complex NLP/entity resolution, a web crawler creates duplicate product records, preventing multi-store price comparisons. A curated set of 32 products and 44 verified URLs guarantees high data fidelity, reliableRecharts visualizations, and predictable scraping runtimes under 1 minute.
- **Alternatives considered**:
  - *Autonomous discovery*: Scrapes full category pages and inserts discovered titles. Rejected due to high risk of merchant IP blocking, catalog clutter, and loss of canonical multi-store grouping.

### Decision 2: Calendar Day Bucket Normalization in PriceChart
- **Rationale**: Worker scrapers process stores asynchronously, resulting in observations stamped with minutes or hours of difference on the same day. Normalizing timestamps to `YYYY-MM-DD` buckets allows Recharts to align multiple store series onto identical X-axis coordinates, showing the latest recorded price per store for that day.
- **Alternatives considered**:
  - *Raw timestamp ticks*: Results in disjointed points where lines do not overlap visually.

### Decision 3: Standard Vercel Rewrites Configuration
- **Rationale**: Single Page Applications using React Router need all non-static asset routes redirected to `/index.html` to avoid 404 responses upon direct browser navigation or reload.
- **Alternatives considered**:
  - *Hash routing (`/#/analytics`)*: Avoided because it produces inferior URLs and impacts web standard navigation.

## Risks / Trade-offs

- **[Merchant image links become stale or 404]** → Handled: `ProductDetailPage.tsx` and catalog cards incorporate fallback `onError` event listeners rendering default category SVG icons.
- **[Strict production security settings on Render]** → Handled: Document and configure `INTERNAL_API_KEY` with >= 32 characters in Render environment dashboard.
