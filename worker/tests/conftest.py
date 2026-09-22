import os
from urllib.parse import urlparse

os.environ.setdefault(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/price_tracker_test"
)
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-secret-token-for-pytest-execution")


db_url = os.environ.get("DATABASE_URL", "")
parsed = urlparse(db_url)
db_name = parsed.path.lstrip("/")
is_protected = db_name in ("price_tracker", "price_tracker_prod")
if is_protected or (db_name and not db_name.endswith("_test")):
    raise RuntimeError(
        f"ABORTING TEST EXECUTION: DATABASE_URL points to protected database '{db_name}'. "
        "Tests must run exclusively against a dedicated test database (e.g. price_tracker_test)."
    )
