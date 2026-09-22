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


def test_price_condition_column_and_constraint_exists():
    """Verify price_condition column and check constraint exist on price_observations."""
    inspector = inspect(engine)
    columns = {col["name"]: col for col in inspector.get_columns("price_observations")}
    assert "price_condition" in columns
    assert columns["price_condition"]["nullable"] is True

    check_constraints = inspector.get_check_constraints("price_observations")
    constraint_names = [cc["name"] for cc in check_constraints]
    assert "ck_price_observations_price_condition" in constraint_names


def test_price_condition_check_constraint_enforces_allowed_values(db_session: Session):
    """Check constraint accepts standard, cash_or_bank_transfer, NULL, and rejects invalid."""
    import uuid
    from datetime import datetime, timezone
    from decimal import Decimal

    import pytest
    from sqlalchemy.exc import IntegrityError

    from app.db.models import Category, PriceObservation, Product, Store, StoreProduct

    cat = Category(name=f"Cat-{uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
    prod = Product(name="Test Product", slug=f"prod-{uuid.uuid4().hex[:6]}", category=cat)
    store = Store(name=f"Store-{uuid.uuid4().hex[:4]}", domain=f"st-{uuid.uuid4().hex[:4]}.com")
    db_session.add_all([cat, prod, store])
    db_session.flush()

    sp = StoreProduct(product_id=prod.id, store_id=store.id, product_url="https://test.com/p")
    db_session.add(sp)
    db_session.flush()

    # 1. Standard condition
    obs_standard = PriceObservation(
        store_product_id=sp.id,
        price=Decimal("100.00"),
        currency="PEN",
        availability="in_stock",
        price_condition="standard",
        captured_at=datetime.now(timezone.utc),
    )
    # 2. Cash or bank transfer condition
    obs_cash = PriceObservation(
        store_product_id=sp.id,
        price=Decimal("95.00"),
        currency="PEN",
        availability="in_stock",
        price_condition="cash_or_bank_transfer",
        captured_at=datetime.now(timezone.utc),
    )
    # 3. NULL condition (historical observation)
    obs_null = PriceObservation(
        store_product_id=sp.id,
        price=Decimal("90.00"),
        currency="PEN",
        availability="in_stock",
        price_condition=None,
        captured_at=datetime.now(timezone.utc),
    )
    db_session.add_all([obs_standard, obs_cash, obs_null])
    db_session.flush()

    # 4. Invalid condition must raise IntegrityError
    obs_invalid = PriceObservation(
        store_product_id=sp.id,
        price=Decimal("80.00"),
        currency="PEN",
        availability="in_stock",
        price_condition="crypto_discount",
        captured_at=datetime.now(timezone.utc),
    )
    db_session.add(obs_invalid)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_migration_004_safe_downgrade_and_upgrade():
    """Verify safe downgrade and upgrade of migration 004 on test database.

    Downgrade drops price_condition and preserves other columns.
    Upgrade head restores price_condition as nullable.
    """
    import pathlib

    from alembic.config import Config

    from alembic import command

    backend_dir = pathlib.Path(__file__).parent.parent
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", str(engine.url))

    # Downgrade 004 revision (004 -> 003)
    try:
        command.downgrade(alembic_cfg, "003_add_mpn_nullable_price")
        inspector = inspect(engine)
        cols_after_down = [col["name"] for col in inspector.get_columns("price_observations")]
        assert "price_condition" not in cols_after_down
        assert "price" in cols_after_down
        assert "currency" in cols_after_down
    finally:
        # Upgrade back to head (restoring 004 and 005)
        command.upgrade(alembic_cfg, "head")

    inspector_up = inspect(engine)
    cols_after_up = {col["name"]: col for col in inspector_up.get_columns("price_observations")}
    assert "price_condition" in cols_after_up
    assert cols_after_up["price_condition"]["nullable"] is True


def test_migration_006_safe_downgrade_and_upgrade():
    """Verify safe downgrade and upgrade of migration 006 on test database."""
    import pathlib

    from alembic.config import Config

    from alembic import command

    backend_dir = pathlib.Path(__file__).parent.parent
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", str(engine.url))

    # Downgrade 006 (006 -> 005)
    try:
        command.downgrade(alembic_cfg, "005_add_scraping_jobs_table")
        inspector = inspect(engine)
        cols_after_down = [col["name"] for col in inspector.get_columns("scraping_jobs")]
        assert "trigger_type" not in cols_after_down
        assert "dispatch_slot" not in cols_after_down
    finally:
        # Upgrade back to head
        command.upgrade(alembic_cfg, "head")

    inspector_up = inspect(engine)
    cols_after_up = {col["name"]: col for col in inspector_up.get_columns("scraping_jobs")}
    assert "trigger_type" in cols_after_up
    assert "dispatch_slot" in cols_after_up
    assert cols_after_up["dispatch_slot"]["nullable"] is True


def test_migration_007_safe_downgrade_and_upgrade():
    """Verify safe downgrade and upgrade of migration 007 on test database."""
    import pathlib

    from alembic.config import Config

    from alembic import command

    backend_dir = pathlib.Path(__file__).parent.parent
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", str(engine.url))

    # Downgrade 007 (007 -> 006)
    try:
        command.downgrade(alembic_cfg, "006_dispatch_slot_trigger_type")
        inspector = inspect(engine)
        q_cols_down = [col["name"] for col in inspector.get_columns("local_queue_messages")]
        j_cols_down = [col["name"] for col in inspector.get_columns("scraping_jobs")]
        assert "sent_to_dlq_at" not in q_cols_down
        assert "replay_count" not in q_cols_down
        assert "sent_to_dlq_at" not in j_cols_down
        assert "last_dlq_reason" not in j_cols_down
    finally:
        # Upgrade back to head
        command.upgrade(alembic_cfg, "head")

    inspector_up = inspect(engine)
    q_cols_up = {col["name"]: col for col in inspector_up.get_columns("local_queue_messages")}
    j_cols_up = {col["name"]: col for col in inspector_up.get_columns("scraping_jobs")}
    assert "sent_to_dlq_at" in q_cols_up
    assert "replay_count" in q_cols_up
    assert "replayed_at" in q_cols_up
    assert "sent_to_dlq_at" in j_cols_up
    assert "last_dlq_reason" in j_cols_up
    assert "replay_count" in j_cols_up
    assert "replayed_at" in j_cols_up


def test_migration_008_safe_downgrade_and_upgrade():
    """Verify safe downgrade and upgrade of migration 008 on test database."""
    import pathlib

    from alembic.config import Config

    from alembic import command

    backend_dir = pathlib.Path(__file__).parent.parent
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", str(engine.url))

    # Downgrade 008 (008 -> 007)
    try:
        command.downgrade(alembic_cfg, "007_dlq_audit_and_replay")
        inspector = inspect(engine)
        tables_down = set(inspector.get_table_names())
        assert "scraping_outbox" not in tables_down
        assert "scraping_dlq_ledger" not in tables_down
        assert "scraping_quarantine" not in tables_down
        j_cols_down = [col["name"] for col in inspector.get_columns("scraping_jobs")]
        assert "payload" not in j_cols_down
    finally:
        # Upgrade back to head
        command.upgrade(alembic_cfg, "head")

    inspector_up = inspect(engine)
    tables_up = set(inspector_up.get_table_names())
    assert "scraping_outbox" in tables_up
    assert "scraping_dlq_ledger" in tables_up
    assert "scraping_quarantine" in tables_up
    j_cols_up = [col["name"] for col in inspector_up.get_columns("scraping_jobs")]
    assert "payload" in j_cols_up


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
