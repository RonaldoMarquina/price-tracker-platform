"""End-to-End integration test covering the complete multi-store scraping lifecycle.

Validation journey:
1. Enqueue job via API (POST /api/v1/scraping/jobs) with internal auth token.
2. Verify message persisted in PostgreSQL queue (local_queue_messages) with status 'pending'.
3. Worker ScrapingConsumer claims and processes message using offline HTML fixture adapter.
4. Verify persistence in price_observations with price, availability, and price_condition.
5. Query read API (GET /api/v1/products/{id}) and verify authoritative best_price contract.
6. Verify strict idempotency on duplicate job_id re-delivery (0 duplicates).
7. Verify distinct job with same price creates a new historical observation.
8. Verify deactivated store (Sercoplus) is skipped cleanly without retries and without DLQ.
"""

import os
import socket
import subprocess
import sys
import time
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock

import httpx
import pytest
from shared.queue.models import LocalQueueMessage
from shared.queue.postgres import PostgresQueue
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.computershop_adapter import ComputerShopAdapter
from app.adapters.sercoplus_adapter import SercoplusAdapter
from app.consumers.scraping_consumer import ScrapingConsumer
from app.core.config import worker_settings
from app.core.network import SafeHttpClient
from app.db.models import Category, PriceObservation, Product, Store, StoreProduct
from app.db.session import SessionLocal
from app.repositories.observation_repository import ObservationRepository
from app.services.scraping_service import ScrapingWorkerService

INTERNAL_API_KEY = "dev-internal-secret-token"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "computershop"


