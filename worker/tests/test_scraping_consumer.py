"""Unit and integration tests for Worker ScrapingConsumer."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from shared.queue.models import LocalQueueMessage
from shared.queue.postgres import PostgresQueue
from shared.schemas.scraping import ScrapingMessage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import ScrapedPriceResult, StoreBlockedError, TransientScrapingError
from app.adapters.fake_store_adapter import FakeStoreAdapter
from app.consumers.scraping_consumer import ScrapingConsumer
from app.db.models import PriceObservation, Store, StoreProduct
from app.db.session import SessionLocal
from app.repositories.observation_repository import ObservationRepository
from app.services.scraping_service import ScrapingWorkerService


@pytest.fixture(autouse=True)
def cleanup_consumer_test_data():
    """Clean up test queue messages after each test to keep DB clean."""
    yield
    with SessionLocal() as db:
        db.query(LocalQueueMessage).filter(LocalQueueMessage.queue_name.like("test-%")).delete(
            synchronize_session=False
        )
        db.commit()


def setup_test_store_product() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Ensure a StoreProduct exists in DB and return (store_id, product_id, store_product_id)."""
    db: Session = SessionLocal()
    try:
        sp = db.scalars(
            select(StoreProduct)
            .join(Store, StoreProduct.store_id == Store.id)
            .where(StoreProduct.is_active.is_(True), Store.is_active.is_(True))
        ).first()
        if not sp:
            store = Store(
                id=uuid.uuid4(),
                name=f"Test Active Store {uuid.uuid4().hex[:4]}",
                domain=f"test-{uuid.uuid4().hex[:6]}.pe",
                is_active=True,
            )
            db.add(store)
            db.flush()
            sp = StoreProduct(
                id=uuid.uuid4(),
                product_id=uuid.uuid4(),
                store_id=store.id,
                product_url=f"https://{store.domain}/item/{uuid.uuid4().hex[:6]}",
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


def test_consumer_acknowledges_store_blocked_without_dlq() -> None:
    """When a store is blocked by bot protection, consumer marks job completed with note.

    It does NOT retry endlessly and does NOT send to DLQ.
    """
    queue = PostgresQueue(session_factory=SessionLocal)
    test_queue = f"test-blocked-{uuid.uuid4().hex[:8]}"
    dlq_name = f"{test_queue}-dlq"

    store_id = uuid.uuid4()
    job_id = uuid.uuid4()
    msg = ScrapingMessage(
        version=1,
        job_id=job_id,
        store_id=store_id,
        product_ids=[uuid.uuid4()],
        requested_at=datetime.now(timezone.utc),
        attempt=1,
    )
    queue.send_message(test_queue, msg)

    # Mock service raising StoreBlockedError
    mock_service = MagicMock(spec=ScrapingWorkerService)
    mock_service.process_job.side_effect = StoreBlockedError(
        "Store blocked by anti-bot challenge (HTTP 403 Cloudflare): https://sercoplus.com/item"
    )

    consumer = ScrapingConsumer(
        queue=queue,
        service=mock_service,
        session_factory=SessionLocal,
        queue_name=test_queue,
        dlq_name=dlq_name,
        max_retries=3,
    )

    handled = consumer.process_next_message()
    assert handled is True

    # 1. Main queue should be empty (message deleted/acknowledged)
    assert queue.get_queue_size(test_queue) == 0

    # 2. DLQ must NOT contain any messages
    assert queue.get_queue_size(dlq_name) == 0

    # 3. Message in local_queue_messages is marked completed with SKIPPED_STORE_BLOCKED reason
    with SessionLocal() as db:
        row = db.scalars(
            select(LocalQueueMessage).where(LocalQueueMessage.queue_name == test_queue)
        ).first()
        assert row is not None
        assert row.status == "completed"
        assert "SKIPPED_STORE_BLOCKED" in str(row.error_reason)


def test_different_jobs_same_product_and_price_create_multiple_observations() -> None:
    """Different job_ids create distinct historical observations even if price/stock are equal."""
    store_id, product_id, sp_id = setup_test_store_product()
    with SessionLocal() as db_pre:
        obs_before_ids = set(
            db_pre.scalars(
                select(PriceObservation.id).where(PriceObservation.store_product_id == sp_id)
            ).all()
        )

    queue = PostgresQueue(session_factory=SessionLocal)
    test_queue = f"test-temporal-{uuid.uuid4().hex[:8]}"

    job_1 = uuid.uuid4()
    job_2 = uuid.uuid4()
    fixed_price = Decimal("350.00")

    class FixedPriceAdapter:
        def fetch_product_price(self, url: str) -> ScrapedPriceResult:
            return ScrapedPriceResult(
                price=fixed_price,
                currency="PEN",
                availability="in_stock",
                captured_at=datetime.now(timezone.utc),
            )

    consumer = ScrapingConsumer(
        queue=queue,
        service=ScrapingWorkerService(
            adapter=FixedPriceAdapter(), repository=ObservationRepository()
        ),
        session_factory=SessionLocal,
        queue_name=test_queue,
        dlq_name=f"{test_queue}-dlq",
    )

    try:
        # Job 1 (e.g. Day 1 scheduled scrape)
        msg_1 = ScrapingMessage(
            version=1,
            job_id=job_1,
            store_id=store_id,
            product_ids=[product_id],
            requested_at=datetime.now(timezone.utc),
            attempt=1,
        )
        queue.send_message(test_queue, msg_1)
        consumer.process_next_message()

        # Job 2 (e.g. Day 2 scheduled scrape - identical price and stock)
        msg_2 = ScrapingMessage(
            version=1,
            job_id=job_2,
            store_id=store_id,
            product_ids=[product_id],
            requested_at=datetime.now(timezone.utc),
            attempt=1,
        )
        queue.send_message(test_queue, msg_2)
        consumer.process_next_message()

        # Both jobs must be persisted as independent historical observations
        with SessionLocal() as db:
            new_obs = db.scalars(
                select(PriceObservation)
                .where(
                    PriceObservation.store_product_id == sp_id,
                    ~PriceObservation.id.in_(obs_before_ids),
                )
                .order_by(PriceObservation.captured_at.asc())
            ).all()

            assert len(new_obs) == 2
            assert new_obs[0].price == fixed_price
            assert new_obs[1].price == fixed_price
            assert new_obs[0].source_hash != new_obs[1].source_hash
    finally:
        with SessionLocal() as clean_db:
            clean_db.query(PriceObservation).filter(
                PriceObservation.store_product_id == sp_id,
                ~PriceObservation.id.in_(obs_before_ids),
            ).delete(synchronize_session=False)
            clean_db.commit()


def test_different_jobs_different_prices_create_multiple_observations() -> None:
    """Two different jobs with different prices create two historical observations."""
    store_id, product_id, sp_id = setup_test_store_product()
    with SessionLocal() as db_pre:
        obs_before_ids = set(
            db_pre.scalars(
                select(PriceObservation.id).where(PriceObservation.store_product_id == sp_id)
            ).all()
        )

    queue = PostgresQueue(session_factory=SessionLocal)
    test_queue = f"test-varying-{uuid.uuid4().hex[:8]}"

    job_1 = uuid.uuid4()
    job_2 = uuid.uuid4()
    price_cycle = [Decimal("400.00"), Decimal("380.00")]

    class VaryingPriceAdapter:
        def fetch_product_price(self, url: str) -> ScrapedPriceResult:
            price = price_cycle.pop(0) if price_cycle else Decimal("380.00")
            return ScrapedPriceResult(
                price=price,
                currency="PEN",
                availability="in_stock",
                captured_at=datetime.now(timezone.utc),
            )

    consumer = ScrapingConsumer(
        queue=queue,
        service=ScrapingWorkerService(
            adapter=VaryingPriceAdapter(), repository=ObservationRepository()
        ),
        session_factory=SessionLocal,
        queue_name=test_queue,
        dlq_name=f"{test_queue}-dlq",
    )

    try:
        msg_1 = ScrapingMessage(
            version=1,
            job_id=job_1,
            store_id=store_id,
            product_ids=[product_id],
            requested_at=datetime.now(timezone.utc),
            attempt=1,
        )
        queue.send_message(test_queue, msg_1)
        consumer.process_next_message()

        msg_2 = ScrapingMessage(
            version=1,
            job_id=job_2,
            store_id=store_id,
            product_ids=[product_id],
            requested_at=datetime.now(timezone.utc),
            attempt=1,
        )
        queue.send_message(test_queue, msg_2)
        consumer.process_next_message()

        with SessionLocal() as db:
            new_obs = db.scalars(
                select(PriceObservation)
                .where(
                    PriceObservation.store_product_id == sp_id,
                    ~PriceObservation.id.in_(obs_before_ids),
                )
                .order_by(PriceObservation.captured_at.asc())
            ).all()

            assert len(new_obs) == 2
            assert new_obs[0].price == Decimal("400.00")
            assert new_obs[1].price == Decimal("380.00")
            assert new_obs[0].source_hash != new_obs[1].source_hash
    finally:
        with SessionLocal() as clean_db:
            clean_db.query(PriceObservation).filter(
                PriceObservation.store_product_id == sp_id,
                ~PriceObservation.id.in_(obs_before_ids),
            ).delete(synchronize_session=False)
            clean_db.commit()


def test_same_job_retry_after_transient_error_does_not_duplicate_observations() -> None:
    """Same job_id retried after a transient error does not create duplicate observations."""
    store_id, product_id, sp_id = setup_test_store_product()
    with SessionLocal() as db_pre:
        obs_before_ids = set(
            db_pre.scalars(
                select(PriceObservation.id).where(PriceObservation.store_product_id == sp_id)
            ).all()
        )

    queue = PostgresQueue(session_factory=SessionLocal)
    test_queue = f"test-retry-idemp-{uuid.uuid4().hex[:8]}"

    job_id = uuid.uuid4()
    msg_attempt_1 = ScrapingMessage(
        version=1,
        job_id=job_id,
        store_id=store_id,
        product_ids=[product_id],
        requested_at=datetime.now(timezone.utc),
        attempt=1,
    )
    msg_attempt_2 = ScrapingMessage(
        version=1,
        job_id=job_id,
        store_id=store_id,
        product_ids=[product_id],
        requested_at=datetime.now(timezone.utc),
        attempt=2,
    )

    consumer = ScrapingConsumer(
        queue=queue,
        service=ScrapingWorkerService(
            adapter=FakeStoreAdapter(), repository=ObservationRepository()
        ),
        session_factory=SessionLocal,
        queue_name=test_queue,
        dlq_name=f"{test_queue}-dlq",
    )

    try:
        # Attempt 1 processes and creates observation
        queue.send_message(test_queue, msg_attempt_1)
        consumer.process_next_message()

        with SessionLocal() as db:
            obs_after_1 = db.scalars(
                select(PriceObservation).where(
                    PriceObservation.store_product_id == sp_id,
                    ~PriceObservation.id.in_(obs_before_ids),
                )
            ).all()
            assert len(obs_after_1) == 1

        # Attempt 2 re-delivered with identical job_id (after transient network drop)
        queue.send_message(test_queue, msg_attempt_2)
        consumer.process_next_message()

        # Total observations must strictly remain 1
        with SessionLocal() as db:
            obs_after_2 = db.scalars(
                select(PriceObservation).where(
                    PriceObservation.store_product_id == sp_id,
                    ~PriceObservation.id.in_(obs_before_ids),
                )
            ).all()
            assert len(obs_after_2) == 1
    finally:
        with SessionLocal() as clean_db:
            clean_db.query(PriceObservation).filter(
                PriceObservation.store_product_id == sp_id,
                ~PriceObservation.id.in_(obs_before_ids),
            ).delete(synchronize_session=False)
            clean_db.commit()
