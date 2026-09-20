"""End-to-End integration test covering the complete asynchronous scraping pipeline.

Flow:
1. POST /api/v1/scraping/jobs (Real HTTP call to API with internal auth token)
2. Message saved in PostgreSQL (local_queue_messages with status 'pending')
3. Worker in independent session claims message via SELECT ... FOR UPDATE SKIP LOCKED
4. Fake adapter generates deterministic result
5. Observation saved in PostgreSQL with unique source_hash
6. Message acknowledged and marked 'completed'
7. Reprocessing the same job_id verifies strict idempotency without duplicating observations
"""

import os
import subprocess
import sys
import time
import uuid
from decimal import Decimal
from typing import Generator

import httpx
import pytest
from shared.queue.models import LocalQueueMessage
from shared.queue.postgres import PostgresQueue
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.fake_store_adapter import FakeStoreAdapter
from app.consumers.scraping_consumer import ScrapingConsumer
from app.core.config import worker_settings
from app.db.models import (
    Category,
    PriceObservation,
    Product,
    ScrapingJob,
    Store,
    StoreProduct,
)
from app.db.session import SessionLocal
from app.repositories.observation_repository import ObservationRepository
from app.services.scraping_service import ScrapingWorkerService

INTERNAL_API_KEY = "dev-internal-secret-token"


@pytest.fixture(scope="module")
def api_server() -> Generator[str, None, None]:
    """Start or provide an isolated FastAPI backend server connected to test database."""
    configured_url = os.getenv("API_BASE_URL")
    if configured_url:
        yield configured_url
        return

    # Spin up isolated test server on port 8005 connected to price_tracker_test
    test_port = "8005"
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../backend"))
    env = os.environ.copy()
    env["DATABASE_URL"] = worker_settings.DATABASE_URL
    env["PYTHONPATH"] = "."
    env["API_PORT"] = test_port

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--port",
            test_port,
            "--host",
            "127.0.0.1",
        ],
        cwd=backend_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    base_url = f"http://127.0.0.1:{test_port}"
    started = False
    for _ in range(40):
        try:
            r = httpx.get(f"{base_url}/health", timeout=1.0)
            if r.status_code == 200:
                started = True
                break
        except Exception:
            time.sleep(0.1)

    if not started:
        proc.terminate()
        raise RuntimeError("Failed to start isolated backend test server on port 8005")

    try:
        yield base_url
    finally:
        proc.terminate()
        proc.wait()


@pytest.fixture
def isolated_e2e_entities() -> Generator[dict, None, None]:
    """Create exclusive Category, Product, Store, and StoreProduct with random UUIDs.

    Guarantees full teardown of created messages, observations, and entities even if test fails.
    """
    db: Session = SessionLocal()
    suffix = uuid.uuid4().hex[:8]

    category = Category(
        id=uuid.uuid4(),
        name=f"E2E Cat {suffix}",
        slug=f"e2e-cat-{suffix}",
    )
    product = Product(
        id=uuid.uuid4(),
        category_id=category.id,
        name=f"E2E Product {suffix}",
        slug=f"e2e-prod-{suffix}",
        brand="E2E Brand",
        model="E2E Model",
    )
    store = Store(
        id=uuid.uuid4(),
        name=f"E2E Store {suffix}",
        domain=f"e2e-{suffix}.com",
    )
    store_product = StoreProduct(
        id=uuid.uuid4(),
        product_id=product.id,
        store_id=store.id,
        product_url=f"https://e2e-{suffix}.com/item/{suffix}",
        is_active=True,
    )

    db.add(category)
    db.add(product)
    db.add(store)
    db.add(store_product)
    db.commit()
    db.refresh(store)
    db.refresh(product)
    db.refresh(store_product)

    created_job_ids: list[str] = []

    try:
        yield {
            "store": store,
            "product": product,
            "store_product": store_product,
            "category": category,
            "job_ids": created_job_ids,
        }
    finally:
        # Guaranteed teardown even if test fails:
        with SessionLocal() as clean_db:
            # 1. Delete queue messages created by this test
            for jid in created_job_ids:
                msgs = clean_db.scalars(
                    select(LocalQueueMessage).where(LocalQueueMessage.queue_name == "scraping-jobs")
                ).all()
                for m in msgs:
                    if m.payload and m.payload.get("job_id") == jid:
                        clean_db.delete(m)

            # 2. Delete observations generated exclusively for this store_product
            clean_db.query(PriceObservation).filter(
                PriceObservation.store_product_id == store_product.id
            ).delete(synchronize_session=False)

            # 3. Delete exclusive StoreProduct, Product, Category, and Store in FK order
            sp_to_delete = clean_db.get(StoreProduct, store_product.id)
            if sp_to_delete:
                clean_db.delete(sp_to_delete)
                clean_db.flush()
            p_to_delete = clean_db.get(Product, product.id)
            if p_to_delete:
                clean_db.delete(p_to_delete)
                clean_db.flush()
                c_to_delete = clean_db.get(Category, category.id)
                if c_to_delete:
                    clean_db.delete(c_to_delete)
                    clean_db.flush()
                clean_db.query(ScrapingJob).filter(
                    ScrapingJob.store_id == store.id
                ).delete(synchronize_session=False)
                clean_db.flush()
                s_to_delete = clean_db.get(Store, store.id)
                if s_to_delete:
                    clean_db.delete(s_to_delete)
                    clean_db.flush()

            clean_db.commit()


