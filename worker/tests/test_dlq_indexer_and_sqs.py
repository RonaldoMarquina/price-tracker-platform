"""Tests for DlqIndexerService, quarantine handling,
worker atomic claim, and redelivery idempotency.
"""

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select, text

# Disable AWS metadata discovery offline
os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "test-key-id"
os.environ["AWS_SECRET_ACCESS_KEY"] = "test-secret-key"

from shared.queue.base import QueueMessage
from shared.schemas.scraping import ScrapingMessage

from app.adapters.base import StoreBlockedError
from app.consumers.scraping_consumer import ScrapingConsumer
from app.db.models import (
    Category,
    Product,
    ScrapingDlqLedger,
    ScrapingJob,
    ScrapingQuarantine,
    Store,
    StoreProduct,
)
from app.db.session import SessionLocal
from app.services.dlq_indexer import DlqIndexerService
from app.services.scraping_service import ScrapingWorkerService


class FakeSqsQueue:
    """In-memory SQS queue simulator for deterministic offline testing."""

    def __init__(self, queue_url: str = "https://sqs.us-east-1.amazonaws.com/123456789012/dlq"):
        self.queue_url = queue_url
        self.messages: list[QueueMessage] = []
        self.deleted_handles: list[str] = []
        self.delete_message_fail = False

    def send_message(self, queue_name: str, message: Any, session: Any = None) -> str:
        body = message if isinstance(message, str) else json.dumps(message)
        msg_id = f"msg-{uuid.uuid4().hex[:8]}"
        rh = f"rh-{uuid.uuid4().hex[:8]}"
        self.messages.append(
            QueueMessage(
                message_id=msg_id,
                receipt_handle=rh,
                body=body,
                attempts=1,
            )
        )
        return msg_id

    def receive_messages(
        self, queue_name: str, max_messages: int = 10, visibility_timeout: int = 30
    ) -> list[QueueMessage]:
        result = self.messages[:max_messages]
        return result

    def delete_message(
        self, queue_name: str, receipt_handle: str, error_reason: str | None = None
    ) -> None:
        if self.delete_message_fail:
            raise RuntimeError("Simulated SQS DeleteMessage network error")
        self.deleted_handles.append(receipt_handle)
        self.messages = [m for m in self.messages if m.receipt_handle != receipt_handle]

    def change_message_visibility(
        self, queue_name: str, receipt_handle: str, visibility_timeout: int
    ) -> None:
        pass


@pytest.fixture(autouse=True)
def cleanup_worker_test_data():
    """Ensure test tables are cleaned up after each test."""
    yield
    with SessionLocal() as db:
        db.execute(
            text(
                "DELETE FROM scraping_quarantine WHERE provider_message_id LIKE '%test%' "
                "OR quarantine_type IN ('invalid_payload', 'missing_job')"
            )
        )
        db.execute(
            text(
                "DELETE FROM scraping_dlq_ledger WHERE store_id IN ("
                "SELECT id FROM stores WHERE domain LIKE 'test-sqs-%')"
            )
        )
        db.execute(
            text(
                "DELETE FROM scraping_jobs WHERE store_id IN ("
                "SELECT id FROM stores WHERE domain LIKE 'test-sqs-%')"
            )
        )
        db.execute(
            text(
                "DELETE FROM store_products WHERE store_id IN ("
                "SELECT id FROM stores WHERE domain LIKE 'test-sqs-%')"
            )
        )
        db.execute(text("DELETE FROM stores WHERE domain LIKE 'test-sqs-%'"))
        db.commit()


