"""Tests for ScrapingJob lifecycle, atomic creation, rollback, and constraints in backend."""

import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from shared.queue.models import LocalQueueMessage
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import settings
from app.db.models import Category, Product, ScrapingJob, Store, StoreProduct
from app.db.session import SessionLocal
from app.main import app
from app.schemas.scraping import ScrapingJobCreate
from app.services.scraping_service import scraping_service

client = TestClient(app)


def get_or_create_entities(db: Session) -> tuple[uuid.UUID, uuid.UUID]:
    """Helper to ensure an active store and product exist."""
    store = db.scalars(select(Store).where(Store.is_active.is_(True))).first()
    if not store:
        store = Store(
            id=uuid.uuid4(),
            name=f"Store Lifecycle {uuid.uuid4().hex[:6]}",
            domain=f"store-{uuid.uuid4().hex[:6]}.pe",
            is_active=True,
        )
        db.add(store)
        db.flush()

    cat = db.scalars(select(Category)).first()
    if not cat:
        cat = Category(
            id=uuid.uuid4(),
            name=f"Cat {uuid.uuid4().hex[:6]}",
            slug=f"cat-{uuid.uuid4().hex[:6]}",
        )
        db.add(cat)
        db.flush()

    product = db.scalars(select(Product).where(Product.is_active.is_(True))).first()
    if not product:
        product = Product(
            id=uuid.uuid4(),
            category_id=cat.id,
            name="Lifecycle CPU",
            slug=f"cpu-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        db.add(product)
        db.flush()

    sp = db.scalars(
        select(StoreProduct).where(
            StoreProduct.product_id == product.id, StoreProduct.store_id == store.id
        )
    ).first()
    if not sp:
        sp = StoreProduct(
            id=uuid.uuid4(),
            product_id=product.id,
            store_id=store.id,
            product_url=f"https://{store.domain}/p/{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        db.add(sp)
        db.flush()

    store_id = store.id
    product_id = product.id
    db.commit()
    return store_id, product_id


def test_create_job_endpoint_persists_queued_job_and_queue_message():
    """POST /api/v1/scraping/jobs persists ScrapingJob(queued) and enqueues message atomically."""
    with SessionLocal() as db:
        store_id, product_id = get_or_create_entities(db)

    response = client.post(
        "/api/v1/scraping/jobs",
        headers={"Authorization": f"Bearer {settings.INTERNAL_API_KEY.get_secret_value()}"},
        json={"store_id": str(store_id), "product_ids": [str(product_id)]},
    )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "queued"

    job_id = uuid.UUID(data["job_id"])

    with SessionLocal() as db:
        try:
            # 1. ScrapingJob is persisted in 'queued' status
            stmt = select(ScrapingJob).where(ScrapingJob.id == job_id)
            job = db.execute(stmt).scalar_one_or_none()
            assert job is not None
            assert job.id == job_id
            assert job.store_id == store_id
            assert job.status == "queued"
            assert job.batch_size == 1
            assert job.observations_created == 0
            assert job.attempts == 0
            assert job.error_reason is None
            assert job.started_at is None
            assert job.finished_at is None
            assert job.created_at is not None

            # 2. LocalQueueMessage is persisted in 'pending' status
            msgs = db.scalars(
                select(LocalQueueMessage).where(LocalQueueMessage.queue_name == "scraping-jobs")
            ).all()
            matching = [m for m in msgs if m.payload.get("job_id") == str(job_id)]
            assert len(matching) == 1
            assert matching[0].status == "pending"
            assert matching[0].attempts == 0
        finally:
            if job:
                db.delete(job)
            for m in matching:
                db.delete(m)
            db.commit()


def test_create_job_atomic_rollback_on_enqueue_failure():
    """If enqueue fails midway, rollback must ensure no orphan ScrapingJob or message exists."""
    with SessionLocal() as db:
        store_id, product_id = get_or_create_entities(db)

    # Mock queue.send_message to raise an error midway
    failing_queue = MagicMock()
    failing_queue.send_message.side_effect = RuntimeError("Database queue disk full error")

    original_queue = scraping_service._queue
    scraping_service._queue = failing_queue

    test_payload = ScrapingJobCreate(store_id=store_id, product_ids=[product_id])

    with SessionLocal() as db:
        jobs_before = len(db.scalars(select(ScrapingJob)).all())
        msgs_stmt = select(LocalQueueMessage).where(LocalQueueMessage.queue_name == "scraping-jobs")
        msgs_before = len(db.scalars(msgs_stmt).all())

        with pytest.raises(RuntimeError, match="Database queue disk full error"):
            scraping_service.create_scraping_job(db=db, payload=test_payload)

        # Verify no ScrapingJob was committed/persisted
        jobs_after = len(db.scalars(select(ScrapingJob)).all())
        assert jobs_after == jobs_before

        # Verify no LocalQueueMessage was committed
        msgs_after = len(db.scalars(msgs_stmt).all())
        assert msgs_after == msgs_before

    scraping_service._queue = original_queue


def test_scraping_job_check_constraints(db_session: Session):
    """Verify check constraints for ScrapingJob: valid status, batch, and non-negative counters."""
    store_id, _ = get_or_create_entities(db_session)

    # 1. Invalid status
    invalid_job = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store_id,
        status="invalid_status",
        batch_size=1,
    )
    db_session.add(invalid_job)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # 2. Batch size <= 0
    zero_batch = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store_id,
        status="queued",
        batch_size=0,
    )
    db_session.add(zero_batch)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # 3. Negative observations
    neg_obs = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store_id,
        status="completed",
        batch_size=1,
        observations_created=-1,
    )
    db_session.add(neg_obs)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # 4. Negative attempts
    neg_att = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store_id,
        status="queued",
        batch_size=1,
        attempts=-1,
    )
    db_session.add(neg_att)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # 5. Temporal coherence: finished_at earlier than started_at
    now = datetime.now(timezone.utc)
    incoherent = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store_id,
        status="completed",
        batch_size=1,
        started_at=now,
        finished_at=now - timedelta(seconds=10),
    )
    db_session.add(incoherent)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_scraping_job_store_foreign_key_restrict():
    """Deleting a Store with associated ScrapingJobs must be RESTRICTED to keep audit history."""
    with SessionLocal() as db:
        store = Store(
            id=uuid.uuid4(),
            name=f"Restrict Store {uuid.uuid4().hex[:6]}",
            domain=f"restrict-{uuid.uuid4().hex[:6]}.pe",
            is_active=True,
        )
        db.add(store)
        db.flush()

        job = ScrapingJob(
            id=uuid.uuid4(),
            store_id=store.id,
            status="completed",
            batch_size=1,
            observations_created=1,
            attempts=1,
        )
        db.add(job)
        db.commit()

        try:
            # Attempting to delete store directly must raise IntegrityError / RESTRICT violation
            db.delete(store)
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
        finally:
            db.delete(job)
            db.delete(store)
            db.commit()


def test_alembic_upgrade_downgrade_cycle():
    """Verify Alembic migration 005 can downgrade -1 and upgrade head repeatedly."""
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alembic_cfg_path = os.path.join(backend_dir, "alembic.ini")

    cfg = Config(alembic_cfg_path)
    cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))

    try:
        # 1. Downgrade -1 (from 005 to 004)
        command.downgrade(cfg, "-1")
    finally:
        # 2. Upgrade back to head (re-applying 005)
        command.upgrade(cfg, "head")
