"""Tests for independent scheduled dispatcher and advisory lock mutual exclusion."""

import uuid
from datetime import datetime, timezone

import pytest
from shared.queue.models import LocalQueueMessage
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.advisory_lock import (
    DISPATCHER_SCHEDULED_LOCK_ID,
    PostgresAdvisoryLock,
)
from app.db.models import Category, Product, ScrapingJob, Store, StoreProduct
from app.db.session import SessionLocal, engine
from app.services.dispatch_service import DispatchService


@pytest.fixture
def db_session():
    """Yield a transactional database session for tests."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.execute(
            text(
                "DELETE FROM store_products WHERE store_id IN ("
                "SELECT id FROM stores "
                "WHERE domain LIKE 'inactive-%' OR domain LIKE 'only-inactive-%')"
            )
        )
        session.execute(
            text(
                "DELETE FROM stores "
                "WHERE domain LIKE 'inactive-%' OR domain LIKE 'only-inactive-%'"
            )
        )
        session.commit()
        session.close()


def create_test_category(db: Session) -> Category:
    """Create a temporary category for testing."""
    cat = Category(
        id=uuid.uuid4(),
        name=f"Dispatcher Cat {uuid.uuid4().hex[:6]}",
        slug=f"disp-cat-{uuid.uuid4().hex[:6]}",
    )
    db.add(cat)
    db.flush()
    return cat


def get_or_create_test_store(
    db: Session,
    name: str = "Test NECS Store",
    domain: str = "necs.pe",
    is_active: bool = True,
) -> Store:
    """Get or create store for testing."""
    existing = db.scalars(select(Store).where(Store.domain == domain)).first()
    if existing:
        existing.is_active = is_active
        db.flush()
        return existing

    store = Store(
        id=uuid.uuid4(),
        name=f"{name} {uuid.uuid4().hex[:6]}",
        domain=domain,
        is_active=is_active,
    )
    db.add(store)
    db.flush()
    return store


def create_test_product(db: Session, category_id: uuid.UUID, is_active: bool = True) -> Product:
    """Create a temporary product for testing."""
    prod = Product(
        id=uuid.uuid4(),
        category_id=category_id,
        name=f"Disp Product {uuid.uuid4().hex[:6]}",
        slug=f"disp-prod-{uuid.uuid4().hex[:6]}",
        is_active=is_active,
    )
    db.add(prod)
    db.flush()
    return prod


def create_test_store_product(
    db: Session, store_id: uuid.UUID, product_id: uuid.UUID, is_active: bool = True
) -> StoreProduct:
    """Associate product to store."""
    sp = StoreProduct(
        id=uuid.uuid4(),
        store_id=store_id,
        product_id=product_id,
        product_url=f"https://store.pe/prod/{uuid.uuid4().hex[:6]}",
        is_active=is_active,
    )
    db.add(sp)
    db.flush()
    return sp


def test_dispatcher_active_store_creates_scheduled_job_and_queue_message(db_session: Session):
    """Dispatcher creates scheduled ScrapingJob and enqueues LocalQueueMessage atomically."""
    cat = create_test_category(db_session)
    store = get_or_create_test_store(db_session, domain="necs.pe", is_active=True)
    prod = create_test_product(db_session, cat.id, is_active=True)
    create_test_store_product(db_session, store.id, prod.id, is_active=True)
    db_session.commit()

    service = DispatchService(db_engine=engine, session_factory=SessionLocal)
    test_slot = datetime(2026, 9, 20, 15, 0, 0, tzinfo=timezone.utc)

    # Clean up prior run for this slot
    db_session.execute(text("DELETE FROM scraping_jobs WHERE dispatch_slot = :s"), {"s": test_slot})
    db_session.commit()

    result = service.run_once(slot=test_slot, allow_offline_adapters=True)

    assert result.skipped_lock is False
    assert result.jobs_created >= 1

    # Verify ScrapingJob in database
    created_job = db_session.execute(
        select(ScrapingJob).where(
            ScrapingJob.store_id == store.id,
            ScrapingJob.dispatch_slot == test_slot,
        )
    ).scalar_one_or_none()

    assert created_job is not None
    assert created_job.trigger_type == "scheduled"
    assert created_job.dispatch_slot == test_slot
    assert created_job.status == "queued"
    assert created_job.batch_size >= 1

    # Verify corresponding LocalQueueMessage
    q_msg = db_session.execute(
        select(LocalQueueMessage).where(
            LocalQueueMessage.payload["job_id"].as_string() == str(created_job.id)
        )
    ).scalar_one_or_none()

    assert q_msg is not None
    assert q_msg.queue_name == "scraping-jobs"
    assert q_msg.status == "pending"

    # Cleanup
    db_session.execute(text("DELETE FROM scraping_jobs WHERE dispatch_slot = :s"), {"s": test_slot})
    if q_msg:
        db_session.delete(q_msg)
    db_session.commit()


def test_dispatcher_excludes_inactive_store(db_session: Session):
    """Dispatcher ignores inactive stores even if they have active products."""
    cat = create_test_category(db_session)
    store = get_or_create_test_store(
        db_session, domain=f"inactive-{uuid.uuid4().hex[:6]}.pe", is_active=False
    )
    prod = create_test_product(db_session, cat.id, is_active=True)
    create_test_store_product(db_session, store.id, prod.id, is_active=True)
    db_session.commit()

    service = DispatchService(db_engine=engine, session_factory=SessionLocal)
    test_slot = datetime(2026, 9, 20, 16, 0, 0, tzinfo=timezone.utc)

    service.run_once(slot=test_slot, allow_offline_adapters=True)

    job = db_session.execute(
        select(ScrapingJob).where(
            ScrapingJob.store_id == store.id,
            ScrapingJob.dispatch_slot == test_slot,
        )
    ).scalar_one_or_none()

    assert job is None


def test_dispatcher_excludes_sercoplus_and_disabled_stores(db_session: Session):
    """Dispatcher strictly excludes Sercoplus and stores without enabled adapters."""
    cat = create_test_category(db_session)
    sercoplus = get_or_create_test_store(
        db_session, name="Sercoplus Active Mock", domain="sercoplus.com", is_active=True
    )
    prod = create_test_product(db_session, cat.id, is_active=True)
    create_test_store_product(db_session, sercoplus.id, prod.id, is_active=True)
    db_session.commit()

    service = DispatchService(db_engine=engine, session_factory=SessionLocal)
    test_slot = datetime(2026, 9, 20, 17, 0, 0, tzinfo=timezone.utc)

    result = service.run_once(slot=test_slot, allow_offline_adapters=False)

    job = db_session.execute(
        select(ScrapingJob).where(
            ScrapingJob.store_id == sercoplus.id,
            ScrapingJob.dispatch_slot == test_slot,
        )
    ).scalar_one_or_none()

    assert job is None
    assert sercoplus.id in result.skipped_stores


def test_dispatcher_excludes_inactive_store_product(db_session: Session):
    """Dispatcher does not dispatch stores that only have inactive products."""
    cat = create_test_category(db_session)
    store = get_or_create_test_store(
        db_session, domain=f"only-inactive-{uuid.uuid4().hex[:6]}.pe", is_active=True
    )
    prod = create_test_product(db_session, cat.id, is_active=True)
    # StoreProduct association is marked inactive
    create_test_store_product(db_session, store.id, prod.id, is_active=False)
    db_session.commit()

    service = DispatchService(db_engine=engine, session_factory=SessionLocal)
    test_slot = datetime(2026, 9, 20, 18, 0, 0, tzinfo=timezone.utc)

    result = service.run_once(slot=test_slot, allow_offline_adapters=True)

    job = db_session.execute(
        select(ScrapingJob).where(
            ScrapingJob.store_id == store.id,
            ScrapingJob.dispatch_slot == test_slot,
        )
    ).scalar_one_or_none()

    assert job is None
    assert store.id in result.skipped_stores


def test_dispatcher_deterministic_slot_normalization(db_session: Session):
    """Naive datetime or non-zero seconds are normalized deterministically to UTC."""
    cat = create_test_category(db_session)
    store = get_or_create_test_store(db_session, domain="computershopperu.com", is_active=True)
    prod = create_test_product(db_session, cat.id, is_active=True)
    create_test_store_product(db_session, store.id, prod.id, is_active=True)
    db_session.commit()

    service = DispatchService(db_engine=engine, session_factory=SessionLocal)
    # Naive datetime with arbitrary minutes and seconds
    naive_slot = datetime(2026, 9, 20, 19, 45, 33)
    expected_slot = datetime(2026, 9, 20, 19, 45, 0, tzinfo=timezone.utc)

    # Clean prior jobs for expected_slot
    db_session.execute(
        text("DELETE FROM scraping_jobs WHERE dispatch_slot = :s"), {"s": expected_slot}
    )
    db_session.commit()

    service.run_once(slot=naive_slot, allow_offline_adapters=True)

    job = db_session.execute(
        select(ScrapingJob).where(
            ScrapingJob.store_id == store.id,
            ScrapingJob.dispatch_slot == expected_slot,
        )
    ).scalar_one_or_none()

    assert job is not None
    assert job.dispatch_slot == expected_slot

    # Cleanup
    db_session.delete(job)
    db_session.commit()


def test_dispatcher_prevents_duplicate_slot_even_if_previous_finished(db_session: Session):
    """Unique partial index prevents repeating the same store and slot even after completion."""
    cat = create_test_category(db_session)
    store = get_or_create_test_store(db_session, domain="cyccomputer.pe", is_active=True)
    prod = create_test_product(db_session, cat.id, is_active=True)
    create_test_store_product(db_session, store.id, prod.id, is_active=True)

    slot = datetime(2026, 9, 20, 20, 0, 0, tzinfo=timezone.utc)
    db_session.execute(text("DELETE FROM scraping_jobs WHERE dispatch_slot = :s"), {"s": slot})
    db_session.commit()

    # First job: already completed
    completed_job = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store.id,
        status="completed",
        trigger_type="scheduled",
        dispatch_slot=slot,
        batch_size=1,
        observations_created=1,
        attempts=1,
        created_at=slot,
        started_at=slot,
        finished_at=slot,
    )
    db_session.add(completed_job)
    db_session.commit()

    service = DispatchService(db_engine=engine, session_factory=SessionLocal)

    # Dispatcher runs for the same slot
    result = service.run_once(slot=slot, allow_offline_adapters=True)

    # Store was skipped idempotently
    assert store.id in result.skipped_stores

    # Total jobs for this store and slot remains exactly 1
    count = db_session.execute(
        select(ScrapingJob).where(
            ScrapingJob.store_id == store.id,
            ScrapingJob.dispatch_slot == slot,
        )
    ).scalars().all()

    assert len(count) == 1

    # Cleanup
    db_session.delete(completed_job)
    db_session.commit()


def test_dispatcher_advisory_lock_busy_skips_cleanly():
    """If another process holds the advisory lock, dispatcher terminates cleanly without jobs."""
    # Open dedicated connection and hold the scheduled advisory lock
    conn = engine.connect()
    try:
        acquired = conn.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": DISPATCHER_SCHEDULED_LOCK_ID},
        ).scalar()
        assert acquired is True

        # Invocating run_once from another connection while lock is held
        service = DispatchService(db_engine=engine, session_factory=SessionLocal)
        result = service.run_once(slot=datetime(2026, 9, 20, 21, 0, 0, tzinfo=timezone.utc))

        assert result.skipped_lock is True
        assert result.jobs_created == 0

    finally:
        conn.execute(
            text("SELECT pg_advisory_unlock(:lock_id)"),
            {"lock_id": DISPATCHER_SCHEDULED_LOCK_ID},
        )
        conn.close()


def test_dispatcher_advisory_lock_released_on_error():
    """Advisory lock is released in finally block even when an exception occurs."""
    lock_id = 999111222  # dedicated test lock id
    lock = PostgresAdvisoryLock(engine, lock_id)

    with pytest.raises(RuntimeError):
        with lock as acquired:
            assert acquired is True
            raise RuntimeError("Simulated unhandled exception during dispatch")

    # Verify lock is completely free by acquiring it again immediately
    conn = engine.connect()
    try:
        reacquired = conn.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": lock_id},
        ).scalar()
        assert reacquired is True
        conn.execute(
            text("SELECT pg_advisory_unlock(:lock_id)"),
            {"lock_id": lock_id},
        )
    finally:
        conn.close()


def test_dispatcher_coherence_constraint_scheduled_and_manual(db_session: Session):
    """Database check constraint enforces scheduled->slot NOT NULL and manual->slot NULL."""
    store = get_or_create_test_store(db_session)
    db_session.commit()

    # 1. Scheduled without slot must fail
    job_invalid_scheduled = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store.id,
        status="queued",
        trigger_type="scheduled",
        dispatch_slot=None,  # Invalid: scheduled requires dispatch_slot
        batch_size=1,
    )
    db_session.add(job_invalid_scheduled)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # 2. Manual with slot must fail
    job_invalid_manual = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store.id,
        status="queued",
        trigger_type="manual",
        dispatch_slot=datetime.now(timezone.utc),  # Invalid: manual requires slot IS NULL
        batch_size=1,
    )
    db_session.add(job_invalid_manual)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # 3. Scheduled with slot succeeds
    job_valid_scheduled = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store.id,
        status="queued",
        trigger_type="scheduled",
        dispatch_slot=datetime(2026, 9, 20, 22, 0, 0, tzinfo=timezone.utc),
        batch_size=1,
    )
    db_session.add(job_valid_scheduled)
    db_session.commit()

    # 4. Manual with null slot succeeds
    job_valid_manual = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store.id,
        status="queued",
        trigger_type="manual",
        dispatch_slot=None,
        batch_size=1,
    )
    db_session.add(job_valid_manual)
    db_session.commit()

    # Cleanup
    db_session.delete(job_valid_scheduled)
    db_session.delete(job_valid_manual)
    db_session.commit()


def test_dispatcher_differentiates_slot_duplicate_from_other_integrity_error(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """Confirm only uq_scraping_jobs_store_dispatch_slot is treated as idempotent skip."""
    cat = create_test_category(db_session)
    store = get_or_create_test_store(db_session, domain="necs.pe", is_active=True)
    prod = create_test_product(db_session, cat.id, is_active=True)
    create_test_store_product(db_session, store.id, prod.id, is_active=True)

    slot = datetime(2026, 9, 20, 23, 30, 0, tzinfo=timezone.utc)
    db_session.execute(text("DELETE FROM scraping_jobs WHERE dispatch_slot = :s"), {"s": slot})
    db_session.commit()

    service = DispatchService(db_engine=engine, session_factory=SessionLocal)

    # 1. Non-slot IntegrityError (e.g. check constraint or other DB constraint violation)
    non_slot_integrity_error = IntegrityError(
        statement="INSERT INTO scraping_jobs ...",
        params={},
        orig=Exception("violates check constraint 'ck_scraping_jobs_status'"),
    )

    def raise_non_slot_error(*args, **kwargs):
        raise non_slot_integrity_error

    monkeypatch.setattr(service.queue, "send_message", raise_non_slot_error)

    result_failed = service.run_once(slot=slot, allow_offline_adapters=True)

    # Store must be marked in failed_stores, NOT skipped_stores
    assert store.id in result_failed.failed_stores
    assert store.id not in result_failed.skipped_stores

    # Confirms transaction rolled back: no orphan ScrapingJob created
    jobs = db_session.scalars(
        select(ScrapingJob).where(
            ScrapingJob.store_id == store.id,
            ScrapingJob.dispatch_slot == slot,
        )
    ).all()
    assert len(jobs) == 0

    # 2. Real slot duplicate IntegrityError (uq_scraping_jobs_store_dispatch_slot)
    monkeypatch.undo()

    # Pre-insert a job for this slot to trigger real unique constraint violation
    existing_job = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store.id,
        status="completed",
        trigger_type="scheduled",
        dispatch_slot=slot,
        batch_size=1,
    )
    db_session.add(existing_job)
    db_session.commit()

    result_skipped = service.run_once(slot=slot, allow_offline_adapters=True)

    # Must be marked in skipped_stores, NOT failed_stores
    assert store.id in result_skipped.skipped_stores
    assert store.id not in result_skipped.failed_stores

    # Cleanup
    db_session.delete(existing_job)
    db_session.commit()
