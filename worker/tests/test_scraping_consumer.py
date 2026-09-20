"""Unit and integration tests for Worker ScrapingConsumer."""

import uuid
from datetime import datetime, timezone

import pytest
from shared.queue.models import LocalQueueMessage
from shared.queue.postgres import PostgresQueue
from shared.schemas.scraping import ScrapingMessage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import ScrapedPriceResult, TransientScrapingError
from app.adapters.fake_store_adapter import FakeStoreAdapter
from app.consumers.scraping_consumer import ScrapingConsumer
from app.db.models import PriceObservation, StoreProduct
from app.db.session import SessionLocal
from app.repositories.observation_repository import ObservationRepository
from app.services.scraping_service import ScrapingWorkerService


@pytest.fixture(autouse=True)
def cleanup_consumer_test_data():
    """Clean up test queue messages after each test to keep DB clean."""
    yield
    with SessionLocal() as db:
        db.query(LocalQueueMessage).filter(
            LocalQueueMessage.queue_name.like("test-%")
        ).delete(synchronize_session=False)
        db.commit()


def setup_test_store_product() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Ensure a StoreProduct exists in DB and return (store_id, product_id, store_product_id)."""
    db: Session = SessionLocal()
    try:
        sp = db.scalars(select(StoreProduct).where(StoreProduct.is_active.is_(True))).first()
        if not sp:
            sp = StoreProduct(
                id=uuid.uuid4(),
                product_id=uuid.uuid4(),
                store_id=uuid.uuid4(),
                product_url=f"https://fake-store.com/item/{uuid.uuid4().hex[:6]}",
                is_active=True,
            )
            db.add(sp)
            db.commit()
            db.refresh(sp)
        return sp.store_id, sp.product_id, sp.id
    finally:
        db.close()


def test_consumer_processes_valid_message_and_acknowledges() -> None:
    """Consumer claims message, runs fake adapter, persists observation, and acknowledges."""
    store_id, product_id, sp_id = setup_test_store_product()
    with SessionLocal() as db_pre:
        obs_before_ids = set(
            db_pre.scalars(
                select(PriceObservation.id).where(PriceObservation.store_product_id == sp_id)
            ).all()
        )

    queue = PostgresQueue(session_factory=SessionLocal)
    test_queue = f"test-worker-{uuid.uuid4().hex[:8]}"

    job_id = uuid.uuid4()
    msg = ScrapingMessage(
        version=1,
        job_id=job_id,
        store_id=store_id,
        product_ids=[product_id],
        requested_at=datetime.now(timezone.utc),
        attempt=1,
    )
    queue.send_message(test_queue, msg)

    consumer = ScrapingConsumer(
        queue=queue,
        service=ScrapingWorkerService(
            adapter=FakeStoreAdapter(), repository=ObservationRepository()
        ),
        session_factory=SessionLocal,
        queue_name=test_queue,
        dlq_name=f"{test_queue}-dlq",
        max_retries=3,
    )

    try:
        handled = consumer.process_next_message()
        assert handled is True

        # Verify message is completed
        assert queue.get_queue_size(test_queue) == 0

        # Verify price observation was created in PostgreSQL
        with SessionLocal() as db:
            obs = db.scalars(
                select(PriceObservation).where(PriceObservation.store_product_id == sp_id)
            ).all()
            new_obs = [o for o in obs if o.id not in obs_before_ids]
            assert len(new_obs) == 1
    finally:
        with SessionLocal() as clean_db:
            clean_db.query(PriceObservation).filter(
                PriceObservation.store_product_id == sp_id,
                ~PriceObservation.id.in_(obs_before_ids),
            ).delete(synchronize_session=False)
            clean_db.commit()


def test_consumer_idempotency_does_not_duplicate_observations() -> None:
    """Reprocessing the same job_id multiple times does NOT create duplicate observations in DB."""
    store_id, product_id, sp_id = setup_test_store_product()
    with SessionLocal() as db_pre:
        obs_before_ids = set(
            db_pre.scalars(
                select(PriceObservation.id).where(PriceObservation.store_product_id == sp_id)
            ).all()
        )

    queue = PostgresQueue(session_factory=SessionLocal)
    test_queue = f"test-idemp-{uuid.uuid4().hex[:8]}"

    job_id = uuid.uuid4()
    msg = ScrapingMessage(
        version=1,
        job_id=job_id,
        store_id=store_id,
        product_ids=[product_id],
        requested_at=datetime.now(timezone.utc),
        attempt=1,
    )

    # First delivery
    queue.send_message(test_queue, msg)

    consumer = ScrapingConsumer(
        queue=queue,
        service=ScrapingWorkerService(
            adapter=FakeStoreAdapter(), repository=ObservationRepository()
        ),
        session_factory=SessionLocal,
        queue_name=test_queue,
        dlq_name=f"{test_queue}-dlq",
        max_retries=3,
    )

    try:
        consumer.process_next_message()

        with SessionLocal() as db:
            count_after_first = db.scalars(
                select(PriceObservation).where(PriceObservation.store_product_id == sp_id)
            ).all()
            first_len = len(count_after_first)

            # Second delivery with EXACT same job_id (simulating at-least-once queue delivery)
            queue.send_message(test_queue, msg)
            consumer.process_next_message()

            count_after_second = db.scalars(
                select(PriceObservation).where(PriceObservation.store_product_id == sp_id)
            ).all()
            second_len = len(count_after_second)

            # STRICT IDEMPOTENCY: Total observations must NOT increase!
            assert second_len == first_len
    finally:
        with SessionLocal() as clean_db:
            clean_db.query(PriceObservation).filter(
                PriceObservation.store_product_id == sp_id,
                ~PriceObservation.id.in_(obs_before_ids),
            ).delete(synchronize_session=False)
            clean_db.commit()


def test_consumer_retries_on_transient_error() -> None:
    """Transient error updates visibility and attempts; exceeding max retries routes to DLQ."""
    store_id, product_id, _ = setup_test_store_product()
    queue = PostgresQueue(session_factory=SessionLocal)
    test_queue = f"test-retry-{uuid.uuid4().hex[:8]}"
    dlq_name = f"{test_queue}-dlq"

    class FailingAdapter:
        def fetch_product_price(self, url: str) -> ScrapedPriceResult:
            raise TransientScrapingError("Simulated 503 Service Unavailable")

    consumer = ScrapingConsumer(
        queue=queue,
        service=ScrapingWorkerService(adapter=FailingAdapter(), repository=ObservationRepository()),
        session_factory=SessionLocal,
        queue_name=test_queue,
        dlq_name=dlq_name,
        max_retries=3,
        visibility_timeout=1,
    )

    msg = ScrapingMessage(
        version=1,
        job_id=uuid.uuid4(),
        store_id=store_id,
        product_ids=[product_id],
        requested_at=datetime.now(timezone.utc),
        attempt=1,
    )
    queue.send_message(test_queue, msg)

    # Attempt 1 -> fails with transient error -> visibility updated for retry
    consumer.process_next_message()

    # Force message visibility for attempt 2 in test
    db: Session = SessionLocal()
    try:
        row = db.scalars(
            select(LocalQueueMessage).where(LocalQueueMessage.queue_name == test_queue)
        ).one()
        assert row.attempts == 1
        assert row.status == "pending"
        row.visible_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

    # Attempt 2 -> fails again
    consumer.process_next_message()

    # Force visibility for attempt 3
    db = SessionLocal()
    try:
        row = db.scalars(
            select(LocalQueueMessage).where(LocalQueueMessage.queue_name == test_queue)
        ).one()
        assert row.attempts == 2
        row.visible_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

    # Attempt 3 -> reaches max_retries=3 -> sent to DLQ
    consumer.process_next_message()

    # Verify main queue has 0 messages
    assert queue.get_queue_size(test_queue) == 0

    # Verify DLQ contains the exhausted message
    db = SessionLocal()
    try:
        dlq_rows = db.scalars(
            select(LocalQueueMessage).where(LocalQueueMessage.queue_name == dlq_name)
        ).all()
        assert len(dlq_rows) == 1
        assert dlq_rows[0].status == "dlq"
        assert "MAX_RETRIES_EXCEEDED" in str(dlq_rows[0].error_reason)
        assert dlq_rows[0].attempts == 3
    finally:
        db.close()


def test_consumer_sends_invalid_schema_to_dlq_immediately() -> None:
    """Poison pill message (invalid schema) is sent to DLQ immediately without retrying."""
    queue = PostgresQueue(session_factory=SessionLocal)
    test_queue = f"test-poison-{uuid.uuid4().hex[:8]}"
    dlq_name = f"{test_queue}-dlq"

    # Send corrupt JSON payload
    queue.send_message(test_queue, '{"corrupted": true, "missing": "fields"}')

    consumer = ScrapingConsumer(
        queue=queue,
        service=ScrapingWorkerService(
            adapter=FakeStoreAdapter(), repository=ObservationRepository()
        ),
        session_factory=SessionLocal,
        queue_name=test_queue,
        dlq_name=dlq_name,
        max_retries=3,
    )

    handled = consumer.process_next_message()
    assert handled is True

    # Main queue should be empty
    assert queue.get_queue_size(test_queue) == 0

    # DLQ should have 1 poison pill record
    db: Session = SessionLocal()
    try:
        dlq_rows = db.scalars(
            select(LocalQueueMessage).where(LocalQueueMessage.queue_name == dlq_name)
        ).all()
        assert len(dlq_rows) == 1
        assert dlq_rows[0].status == "dlq"
        assert "INVALID_SCHEMA" in str(dlq_rows[0].error_reason)
    finally:
        db.close()
