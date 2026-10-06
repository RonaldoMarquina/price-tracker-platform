# Proposal: Automate Daily Scraping Dispatch

## Why

Currently, triggering scraping requires either running a persistent local dispatcher service or manually issuing HTTP requests to the protected `POST /api/v1/scraping/dispatch` endpoint. In cloud deployments (especially on zero-cost tiers like Render and Vercel), maintaining a continuously running daemon is cost-prohibitive and prone to idle timeouts. A scheduled automated daily dispatch is needed to trigger scraping runs once per day reliably and without recurring infrastructure expense.

## What Changes

- Implement a GitHub Actions workflow (`.github/workflows/daily-scraping.yml`) scheduled via standard cron (e.g. daily at 11:00 UTC / 6:00 AM PET) with manual execution trigger (`workflow_dispatch`).
- Configure secure secret ingestion for `API_BASE_URL` and `INTERNAL_API_KEY` to authenticate against the protected scraping dispatch API.
- Provide a CLI dispatch script (`scripts/trigger_daily_scraping.py` or bash script) for local testing and manual operator triggers.
- Validate that daily scraping runs execute idempotently, respecting advisory locks and deduplication rules.

## Capabilities

### New Capabilities
- `automated-daily-scraping`: Defines requirements for scheduled cron-based dispatch execution against the protected scraping dispatch API, failure logging, and operational auditability.

### Modified Capabilities
<!-- None: No existing specs are modified. -->

## Impact

- **CI/CD / Automation**: `.github/workflows/daily-scraping.yml`.
- **Scripts**: `scripts/trigger_daily_scraping.sh`.
- **Backend API**: Consumes existing `POST /api/v1/scraping/dispatch` with `INTERNAL_API_KEY`.