def setup_test_store_product() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Helper to create a valid Store, Product, and StoreProduct in DB."""
    with SessionLocal() as db:
        store = Store(
            id=uuid.uuid4(),
            name=f"Store-{uuid.uuid4().hex[:6]}",
            domain=f"test-sqs-{uuid.uuid4().hex[:6]}.com",
            is_active=True,
        )
        cat = Category(name=f"Cat-{uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
        db.add_all([store, cat])
        db.flush()

        prod = Product(name="Test Product", slug=f"prod-{uuid.uuid4().hex[:6]}", category_id=cat.id)
        db.add(prod)
        db.flush()

        sp = StoreProduct(
            store_id=store.id,
            product_id=prod.id,
            product_url=f"https://{store.domain}/p1",
            is_active=True,
        )
        db.add(sp)
        db.commit()
        return store.id, prod.id, sp.id


def test_dlq_indexer_quarantine_invalid_payload():
    """Requirement 9: Quarantine invalid payload without deleting until committed."""
    sqs = FakeSqsQueue()
    indexer = DlqIndexerService(session_factory=SessionLocal, sqs_queue_service=sqs)

    bad_body = "{invalid_json: 123"
    msg_id = "test-bad-msg-1"
    rh = "rh-bad-1"
    sqs.messages.append(
        QueueMessage(
            message_id=msg_id,
            receipt_handle=rh,
            body=bad_body,
            attempts=3,
        )
    )

    processed = indexer.process_cycle(max_messages=10)
    assert processed == 0  # Quarantined messages don't count as successfully indexed jobs
    assert rh in sqs.deleted_handles

    with SessionLocal() as db:
        q_row = db.scalars(
            select(ScrapingQuarantine).where(ScrapingQuarantine.provider_message_id == msg_id)
        ).first()
        assert q_row is not None
        assert q_row.quarantine_type == "invalid_payload"
        assert q_row.body_sha256 == hashlib.sha256(bad_body.encode("utf-8")).hexdigest()
        assert q_row.status == "quarantined"
        assert q_row.attempts == 3


def test_dlq_indexer_quarantine_missing_job():
    """Requirement 9: Quarantine messages whose ScrapingJob does not exist."""
    sqs = FakeSqsQueue()
    indexer = DlqIndexerService(session_factory=SessionLocal, sqs_queue_service=sqs)

    nonexistent_job_id = uuid.uuid4()
    msg = ScrapingMessage(
        version=1,
        job_id=nonexistent_job_id,
        store_id=uuid.uuid4(),
        product_ids=[uuid.uuid4()],
        requested_at=datetime.now(timezone.utc),
        attempt=3,
    )
    body = msg.model_dump_json()
    msg_id = "test-missing-job-msg-2"
    rh = "rh-missing-2"
    sqs.messages.append(
        QueueMessage(
            message_id=msg_id,
            receipt_handle=rh,
            body=body,
            attempts=3,
        )
    )

    processed = indexer.process_cycle(max_messages=10)
    assert processed == 0
    assert rh in sqs.deleted_handles

    with SessionLocal() as db:
        q_row = db.scalars(
            select(ScrapingQuarantine).where(ScrapingQuarantine.provider_message_id == msg_id)
        ).first()
        assert q_row is not None
        assert q_row.quarantine_type == "missing_job"
        assert str(nonexistent_job_id) in q_row.error_reason


def test_dlq_indexer_redelivery_after_failed_delete_no_job_regression():
    """Requirement 2: Redelivery after failed DeleteMessage must NOT alter ScrapingJob or Ledger."""
    store_id, prod_id, sp_id = setup_test_store_product()
    now_utc = datetime.now(timezone.utc)

    # 1. Create ScrapingJob in retrying
    job_id = uuid.uuid4()
    logical_msg_id = uuid.uuid4()
    msg = ScrapingMessage(
        version=1,
        job_id=job_id,
        store_id=store_id,
        product_ids=[prod_id],
        requested_at=now_utc,
        attempt=3,
        logical_message_id=logical_msg_id,
        root_logical_message_id=logical_msg_id,
    )

    with SessionLocal() as db:
        job = ScrapingJob(
            id=job_id,
            store_id=store_id,
            status="retrying",
            trigger_type="manual",
            batch_size=1,
            attempts=3,
            error_reason="Connection error",
            payload=msg.model_dump(mode="json"),
            created_at=now_utc,
        )
        db.add(job)
        db.commit()

    sqs = FakeSqsQueue()
    indexer = DlqIndexerService(session_factory=SessionLocal, sqs_queue_service=sqs)

    # Put physical message in DLQ
    body_str = msg.model_dump_json()
    msg_id = "test-redelivery-msg"
    rh = "rh-redelivery-1"
    sqs.messages.append(
        QueueMessage(
            message_id=msg_id,
            receipt_handle=rh,
            body=body_str,
            attempts=3,
        )
    )

    # 2. Simulate DeleteMessage failure during first indexing run
    sqs.delete_message_fail = True
    processed = indexer.process_cycle(max_messages=1)
    assert processed == 1

    # Verify job became dead_letter and ledger created
    with SessionLocal() as db:
        j1 = db.get(ScrapingJob, job_id)
        assert j1.status == "dead_letter"
        l1 = db.get(ScrapingDlqLedger, logical_msg_id)
        assert l1 is not None
        assert l1.status == "in_dlq"
        orig_sent_at = l1.sent_to_dlq_at

    # 3. Operator replays the job -> job becomes queued, ledger becomes replay_pending
    with SessionLocal() as db:
        j_replay = db.get(ScrapingJob, job_id)
        j_replay.status = "queued"
        j_replay.replay_count = 1
        new_active_logical_id = uuid.uuid4()
        new_payload = dict(msg.model_dump(mode="json"))
        new_payload["logical_message_id"] = str(new_active_logical_id)
        j_replay.payload = new_payload

        l_replay = db.get(ScrapingDlqLedger, logical_msg_id)
        l_replay.status = "replay_pending"
        db.commit()

    # 4. Same physical message is delivered again (redelivery from DLQ)
    # Restore DeleteMessage to succeed now
    sqs.delete_message_fail = False
    processed_2 = indexer.process_cycle(max_messages=1)
    assert processed_2 == 0  # Redelivery already in ledger does NOT count as new job indexed
    assert rh in sqs.deleted_handles

    # 5. Verify ScrapingJob remained queued and ledger remained replay_pending!
    with SessionLocal() as db:
        j_final = db.get(ScrapingJob, job_id)
        assert j_final.status == "queued"  # MUST NOT regress to dead_letter!

        l_final = db.get(ScrapingDlqLedger, logical_msg_id)
        assert l_final.status == "replay_pending"  # MUST NOT be overwritten!
        assert l_final.sent_to_dlq_at == orig_sent_at


def test_dlq_indexer_obsolete_cycle_does_not_revert_job():
    """Requirement 3: An obsolete logical_message_id must NOT revert active job to dead_letter."""
    store_id, prod_id, sp_id = setup_test_store_product()
    now_utc = datetime.now(timezone.utc)

    job_id = uuid.uuid4()
    old_logical_id = uuid.uuid4()
    active_logical_id = uuid.uuid4()

    # ScrapingJob is actively queued or processing in cycle 2
    active_msg = ScrapingMessage(
        version=1,
        job_id=job_id,
        store_id=store_id,
        product_ids=[prod_id],
        requested_at=now_utc,
        attempt=1,
        logical_message_id=active_logical_id,
    )
    with SessionLocal() as db:
        job = ScrapingJob(
            id=job_id,
            store_id=store_id,
            status="processing",
            trigger_type="manual",
            batch_size=1,
            attempts=1,
            payload=active_msg.model_dump(mode="json"),
            created_at=now_utc,
            started_at=now_utc,
        )
        db.add(job)
        db.commit()

    # Physical DLQ delivers a message with old_logical_id from cycle 1
    obsolete_msg = ScrapingMessage(
        version=1,
        job_id=job_id,
        store_id=store_id,
        product_ids=[prod_id],
        requested_at=now_utc - timedelta(minutes=10),
        attempt=3,
        logical_message_id=old_logical_id,
    )
    sqs = FakeSqsQueue()
    indexer = DlqIndexerService(session_factory=SessionLocal, sqs_queue_service=sqs)
    sqs.messages.append(
        QueueMessage(
            message_id="obsolete-msg-1",
            receipt_handle="rh-obs-1",
            body=obsolete_msg.model_dump_json(),
            attempts=3,
        )
    )

    processed = indexer.process_cycle(max_messages=1)
    assert processed == 0
    assert "rh-obs-1" in sqs.deleted_handles

    with SessionLocal() as db:
        j = db.get(ScrapingJob, job_id)
        assert j.status == "processing"  # Unchanged!


def test_dlq_indexer_completed_or_skipped_never_returns_to_dead_letter():
    """Requirement 3: Completed or skipped jobs must NEVER return to dead_letter."""
    store_id, prod_id, sp_id = setup_test_store_product()
    now_utc = datetime.now(timezone.utc)

    job_id = uuid.uuid4()
    msg = ScrapingMessage(
        version=1,
        job_id=job_id,
        store_id=store_id,
        product_ids=[prod_id],
        requested_at=now_utc,
        attempt=3,
    )

    with SessionLocal() as db:
        job = ScrapingJob(
            id=job_id,
            store_id=store_id,
            status="completed",
            trigger_type="manual",
            batch_size=1,
            observations_created=1,
            attempts=1,
            payload=msg.model_dump(mode="json"),
            created_at=now_utc,
            finished_at=now_utc,
        )
        db.add(job)
        db.commit()

    sqs = FakeSqsQueue()
    indexer = DlqIndexerService(session_factory=SessionLocal, sqs_queue_service=sqs)
    sqs.messages.append(
        QueueMessage(
            message_id="dlq-after-completed",
            receipt_handle="rh-comp-1",
            body=msg.model_dump_json(),
            attempts=3,
        )
    )

    processed = indexer.process_cycle(max_messages=1)
    assert processed == 0
    assert "rh-comp-1" in sqs.deleted_handles

    with SessionLocal() as db:
        j = db.get(ScrapingJob, job_id)
        assert j.status == "completed"  # Stays completed!


def test_multi_cycle_dlq_failure_retains_ledger_history():
    """Requirement 12: Multi failures across replays create separate ledger rows."""
    store_id, prod_id, sp_id = setup_test_store_product()
    now_utc = datetime.now(timezone.utc)

    job_id = uuid.uuid4()
    logical_1 = uuid.uuid4()
    logical_2 = uuid.uuid4()

    # Cycle 1 lands in DLQ
    msg1 = ScrapingMessage(
        version=1,
        job_id=job_id,
        store_id=store_id,
        product_ids=[prod_id],
        requested_at=now_utc,
        attempt=3,
        logical_message_id=logical_1,
        root_logical_message_id=logical_1,
    )
    with SessionLocal() as db:
        job = ScrapingJob(
            id=job_id,
            store_id=store_id,
            status="retrying",
            trigger_type="manual",
            batch_size=1,
            attempts=3,
            payload=msg1.model_dump(mode="json"),
            created_at=now_utc,
        )
        db.add(job)
        db.commit()

    sqs = FakeSqsQueue()
    indexer = DlqIndexerService(session_factory=SessionLocal, sqs_queue_service=sqs)
    sqs.messages.append(
        QueueMessage(
            message_id="cycle-1-dlq",
            receipt_handle="rh-c1",
            body=msg1.model_dump_json(),
            attempts=3,
        )
    )
    indexer.process_cycle(max_messages=1)

    # Replay happens, updates payload to cycle 2
    msg2 = ScrapingMessage(
        version=1,
        job_id=job_id,
        store_id=store_id,
        product_ids=[prod_id],
        requested_at=now_utc,
        attempt=3,
        logical_message_id=logical_2,
        root_logical_message_id=logical_1,  # Same root
        replayed_from_message_id=logical_1,
    )
    with SessionLocal() as db:
        j = db.get(ScrapingJob, job_id)
        j.status = "retrying"
        j.replay_count = 1
        j.payload = msg2.model_dump(mode="json")
        db.commit()

    # Cycle 2 fails and lands in DLQ
    sqs.messages.append(
        QueueMessage(
            message_id="cycle-2-dlq",
            receipt_handle="rh-c2",
            body=msg2.model_dump_json(),
            attempts=3,
        )
    )
    indexer.process_cycle(max_messages=1)

    # Verify both ledger rows exist and root_logical_message_id is preserved!
    with SessionLocal() as db:
        l1 = db.get(ScrapingDlqLedger, logical_1)
        l2 = db.get(ScrapingDlqLedger, logical_2)
        assert l1 is not None
        assert l2 is not None
        assert l2.replayed_from_message_id == logical_1
        assert l1.root_logical_message_id == logical_1
        assert l2.root_logical_message_id == logical_1


def test_store_blocked_error_never_sent_to_dlq_or_ledger():
    """Requirement 10: StoreBlockedError results in skipped and immediate delete without DLQ."""
    store_id, prod_id, sp_id = setup_test_store_product()
    now_utc = datetime.now(timezone.utc)

    job_id = uuid.uuid4()
    msg = ScrapingMessage(
        version=1,
        job_id=job_id,
        store_id=store_id,
        product_ids=[prod_id],
        requested_at=now_utc,
        attempt=1,
    )

    with SessionLocal() as db:
        job = ScrapingJob(
            id=job_id,
            store_id=store_id,
            status="queued",
            trigger_type="manual",
            batch_size=1,
            attempts=0,
            payload=msg.model_dump(mode="json"),
            created_at=now_utc,
        )
        db.add(job)
        db.commit()

    sqs = FakeSqsQueue()
    mock_service = MagicMock(spec=ScrapingWorkerService)
    mock_service.process_job.side_effect = StoreBlockedError("Cloudflare 403 Forbidden")

    consumer = ScrapingConsumer(
        queue=sqs,
        service=mock_service,
        session_factory=SessionLocal,
        queue_name="scraping-jobs",
    )

    sqs.messages.append(
        QueueMessage(
            message_id="blocked-msg-1",
            receipt_handle="rh-blocked-1",
            body=msg.model_dump_json(),
            attempts=1,
        )
    )
    handled = consumer.process_next_message()
    assert handled is True
    assert "rh-blocked-1" in sqs.deleted_handles

    with SessionLocal() as db:
        j = db.get(ScrapingJob, job_id)
        assert j.status == "skipped"
        assert "SKIPPED_STORE_BLOCKED" in j.error_reason

        # Ensure NO rows in ledger or quarantine
        ledgers = db.scalars(
            select(ScrapingDlqLedger).where(ScrapingDlqLedger.job_id == job_id)
        ).all()
        assert len(ledgers) == 0


def test_worker_concurrency_atomic_claim_prevents_duplicate_scrape():
    """Requirement 11: Atomic claim with_for_update prevents concurrent duplicate executions."""
    store_id, prod_id, sp_id = setup_test_store_product()
    now_utc = datetime.now(timezone.utc)

    job_id = uuid.uuid4()
    msg = ScrapingMessage(
        version=1,
        job_id=job_id,
        store_id=store_id,
        product_ids=[prod_id],
        requested_at=now_utc,
        attempt=1,
    )

    with SessionLocal() as db:
        job = ScrapingJob(
            id=job_id,
            store_id=store_id,
            status="queued",
            trigger_type="manual",
            batch_size=1,
            attempts=0,
            payload=msg.model_dump(mode="json"),
            created_at=now_utc,
        )
        db.add(job)
        db.commit()

    sqs = FakeSqsQueue()
    mock_service = MagicMock(spec=ScrapingWorkerService)
    mock_service.process_job.return_value = 1

    consumer = ScrapingConsumer(
        queue=sqs,
        service=mock_service,
        session_factory=SessionLocal,
        queue_name="scraping-jobs",
        visibility_timeout=60,
    )

    # Put first copy
    sqs.messages.append(
        QueueMessage(
            message_id="concurrent-1",
            receipt_handle="rh-c1",
            body=msg.model_dump_json(),
            attempts=1,
        )
    )
    handled_1 = consumer.process_next_message()
    assert handled_1 is True
    assert mock_service.process_job.call_count == 1

    # Put second copy (duplicate)
    sqs.messages.append(
        QueueMessage(
            message_id="concurrent-2",
            receipt_handle="rh-c2",
            body=msg.model_dump_json(),
            attempts=1,
        )
    )
    handled_2 = consumer.process_next_message()
    assert handled_2 is True
    # process_job MUST NOT have been called a second time!
    assert mock_service.process_job.call_count == 1


def test_worker_lease_recovery_after_crash():
    """Requirement 11: Worker recovers crashed job when lease (visibility timeout) expires."""
    store_id, prod_id, sp_id = setup_test_store_product()
    now_utc = datetime.now(timezone.utc)
    expired_start = now_utc - timedelta(seconds=120)  # visibility_timeout=60s

    job_id = uuid.uuid4()
    msg = ScrapingMessage(
        version=1,
        job_id=job_id,
        store_id=store_id,
        product_ids=[prod_id],
        requested_at=expired_start,
        attempt=2,
    )

    with SessionLocal() as db:
        job = ScrapingJob(
            id=job_id,
            store_id=store_id,
            status="processing",
            trigger_type="manual",
            batch_size=1,
            attempts=1,
            payload=msg.model_dump(mode="json"),
            created_at=expired_start,
            started_at=expired_start,
        )
        db.add(job)
        db.commit()

    sqs = FakeSqsQueue()
    mock_service = MagicMock(spec=ScrapingWorkerService)
    mock_service.process_job.return_value = 1

    consumer = ScrapingConsumer(
        queue=sqs,
        service=mock_service,
        session_factory=SessionLocal,
        queue_name="scraping-jobs",
        visibility_timeout=60,
    )

    sqs.messages.append(
        QueueMessage(
            message_id="crashed-recovery-msg",
            receipt_handle="rh-crash-1",
            body=msg.model_dump_json(),
            attempts=2,
        )
    )

    handled = consumer.process_next_message()
    assert handled is True
    assert mock_service.process_job.call_count == 1

    with SessionLocal() as db:
        j = db.get(ScrapingJob, job_id)
        assert j.status == "completed"
        assert j.attempts == 2


def test_dlq_indexer_startup_and_sigterm_handling_offline():
    """Requirement: DLQ indexer must run offline with Stubber and handle SIGTERM cleanly."""
    import signal

    import boto3
    from botocore.stub import Stubber
    from shared.queue.sqs import SqsQueue

    import app.services.dlq_indexer as dlq_module

    sqs_client = boto3.client(
        "sqs",
        region_name="us-east-1",
        aws_access_key_id="offline-mock",
        aws_secret_access_key="offline-mock",
    )
    stubber = Stubber(sqs_client)
    stubber.add_response("receive_message", {"Messages": []})
    stubber.activate()

    dlq_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-dlq"
    queue_service = SqsQueue(
        client=sqs_client,
        queue_url_map={"scraping-jobs-dlq": dlq_url},
    )

    indexer = DlqIndexerService(
        session_factory=SessionLocal,
        sqs_queue_service=queue_service,
        dlq_name="scraping-jobs-dlq",
    )

    # 1. Verify cycle completes with 0 external network/DNS resolution
    processed = indexer.process_cycle(max_messages=10)
    assert processed == 0

    # 2. Verify signal handler stops the loop cleanly
    dlq_module._running = True
    dlq_module._handle_exit_signal(signal.SIGTERM, None)
    assert dlq_module._running is False
    dlq_module._running = True
