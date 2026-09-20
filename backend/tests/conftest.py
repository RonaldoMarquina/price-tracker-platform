"""Pytest configuration for backend test suite."""

import os

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/price_tracker_test"
)

from app.db.session import engine


@pytest.fixture
def db_session():
    """Provide a database session wrapped in an outer transaction that rolls back everything."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
