"""Tests for DLQ inspection and safe transactional replay API endpoints."""

import os
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from shared.queue.models import LocalQueueMessage
from shared.queue.postgres import PostgresQueue
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import Category, Product, ScrapingJob, Store, StoreProduct
from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)
VALID_TOKEN = os.getenv("INTERNAL_API_KEY", "dev-internal-secret-token")
AUTH_HEADERS = {"Authorization": f"Bearer {VALID_TOKEN}"}


@pytest.fixture
def db_session():
    """Yield a transactional database session and clean up temporary test records."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.execute(
            text(
                "DELETE FROM store_products WHERE store_id IN ("
                "SELECT id FROM stores "
                "WHERE domain LIKE 'inactive-%' OR domain LIKE 'dlq-%')"
            )
        )
        session.execute(
            text("DELETE FROM stores WHERE domain LIKE 'inactive-%' OR domain LIKE 'dlq-%'")
        )
        session.commit()
        session.close()


def create_dlq_fixtures(db: Session):
    """Create test category, store, product, and store_product."""
    cat = Category(
        id=uuid.uuid4(),
        name=f"DLQ Cat {uuid.uuid4().hex[:6]}",
        slug=f"dlq-cat-{uuid.uuid4().hex[:6]}",
    )
    db.add(cat)
    db.flush()

    store = db.scalars(select(Store).where(Store.domain == "necs.pe")).first()
    if not store:
        store = Store(
            id=uuid.uuid4(),
            name=f"DLQ Test Store {uuid.uuid4().hex[:6]}",
            domain="necs.pe",
            is_active=True,
        )
        db.add(store)
        db.flush()

    prod = Product(
        id=uuid.uuid4(),
        category_id=cat.id,
        name=f"DLQ Product {uuid.uuid4().hex[:6]}",
        slug=f"dlq-prod-{uuid.uuid4().hex[:6]}",
        is_active=True,
    )
    db.add(prod)
    db.flush()

    sp = StoreProduct(
        id=uuid.uuid4(),
        store_id=store.id,
        product_id=prod.id,
        product_url="https://necs.pe/p-dlq",
        is_active=True,
    )
    db.add(sp)
    db.commit()

    return store, prod, sp


def test_dlq_endpoints_require_authentication():
    """Both GET /dlq and POST /dlq/replay require valid Authorization Bearer header."""
    # 1. GET /dlq
    res_no_auth = client.get("/api/v1/scraping/dlq")
    assert res_no_auth.status_code == 401

    res_bad_auth = client.get("/api/v1/scraping/dlq", headers={"Authorization": "Bearer bad-token"})
    assert res_bad_auth.status_code == 401

    # 2. POST /dlq/replay
    body = {"message_ids": [str(uuid.uuid4())]}
    res_post_no_auth = client.post("/api/v1/scraping/dlq/replay", json=body)
    assert res_post_no_auth.status_code == 401

    res_post_bad_auth = client.post(
        "/api/v1/scraping/dlq/replay",
        headers={"Authorization": "Bearer bad-token"},
        json=body,
    )
    assert res_post_bad_auth.status_code == 401


def test_dlq_empty_returns_empty_list(db_session: Session):
    """GET /dlq on an empty DLQ returns total=0 and items=[]."""
    db_session.execute(
        text("DELETE FROM local_queue_messages WHERE queue_name = 'scraping-jobs-dlq'")
    )
    db_session.commit()

    res = client.get("/api/v1/scraping/dlq", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["page"] == 1
    assert data["total_pages"] == 0


def test_dlq_inspection_pagination_filtering_and_order(db_session: Session):
    """GET /dlq supports pagination, store_id filter, date filters, and descending order."""
    store, prod, _ = create_dlq_fixtures(db_session)
    now = datetime.now(timezone.utc)

    # Clean existing DLQ
    db_session.execute(
        text("DELETE FROM local_queue_messages WHERE queue_name = 'scraping-jobs-dlq'")
    )
    db_session.commit()

    # Create 3 DLQ messages with sequential timestamps
    msg_ids = []
    for i in range(3):
        job = ScrapingJob(
            id=uuid.uuid4(),
            store_id=store.id,
            status="dead_letter",
            trigger_type="manual",
            batch_size=1,
            attempts=3,
            error_reason=f"Error {i}",
            sent_to_dlq_at=now - timedelta(minutes=10 - i * 2),
        )
        db_session.add(job)
        db_session.flush()

        msg = LocalQueueMessage(
            id=uuid.uuid4(),
            queue_name="scraping-jobs-dlq",
            payload={
                "job_id": str(job.id),
                "store_id": str(store.id),
                "product_ids": [str(prod.id)],
                "attempt": 3,
                "version": 1,
            },
            status="dlq",
            attempts=3,
            error_reason=f"Error {i}",
            sent_to_dlq_at=now - timedelta(minutes=10 - i * 2),
            created_at=now - timedelta(minutes=30),
        )
        db_session.add(msg)
        db_session.flush()
        msg_ids.append(msg.id)

    db_session.commit()

    # Test page_size=2, page=1
    res_p1 = client.get("/api/v1/scraping/dlq?page=1&page_size=2", headers=AUTH_HEADERS)
    assert res_p1.status_code == 200
    data_p1 = res_p1.json()
    assert data_p1["total"] == 3
    assert len(data_p1["items"]) == 2
    assert data_p1["total_pages"] == 2
    # Verify descending order: item 0 has newest sent_to_dlq_at (msg_ids[2])
    item_0 = data_p1["items"][0]
    assert item_0["message_id"] == str(msg_ids[2])
    assert item_0["job_id"] is not None
    assert item_0["store_id"] == str(store.id)
    assert item_0["store_name"] == store.name
    assert item_0["products_count"] == 1
    assert item_0["attempts"] == 3
    assert item_0["error_reason"] == "Error 2"
    assert item_0["created_at"] is not None
    assert item_0["sent_to_dlq_at"] is not None
    assert item_0["replay_count"] == 0
    assert item_0["replayed_at"] is None
    assert item_0["replayable"] is True
    assert item_0["replay_block_reason"] is None
    assert data_p1["items"][1]["message_id"] == str(msg_ids[1])

    # Test page=2
    res_p2 = client.get("/api/v1/scraping/dlq?page=2&page_size=2", headers=AUTH_HEADERS)
    assert res_p2.status_code == 200
    data_p2 = res_p2.json()
    assert len(data_p2["items"]) == 1
    assert data_p2["items"][0]["message_id"] == str(msg_ids[0])

    # Test filter by store_id
    res_store = client.get(f"/api/v1/scraping/dlq?store_id={store.id}", headers=AUTH_HEADERS)
    assert res_store.status_code == 200
    assert res_store.json()["total"] == 3

    # Test filter by date range
    from_iso = (now - timedelta(minutes=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    to_iso = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    res_range = client.get(
        f"/api/v1/scraping/dlq?from_date={from_iso}&to_date={to_iso}",
        headers=AUTH_HEADERS,
    )
    assert res_range.status_code == 200
    assert res_range.json()["total"] == 1


def test_dlq_inspection_sanitization_and_no_sensitive_leak(db_session: Session):
    """GET /dlq sanitizes error_reason and never returns payload, receipt_handle or tokens."""
    store, prod, _ = create_dlq_fixtures(db_session)
    now = datetime.now(timezone.utc)

    dirty_error = (
        "Fatal error:\nAuthorization: Bearer secret-token-12345\n"
        + "Traceback (most recent call last):\n"
        + "  File 'secret/code.py', line 99\n"
        + "x" * 600
    )

    job = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store.id,
        status="dead_letter",
        trigger_type="manual",
        batch_size=1,
        attempts=3,
        error_reason=dirty_error,
        sent_to_dlq_at=now,
    )
    db_session.add(job)
    db_session.flush()

    msg = LocalQueueMessage(
        id=uuid.uuid4(),
        queue_name="scraping-jobs-dlq",
        payload={
            "job_id": str(job.id),
            "store_id": str(store.id),
            "product_ids": [str(prod.id)],
            "secret_credential": "super-sensitive-value",
        },
        status="dlq",
        attempts=3,
        error_reason=dirty_error,
        sent_to_dlq_at=now,
        created_at=now,
    )
    db_session.add(msg)
    db_session.commit()

    res = client.get(f"/api/v1/scraping/dlq?store_id={store.id}", headers=AUTH_HEADERS)
    assert res.status_code == 200
    items = res.json()["items"]
    target = next((it for it in items if it["message_id"] == str(msg.id)), None)
    assert target is not None

    # Sanitized error reason: <= 500 chars, no raw line breaks, no tokens
    assert target["error_reason"] is not None
    assert len(target["error_reason"]) <= 500
    assert "\n" not in target["error_reason"]
    assert "\r" not in target["error_reason"]
    assert "secret-token-12345" not in target["error_reason"]

    # Critical security checks: raw payload and sensitive fields are absent
    raw_response_text = res.text
    assert "super-sensitive-value" not in raw_response_text
    assert "secret_credential" not in raw_response_text
    assert "receipt_handle" not in target


def test_dlq_malformed_and_legacy_payloads_handling(db_session: Session):
    """GET /dlq handles malformed payloads gracefully with replayable=False and block reason."""
    now = datetime.now(timezone.utc)

    # 1. Non-dict payload
    msg_non_dict = LocalQueueMessage(
        id=uuid.uuid4(),
        queue_name="scraping-jobs-dlq",
        payload="poison-payload",
        status="dlq",
        attempts=1,
        sent_to_dlq_at=now,
        created_at=now,
    )
    # 2. Missing job_id
    msg_missing_job = LocalQueueMessage(
        id=uuid.uuid4(),
        queue_name="scraping-jobs-dlq",
        payload={"store_id": str(uuid.uuid4()), "product_ids": []},
        status="dlq",
        attempts=1,
        sent_to_dlq_at=now,
        created_at=now,
    )
    # 3. Invalid UUID job_id
    msg_invalid_job = LocalQueueMessage(
        id=uuid.uuid4(),
        queue_name="scraping-jobs-dlq",
        payload={"job_id": "not-a-uuid", "store_id": str(uuid.uuid4())},
        status="dlq",
        attempts=1,
        sent_to_dlq_at=now,
        created_at=now,
    )
    # 4. Missing product_ids
    msg_missing_pids = LocalQueueMessage(
        id=uuid.uuid4(),
        queue_name="scraping-jobs-dlq",
        payload={"job_id": str(uuid.uuid4()), "store_id": str(uuid.uuid4())},
        status="dlq",
        attempts=1,
        sent_to_dlq_at=now,
        created_at=now,
    )
    db_session.add_all([msg_non_dict, msg_missing_job, msg_invalid_job, msg_missing_pids])
    db_session.commit()

    res = client.get("/api/v1/scraping/dlq", headers=AUTH_HEADERS)
    assert res.status_code == 200
    items = {it["message_id"]: it for it in res.json()["items"]}

    for mid in [msg_non_dict.id, msg_missing_job.id, msg_invalid_job.id, msg_missing_pids.id]:
        item = items.get(str(mid))
        assert item is not None
        assert item["replayable"] is False
        assert item["products_count"] == 0
        assert item["replay_block_reason"] is not None
        assert "INVALID_DLQ_PAYLOAD" in item["replay_block_reason"]

    # Specific null checks
    assert items[str(msg_non_dict.id)]["job_id"] is None
    assert items[str(msg_non_dict.id)]["store_id"] is None
    assert items[str(msg_missing_job.id)]["job_id"] is None
    assert items[str(msg_invalid_job.id)]["job_id"] is None
    assert items[str(msg_missing_pids.id)]["products_count"] == 0

    # Replay on malformed message returns 409 Conflict
    res_replay = client.post(
        "/api/v1/scraping/dlq/replay",
        headers=AUTH_HEADERS,
        json={"message_ids": [str(msg_non_dict.id)]},
    )
    assert res_replay.status_code == 409


def test_dlq_replay_validation_errors():
    """POST /dlq/replay rejects empty body, > 50 IDs, and duplicate IDs with 422."""
    # 1. Empty body
    res_empty = client.post(
        "/api/v1/scraping/dlq/replay",
        headers=AUTH_HEADERS,
        json={"message_ids": []},
    )
    assert res_empty.status_code == 422

    # 2. More than 50 IDs
    ids_51 = [str(uuid.uuid4()) for _ in range(51)]
    res_too_many = client.post(
        "/api/v1/scraping/dlq/replay",
        headers=AUTH_HEADERS,
        json={"message_ids": ids_51},
    )
    assert res_too_many.status_code == 422

    # 3. Duplicate IDs
    dup_id = str(uuid.uuid4())
    res_dup = client.post(
        "/api/v1/scraping/dlq/replay",
        headers=AUTH_HEADERS,
        json={"message_ids": [dup_id, dup_id]},
    )
    assert res_dup.status_code == 422


def test_dlq_replay_message_not_found_returns_404():
    """POST /dlq/replay returns 404 when one or more message IDs do not exist."""
    missing_id = str(uuid.uuid4())
    res = client.post(
        "/api/v1/scraping/dlq/replay",
        headers=AUTH_HEADERS,
        json={"message_ids": [missing_id]},
    )
    assert res.status_code == 404


def test_dlq_replay_message_not_in_dlq_returns_409(db_session: Session):
    """POST /dlq/replay returns 409 when message is in an active or completed status."""
    msg = LocalQueueMessage(
        id=uuid.uuid4(),
        queue_name="scraping-jobs",
        payload={"job_id": str(uuid.uuid4()), "store_id": str(uuid.uuid4()), "product_ids": []},
        status="pending",
        attempts=0,
    )
    db_session.add(msg)
    db_session.commit()

    res = client.post(
        "/api/v1/scraping/dlq/replay",
        headers=AUTH_HEADERS,
        json={"message_ids": [str(msg.id)]},
    )
    assert res.status_code == 409


def test_dlq_replay_scraping_job_not_found_or_not_dead_letter_returns_409(
    db_session: Session,
):
    """POST /dlq/replay returns 409 if ScrapingJob does not exist or status != dead_letter."""
    store, prod, _ = create_dlq_fixtures(db_session)

    # 1. Job completed instead of dead_letter
    job_completed = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store.id,
        status="completed",
        trigger_type="manual",
        batch_size=1,
    )
    db_session.add(job_completed)
    db_session.flush()

    msg1 = LocalQueueMessage(
        id=uuid.uuid4(),
        queue_name="scraping-jobs-dlq",
        payload={
            "job_id": str(job_completed.id),
            "store_id": str(store.id),
            "product_ids": [str(prod.id)],
        },
        status="dlq",
        attempts=3,
    )
    db_session.add(msg1)
    db_session.commit()

    res1 = client.post(
        "/api/v1/scraping/dlq/replay",
        headers=AUTH_HEADERS,
        json={"message_ids": [str(msg1.id)]},
    )
    assert res1.status_code == 409

    # 2. Job does not exist
    orphan_job_id = uuid.uuid4()
    msg2 = LocalQueueMessage(
        id=uuid.uuid4(),
        queue_name="scraping-jobs-dlq",
        payload={
            "job_id": str(orphan_job_id),
            "store_id": str(store.id),
            "product_ids": [str(prod.id)],
        },
        status="dlq",
        attempts=3,
    )
    db_session.add(msg2)
    db_session.commit()

    res2 = client.post(
        "/api/v1/scraping/dlq/replay",
        headers=AUTH_HEADERS,
        json={"message_ids": [str(msg2.id)]},
    )
    assert res2.status_code == 409


def test_dlq_replay_single_message_success(db_session: Session):
    """POST /dlq/replay successfully moves message to scraping-jobs and resets state."""
    store, prod, _ = create_dlq_fixtures(db_session)
    now = datetime.now(timezone.utc)

    job = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store.id,
        status="dead_letter",
        trigger_type="manual",
        batch_size=1,
        attempts=3,
        error_reason="Fatal error occurred",
        sent_to_dlq_at=now - timedelta(hours=1),
        started_at=now - timedelta(hours=1, minutes=5),
        finished_at=now - timedelta(hours=1),
    )
    db_session.add(job)
    db_session.flush()

    msg = LocalQueueMessage(
        id=uuid.uuid4(),
        queue_name="scraping-jobs-dlq",
        payload={
            "job_id": str(job.id),
            "store_id": str(store.id),
            "product_ids": [str(prod.id)],
            "attempt": 3,
            "version": 1,
            "requested_at": (now - timedelta(hours=2)).isoformat(),
        },
        status="dlq",
        attempts=3,
        error_reason="Fatal error occurred",
        sent_to_dlq_at=now - timedelta(hours=1),
        created_at=now - timedelta(hours=2),
    )
    db_session.add(msg)
    db_session.commit()

    res = client.post(
        "/api/v1/scraping/dlq/replay",
        headers=AUTH_HEADERS,
        json={"message_ids": [str(msg.id)]},
    )
    assert res.status_code == 202
    data = res.json()
    assert data["replayed_count"] == 1
    assert data["message_ids"] == [str(msg.id)]
    assert data["job_ids"] == [str(job.id)]
    assert data["status"] == "accepted"

    # Verify database state in refreshed session
    db_session.expire_all()
    updated_msg = db_session.get(LocalQueueMessage, msg.id)
    assert updated_msg is not None
    assert updated_msg.queue_name == "scraping-jobs"
    assert updated_msg.status == "pending"
    assert updated_msg.attempts == 0
    assert updated_msg.receipt_handle is None
    assert updated_msg.replay_count == 1
    assert updated_msg.replayed_at is not None
    assert updated_msg.visible_at <= datetime.now(timezone.utc)
    # Payload attempt reset
    assert updated_msg.payload["attempt"] == 1
    assert updated_msg.payload["job_id"] == str(job.id)

    updated_job = db_session.get(ScrapingJob, job.id)
    assert updated_job is not None
    assert updated_job.status == "queued"
    assert updated_job.attempts == 0
    assert updated_job.replay_count == 1
    assert updated_job.replayed_at is not None
    assert updated_job.started_at is None
    assert updated_job.finished_at is None
    assert updated_job.error_reason is None
    assert updated_job.last_dlq_reason == "Fatal error occurred"


def test_dlq_replay_batch_atomic_rollback_on_single_failure(db_session: Session):
    """If one message in a replay batch fails validation, entire batch is rolled back."""
    store, prod, _ = create_dlq_fixtures(db_session)
    now = datetime.now(timezone.utc)

    # Valid message + job
    job1 = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store.id,
        status="dead_letter",
        trigger_type="manual",
        batch_size=1,
    )
    db_session.add(job1)
    db_session.flush()

    msg1 = LocalQueueMessage(
        id=uuid.uuid4(),
        queue_name="scraping-jobs-dlq",
        payload={
            "job_id": str(job1.id),
            "store_id": str(store.id),
            "product_ids": [str(prod.id)],
        },
        status="dlq",
        attempts=3,
        sent_to_dlq_at=now,
    )
    db_session.add(msg1)

    # Invalid message (missing corresponding ScrapingJob)
    msg2 = LocalQueueMessage(
        id=uuid.uuid4(),
        queue_name="scraping-jobs-dlq",
        payload={
            "job_id": str(uuid.uuid4()),
            "store_id": str(store.id),
            "product_ids": [str(prod.id)],
        },
        status="dlq",
        attempts=3,
        sent_to_dlq_at=now,
    )
    db_session.add(msg2)
    db_session.commit()

    # Attempt replay with both IDs
    res = client.post(
        "/api/v1/scraping/dlq/replay",
        headers=AUTH_HEADERS,
        json={"message_ids": [str(msg1.id), str(msg2.id)]},
    )
    assert res.status_code == 409

    # Verify atomic rollback: msg1 must still be in DLQ
    db_session.expire_all()
    m1_check = db_session.get(LocalQueueMessage, msg1.id)
    assert m1_check is not None
    assert m1_check.queue_name == "scraping-jobs-dlq"
    assert m1_check.status == "dlq"
    assert m1_check.replay_count == 0

    j1_check = db_session.get(ScrapingJob, job1.id)
    assert j1_check is not None
    assert j1_check.status == "dead_letter"
    assert j1_check.replay_count == 0


def test_dlq_replay_real_concurrent_conflict(db_session: Session):
    """Two concurrent replay requests on the same message: one succeeds (202), other 409."""
    store, prod, _ = create_dlq_fixtures(db_session)
    now = datetime.now(timezone.utc)

    job = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store.id,
        status="dead_letter",
        trigger_type="manual",
        batch_size=1,
    )
    db_session.add(job)
    db_session.flush()

    msg = LocalQueueMessage(
        id=uuid.uuid4(),
        queue_name="scraping-jobs-dlq",
        payload={
            "job_id": str(job.id),
            "store_id": str(store.id),
            "product_ids": [str(prod.id)],
        },
        status="dlq",
        attempts=3,
        sent_to_dlq_at=now,
    )
    db_session.add(msg)
    db_session.commit()

    target_id_str = str(msg.id)
    results = []

    def perform_replay():
        # Dedicated client call in separate thread
        r = client.post(
            "/api/v1/scraping/dlq/replay",
            headers=AUTH_HEADERS,
            json={"message_ids": [target_id_str]},
        )
        results.append(r.status_code)

    t1 = threading.Thread(target=perform_replay)
    t2 = threading.Thread(target=perform_replay)

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # One thread gets 202 Accepted, the other gets 409 Conflict
    assert 202 in results
    assert 409 in results

    # The message must only be replayed once
    db_session.expire_all()
    check_msg = db_session.get(LocalQueueMessage, msg.id)
    assert check_msg is not None
    assert check_msg.queue_name == "scraping-jobs"
    assert check_msg.status == "pending"
    assert check_msg.replay_count == 1


def test_dlq_replayed_job_state_and_observations_preservation(
    db_session: Session,
):
    """Replaying preserves cumulative observations_created and resets job state cleanly."""
    store, prod, _ = create_dlq_fixtures(db_session)
    now = datetime.now(timezone.utc)

    # Job previously completed 5 observations before entering dead_letter
    job = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store.id,
        status="dead_letter",
        trigger_type="manual",
        batch_size=10,
        attempts=3,
        observations_created=5,
        started_at=now - timedelta(minutes=15),
        finished_at=now - timedelta(minutes=10),
        error_reason="Fatal connection timeout to external vendor",
        sent_to_dlq_at=now - timedelta(minutes=10),
    )
    db_session.add(job)
    db_session.flush()

    msg = LocalQueueMessage(
        id=uuid.uuid4(),
        queue_name="scraping-jobs-dlq",
        payload={
            "version": 1,
            "job_id": str(job.id),
            "store_id": str(store.id),
            "product_ids": [str(prod.id)],
            "attempt": 3,
            "requested_at": now.isoformat(),
        },
        status="dlq",
        attempts=3,
        sent_to_dlq_at=now - timedelta(minutes=10),
    )
    db_session.add(msg)
    db_session.commit()

    # Replay message
    res_replay = client.post(
        "/api/v1/scraping/dlq/replay",
        headers=AUTH_HEADERS,
        json={"message_ids": [str(msg.id)]},
    )
    assert res_replay.status_code == 202

    # Verify atomic updates to ScrapingJob
    db_session.expire_all()
    replayed_job = db_session.get(ScrapingJob, job.id)
    assert replayed_job is not None
    assert replayed_job.status == "queued"
    assert replayed_job.attempts == 0
    assert replayed_job.started_at is None
    assert replayed_job.finished_at is None
    assert replayed_job.error_reason is None
    assert replayed_job.last_dlq_reason == "Fatal connection timeout to external vendor"
    # Observations count is preserved cumulatively (not reset to 0)
    assert replayed_job.observations_created == 5
    assert replayed_job.replay_count == 1
    assert replayed_job.replayed_at is not None

    # Verify LocalQueueMessage state
    replayed_msg = db_session.get(LocalQueueMessage, msg.id)
    assert replayed_msg is not None
    assert replayed_msg.queue_name == "scraping-jobs"
    assert replayed_msg.status == "pending"
    assert replayed_msg.attempts == 0
    assert replayed_msg.payload["attempt"] == 1
    assert replayed_msg.replay_count == 1
    assert replayed_msg.replayed_at is not None


def test_dlq_re_entering_dlq_updates_sent_to_dlq_at_and_accumulates_replay_count(
    db_session: Session,
):
    """When a replayed job fails again, sent_to_dlq_at is updated and replay_count remains."""
    store, prod, _ = create_dlq_fixtures(db_session)
    now = datetime.now(timezone.utc)

    # Clean any leftover messages in queues
    db_session.execute(
        text(
            "DELETE FROM local_queue_messages "
            "WHERE queue_name IN ('scraping-jobs', 'scraping-jobs-dlq')"
        )
    )
    db_session.commit()

    job = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store.id,
        status="dead_letter",
        trigger_type="manual",
        batch_size=1,
        attempts=3,
        sent_to_dlq_at=now - timedelta(hours=2),
    )
    db_session.add(job)
    db_session.flush()

    msg = LocalQueueMessage(
        id=uuid.uuid4(),
        queue_name="scraping-jobs-dlq",
        payload={
            "job_id": str(job.id),
            "store_id": str(store.id),
            "product_ids": [str(prod.id)],
        },
        status="dlq",
        attempts=3,
        sent_to_dlq_at=now - timedelta(hours=2),
    )
    db_session.add(msg)
    db_session.commit()

    # Replay message
    res = client.post(
        "/api/v1/scraping/dlq/replay",
        headers=AUTH_HEADERS,
        json={"message_ids": [str(msg.id)]},
    )
    assert res.status_code == 202

    # Simulate message re-entering DLQ after second failure
    queue = PostgresQueue(session_factory=SessionLocal)
    # Claim message
    claimed = queue.receive_messages("scraping-jobs", max_messages=1)
    assert len(claimed) == 1
    assert claimed[0].message_id == str(msg.id)

    new_dlq_time = datetime.now(timezone.utc)
    queue.send_to_dlq(
        "scraping-jobs-dlq",
        message_payload=claimed[0].body,
        error_reason="Second fatal error",
        attempts=3,
        receipt_handle=claimed[0].receipt_handle,
    )

    db_session.expire_all()
    second_dlq_msg = db_session.get(LocalQueueMessage, msg.id)
    assert second_dlq_msg is not None
    assert second_dlq_msg.queue_name == "scraping-jobs-dlq"
    assert second_dlq_msg.status == "dlq"
    # Cumulative replay count preserved
    assert second_dlq_msg.replay_count == 1
    # Updated sent_to_dlq_at
    assert second_dlq_msg.sent_to_dlq_at is not None
    assert second_dlq_msg.sent_to_dlq_at >= new_dlq_time - timedelta(seconds=2)


def test_skipped_store_blocked_never_moves_to_dlq_nor_replayable(db_session: Session):
    """StoreBlockedError results in status='skipped', never enters DLQ, sent_to_dlq_at is None,
    never appears in GET /dlq, and cannot be replayed."""
    store, prod, _ = create_dlq_fixtures(db_session)
    now = datetime.now(timezone.utc)

    # Clean existing DLQ
    db_session.execute(
        text(
            "DELETE FROM local_queue_messages "
            "WHERE queue_name IN ('scraping-jobs', 'scraping-jobs-dlq')"
        )
    )
    db_session.commit()

    # Job was marked as skipped due to store blocked
    job = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store.id,
        status="skipped",
        trigger_type="manual",
        batch_size=1,
        attempts=1,
        error_reason="SKIPPED_STORE_BLOCKED: Cloudflare 403 Challenge",
        finished_at=now,
    )
    db_session.add(job)
    db_session.commit()

    # Verify sent_to_dlq_at is None on skipped job
    assert job.sent_to_dlq_at is None
    assert job.replay_count == 0
    assert job.replayed_at is None

    # GET /dlq must be empty (skipped jobs never enter DLQ)
    res_dlq = client.get("/api/v1/scraping/dlq", headers=AUTH_HEADERS)
    assert res_dlq.status_code == 200
    assert res_dlq.json()["total"] == 0
    assert len(res_dlq.json()["items"]) == 0

    # Even if someone artificially crafted a DLQ message pointing to this skipped job:
    fake_dlq_msg = LocalQueueMessage(
        id=uuid.uuid4(),
        queue_name="scraping-jobs-dlq",
        payload={
            "job_id": str(job.id),
            "store_id": str(store.id),
            "product_ids": [str(prod.id)],
        },
        status="dlq",
        attempts=1,
        sent_to_dlq_at=now,
    )
    db_session.add(fake_dlq_msg)
    db_session.commit()

    # In GET /dlq, it must be marked replayable=False because job is 'skipped', not 'dead_letter'
    res_check = client.get(f"/api/v1/scraping/dlq?store_id={store.id}", headers=AUTH_HEADERS)
    assert res_check.status_code == 200
    item = res_check.json()["items"][0]
    assert item["replayable"] is False
    assert item["replay_block_reason"] == "JOB_STATUS_NOT_REPLAYABLE: skipped"

    # POST /replay must be rejected with 409 Conflict
    res_replay = client.post(
        "/api/v1/scraping/dlq/replay",
        headers=AUTH_HEADERS,
        json={"message_ids": [str(fake_dlq_msg.id)]},
    )
    assert res_replay.status_code == 409
    assert "skipped" in res_replay.text
