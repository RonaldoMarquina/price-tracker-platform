"""Pytest configuration for backend test suite."""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/price_tracker_test"
)
