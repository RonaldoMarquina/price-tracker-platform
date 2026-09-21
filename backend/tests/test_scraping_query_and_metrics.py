"""Tests for scraping jobs query, metrics, and manual dispatch endpoints."""

import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from shared.queue.models import LocalQueueMessage
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.advisory_lock import DISPATCHER_MANUAL_LOCK_ID
from app.db.models import Category, Product, ScrapingJob, Store, StoreProduct
from app.db.session import SessionLocal, engine
from app.main import app
from app.services.dispatch_service import dispatch_service

client = TestClient(app)
VALID_TOKEN = os.getenv("INTERNAL_API_KEY", "dev-internal-secret-token")
AUTH_HEADERS = {"Authorization": f"Bearer {VALID_TOKEN}"}


@pytest.fixture
def db_session():
    """Yield a transactional database session."""
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


def create_fixtures(db: Session):
    """Create test category, stores, products, and associations."""
    cat = Category(
        id=uuid.uuid4(),
        name=f"Test Cat {uuid.uuid4().hex[:6]}",
        slug=f"cat-{uuid.uuid4().hex[:6]}",
    )
    db.add(cat)
    db.flush()

    store_necs = db.scalars(select(Store).where(Store.domain == "necs.pe")).first()
    if not store_necs:
        store_necs = Store(
            id=uuid.uuid4(),
            name=f"NECS Test {uuid.uuid4().hex[:6]}",
            domain="necs.pe",
            is_active=True,
        )
        db.add(store_necs)

    store_mk = db.scalars(select(Store).where(Store.domain == "memorykings.pe")).first()
    if not store_mk:
        store_mk = Store(
            id=uuid.uuid4(),
            name=f"MemoryKings Test {uuid.uuid4().hex[:6]}",
            domain="memorykings.pe",
            is_active=True,
        )
        db.add(store_mk)

    store_inactive = db.scalars(select(Store).where(Store.is_active.is_(False))).first()
    if not store_inactive:
        store_inactive = Store(
            id=uuid.uuid4(),
            name=f"Inactive Test {uuid.uuid4().hex[:6]}",
            domain=f"inactive-{uuid.uuid4().hex[:6]}.pe",
            is_active=False,
        )
        db.add(store_inactive)
    db.flush()

    prod1 = Product(
        id=uuid.uuid4(),
        category_id=cat.id,
        name=f"Product 1 {uuid.uuid4().hex[:6]}",
        slug=f"p1-{uuid.uuid4().hex[:6]}",
        is_active=True,
    )
    prod2 = Product(
        id=uuid.uuid4(),
        category_id=cat.id,
        name=f"Product 2 {uuid.uuid4().hex[:6]}",
        slug=f"p2-{uuid.uuid4().hex[:6]}",
        is_active=True,
    )
    db.add_all([prod1, prod2])
    db.flush()

    sp1 = StoreProduct(
        id=uuid.uuid4(),
        store_id=store_necs.id,
        product_id=prod1.id,
        product_url="https://necs.pe/p1",
        is_active=True,
    )
    sp2 = StoreProduct(
        id=uuid.uuid4(),
        store_id=store_mk.id,
        product_id=prod2.id,
        product_url="https://memorykings.pe/p2",
        is_active=True,
    )
    db.add_all([sp1, sp2])
    db.commit()

    return store_necs, store_mk, store_inactive, prod1, prod2


def test_scraping_endpoints_require_authentication():
    """All scraping inspection and dispatch endpoints return 401 when unauthorized."""
    random_id = str(uuid.uuid4())

    endpoints = [
        ("GET", "/api/v1/scraping/jobs"),
        ("GET", f"/api/v1/scraping/jobs/{random_id}"),
        ("GET", "/api/v1/scraping/queue/metrics"),
        ("POST", "/api/v1/scraping/dispatch"),
    ]

    for method, path in endpoints:
        # Missing token
        res = client.request(method, path)
        assert res.status_code == 401, f"Expected 401 for missing token on {method} {path}"

        # Invalid token
        res_invalid = client.request(
            method, path, headers={"Authorization": "Bearer invalid-secret"}
        )
        assert res_invalid.status_code == 401, f"Expected 401 for bad token on {method} {path}"