def get_free_port() -> int:
    """Find an available ephemeral port for the isolated test server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def api_server() -> Generator[str, None, None]:
    """Start an isolated FastAPI backend server connected to test database."""
    configured_url = os.getenv("API_BASE_URL")
    if configured_url:
        yield configured_url
        return

    test_port = str(get_free_port())
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
    for _ in range(50):
        try:
            r = httpx.get(f"{base_url}/health", timeout=1.0)
            if r.status_code == 200:
                started = True
                break
        except Exception:
            time.sleep(0.1)

    if not started:
        proc.terminate()
        raise RuntimeError(f"Failed to start isolated backend test server on port {test_port}")

    try:
        yield base_url
    finally:
        proc.terminate()
        proc.wait()


@pytest.fixture
def isolated_flow_entities() -> Generator[dict, None, None]:
    """Create isolated entities for the full E2E journey."""
    db: Session = SessionLocal()
    category = Category(
        name=f"E2E Cat-{uuid.uuid4().hex[:6]}",
        slug=f"e2e-cat-{uuid.uuid4().hex[:6]}",
    )
    db.add(category)
    db.flush()

    product = Product(
        category_id=category.id,
        name="DeepCool AK620 Digital ARGB",
        slug=f"deepcool-ak620-{uuid.uuid4().hex[:6]}",
        brand="DeepCool",
        model="AK620 Digital",
        mpn="R-AK620-BKADMN-GJD",
    )
    db.add(product)

    # Active store: Computer Shop Perú (lookup existing or create if missing)
    store_active = db.scalar(select(Store).where(Store.domain == "computershopperu.com"))
    created_active = False
    if not store_active:
        store_active = Store(
            name="Computer Shop Perú",
            domain="computershopperu.com",
            is_active=True,
        )
        db.add(store_active)
        created_active = True

    # Deactivated store: Sercoplus (lookup existing or create if missing)
    store_inactive = db.scalar(select(Store).where(Store.domain == "sercoplus.com"))
    created_inactive = False
    if not store_inactive:
        store_inactive = Store(
            name="Sercoplus",
            domain="sercoplus.com",
            is_active=False,
        )
        db.add(store_inactive)
        created_inactive = True

    db.flush()

    sp_active = StoreProduct(
        product_id=product.id,
        store_id=store_active.id,
        product_url=(
            "https://computershopperu.com/producto/refrigeracion-aire/"
            "40069-deepcool-ak620-digital-se-black-argb-cooler-cpu-pnr-ak620-bkadmn-gjd.html"
        ),
        external_sku="269645564",
    )
    sp_inactive = StoreProduct(
        product_id=product.id,
        store_id=store_inactive.id,
        product_url="https://sercoplus.com/cooler-cpu-ak620.html",
        external_sku="SP-AK620",
    )
    db.add_all([sp_active, sp_inactive])
    db.commit()

    created_job_ids: list[str] = []

    try:
        yield {
            "product": product,
            "category": category,
            "store_active": store_active,
            "store_inactive": store_inactive,
            "sp_active": sp_active,
            "sp_inactive": sp_inactive,
            "job_ids": created_job_ids,
        }
    finally:
        with SessionLocal() as clean_db:
            # 1. Cleanup queue messages
            for jid in created_job_ids:
                msgs = clean_db.scalars(
                    select(LocalQueueMessage).where(
                        LocalQueueMessage.queue_name.in_(["scraping-jobs", "scraping-jobs-dlq"])
                    )
                ).all()
                for m in msgs:
                    if m.payload and m.payload.get("job_id") == jid:
                        clean_db.delete(m)

            # 2. Cleanup observations
            clean_db.query(PriceObservation).filter(
                PriceObservation.store_product_id.in_([sp_active.id, sp_inactive.id])
            ).delete(synchronize_session=False)

            # 3. Cleanup store_products
            clean_db.query(StoreProduct).filter(
                StoreProduct.id.in_([sp_active.id, sp_inactive.id])
            ).delete(synchronize_session=False)

            # 4. Cleanup product and category
            clean_db.query(Product).filter(Product.id == product.id).delete(
                synchronize_session=False
            )
            clean_db.query(Category).filter(Category.id == category.id).delete(
                synchronize_session=False
            )

            # Only delete stores if created exclusively for this fixture
            if created_active:
                clean_db.query(Store).filter(Store.id == store_active.id).delete(
                    synchronize_session=False
                )
            if created_inactive:
                clean_db.query(Store).filter(Store.id == store_inactive.id).delete(
                    synchronize_session=False
                )

            clean_db.commit()


def test_complete_e2e_scraping_flow_and_presentation(
    api_server: str, isolated_flow_entities: dict
) -> None:
    """Validate complete flow:
    API enqueue -> PostgreSQL Queue -> Worker with offline fixture ->
    PostgreSQL persistence -> API read -> Frontend contract -> Idempotency -> Deactivated store.
    """
    entities = isolated_flow_entities
    product = entities["product"]
    store_active = entities["store_active"]
    sp_active = entities["sp_active"]
    store_inactive = entities["store_inactive"]

    # --------------------------------------------------------------------------
    # 1. Enqueue job via API (POST /api/v1/scraping/jobs)
    # --------------------------------------------------------------------------
    resp = httpx.post(
        f"{api_server}/api/v1/scraping/jobs",
        headers={"Authorization": f"Bearer {INTERNAL_API_KEY}"},
        json={"store_id": str(store_active.id), "product_ids": [str(product.id)]},
        timeout=10.0,
    )
    assert resp.status_code == 202
    job_data = resp.json()
    job_id = job_data["job_id"]
    entities["job_ids"].append(job_id)

    # --------------------------------------------------------------------------
    # 2. Verify message persisted in PostgreSQL queue (local_queue_messages)
    # --------------------------------------------------------------------------
    with SessionLocal() as db:
        queue_msgs = db.scalars(
            select(LocalQueueMessage).where(LocalQueueMessage.queue_name == "scraping-jobs")
        ).all()
        matching = [m for m in queue_msgs if m.payload.get("job_id") == job_id]
        assert len(matching) == 1
        msg_record = matching[0]
        assert msg_record.status == "pending"
        assert msg_record.attempts == 0

    # --------------------------------------------------------------------------
    # 3. Worker ScrapingConsumer processes message using offline HTML fixture
    # --------------------------------------------------------------------------
    offline_html = (FIXTURES_DIR / "product_in_stock.html").read_text(encoding="utf-8")
    mock_http_client = MagicMock(spec=SafeHttpClient)
    mock_http_client.get.return_value = httpx.Response(
        status_code=200,
        text=offline_html,
        request=httpx.Request("GET", sp_active.product_url),
    )

    adapter = ComputerShopAdapter(http_client=mock_http_client)
    worker_queue = PostgresQueue(session_factory=SessionLocal)
    consumer = ScrapingConsumer(
        queue=worker_queue,
        service=ScrapingWorkerService(adapter=adapter, repository=ObservationRepository()),
        session_factory=SessionLocal,
        queue_name="scraping-jobs",
        dlq_name="scraping-jobs-dlq",
        max_retries=3,
    )

    # Process until target message is completed
    for _ in range(5):
        with SessionLocal() as check_db:
            refreshed = check_db.scalar(
                select(LocalQueueMessage).where(LocalQueueMessage.id == msg_record.id)
            )
            if refreshed and refreshed.status == "completed":
                break
        consumer.process_next_message()

    # --------------------------------------------------------------------------
    # 4. Verify persistence of price, availability, and price_condition
    # --------------------------------------------------------------------------
    with SessionLocal() as db:
        obs = db.scalars(
            select(PriceObservation).where(PriceObservation.store_product_id == sp_active.id)
        ).all()
        assert len(obs) == 1
        observation = obs[0]
        assert observation.price == Decimal("253.13")
        assert observation.currency == "PEN"
        assert observation.availability == "in_stock"
        assert observation.price_condition == "cash_or_bank_transfer"

    # --------------------------------------------------------------------------
    # 5. Query read API (GET /api/v1/products/{id}) and verify best_price contract
    # --------------------------------------------------------------------------
    detail_resp = httpx.get(f"{api_server}/api/v1/products/{product.id}", timeout=10.0)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()

    assert detail["name"] == "DeepCool AK620 Digital ARGB"
    assert detail["best_price"] is not None
    best_price = detail["best_price"]
    assert best_price["amount"] == "253.13"
    assert best_price["currency"] == "PEN"
    assert best_price["store_name"] == store_active.name
    assert best_price["price_condition"] == "cash_or_bank_transfer"

    # --------------------------------------------------------------------------
    # 6. Idempotency: Second processing of the exact same job_id creates NO duplicate
    # --------------------------------------------------------------------------
    worker_queue.send_message("scraping-jobs", msg_record.payload)
    consumer.process_next_message()

    with SessionLocal() as db:
        obs_after_retry = db.scalars(
            select(PriceObservation).where(PriceObservation.store_product_id == sp_active.id)
        ).all()
        assert len(obs_after_retry) == 1  # Still 1, 0 duplicates!

    # --------------------------------------------------------------------------
    # 7. Distinct job with same price creates a new historical observation
    # --------------------------------------------------------------------------
    resp_job2 = httpx.post(
        f"{api_server}/api/v1/scraping/jobs",
        headers={"Authorization": f"Bearer {INTERNAL_API_KEY}"},
        json={"store_id": str(store_active.id), "product_ids": [str(product.id)]},
        timeout=10.0,
    )
    assert resp_job2.status_code == 202
    job2_id = resp_job2.json()["job_id"]
    entities["job_ids"].append(job2_id)

    # Process job 2
    for _ in range(5):
        consumer.process_next_message()

    with SessionLocal() as db:
        obs_after_job2 = db.scalars(
            select(PriceObservation).where(PriceObservation.store_product_id == sp_active.id)
        ).all()
        assert len(obs_after_job2) == 2  # New historical record created!

    # --------------------------------------------------------------------------
    # 8. Sercoplus deactivated store confirmed without retry and without DLQ
    # --------------------------------------------------------------------------
    # 8a. API gate: Enqueuing a job for an inactive store is rejected with 404
    resp_inactive_api = httpx.post(
        f"{api_server}/api/v1/scraping/jobs",
        headers={"Authorization": f"Bearer {INTERNAL_API_KEY}"},
        json={"store_id": str(store_inactive.id), "product_ids": [str(product.id)]},
        timeout=10.0,
    )
    assert resp_inactive_api.status_code == 404
    assert resp_inactive_api.json()["error"]["code"] == "STORE_NOT_FOUND"

    # 8b. Worker consumer gate: If an inactive store message exists in queue,
    # it is processed, acknowledged/completed with SKIPPED_STORE_DISABLED,
    # not retried (attempts == 1), and NOT forwarded to DLQ.
    inactive_job_id = str(uuid.uuid4())
    entities["job_ids"].append(inactive_job_id)
    worker_queue.send_message(
        "scraping-jobs",
        {
            "version": 1,
            "job_id": inactive_job_id,
            "store_id": str(store_inactive.id),
            "product_ids": [str(product.id)],
            "requested_at": "2026-09-20T12:00:00Z",
            "attempt": 1,
        },
    )

    consumer_inactive = ScrapingConsumer(
        queue=worker_queue,
        service=ScrapingWorkerService(
            adapter=SercoplusAdapter(), repository=ObservationRepository()
        ),
        session_factory=SessionLocal,
        queue_name="scraping-jobs",
        dlq_name="scraping-jobs-dlq",
        max_retries=3,
    )
    consumer_inactive.process_next_message()

    with SessionLocal() as db:
        # Verify message was skipped and marked completed/deleted without retrying
        inactive_msg = db.scalar(
            select(LocalQueueMessage).where(
                LocalQueueMessage.queue_name == "scraping-jobs",
                LocalQueueMessage.payload["job_id"].astext == inactive_job_id,
            )
        )
        assert inactive_msg is not None
        assert inactive_msg.status == "completed"
        assert inactive_msg.attempts == 1  # No repeated retries!
        assert "SKIPPED_STORE_DISABLED" in (inactive_msg.error_reason or "")

        # Verify DLQ received NO messages for this job
        dlq_msgs = db.scalars(
            select(LocalQueueMessage).where(LocalQueueMessage.queue_name == "scraping-jobs-dlq")
        ).all()
        dlq_matching = [
            m for m in dlq_msgs if m.payload and m.payload.get("job_id") == inactive_job_id
        ]
        assert len(dlq_matching) == 0  # No DLQ pollution!
