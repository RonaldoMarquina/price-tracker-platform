"""Tests for ScrapingConsumer job tracking, state machine transitions, and error handling."""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from shared.queue.models import LocalQueueMessage
from shared.queue.postgres import PostgresQueue
from shared.schemas.scraping import ScrapingMessage
from sqlalchemy import select

from app.adapters.base import (
    StoreBlockedError,
    StoreDisabledError,
    TerminalInternalError,
    TransientScrapingError,
)
from app.adapters.fake_store_adapter import FakeStoreAdapter
from app.consumers.scraping_consumer import (
    InvalidStateTransitionError,
    ScrapingConsumer,
    sanitize_error,
    transition_job_status,
)
from app.db.models import PriceObservation, Product, ScrapingJob, Store, StoreProduct
from app.db.session import SessionLocal
from app.repositories.observation_repository import ObservationRepository
from app.services.scraping_service import ScrapingWorkerService


def setup_test_entities() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Ensure a valid active Store, Product and StoreProduct exist in PostgreSQL."""
    with SessionLocal() as db:
        store = db.scalars(select(Store).where(Store.is_active.is_(True))).first()
        if not store:
            store = Store(
                id=uuid.uuid4(),
                name=f"Consumer Tracking Store {uuid.uuid4().hex[:6]}",
                domain=f"tracking-{uuid.uuid4().hex[:6]}.pe",
                is_active=True,
            )
            db.add(store)
            db.flush()

        product = db.scalars(select(Product).where(Product.is_active.is_(True))).first()
        if not product:
            product = Product(
                id=uuid.uuid4(),
                category_id=uuid.uuid4(),
                name="Tracking CPU",
                slug=f"tracking-cpu-{uuid.uuid4().hex[:6]}",
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

        db.commit()
        return store.id, product.id, sp.id


@pytest.fixture(autouse=True)
def cleanup_test_data():
    """Clean up test queue messages and scraping jobs after each test."""
    yield
    with SessionLocal() as db:
        db.query(LocalQueueMessage).filter(
            LocalQueueMessage.queue_name.like("test-track-%")
        ).delete(synchronize_session=False)
        db.commit()


def test_sanitize_error_limits_length_and_multiline():
    """Verify error sanitization strips newlines and limits length to max_length."""
    assert sanitize_error(None) is None
    short_err = "Simple error"
    assert sanitize_error(short_err) == "Simple error"

    multiline_err = "Error line 1\n   Error line 2\n\n Error line 3"
    assert sanitize_error(multiline_err) == "Error line 1 Error line 2 Error line 3"

    long_err = "A" * 600
    sanitized = sanitize_error(long_err, max_length=100)
    assert len(sanitized) == 100
    assert sanitized.endswith("...")


def test_state_machine_invalid_transitions_raise_error():
    """Verify disallowed state transitions raise InvalidStateTransitionError."""
    job = ScrapingJob(
        id=uuid.uuid4(),
        store_id=uuid.uuid4(),
        status="queued",
    )

    # queued cannot jump directly to completed
    with pytest.raises(InvalidStateTransitionError):
        transition_job_status(job, "completed")

    # queued cannot jump directly to retrying
    with pytest.raises(InvalidStateTransitionError):
        transition_job_status(job, "retrying")

    # queued -> processing is valid
    transition_job_status(job, "processing")
    assert job.status == "processing"
    assert job.started_at is not None

    # retrying cannot jump to completed directly without processing
    job.status = "retrying"
    with pytest.raises(InvalidStateTransitionError):
        transition_job_status(job, "completed")

    # terminal states cannot transition further in 7A
    job.status = "completed"
    with pytest.raises(InvalidStateTransitionError):
        transition_job_status(job, "processing")


def test_consumer_reconciles_legacy_message_without_prior_scraping_job():
    """Consumer consuming older message without ScrapingJob idempotently tracks it."""
    store_id, product_id, sp_id = setup_test_entities()
    queue = PostgresQueue(session_factory=SessionLocal)
    test_queue = f"test-track-{uuid.uuid4().hex[:8]}"

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
    )

    try:
        handled = consumer.process_next_message()
        assert handled is True

        with SessionLocal() as db:
            stmt = select(ScrapingJob).where(ScrapingJob.id == job_id)
            job = db.execute(stmt).scalar_one_or_none()
            assert job is not None
            assert job.id == job_id
            assert job.store_id == store_id
            assert job.status == "completed"
            assert job.observations_created == 1
            assert job.attempts == 1
            assert job.started_at is not None
            assert job.finished_at is not None
            assert job.started_at <= job.finished_at
    finally:
        with SessionLocal() as db:
            db.query(PriceObservation).filter(PriceObservation.store_product_id == sp_id).delete()
            db.query(ScrapingJob).filter(ScrapingJob.id == job_id).delete()
            db.commit()


def test_consumer_transition_processing_to_completed_and_accurate_count():
    """Consumer transitions queued -> processing -> completed and records count."""
    store_id, product_id, sp_id = setup_test_entities()
    queue = PostgresQueue(session_factory=SessionLocal)
    test_queue = f"test-track-{uuid.uuid4().hex[:8]}"

    job_id = uuid.uuid4()
    now_utc = datetime.now(timezone.utc)

    # 1. Pre-create ScrapingJob in 'queued' status
    with SessionLocal() as db:
        job = ScrapingJob(
            id=job_id,
            store_id=store_id,
            status="queued",
            batch_size=1,
            observations_created=0,
            attempts=0,
            created_at=now_utc,
        )
        db.add(job)
        db.commit()

    msg = ScrapingMessage(
        version=1,
        job_id=job_id,
        store_id=store_id,
        product_ids=[product_id],
        requested_at=now_utc,
        attempt=1,
    )
    queue.send_message(test_queue, msg)

    consumer = ScrapingConsumer(
        queue=queue,
        service=ScrapingWorkerService(
            adapter=FakeStoreAdapter(default_price=Decimal("250.00")),
            repository=ObservationRepository(),
        ),
        session_factory=SessionLocal,
        queue_name=test_queue,
        dlq_name=f"{test_queue}-dlq",
    )

    try:
        handled = consumer.process_next_message()
        assert handled is True

        with SessionLocal() as db:
            persisted_job = db.execute(
                select(ScrapingJob).where(ScrapingJob.id == job_id)
            ).scalar_one_or_none()
            assert persisted_job is not None
            assert persisted_job.status == "completed"
            assert persisted_job.observations_created == 1
            assert persisted_job.attempts == 1
            assert persisted_job.started_at is not None
            assert persisted_job.finished_at is not None
            assert persisted_job.finished_at >= persisted_job.started_at
            assert persisted_job.error_reason is None
    finally:
        with SessionLocal() as db:
            db.query(PriceObservation).filter(PriceObservation.store_product_id == sp_id).delete()
            db.query(ScrapingJob).filter(ScrapingJob.id == job_id).delete()
            db.commit()


def test_consumer_transition_processing_to_retrying_to_processing_to_completed():
    """Transient error transitions to retrying; retry completes with same started_at."""
    store_id, product_id, sp_id = setup_test_entities()
    queue = PostgresQueue(session_factory=SessionLocal)
    test_queue = f"test-track-{uuid.uuid4().hex[:8]}"

    job_id = uuid.uuid4()
    now_utc = datetime.now(timezone.utc)

    with SessionLocal() as db:
        job = ScrapingJob(
            id=job_id,
            store_id=store_id,
            status="queued",
            batch_size=1,
            attempts=0,
            created_at=now_utc,
        )
        db.add(job)
        db.commit()

    msg = ScrapingMessage(
        version=1,
        job_id=job_id,
        store_id=store_id,
        product_ids=[product_id],
        requested_at=now_utc,
        attempt=1,
    )
    queue.send_message(test_queue, msg)

    # Attempt 1: Mock service raises TransientScrapingError
    failing_service = MagicMock(spec=ScrapingWorkerService)
    failing_service.process_job.side_effect = TransientScrapingError("503 Service Unavailable")

    consumer_attempt1 = ScrapingConsumer(
        queue=queue,
        service=failing_service,
        session_factory=SessionLocal,
        queue_name=test_queue,
        dlq_name=f"{test_queue}-dlq",
        max_retries=3,
    )

    try:
        handled1 = consumer_attempt1.process_next_message()
        assert handled1 is True

        with SessionLocal() as db:
            job1 = db.execute(select(ScrapingJob).where(ScrapingJob.id == job_id)).scalar_one()
            assert job1.status == "retrying"
            assert job1.attempts == 1
            assert job1.started_at is not None
            first_started_at = job1.started_at
            assert job1.finished_at is None  # retrying MUST NOT set finished_at
            assert "503 Service Unavailable" in str(job1.error_reason)

        # Make message visible again for attempt 2
        with SessionLocal() as db:
            db.query(LocalQueueMessage).filter(LocalQueueMessage.queue_name == test_queue).update(
                {"visible_at": datetime.now(timezone.utc) - timedelta(seconds=5)}
            )
            db.commit()

        # Attempt 2: Service succeeds
        consumer_attempt2 = ScrapingConsumer(
            queue=queue,
            service=ScrapingWorkerService(
                adapter=FakeStoreAdapter(), repository=ObservationRepository()
            ),
            session_factory=SessionLocal,
            queue_name=test_queue,
            dlq_name=f"{test_queue}-dlq",
            max_retries=3,
        )

        handled2 = consumer_attempt2.process_next_message()
        assert handled2 is True

        with SessionLocal() as db:
            job2 = db.execute(select(ScrapingJob).where(ScrapingJob.id == job_id)).scalar_one()
            assert job2.status == "completed"
            assert job2.attempts == 2
            assert job2.started_at == first_started_at  # started_at preserved from attempt 1
            assert job2.finished_at is not None
            assert job2.finished_at >= job2.started_at
            assert job2.observations_created == 1
    finally:
        with SessionLocal() as db:
            db.query(PriceObservation).filter(PriceObservation.store_product_id == sp_id).delete()
            db.query(ScrapingJob).filter(ScrapingJob.id == job_id).delete()
            db.commit()


def test_consumer_transition_skipped_store_disabled():
    """StoreDisabledError transitions to skipped without retries or DLQ."""
    store_id, product_id, _ = setup_test_entities()
    queue = PostgresQueue(session_factory=SessionLocal)
    test_queue = f"test-track-{uuid.uuid4().hex[:8]}"
    dlq_name = f"{test_queue}-dlq"

    job_id = uuid.uuid4()
    with SessionLocal() as db:
        job = ScrapingJob(id=job_id, store_id=store_id, status="queued", batch_size=1)
        db.add(job)
        db.commit()

    msg = ScrapingMessage(
        version=1,
        job_id=job_id,
        store_id=store_id,
        product_ids=[product_id],
        requested_at=datetime.now(timezone.utc),
        attempt=1,
    )
    queue.send_message(test_queue, msg)

    mock_service = MagicMock(spec=ScrapingWorkerService)
    mock_service.process_job.side_effect = StoreDisabledError("Store has been deactivated by admin")

    consumer = ScrapingConsumer(
        queue=queue,
        service=mock_service,
        session_factory=SessionLocal,
        queue_name=test_queue,
        dlq_name=dlq_name,
    )

    try:
        handled = consumer.process_next_message()
        assert handled is True
        assert queue.get_queue_size(test_queue) == 0
        assert queue.get_queue_size(dlq_name) == 0

        with SessionLocal() as db:
            persisted = db.execute(select(ScrapingJob).where(ScrapingJob.id == job_id)).scalar_one()
            assert persisted.status == "skipped"
            assert "SKIPPED_STORE_DISABLED" in str(persisted.error_reason)
            assert persisted.finished_at is not None
            assert persisted.observations_created == 0
    finally:
        with SessionLocal() as db:
            db.query(ScrapingJob).filter(ScrapingJob.id == job_id).delete()
            db.commit()


def test_consumer_transition_skipped_store_blocked():
    """StoreBlockedError transitions to skipped with SKIPPED_STORE_BLOCKED."""
    store_id, product_id, _ = setup_test_entities()
    queue = PostgresQueue(session_factory=SessionLocal)
    test_queue = f"test-track-{uuid.uuid4().hex[:8]}"
    dlq_name = f"{test_queue}-dlq"

    job_id = uuid.uuid4()
    with SessionLocal() as db:
        job = ScrapingJob(id=job_id, store_id=store_id, status="queued", batch_size=1)
        db.add(job)
        db.commit()

    msg = ScrapingMessage(
        version=1,
        job_id=job_id,
        store_id=store_id,
        product_ids=[product_id],
        requested_at=datetime.now(timezone.utc),
        attempt=1,
    )
    queue.send_message(test_queue, msg)

    mock_service = MagicMock(spec=ScrapingWorkerService)
    mock_service.process_job.side_effect = StoreBlockedError("Cloudflare 403 Challenge")

    consumer = ScrapingConsumer(
        queue=queue,
        service=mock_service,
        session_factory=SessionLocal,
        queue_name=test_queue,
        dlq_name=dlq_name,
    )

    try:
        handled = consumer.process_next_message()
        assert handled is True
        assert queue.get_queue_size(test_queue) == 0
        assert queue.get_queue_size(dlq_name) == 0

        with SessionLocal() as db:
            persisted = db.execute(select(ScrapingJob).where(ScrapingJob.id == job_id)).scalar_one()
            assert persisted.status == "skipped"
            assert "SKIPPED_STORE_BLOCKED" in str(persisted.error_reason)
            assert persisted.finished_at is not None
            assert persisted.sent_to_dlq_at is None
            assert persisted.replay_count == 0
            assert persisted.replayed_at is None
    finally:
        with SessionLocal() as db:
            db.query(ScrapingJob).filter(ScrapingJob.id == job_id).delete()
            db.commit()


def test_consumer_transition_exhausted_retries_to_dead_letter():
    """When attempts reach max_retries, error transitions to dead_letter with DLQ."""
    store_id, product_id, _ = setup_test_entities()
    queue = PostgresQueue(session_factory=SessionLocal)
    test_queue = f"test-track-{uuid.uuid4().hex[:8]}"
    dlq_name = f"{test_queue}-dlq"

    job_id = uuid.uuid4()
    with SessionLocal() as db:
        job = ScrapingJob(id=job_id, store_id=store_id, status="queued", batch_size=1)
        db.add(job)
        db.commit()

    msg = ScrapingMessage(
        version=1,
        job_id=job_id,
        store_id=store_id,
        product_ids=[product_id],
        requested_at=datetime.now(timezone.utc),
        attempt=1,
    )
    queue.send_message(test_queue, msg)

    # Set attempts = 2 so the next claim becomes attempts = 3 (= max_retries)
    with SessionLocal() as db:
        db.query(LocalQueueMessage).filter(LocalQueueMessage.queue_name == test_queue).update(
            {"attempts": 2}
        )
        db.commit()

    mock_service = MagicMock(spec=ScrapingWorkerService)
    mock_service.process_job.side_effect = TransientScrapingError("Gateway Timeout 504")

    consumer = ScrapingConsumer(
        queue=queue,
        service=mock_service,
        session_factory=SessionLocal,
        queue_name=test_queue,
        dlq_name=dlq_name,
        max_retries=3,
    )

    try:
        handled = consumer.process_next_message()
        assert handled is True

        with SessionLocal() as db:
            dlq_rows = db.scalars(
                select(LocalQueueMessage).where(LocalQueueMessage.queue_name == dlq_name)
            ).all()
            assert len(dlq_rows) == 1
            assert dlq_rows[0].status == "dlq"

        with SessionLocal() as db:
            persisted = db.execute(select(ScrapingJob).where(ScrapingJob.id == job_id)).scalar_one()
            assert persisted.status == "dead_letter"
            assert persisted.attempts == 3
            assert "MAX_RETRIES_EXCEEDED" in str(persisted.error_reason)
            assert persisted.finished_at is not None
    finally:
        with SessionLocal() as db:
            db.query(LocalQueueMessage).filter(LocalQueueMessage.queue_name == dlq_name).delete()
            db.query(ScrapingJob).filter(ScrapingJob.id == job_id).delete()
            db.commit()


def test_consumer_transition_terminal_internal_error_to_failed():
    """TerminalInternalError transitions to failed, deletes queue msg, no DLQ."""
    store_id, product_id, _ = setup_test_entities()
    queue = PostgresQueue(session_factory=SessionLocal)
    test_queue = f"test-track-{uuid.uuid4().hex[:8]}"
    dlq_name = f"{test_queue}-dlq"

    job_id = uuid.uuid4()
    with SessionLocal() as db:
        job = ScrapingJob(id=job_id, store_id=store_id, status="queued", batch_size=1)
        db.add(job)
        db.commit()

    msg = ScrapingMessage(
        version=1,
        job_id=job_id,
        store_id=store_id,
        product_ids=[product_id],
        requested_at=datetime.now(timezone.utc),
        attempt=1,
    )
    queue.send_message(test_queue, msg)

    mock_service = MagicMock(spec=ScrapingWorkerService)
    mock_service.process_job.side_effect = TerminalInternalError("Unrecoverable format failure")

    consumer = ScrapingConsumer(
        queue=queue,
        service=mock_service,
        session_factory=SessionLocal,
        queue_name=test_queue,
        dlq_name=dlq_name,
    )

    try:
        handled = consumer.process_next_message()
        assert handled is True
        # Main queue message is acknowledged/deleted
        assert queue.get_queue_size(test_queue) == 0
        # DLQ remains empty!
        assert queue.get_queue_size(dlq_name) == 0

        with SessionLocal() as db:
            persisted = db.execute(select(ScrapingJob).where(ScrapingJob.id == job_id)).scalar_one()
            assert persisted.status == "failed"
            assert "FAILED_TERMINAL_ERROR" in str(persisted.error_reason)
            assert persisted.finished_at is not None
    finally:
        with SessionLocal() as db:
            db.query(ScrapingJob).filter(ScrapingJob.id == job_id).delete()
            db.commit()


def test_consumer_idempotency_double_processing_same_job():
    """Delivering message for already completed job acknowledges without re-executing."""
    store_id, product_id, sp_id = setup_test_entities()
    queue = PostgresQueue(session_factory=SessionLocal)
    test_queue = f"test-track-{uuid.uuid4().hex[:8]}"

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

    mock_service = MagicMock(spec=ScrapingWorkerService)
    mock_service.process_job.return_value = 1

    consumer = ScrapingConsumer(
        queue=queue,
        service=mock_service,
        session_factory=SessionLocal,
        queue_name=test_queue,
        dlq_name=f"{test_queue}-dlq",
    )

    try:
        # Run 1: completed
        consumer.process_next_message()
        assert mock_service.process_job.call_count == 1

        with SessionLocal() as db:
            job = db.execute(select(ScrapingJob).where(ScrapingJob.id == job_id)).scalar_one()
            assert job.status == "completed"

        # Re-deliver message with exact same job_id
        queue.send_message(test_queue, msg)

        # Run 2: Idempotent bypass
        consumer.process_next_message()
        # process_job was NOT called again
        assert mock_service.process_job.call_count == 1
        # Message was still acknowledged/deleted from queue
        assert queue.get_queue_size(test_queue) == 0
    finally:
        with SessionLocal() as db:
            db.query(ScrapingJob).filter(ScrapingJob.id == job_id).delete()
            db.commit()


def test_consumer_recovery_from_abandoned_processing():
    """Abandoned processing recovers on subsequent claim and completes cleanly."""
    store_id, product_id, sp_id = setup_test_entities()
    queue = PostgresQueue(session_factory=SessionLocal)
    test_queue = f"test-track-{uuid.uuid4().hex[:8]}"

    job_id = uuid.uuid4()
    initial_started_at = datetime.now(timezone.utc) - timedelta(minutes=5)

    # 1. ScrapingJob left in 'processing' by crashed worker
    with SessionLocal() as db:
        job = ScrapingJob(
            id=job_id,
            store_id=store_id,
            status="processing",
            batch_size=1,
            attempts=1,
            started_at=initial_started_at,
            created_at=initial_started_at - timedelta(minutes=1),
        )
        db.add(job)
        db.commit()

    # 2. Enqueue message with expired visibility (simulating abandoned message)
    msg = ScrapingMessage(
        version=1,
        job_id=job_id,
        store_id=store_id,
        product_ids=[product_id],
        requested_at=initial_started_at,
        attempt=1,
    )
    queue.send_message(test_queue, msg)
    with SessionLocal() as db:
        db.query(LocalQueueMessage).filter(LocalQueueMessage.queue_name == test_queue).update(
            {
                "attempts": 1,
                "status": "processing",
                "visible_at": datetime.now(timezone.utc) - timedelta(seconds=1),
            }
        )
        db.commit()

    # 3. New consumer claims the message
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
        handled = consumer.process_next_message()
        assert handled is True

        with SessionLocal() as db:
            stmt = select(ScrapingJob).where(ScrapingJob.id == job_id)
            recovered_job = db.execute(stmt).scalar_one()
            assert recovered_job.status == "completed"
            assert recovered_job.attempts == 2  # Incremented attempt on reclaim
            assert recovered_job.started_at == initial_started_at  # Preserved original start time
            assert recovered_job.finished_at is not None
            assert recovered_job.observations_created == 1
    finally:
        with SessionLocal() as db:
            db.query(PriceObservation).filter(PriceObservation.store_product_id == sp_id).delete()
            db.query(ScrapingJob).filter(ScrapingJob.id == job_id).delete()
            db.commit()


def test_consumer_processes_replayed_job_with_observation_idempotency():
    """Verify replayed message is processed without duplicating observations or double counting."""
    import hashlib

    store_id, product_id, sp_id = setup_test_entities()
    job_id = uuid.uuid4()
    test_queue = f"test-replayed-queue-{uuid.uuid4().hex[:8]}"
    queue = PostgresQueue(session_factory=SessionLocal)

    # 1. Simulate pre-existing observation created in prior execution
    idempotency_key = f"{job_id}:{sp_id}"
    source_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()

    with SessionLocal() as db:
        obs = PriceObservation(
            id=uuid.uuid4(),
            store_product_id=sp_id,
            price=Decimal("199.99"),
            currency="PEN",
            availability="in_stock",
            price_condition="cash_or_bank_transfer",
            source_hash=source_hash,
            captured_at=datetime.now(timezone.utc) - timedelta(minutes=20),
        )
        db.add(obs)

        # 2. Replayed job in queued state with attempts reset and cumulative observations=1
        replayed_job = ScrapingJob(
            id=job_id,
            store_id=store_id,
            status="queued",
            trigger_type="manual",
            batch_size=1,
            attempts=0,
            observations_created=1,
            replay_count=1,
            replayed_at=datetime.now(timezone.utc),
            last_dlq_reason="Previous fatal error",
        )
        db.add(replayed_job)
        db.commit()

    # 3. Enqueue replayed message with attempt=1
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
    )

    try:
        handled = consumer.process_next_message()
        assert handled is True

        with SessionLocal() as db:
            stmt = select(ScrapingJob).where(ScrapingJob.id == job_id)
            job = db.execute(stmt).scalar_one()
            assert job.status == "completed"
            assert job.attempts == 1
            # Cumulative total preserved (no duplicate observation counted)
            assert job.observations_created == 1
            assert job.error_reason is None

            # Verify no duplicate PriceObservation inserted
            stmt_obs = select(PriceObservation).where(PriceObservation.store_product_id == sp_id)
            all_obs = db.execute(stmt_obs).scalars().all()
            assert len(all_obs) == 1
            assert all_obs[0].source_hash == source_hash
    finally:
        with SessionLocal() as db:
            db.query(PriceObservation).filter(PriceObservation.store_product_id == sp_id).delete()
            db.query(ScrapingJob).filter(ScrapingJob.id == job_id).delete()
            db.commit()


def test_replayed_message_resets_attempt_counter_and_does_not_immediately_dlq():
    """Demonstrate a replayed message (attempts=0, attempt=1) retries normally
    instead of immediate DLQ."""
    store_id, product_id, sp_id = setup_test_entities()
    job_id = uuid.uuid4()
    test_queue = f"test-replayed-retry-queue-{uuid.uuid4().hex[:8]}"
    queue = PostgresQueue(session_factory=SessionLocal)

    with SessionLocal() as db:
        replayed_job = ScrapingJob(
            id=job_id,
            store_id=store_id,
            status="queued",
            trigger_type="manual",
            batch_size=1,
            attempts=0,
            replay_count=1,
            replayed_at=datetime.now(timezone.utc),
        )
        db.add(replayed_job)
        db.commit()

    # Enqueue message with attempt=1 (reset by replay)
    msg = ScrapingMessage(
        version=1,
        job_id=job_id,
        store_id=store_id,
        product_ids=[product_id],
        requested_at=datetime.now(timezone.utc),
        attempt=1,
    )
    queue.send_message(test_queue, msg)

    # Mock adapter to raise a transient error
    mock_adapter = MagicMock()
    mock_adapter.fetch_product_price.side_effect = TransientScrapingError(
        "Temporary network hiccup"
    )

    consumer = ScrapingConsumer(
        queue=queue,
        service=ScrapingWorkerService(adapter=mock_adapter, repository=ObservationRepository()),
        session_factory=SessionLocal,
        queue_name=test_queue,
        dlq_name=f"{test_queue}-dlq",
        max_retries=3,
    )

    try:
        handled = consumer.process_next_message()
        assert handled is True

        with SessionLocal() as db:
            stmt = select(ScrapingJob).where(ScrapingJob.id == job_id)
            job = db.execute(stmt).scalar_one()
            # Must transition to retrying, NOT dead_letter!
            assert job.status == "retrying"
            assert job.attempts == 1

            # DLQ queue must be empty
            assert queue.get_queue_size(f"{test_queue}-dlq") == 0
    finally:
        with SessionLocal() as db:
            db.query(PriceObservation).filter(PriceObservation.store_product_id == sp_id).delete()
            db.query(ScrapingJob).filter(ScrapingJob.id == job_id).delete()
            db.commit()
