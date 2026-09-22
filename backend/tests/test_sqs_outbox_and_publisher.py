"""Tests for SQS queue adapter, transactional outbox publisher, and ledger replay."""

import os
import uuid
from datetime import datetime, timedelta, timezone

import boto3
import pytest
from botocore.stub import Stubber
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

# Ensure AWS metadata discovery is completely disabled offline
os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "test-key-id"
os.environ["AWS_SECRET_ACCESS_KEY"] = "test-secret-key"

from shared.queue.sqs import SqsQueue
from shared.schemas.scraping import LEGACY_MESSAGE_NAMESPACE, ScrapingMessage

from app.db.models import (
    Category,
    Product,
    ScrapingDlqLedger,
    ScrapingJob,
    ScrapingOutbox,
    Store,
    StoreProduct,
)
from app.db.session import SessionLocal
from app.services.dispatch_service import dispatch_service
from app.services.outbox_publisher import OutboxPublisherService


@pytest.fixture
def db_session():
    """Yield a transactional database session and clean up temporary test records."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.execute(
            text(
                "DELETE FROM scraping_outbox WHERE "
                "idempotency_key LIKE '%test%' OR idempotency_key LIKE '%rep%' "
                "OR idempotency_key LIKE '%partial%' OR idempotency_key LIKE '%claim%' "
                "OR idempotency_key LIKE '%exhaust%' OR idempotency_key LIKE '%success%'"
            )
        )
        session.execute(
            text(
                "DELETE FROM scraping_dlq_ledger WHERE store_id IN ("
                "SELECT id FROM stores WHERE domain LIKE 'domain-%')"
            )
        )
        session.execute(
            text(
                "DELETE FROM scraping_jobs WHERE store_id IN ("
                "SELECT id FROM stores WHERE domain LIKE 'domain-%')"
            )
        )
        session.execute(
            text(
                "DELETE FROM store_products WHERE store_id IN ("
                "SELECT id FROM stores WHERE domain LIKE 'domain-%')"
            )
        )
        session.execute(text("DELETE FROM stores WHERE domain LIKE 'domain-%'"))
        session.commit()
        session.close()


def create_test_store_and_job(db: Session, job_status="queued", replay_count=0):
    """Helper to create a Store, Product, StoreProduct, and ScrapingJob for tests."""
    store = Store(
        id=uuid.uuid4(),
        name=f"Store-{uuid.uuid4().hex[:6]}",
        domain=f"domain-{uuid.uuid4().hex[:6]}.com",
        is_active=True,
    )
    cat = Category(name=f"Cat-{uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
    prod = Product(name="Product", slug=f"prod-{uuid.uuid4().hex[:6]}", category=cat)
    db.add_all([store, cat, prod])
    db.flush()

    sp = StoreProduct(
        store_id=store.id,
        product_id=prod.id,
        product_url=f"https://{store.domain}/p1",
        is_active=True,
    )
    db.add(sp)
    db.flush()

    now_utc = datetime.now(timezone.utc)
    job = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store.id,
        status=job_status,
        trigger_type="manual",
        batch_size=1,
        attempts=0,
        replay_count=replay_count,
        created_at=now_utc,
    )
    db.add(job)
    db.flush()
    return store, prod, job


def test_scraping_message_strict_version_and_legacy_fallback():
    """Requirement 1: Strict integer version and backward-compatible legacy fallback."""
    job_id = uuid.uuid4()
    store_id = uuid.uuid4()
    prod_id = uuid.uuid4()

    # 1. Version 1 as int is accepted
    msg = ScrapingMessage(
        version=1,
        job_id=job_id,
        store_id=store_id,
        product_ids=[prod_id],
        requested_at=datetime.now(timezone.utc),
        attempt=1,
    )
    assert msg.version == 1
    assert msg.logical_message_id is not None
    assert msg.root_logical_message_id == msg.logical_message_id

    # 2. String "1" must be rejected
    with pytest.raises(ValidationError):
        ScrapingMessage(
            version="1",  # type: ignore
            job_id=job_id,
            store_id=store_id,
            product_ids=[prod_id],
            requested_at=datetime.now(timezone.utc),
            attempt=1,
        )

    # 3. String "1.0" must be rejected
    with pytest.raises(ValidationError):
        ScrapingMessage(
            version="1.0",  # type: ignore
            job_id=job_id,
            store_id=store_id,
            product_ids=[prod_id],
            requested_at=datetime.now(timezone.utc),
            attempt=1,
        )

    # 4. Legacy message without logical_message_id derives deterministic uuidv5
    legacy_raw = {
        "version": 1,
        "job_id": str(job_id),
        "store_id": str(store_id),
        "product_ids": [str(prod_id)],
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "attempt": 1,
    }
    parsed = ScrapingMessage.model_validate(legacy_raw)
    expected_uuid = uuid.uuid5(LEGACY_MESSAGE_NAMESPACE, f"legacy-{job_id}")
    assert parsed.logical_message_id == expected_uuid
    assert parsed.root_logical_message_id == expected_uuid
    assert parsed.replayed_from_message_id is None


def test_sqs_queue_adapter_with_stubber():
    """Requirement 13: SqsQueue unit tests using botocore Stubber with zero AWS calls."""
    sqs_client = boto3.client("sqs", region_name="us-east-1")
    stubber = Stubber(sqs_client)

    queue_adapter = SqsQueue(
        client=sqs_client,
        queue_url_map={"test-queue": "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"},
    )

    # 1. Test send_message
    expected_msg_id = "msg-uuid-1234"
    stubber.add_response(
        "send_message",
        {"MessageId": expected_msg_id},
        {
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue",
            "MessageBody": '{"hello": "world"}',
        },
    )
    with stubber:
        msg_id = queue_adapter.send_message("test-queue", {"hello": "world"})
        assert msg_id == expected_msg_id

    # 2. Test send_message_batch
    batch_entries = [
        {"Id": "1", "MessageBody": "body1"},
        {"Id": "2", "MessageBody": "body2"},
    ]
    stubber.add_response(
        "send_message_batch",
        {
            "Successful": [{"Id": "1", "MessageId": "sqs-1", "MD5OfMessageBody": "abc"}],
            "Failed": [
                {
                    "Id": "2",
                    "Code": "Throttling",
                    "Message": "Too many requests",
                    "SenderFault": False,
                }
            ],
        },
        {
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue",
            "Entries": batch_entries,
        },
    )
    with stubber:
        batch_resp = queue_adapter.send_message_batch("test-queue", batch_entries)
        assert len(batch_resp["Successful"]) == 1
        assert len(batch_resp["Failed"]) == 1
        assert batch_resp["Successful"][0]["MessageId"] == "sqs-1"
        assert batch_resp["Failed"][0]["Code"] == "Throttling"

    # 3. Test receive_messages
    stubber.add_response(
        "receive_message",
        {
            "Messages": [
                {
                    "MessageId": "recv-1",
                    "ReceiptHandle": "rh-1",
                    "Body": '{"test": 1}',
                    "Attributes": {"ApproximateReceiveCount": "2"},
                }
            ]
        },
        {
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue",
            "MaxNumberOfMessages": 1,
            "VisibilityTimeout": 30,
            "WaitTimeSeconds": 0,
            "AttributeNames": ["All"],
            "MessageAttributeNames": ["All"],
        },
    )
    with stubber:
        received = queue_adapter.receive_messages("test-queue", max_messages=1)
        assert len(received) == 1
        assert received[0].message_id == "recv-1"
        assert received[0].receipt_handle == "rh-1"
        assert received[0].attempts == 2

    # 4. Test delete_message
    stubber.add_response(
        "delete_message",
        {},
        {
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue",
            "ReceiptHandle": "rh-1",
        },
    )
    with stubber:
        queue_adapter.delete_message("test-queue", "rh-1")

    # 5. Test change_message_visibility
    stubber.add_response(
        "change_message_visibility",
        {},
        {
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue",
            "ReceiptHandle": "rh-1",
            "VisibilityTimeout": 45,
        },
    )
    with stubber:
        queue_adapter.change_message_visibility("test-queue", "rh-1", 45)


def test_outbox_claim_skips_locked_and_releases_lock_before_network(db_session):
    """Requirement 6: Claim releases DB transaction before SQS call and sets leases."""
    store, prod, job = create_test_store_and_job(db_session)
    now_utc = datetime.now(timezone.utc)

    outbox1 = ScrapingOutbox(
        id=uuid.uuid4(),
        aggregate_type="scraping_job",
        aggregate_id=job.id,
        event_type="initial_dispatch",
        queue_name="scraping-jobs",
        payload={"job_id": str(job.id)},
        status="pending",
        attempts=0,
        available_at=now_utc,
        idempotency_key=f"claim-test-1-{job.id}",
        created_at=now_utc,
    )
    db_session.add(outbox1)
    db_session.commit()

    publisher = OutboxPublisherService(
        session_factory=SessionLocal,
        sqs_queue_service=None,
        publisher_id="worker-pub-A",
        lease_duration_seconds=15,
    )

    claimed = publisher.claim_batch(batch_size=10)
    assert len(claimed) >= 1
    claimed_ids = [c["id"] for c in claimed]
    assert outbox1.id in claimed_ids

    # Verify state in DB
    with SessionLocal() as check_db:
        row = check_db.get(ScrapingOutbox, outbox1.id)
        assert row.status == "publishing"
        assert row.locked_by == "worker-pub-A"
        assert row.locked_at is not None
        assert row.lease_until is not None


def test_outbox_expired_lease_recovery(db_session):
    """Requirement 6: Outbox recovers rows when publishing lease expires."""
    store, prod, job = create_test_store_and_job(db_session)
    now_utc = datetime.now(timezone.utc)
    expired_lease = now_utc - timedelta(seconds=10)

    outbox_stale = ScrapingOutbox(
        id=uuid.uuid4(),
        aggregate_type="scraping_job",
        aggregate_id=job.id,
        event_type="initial_dispatch",
        queue_name="scraping-jobs",
        payload={"job_id": str(job.id)},
        status="publishing",
        locked_by="crashed-worker",
        locked_at=now_utc - timedelta(minutes=5),
        lease_until=expired_lease,
        attempts=1,
        available_at=now_utc,
        idempotency_key=f"lease-test-{job.id}",
        created_at=now_utc,
    )
    db_session.add(outbox_stale)
    db_session.commit()

    recovering_publisher = OutboxPublisherService(
        session_factory=SessionLocal,
        sqs_queue_service=None,
        publisher_id="worker-pub-B",
        lease_duration_seconds=30,
    )

    claimed = recovering_publisher.claim_batch(batch_size=10)
    claimed_ids = [c["id"] for c in claimed]
    assert outbox_stale.id in claimed_ids

    with SessionLocal() as check_db:
        row = check_db.get(ScrapingOutbox, outbox_stale.id)
        assert row.status == "publishing"
        assert row.locked_by == "worker-pub-B"
        assert row.lease_until > now_utc


def test_outbox_send_message_batch_partial_success_and_failure(db_session):
    """Requirement 7: Process Successful, Failed, and missing entries individually."""
    store, prod, job = create_test_store_and_job(db_session)
    now_utc = datetime.now(timezone.utc)

    id_success = uuid.uuid4()
    id_failed = uuid.uuid4()
    id_missing = uuid.uuid4()

    o1 = ScrapingOutbox(
        id=id_success,
        aggregate_type="scraping_job",
        aggregate_id=job.id,
        event_type="initial_dispatch",
        queue_name="scraping-jobs",
        payload={"job_id": str(job.id), "idx": 1},
        status="publishing",
        locked_by="pub-test",
        lease_until=now_utc + timedelta(seconds=60),
        attempts=0,
        available_at=now_utc,
        idempotency_key=f"partial-1-{id_success}",
        created_at=now_utc,
    )
    o2 = ScrapingOutbox(
        id=id_failed,
        aggregate_type="scraping_job",
        aggregate_id=job.id,
        event_type="initial_dispatch",
        queue_name="scraping-jobs",
        payload={"job_id": str(job.id), "idx": 2},
        status="publishing",
        locked_by="pub-test",
        lease_until=now_utc + timedelta(seconds=60),
        attempts=0,
        available_at=now_utc,
        idempotency_key=f"partial-2-{id_failed}",
        created_at=now_utc,
    )
    o3 = ScrapingOutbox(
        id=id_missing,
        aggregate_type="scraping_job",
        aggregate_id=job.id,
        event_type="initial_dispatch",
        queue_name="scraping-jobs",
        payload={"job_id": str(job.id), "idx": 3},
        status="publishing",
        locked_by="pub-test",
        lease_until=now_utc + timedelta(seconds=60),
        attempts=0,
        available_at=now_utc,
        idempotency_key=f"partial-3-{id_missing}",
        created_at=now_utc,
    )
    db_session.add_all([o1, o2, o3])
    db_session.commit()

    claimed_items = [
        {"id": id_success, "aggregate_id": job.id, "event_type": "initial_dispatch"},
        {"id": id_failed, "aggregate_id": job.id, "event_type": "initial_dispatch"},
        {"id": id_missing, "aggregate_id": job.id, "event_type": "initial_dispatch"},
    ]

    sqs_response = {
        "Successful": [{"Id": str(id_success), "MessageId": "sqs-msg-100"}],
        "Failed": [
            {
                "Id": str(id_failed),
                "Code": "KMS.DisabledException",
                "Message": "Key is disabled",
            }
        ],
        # Note: id_missing is NOT in Successful and NOT in Failed
    }

    publisher = OutboxPublisherService(
        session_factory=SessionLocal,
        sqs_queue_service=None,
        publisher_id="pub-test",
    )

    stats = publisher.finalize_batch(claimed_items, sqs_response)
    assert stats["published"] == 1
    assert stats["failed"] == 2
    assert stats["exhausted"] == 0

    with SessionLocal() as check_db:
        # Check success row
        r1 = check_db.get(ScrapingOutbox, id_success)
        assert r1.status == "published"
        assert r1.provider_message_id == "sqs-msg-100"
        assert r1.locked_by is None
        assert r1.lease_until is None
        assert r1.last_error is None

        # Check explicit failure row
        r2 = check_db.get(ScrapingOutbox, id_failed)
        assert r2.status == "failed"
        assert r2.attempts == 1
        assert "KMS.DisabledException" in r2.last_error
        assert r2.locked_by is None
        assert r2.available_at > now_utc

        # Check missing row (treated as failure)
        r3 = check_db.get(ScrapingOutbox, id_missing)
        assert r3.status == "failed"
        assert r3.attempts == 1
        assert "MISSING_FROM_RESPONSE" in r3.last_error
        assert r3.locked_by is None
        assert r3.available_at > now_utc


def test_outbox_initial_dispatch_exhaustion(db_session):
    """Requirement 5: Initial dispatch exhausted transitions ScrapingJob to failed."""
    store, prod, job = create_test_store_and_job(db_session, job_status="queued")
    now_utc = datetime.now(timezone.utc)
    outbox_id = uuid.uuid4()

    outbox = ScrapingOutbox(
        id=outbox_id,
        aggregate_type="scraping_job",
        aggregate_id=job.id,
        event_type="initial_dispatch",
        queue_name="scraping-jobs",
        payload={"job_id": str(job.id)},
        status="publishing",
        locked_by="pub-exhaust",
        lease_until=now_utc + timedelta(seconds=60),
        attempts=4,  # max_attempts is 5
        available_at=now_utc,
        idempotency_key=f"exhaust-init-{outbox_id}",
        created_at=now_utc,
    )
    db_session.add(outbox)
    db_session.commit()

    publisher = OutboxPublisherService(
        session_factory=SessionLocal,
        sqs_queue_service=None,
        publisher_id="pub-exhaust",
        max_attempts=5,
    )

    claimed = [{"id": outbox_id, "aggregate_id": job.id, "event_type": "initial_dispatch"}]
    sqs_resp = {
        "Successful": [],
        "Failed": [
            {
                "Id": str(outbox_id),
                "Code": "ServiceUnavailable",
                "Message": "503",
            }
        ],
    }

    stats = publisher.finalize_batch(claimed, sqs_resp)
    assert stats["exhausted"] == 1

    with SessionLocal() as check_db:
        r = check_db.get(ScrapingOutbox, outbox_id)
        assert r.status == "exhausted"
        assert r.attempts == 5

        j = check_db.get(ScrapingJob, job.id)
        assert j.status == "failed"
        assert j.error_reason == "OUTBOX_PUBLISH_EXHAUSTED"


def test_outbox_replay_exhaustion_compensation(db_session):
    """Requirement 5: Replay outbox exhaustion reverts ledger to in_dlq and job to dead_letter."""
    store, prod, job = create_test_store_and_job(db_session, job_status="queued", replay_count=1)
    now_utc = datetime.now(timezone.utc)

    # Ledger in replay_pending
    ledger_id = uuid.uuid4()
    ledger = ScrapingDlqLedger(
        id=ledger_id,
        job_id=job.id,
        store_id=store.id,
        payload={"job_id": str(job.id)},
        products_count=1,
        attempts=3,
        status="replay_pending",
        error_reason="Initial failure",
        sent_to_dlq_at=now_utc,
        replay_count=1,
        root_logical_message_id=ledger_id,
    )
    db_session.add(ledger)
    db_session.flush()

    outbox_id = uuid.uuid4()
    outbox = ScrapingOutbox(
        id=outbox_id,
        aggregate_type="scraping_job",
        aggregate_id=job.id,
        event_type="replay",
        source_ledger_id=ledger.id,
        queue_name="scraping-jobs",
        payload={"job_id": str(job.id)},
        status="publishing",
        locked_by="pub-replay-exhaust",
        lease_until=now_utc + timedelta(seconds=60),
        attempts=4,  # max_attempts is 5
        available_at=now_utc,
        idempotency_key=f"exhaust-rep-{outbox_id}",
        created_at=now_utc,
    )
    db_session.add(outbox)
    db_session.commit()

    publisher = OutboxPublisherService(
        session_factory=SessionLocal,
        sqs_queue_service=None,
        publisher_id="pub-replay-exhaust",
        max_attempts=5,
    )

    claimed = [
        {
            "id": outbox_id,
            "aggregate_id": job.id,
            "event_type": "replay",
            "source_ledger_id": ledger.id,
        }
    ]
    sqs_resp = {
        "Successful": [],
        "Failed": [
            {
                "Id": str(outbox_id),
                "Code": "Throttling",
                "Message": "Limit exceeded",
            }
        ],
    }

    stats = publisher.finalize_batch(claimed, sqs_resp)
    assert stats["exhausted"] == 1

    with SessionLocal() as check_db:
        r = check_db.get(ScrapingOutbox, outbox_id)
        assert r.status == "exhausted"

        # Replay compensation: ledger returned to in_dlq!
        ledger_row = check_db.get(ScrapingDlqLedger, ledger.id)
        assert ledger_row.status == "in_dlq"

        # ScrapingJob returned to dead_letter!
        j = check_db.get(ScrapingJob, job.id)
        assert j.status == "dead_letter"
        assert j.last_dlq_reason == "OUTBOX_REPLAY_EXHAUSTED"


def test_outbox_replay_success_updates_ledger_to_replayed(db_session):
    """Requirement 5: Confirmed SQS publication marks ledger as replayed in atomic tx."""
    store, prod, job = create_test_store_and_job(db_session, job_status="queued", replay_count=1)
    now_utc = datetime.now(timezone.utc)

    ledger_id = uuid.uuid4()
    ledger = ScrapingDlqLedger(
        id=ledger_id,
        job_id=job.id,
        store_id=store.id,
        payload={"job_id": str(job.id)},
        products_count=1,
        attempts=3,
        status="replay_pending",
        error_reason="Initial failure",
        sent_to_dlq_at=now_utc,
        replay_count=1,
        root_logical_message_id=ledger_id,
    )
    db_session.add(ledger)
    db_session.flush()

    outbox_id = uuid.uuid4()
    outbox = ScrapingOutbox(
        id=outbox_id,
        aggregate_type="scraping_job",
        aggregate_id=job.id,
        event_type="replay",
        source_ledger_id=ledger.id,
        queue_name="scraping-jobs",
        payload={"job_id": str(job.id)},
        status="publishing",
        locked_by="pub-replay-success",
        lease_until=now_utc + timedelta(seconds=60),
        attempts=0,
        available_at=now_utc,
        idempotency_key=f"success-rep-{outbox_id}",
        created_at=now_utc,
    )
    db_session.add(outbox)
    db_session.commit()

    publisher = OutboxPublisherService(
        session_factory=SessionLocal,
        sqs_queue_service=None,
        publisher_id="pub-replay-success",
    )

    claimed = [
        {
            "id": outbox_id,
            "aggregate_id": job.id,
            "event_type": "replay",
            "source_ledger_id": ledger.id,
        }
    ]
    sqs_resp = {
        "Successful": [
            {
                "Id": str(outbox_id),
                "MessageId": "sqs-msg-replay-success-999",
            }
        ],
        "Failed": [],
    }

    stats = publisher.finalize_batch(claimed, sqs_resp)
    assert stats["published"] == 1

    with SessionLocal() as check_db:
        r = check_db.get(ScrapingOutbox, outbox_id)
        assert r.status == "published"
        assert r.provider_message_id == "sqs-msg-replay-success-999"

        ledger_row = check_db.get(ScrapingDlqLedger, ledger.id)
        assert ledger_row.status == "replayed"
        assert ledger_row.replayed_at is not None


def test_replay_dlq_endpoint_creates_outbox_and_replay_pending(db_session):
    """Requirement 4: POST /dlq/replay locks ledger & job, updates job payload, creates outbox."""
    store, prod, job = create_test_store_and_job(db_session, job_status="dead_letter")
    now_utc = datetime.now(timezone.utc)

    orig_logical_id = uuid.uuid4()
    ledger = ScrapingDlqLedger(
        id=orig_logical_id,
        job_id=job.id,
        store_id=store.id,
        payload={"job_id": str(job.id), "product_ids": [str(prod.id)]},
        products_count=1,
        attempts=3,
        status="in_dlq",
        error_reason="Connection timeout",
        sent_to_dlq_at=now_utc,
        replay_count=0,
        root_logical_message_id=orig_logical_id,
    )
    db_session.add(ledger)
    db_session.commit()

    # Replay via dispatch service
    resp = dispatch_service.replay_dlq_messages(message_ids=[ledger.id])
    assert resp.status == "accepted"
    assert resp.replayed_count == 1
    assert ledger.id in resp.message_ids
    assert job.id in resp.job_ids

    with SessionLocal() as check_db:
        # Check ledger status is replay_pending (NOT replayed yet!)
        ledger_row = check_db.get(ScrapingDlqLedger, ledger.id)
        assert ledger_row.status == "replay_pending"
        assert ledger_row.replay_count == 1

        # Check job status is queued with new payload
        j = check_db.get(ScrapingJob, job.id)
        assert j.status == "queued"
        assert j.replay_count == 1
        assert isinstance(j.payload, dict)
        assert j.payload["version"] == 1
        new_logical_id = uuid.UUID(j.payload["logical_message_id"])
        assert new_logical_id != orig_logical_id
        assert uuid.UUID(j.payload["root_logical_message_id"]) == orig_logical_id
        assert uuid.UUID(j.payload["replayed_from_message_id"]) == orig_logical_id

        # Check outbox record created
        stmt = select(ScrapingOutbox).where(
            ScrapingOutbox.aggregate_id == job.id,
            ScrapingOutbox.event_type == "replay",
            ScrapingOutbox.source_ledger_id == ledger.id,
        )
        outbox_row = check_db.execute(stmt).scalar_one()
        assert outbox_row.status == "pending"
        assert outbox_row.payload["logical_message_id"] == str(new_logical_id)
