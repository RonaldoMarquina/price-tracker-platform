# Automated Daily Scraping

## Purpose

Enables automated, serverless daily scheduling of the scraping dispatch lifecycle through secure GitHub Actions workflows and operator scripts.

## Requirements

### Requirement: Scheduled Daily Dispatch Execution
The platform SHALL support scheduled automated triggering of the scraping dispatch process once per day via an external cron workflow, dispatching jobs to all active authorized merchant stores.

#### Scenario: Cron workflow triggers daily dispatch
- **WHEN** the scheduled daily cron triggers (e.g. at 11:00 UTC / 6:00 AM PET)
- **THEN** the workflow sends an authenticated POST request to `/api/v1/scraping/dispatch`, logging the resulting job count and summary

### Requirement: Authenticated Dispatch Security
The dispatch trigger mechanism SHALL supply a valid `X-Internal-API-Key` or `Authorization: Bearer <key>` header derived from secure repository secrets, rejecting unauthenticated or invalid invocation attempts.

#### Scenario: Dispatch rejected with missing or invalid token
- **WHEN** an invocation is attempted without the valid internal API key
- **THEN** the API returns HTTP status 401 or 403 and no scraping jobs are scheduled

### Requirement: Idempotent Daily Scraping Cycle
The scraping dispatch process SHALL execute idempotently, acquiring exclusive advisory locks to prevent overlapping duplicate runs during the same dispatch time window.

#### Scenario: Duplicate triggers in the same slot do not duplicate jobs
- **WHEN** a dispatch request is received while a run is in progress or within the same normalized dispatch time slot
- **THEN** the system skips or returns an advisory lock conflict rather than generating redundant scraping jobs for the same store
