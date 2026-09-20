"""Integration tests for database migrations, schema verification, and seed idempotency."""

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.db.seed import seed_dev_data
from app.db.session import SessionLocal, engine


def test_required_tables_exist():
    """Verify that all five entities defined in DATA_MODEL.md exist in the database."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    required_tables = {
        "categories",
        "products",
        "stores",
        "store_products",
        "price_observations",
    }
    assert required_tables.issubset(set(tables)), f"Missing tables: {required_tables - set(tables)}"


def test_price_observations_index_exists():
    """Verify composite index (store_product_id, captured_at DESC) exists on price_observations."""
    inspector = inspect(engine)
    indexes = inspector.get_indexes("price_observations")
    index_names = [idx["name"] for idx in indexes]

    assert "ix_price_observations_store_product_captured_at" in index_names


def test_store_products_unique_constraint_exists():
    """Verify unique constraint on (product_id, store_id, product_url) exists."""
    inspector = inspect(engine)
    unique_constraints = inspector.get_unique_constraints("store_products")
    constraint_names = [uc["name"] for uc in unique_constraints]

    assert "uq_store_products_product_store_url" in constraint_names


def test_price_positive_check_constraint_exists():
    """Verify check constraint on price and currency validity exists."""
    inspector = inspect(engine)
    check_constraints = inspector.get_check_constraints("price_observations")
    constraint_names = [cc["name"] for cc in check_constraints]

    assert "ck_price_observations_price_currency_valid" in constraint_names


def test_seed_idempotency():
    """Verify seed function can be called multiple times without duplicate records or errors."""
    db: Session = SessionLocal()
    try:
        # Initial seed ensures base data exists
        seed_dev_data(db)
        # Running seed again should result in 0 new records inserted
        second_run_counts = seed_dev_data(db)
        assert second_run_counts["categories"] == 0
        assert second_run_counts["stores"] == 0
        assert second_run_counts["products"] == 0
        assert second_run_counts["store_products"] == 0
        assert second_run_counts["price_observations"] == 0

        # Verify tables actually have records
        cat_count = db.execute(text("SELECT count(*) FROM categories")).scalar()
        assert cat_count >= 3
    finally:
        db.close()
