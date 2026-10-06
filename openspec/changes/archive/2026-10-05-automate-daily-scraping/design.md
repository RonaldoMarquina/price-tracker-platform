# Design: Automated Daily Scraping

## Context

The backend provides a protected endpoint `POST /api/v1/scraping/dispatch` secured by `INTERNAL_API_KEY`. To ensure the catalog updates its price observations on a daily cadence without keeping expensive or fragile background daemon processes running on free-tier cloud platforms, an external cron orchestrator is required.

## Goals / Non-Goals

**Goals:**
- Provide `.github/workflows/daily-scraping.yml` executing once every 24 hours (11:00 UTC / 6:00 AM Lima time).
- Enable manual on-demand execution through GitHub Actions `workflow_dispatch` button.
- Include cold-start wake-up logic (`GET /health` retry) before issuing the dispatch request.
- Provide a developer/operator CLI script (`scripts/trigger_daily_scraping.sh`) with colored output and exit status checks.

**Non-Goals:**
- Introducing external brokers (Redis, Celery, RabbitMQ) into the MVP architecture.
- Running persistent polling daemons in cloud environments that sleep on idle.

## Decisions

### Decision 1: GitHub Actions Cron Orchestration
- **Rationale**: GitHub Actions provides free monthly runner minutes for public and private repositories, natively supports cron schedules (`schedule: - cron: '0 11 * * *'`), and stores sensitive credentials in encrypted repository secrets (`API_BASE_URL`, `INTERNAL_API_KEY`).
- **Alternatives considered**:
  - *Free external cron services (cron-job.org / EasyCron)*: Requires maintaining third-party accounts; less auditable than native repo workflows.
  - *Continuous sleeping loop in container*: Fails on platforms that sleep containers after 15 minutes of inactivity.

### Decision 2: Pre-warming Cold Starts
- **Rationale**: Free tier web services (such as Render) enter sleep mode after 15 minutes of inactivity, taking 30-40 seconds to spin up upon receiving an HTTP request. The action will ping `/health` with retries before posting to `/api/v1/scraping/dispatch`.
- **Alternatives considered**:
  - *Direct POST without wake-up*: Risks HTTP gateway 504 timeouts on cold containers.

### Decision 3: Local Shell Trigger Script
- **Rationale**: Developers need a 1-line command to trigger and verify the full scraping dispatch locally or against staging without logging into GitHub. A shell script `scripts/trigger_daily_scraping.sh` reads `.env` and issues the request.

## Risks / Trade-offs

- **[GitHub Actions scheduled crons may experience minor queue delays (5-15 mins)]** → Acceptable: Price tracking on a daily granularity does not require sub-second precision.
- **[Secret exposure]** → Mitigated: `INTERNAL_API_KEY` is referenced solely via GitHub Encrypted Secrets and masked in workflow logs.