def test_e2e_scraping_pipeline_lifecycle(api_server: str, isolated_e2e_entities: dict) -> None:
    """Execute complete end-to-end scraping pipeline with fully isolated entities."""
    sp = isolated_e2e_entities["store_product"]
    store_id = sp.store_id
    product_id = sp.product_id

    # Step 1: Count observations before running job strictly for this exclusive store_product_id
    with SessionLocal() as db:
        obs_before = db.scalars(
            select(PriceObservation).where(PriceObservation.store_product_id == sp.id)
        ).all()
        initial_obs_count = len(obs_before)
        assert initial_obs_count == 0

    # Step 2: POST /api/v1/scraping/jobs by authorized internal operator
    response = httpx.post(
        f"{api_server}/api/v1/scraping/jobs",
        headers={"Authorization": f"Bearer {INTERNAL_API_KEY}"},
        json={"store_id": str(store_id), "product_ids": [str(product_id)]},
        timeout=10.0,
    )
    assert response.status_code == 202, f"Expected 202, got {response.status_code}: {response.text}"
    data = response.json()
    job_id = uuid.UUID(data["job_id"])
    assert data["status"] == "queued"
    isolated_e2e_entities["job_ids"].append(str(job_id))

    # Step 3: Verify message is saved in PostgreSQL queue with status 'pending'
    with SessionLocal() as db:
        queue_row = db.scalars(
            select(LocalQueueMessage).where(LocalQueueMessage.queue_name == "scraping-jobs")
        ).all()
        matching = [r for r in queue_row if r.payload.get("job_id") == str(job_id)]
        assert len(matching) == 1, "Job was not found in local_queue_messages"
        msg_record = matching[0]
        assert msg_record.status == "pending"
        assert msg_record.attempts == 0
        assert msg_record.receipt_handle is None

    # Step 4: Worker consumer processes messages until target job is completed
    worker_queue = PostgresQueue(session_factory=SessionLocal)
    consumer = ScrapingConsumer(
        queue=worker_queue,
        service=ScrapingWorkerService(
            adapter=FakeStoreAdapter(), repository=ObservationRepository()
        ),
        session_factory=SessionLocal,
        queue_name="scraping-jobs",
        dlq_name="scraping-jobs-dlq",
        max_retries=3,
    )

    for _ in range(5):
        with SessionLocal() as check_db:
            refreshed = check_db.scalar(
                select(LocalQueueMessage).where(LocalQueueMessage.id == msg_record.id)
            )
            if refreshed and refreshed.status == "completed":
                break
        consumer.process_next_message()

    # Step 5: Verify observation is saved in PostgreSQL strictly for this exclusive store_product_id
    with SessionLocal() as db:
        obs_after = db.scalars(
            select(PriceObservation).where(PriceObservation.store_product_id == sp.id)
        ).all()
        assert len(obs_after) == initial_obs_count + 1

        new_obs = obs_after[-1]
        assert new_obs.price > Decimal("0")
        assert new_obs.currency == "PEN"
        assert new_obs.availability == "in_stock"
        assert new_obs.source_hash is not None

    # Step 6: Verify message is confirmed (status 'completed', processed_at set)
    with SessionLocal() as verify_db:
        refreshed_msg = verify_db.scalar(
            select(LocalQueueMessage).where(LocalQueueMessage.id == msg_record.id)
        )
        assert refreshed_msg is not None
        assert refreshed_msg.status == "completed"
        assert refreshed_msg.processed_at is not None
        assert refreshed_msg.receipt_handle is None
        assert refreshed_msg.attempts >= 1

    # Step 7: Idempotency verification: Simulate re-delivery of the exact same message
    worker_queue.send_message("scraping-jobs", msg_record.payload)
    rehandled = consumer.process_next_message()
    assert rehandled is True

    # Count MUST NOT increase due to ON CONFLICT (source_hash) DO NOTHING
    with SessionLocal() as db:
        obs_recheck = db.scalars(
            select(PriceObservation).where(PriceObservation.store_product_id == sp.id)
        ).all()
        assert len(obs_recheck) == initial_obs_count + 1
