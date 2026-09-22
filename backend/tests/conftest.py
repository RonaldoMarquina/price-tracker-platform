import os
from urllib.parse import urlparse

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/price_tracker_test"
)

db_url = os.environ.get("DATABASE_URL", "")
parsed = urlparse(db_url)
db_name = parsed.path.lstrip("/")
is_protected = db_name in ("price_tracker", "price_tracker_prod")
if is_protected or (db_name and not db_name.endswith("_test")):
    raise RuntimeError(
        f"ABORTING TEST EXECUTION: DATABASE_URL points to protected database '{db_name}'. "
        "Tests must run exclusively against a dedicated test database (e.g. price_tracker_test)."
    )

from app.db.session import engine  # noqa: E402


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
