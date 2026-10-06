# Spec Delta: Catalog and Deployment Readiness

## Purpose

Ensures the canonical hardware catalog, multi-store time-series chart visualization, and single-page application routing are fully validated and ready for edge production deployment.

## ADDED Requirements

### Requirement: Canonical Catalog Curation and Static Integrity
The backend canonical seed SHALL provide verified PC hardware catalog records and merchant associations with valid, authoritative image assets and store product URLs without reliance on placeholder data.

#### Scenario: Seed execution populates canonical products and store associations
- **WHEN** the canonical seed procedure is executed on an empty or existing database
- **THEN** the system ensures 32 canonical products and 44 store products are persisted idempotently with validated categories and active status

#### Scenario: Canonical images use authorized merchant CDNs
- **WHEN** catalog items and store associations are queried through the API
- **THEN** product image URLs point exclusively to validated merchant endpoints or null, without synthetic placeholder strings

### Requirement: Multi-Store Chart Observation Time Alignment
The frontend price chart component SHALL group and align price observations from multiple stores that occur on the same local calendar day to ensure consistent multi-series comparison without fragmented date intervals.

#### Scenario: Observations on the same calendar day align to a single time point
- **WHEN** a product has price observations recorded from two different stores at different minutes within the same local calendar date
- **THEN** the chart maps both prices to the identical calendar date tick on the horizontal axis and retains the latest observation per store

### Requirement: Single Page Application Client-Side Edge Rewriting
The web client distribution SHALL include configuration for edge hosting providers to rewrite non-static URL requests to the application entrypoint, enabling deep-linking and page refreshes on subroutes.

#### Scenario: Client-side routes rewrite to root index
- **WHEN** an edge hosting provider receives an HTTP GET request for a subroute such as `/analytics` or `/products/prod-uuid`
- **THEN** the edge server rewrites the request destination to `/index.html` with status 200 rather than returning a 404 response