def test_list_jobs_pagination_and_filters(db_session: Session):
    """GET /jobs supports pagination, date filters, and status filters."""
    store, _, _, _, _ = create_fixtures(db_session)
    now = datetime.now(timezone.utc)

    # Create 3 jobs for the test store
    job1 = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store.id,
        status="completed",
        trigger_type="manual",
        batch_size=2,
        observations_created=2,
        created_at=now - timedelta(minutes=10),
    )
    job2 = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store.id,
        status="failed",
        trigger_type="manual",
        batch_size=1,
        observations_created=0,
        error_reason="Permanent 404 structure missing",
        created_at=now - timedelta(minutes=5),
    )
    job3 = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store.id,
        status="queued",
        trigger_type="manual",
        batch_size=1,
        created_at=now,
    )
    db_session.add_all([job1, job2, job3])
    db_session.commit()

    # 1. Filter by store_id and pagination
    res = client.get(
        f"/api/v1/scraping/jobs?store_id={store.id}&page=1&page_size=2",
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["total_pages"] == 2
    # Verify deterministic sorting (job3 was created most recently)
    assert data["items"][0]["id"] == str(job3.id)

    # 2. Filter by status
    res_status = client.get(
        f"/api/v1/scraping/jobs?store_id={store.id}&status=failed",
        headers=AUTH_HEADERS,
    )
    assert res_status.status_code == 200
    data_status = res_status.json()
    assert data_status["total"] == 1
    assert data_status["items"][0]["id"] == str(job2.id)
    assert data_status["items"][0]["error_reason"] == "Permanent 404 structure missing"

    # Cleanup
    db_session.delete(job1)
    db_session.delete(job2)
    db_session.delete(job3)
    db_session.commit()


def test_list_jobs_invalid_date_range_returns_422():
    """GET /jobs returns 422 if from_date is later than to_date."""
    from_date = "2026-09-20T18:00:00Z"
    to_date = "2026-09-20T17:00:00Z"

    res = client.get(
        f"/api/v1/scraping/jobs?from_date={from_date}&to_date={to_date}",
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 422


def test_get_job_detail_success_and_404(db_session: Session):
    """GET /jobs/{job_id} returns detailed audit data or 404."""
    store, _, _, _, _ = create_fixtures(db_session)
    job = ScrapingJob(
        id=uuid.uuid4(),
        store_id=store.id,
        status="completed",
        trigger_type="manual",
        batch_size=5,
        observations_created=5,
        attempts=1,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    db_session.commit()

    # Success
    res = client.get(f"/api/v1/scraping/jobs/{job.id}", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == str(job.id)
    assert data["store_id"] == str(store.id)
    assert data["store_name"] == store.name
    assert data["status"] == "completed"
    assert data["batch_size"] == 5
    assert data["observations_created"] == 5

    # Nonexistent
    non_existent = str(uuid.uuid4())
    res_404 = client.get(f"/api/v1/scraping/jobs/{non_existent}", headers=AUTH_HEADERS)
    assert res_404.status_code == 404

    # Cleanup
    db_session.delete(job)
    db_session.commit()


def test_queue_metrics_endpoint(db_session: Session):
    """GET /queue/metrics separates live queue state from historical jobs performance."""
    now = datetime.now(timezone.utc)

    # 1. Clean queue test messages
    db_session.execute(
        text("DELETE FROM local_queue_messages WHERE queue_name LIKE 'scraping-jobs%'")
    )
    db_session.commit()

    # Insert 1 visible pending message
    msg_pending = LocalQueueMessage(
        id=uuid.uuid4(),
        queue_name="scraping-jobs",
        payload={"job_id": str(uuid.uuid4())},
        status="pending",
        attempts=0,
        visible_at=now - timedelta(seconds=60),
        created_at=now - timedelta(seconds=60),
    )
    # Insert 1 processing message
    msg_proc = LocalQueueMessage(
        id=uuid.uuid4(),
        queue_name="scraping-jobs",
        payload={"job_id": str(uuid.uuid4())},
        status="processing",
        attempts=1,
        visible_at=now + timedelta(seconds=30),
        created_at=now - timedelta(seconds=30),
    )
    # Insert 1 retrying message (attempts > 0, pending)
    msg_retry = LocalQueueMessage(
        id=uuid.uuid4(),
        queue_name="scraping-jobs",
        payload={"job_id": str(uuid.uuid4())},
        status="pending",
        attempts=2,
        visible_at=now + timedelta(seconds=15),
        created_at=now - timedelta(seconds=45),
    )
    # Insert 1 DLQ message
    msg_dlq = LocalQueueMessage(
        id=uuid.uuid4(),
        queue_name="scraping-jobs-dlq",
        payload={"job_id": str(uuid.uuid4())},
        status="dlq",
        attempts=3,
        visible_at=now,
        created_at=now - timedelta(seconds=120),
    )
    db_session.add_all([msg_pending, msg_proc, msg_retry, msg_dlq])
    db_session.commit()

    res = client.get("/api/v1/scraping/queue/metrics?window_hours=24", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()

    assert data["pending"] == 1
    assert data["processing"] == 1
    assert data["retrying"] == 1
    assert data["dlq"] == 1
    assert data["oldest_pending_seconds"] is not None
    assert data["oldest_pending_seconds"] >= 50.0

    # Cleanup
    db_session.delete(msg_pending)
    db_session.delete(msg_proc)
    db_session.delete(msg_retry)
    db_session.delete(msg_dlq)
    db_session.commit()


def test_manual_dispatch_specific_store(db_session: Session):
    """POST /dispatch for a specific store generates manual jobs."""
    store, _, _, _, _ = create_fixtures(db_session)

    res = client.post(
        "/api/v1/scraping/dispatch",
        json={"store_id": str(store.id)},
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 202
    data = res.json()
    assert data["jobs_created"] == 1
    assert len(data["job_ids"]) == 1

    job_id = uuid.UUID(data["job_ids"][0])
    job = db_session.execute(
        select(ScrapingJob).where(ScrapingJob.id == job_id)
    ).scalar_one_or_none()

    assert job is not None
    assert job.trigger_type == "manual"
    assert job.dispatch_slot is None
    assert job.status == "queued"

    # Cleanup
    db_session.delete(job)
    db_session.commit()


def test_manual_dispatch_invalid_or_inactive_store(db_session: Session):
    """POST /dispatch returns 404 for nonexistent and 422 for inactive store."""
    _, _, store_inactive, _, _ = create_fixtures(db_session)

    # 404 on nonexistent
    res_404 = client.post(
        "/api/v1/scraping/dispatch",
        json={"store_id": str(uuid.uuid4())},
        headers=AUTH_HEADERS,
    )
    assert res_404.status_code == 404

    # 422 on inactive store
    res_422 = client.post(
        "/api/v1/scraping/dispatch",
        json={"store_id": str(store_inactive.id)},
        headers=AUTH_HEADERS,
    )
    assert res_422.status_code == 422


def test_manual_dispatch_concurrency_lock_returns_409():
    """If another manual dispatch is currently holding the advisory lock, returns 409 Conflict."""
    conn = engine.connect()
    try:
        # Hold manual advisory lock
        acquired = conn.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": DISPATCHER_MANUAL_LOCK_ID},
        ).scalar()
        assert acquired is True

        # Attempt manual dispatch via API
        res = client.post("/api/v1/scraping/dispatch", json={}, headers=AUTH_HEADERS)
        assert res.status_code == 409
        error_msg = res.json().get("error", {}).get("message") or res.json().get("detail", "")
        assert "ya se encuentra en ejecución" in error_msg

    finally:
        conn.execute(
            text("SELECT pg_advisory_unlock(:lock_id)"),
            {"lock_id": DISPATCHER_MANUAL_LOCK_ID},
        )
        conn.close()


def test_manual_dispatch_rollback_on_enqueue_failure_per_store(db_session: Session):
    """If queue.send_message fails for a store, ScrapingJob is rolled back cleanly."""
    store, _, _, _, _ = create_fixtures(db_session)

    # Mock queue.send_message to raise an error
    mock_queue = MagicMock()
    mock_queue.send_message.side_effect = RuntimeError("Simulated connection failure to queue")

    custom_service = type(dispatch_service)(
        db_engine=engine,
        session_factory=SessionLocal,
        queue=mock_queue,
    )

    result = custom_service.dispatch_manual(store_id=store.id, allow_offline_adapters=True)

    assert result.jobs_created == 0
    assert store.id in result.failed_stores

    # Ensure no orphaned ScrapingJob remained in the database
    orphaned = db_session.execute(
        select(ScrapingJob).where(
            ScrapingJob.store_id == store.id,
            ScrapingJob.status == "queued",
        )
    ).scalars().all()

    # None of the failed ones were persisted
    assert len(orphaned) == 0
