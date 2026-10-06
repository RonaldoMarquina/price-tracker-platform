#!/usr/bin/env bash
# ==============================================================================
# Price Tracker Platform - Render Deployment Entrypoint
# Runs database migrations, catalog seeding, launches the background worker
# process, and serves the FastAPI web API in the foreground.
# ==============================================================================

set -e

echo "==> Running database migrations..."
alembic upgrade head

echo "==> Seeding canonical catalog and price observations..."
SEED_DEMO_OBSERVATIONS=true python -m app.db.seed

echo "==> Starting background scraping worker..."
PYTHONPATH=worker:. python -m app.main &
WORKER_PID=$!
echo "==> Background worker started with PID $WORKER_PID"

echo "==> Starting FastAPI web server on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
