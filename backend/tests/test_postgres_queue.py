"""Unit and integration tests for PostgreSQL persistent queue."""

import time
import uuid

import pytest
from shared.queue.models import LocalQueueMessage
from shared.queue.postgres import PostgresQueue
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal


@pytest.fixture(autouse=True)
def cleanup_queue_test_data():
    """Clean up test queue messages after each test to keep DB clean."""
    yield
    with SessionLocal() as db:
        db.query(LocalQueueMessage).filter(LocalQueueMessage.queue_name.like("test-%")).delete(
            synchronize_session=False
        )
        db.commit()


def test_postgres_queue_send_and_receive() -> None:
    """Verify message sending, claiming with attempts count, and deletion."""
    queue = PostgresQueue(session_factory=SessionLocal)
    test_queue = f"test-q-{uuid.uuid4().hex[:8]}"

    payload = {"key": "val", "num": 42}
    msg_id = queue.send_message(test_queue, payload)
    assert msg_id is not None

    messages = queue.receive_messages(test_queue, max_messages=1, visibility_timeout=10)
    assert len(messages) == 1
    msg = messages[0]
    assert msg.message_id == msg_id
    assert msg.attempts == 1
    assert "val" in msg.body

    # Confirm message
    queue.delete_message(test_queue, msg.receipt_handle)

    # Verify no more messages available
    remaining = queue.receive_messages(test_queue, max_messages=1)
    assert len(remaining) == 0

    # Verify status in database is completed
    db: Session = SessionLocal()
    try:
        row = db.scalars(
            select(LocalQueueMessage).where(LocalQueueMessage.id == uuid.UUID(msg_id))
        ).one()
        assert row.status == "completed"
        assert row.processed_at is not None
        assert row.receipt_handle is None
    finally:
        db.close()


def test_postgres_queue_skip_locked_concurrent_claim() -> None:
    """Verify that multiple consumers claiming concurrently receive different messages."""
    queue = PostgresQueue(session_factory=SessionLocal)
    test_queue = f"test-q-{uuid.uuid4().hex[:8]}"

    id1 = queue.send_message(test_queue, {"msg": 1})
    id2 = queue.send_message(test_queue, {"msg": 2})

    claim1 = queue.receive_messages(test_queue, max_messages=1, visibility_timeout=30)
    claim2 = queue.receive_messages(test_queue, max_messages=1, visibility_timeout=30)

    assert len(claim1) == 1
    assert len(claim2) == 1
    assert claim1[0].message_id != claim2[0].message_id
    assert {claim1[0].message_id, claim2[0].message_id} == {id1, id2}


def test_postgres_queue_visibility_recovery() -> None:
    """When a worker crashes mid-processing, message becomes available after visibility timeout."""
    queue = PostgresQueue(session_factory=SessionLocal)
    test_queue = f"test-q-{uuid.uuid4().hex[:8]}"

    msg_id = queue.send_message(test_queue, {"task": "in-flight-worker-crash"})

    # Claim with short 1-second visibility timeout
    claimed = queue.receive_messages(test_queue, max_messages=1, visibility_timeout=1)
    assert len(claimed) == 1
    assert claimed[0].attempts == 1

    # Immediately after claim, no messages should be visible
    immediate = queue.receive_messages(test_queue, max_messages=1)
    assert len(immediate) == 0

    # Wait for visibility timeout to expire (simulating worker dead or crashed)
    time.sleep(1.2)

    # After expiration, the message must be reclaimed and attempts incremented
    reclaimed = queue.receive_messages(test_queue, max_messages=1, visibility_timeout=10)
    assert len(reclaimed) == 1
    assert reclaimed[0].message_id == msg_id
    assert reclaimed[0].attempts == 2

    queue.delete_message(test_queue, reclaimed[0].receipt_handle)


def test_postgres_queue_dlq_transfer() -> None:
    """Verify transfer of message to DLQ."""
    queue = PostgresQueue(session_factory=SessionLocal)
    main_queue = f"test-main-q-{uuid.uuid4().hex[:8]}"
    dlq_name = f"test-main-dlq-{uuid.uuid4().hex[:8]}"

    queue.send_message(main_queue, {"bad": "data"})
    claimed = queue.receive_messages(main_queue, max_messages=1)
    assert len(claimed) == 1
    msg = claimed[0]

    dlq_id = queue.send_to_dlq(
        dlq_name=dlq_name,
        message_payload=msg.body,
        error_reason="MAX_RETRIES_EXCEEDED",
        attempts=msg.attempts,
        receipt_handle=msg.receipt_handle,
    )

    # Verify not in main queue
    assert queue.get_queue_size(main_queue) == 0

    # Verify present in DLQ
    db: Session = SessionLocal()
    try:
        row = db.scalars(
            select(LocalQueueMessage).where(LocalQueueMessage.id == uuid.UUID(dlq_id))
        ).one()
        assert row.queue_name == dlq_name
        assert row.status == "dlq"
        assert row.error_reason == "MAX_RETRIES_EXCEEDED"
        assert row.attempts == 1
    finally:
        db.close()
