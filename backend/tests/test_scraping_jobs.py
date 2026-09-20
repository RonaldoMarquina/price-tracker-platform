"""Integration tests for POST /api/v1/scraping/jobs endpoint."""

import uuid

from fastapi.testclient import TestClient
from shared.queue.models import LocalQueueMessage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Category, Product, Store, StoreProduct
from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)


def get_or_create_test_entities() -> tuple[Store, Product]:
    """Helper to ensure a valid store and product exist in database."""
    db: Session = SessionLocal()
    try:
        store = db.scalars(select(Store).where(Store.is_active.is_(True))).first()
        if not store:
            store = Store(
                name=f"Test Store {uuid.uuid4().hex[:6]}",
                domain=f"store-{uuid.uuid4().hex[:6]}.com",
            )
            db.add(store)
            db.flush()

        cat = db.scalars(select(Category)).first()
        if not cat:
            cat = Category(name=f"Cat {uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
            db.add(cat)
            db.flush()

        product = db.scalars(select(Product).where(Product.is_active.is_(True))).first()
        if not product:
            product = Product(
                category_id=cat.id,
                name="Test CPU",
                slug=f"test-cpu-{uuid.uuid4().hex[:6]}",
                brand="AMD",
                model="7800X3D",
            )
            db.add(product)
            db.flush()

        # Ensure StoreProduct link exists
        sp = db.scalars(
            select(StoreProduct).where(
                StoreProduct.product_id == product.id, StoreProduct.store_id == store.id
            )
        ).first()
        if not sp:
            sp = StoreProduct(
                product_id=product.id,
                store_id=store.id,
                product_url=f"https://example.com/p/{uuid.uuid4().hex[:6]}",
            )
            db.add(sp)
            db.flush()

        db.commit()
        db.refresh(store)
        db.refresh(product)
        return store, product
    finally:
        db.close()


def test_create_job_unauthorized_missing_token() -> None:
    """Attempting to create a job without authorization header must return 401."""
    store, product = get_or_create_test_entities()
    response = client.post(
        "/api/v1/scraping/jobs",
        json={"store_id": str(store.id), "product_ids": [str(product.id)]},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "UNAUTHORIZED"


def test_create_job_unauthorized_invalid_token() -> None:
    """Attempting to create a job with invalid Bearer token must return 401."""
    store, product = get_or_create_test_entities()
    response = client.post(
        "/api/v1/scraping/jobs",
        headers={"Authorization": "Bearer invalid-secret-token"},
        json={"store_id": str(store.id), "product_ids": [str(product.id)]},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "UNAUTHORIZED"


def test_create_job_store_not_found() -> None:
    """Requesting a job for a non-existent store_id must return 404 STORE_NOT_FOUND."""
    _, product = get_or_create_test_entities()
    fake_store_id = uuid.uuid4()
    response = client.post(
        "/api/v1/scraping/jobs",
        headers={"Authorization": f"Bearer {settings.INTERNAL_API_KEY}"},
        json={"store_id": str(fake_store_id), "product_ids": [str(product.id)]},
    )
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "STORE_NOT_FOUND"


def test_create_job_product_not_found() -> None:
    """Requesting a job for a non-existent product_id must return 404 PRODUCT_NOT_FOUND."""
    store, _ = get_or_create_test_entities()
    fake_product_id = uuid.uuid4()
    response = client.post(
        "/api/v1/scraping/jobs",
        headers={"Authorization": f"Bearer {settings.INTERNAL_API_KEY}"},
        json={"store_id": str(store.id), "product_ids": [str(fake_product_id)]},
    )
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "PRODUCT_NOT_FOUND"


def test_create_job_empty_product_ids_validation_error() -> None:
    """Payload with empty product_ids must return 422 Unprocessable Entity."""
    store, _ = get_or_create_test_entities()
    response = client.post(
        "/api/v1/scraping/jobs",
        headers={"Authorization": f"Bearer {settings.INTERNAL_API_KEY}"},
        json={"store_id": str(store.id), "product_ids": []},
    )
    assert response.status_code == 422


def test_create_job_success_enqueues_and_returns_202() -> None:
    """Valid request returns 202 Accepted and persists message in local_queue_messages."""
    store, product = get_or_create_test_entities()
    response = client.post(
        "/api/v1/scraping/jobs",
        headers={"Authorization": f"Bearer {settings.INTERNAL_API_KEY}"},
        json={"store_id": str(store.id), "product_ids": [str(product.id)]},
    )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "queued"

    job_id = uuid.UUID(data["job_id"])

    # Verify message persisted in PostgreSQL queue
    db: Session = SessionLocal()
    try:
        msg = db.scalars(
            select(LocalQueueMessage).where(LocalQueueMessage.queue_name == "scraping-jobs")
        ).all()
        matching = [m for m in msg if m.payload.get("job_id") == str(job_id)]
        assert len(matching) == 1
        persisted = matching[0]
        assert persisted.status == "pending"
        assert persisted.payload["version"] == 1
        assert persisted.payload["store_id"] == str(store.id)
        assert persisted.payload["product_ids"] == [str(product.id)]
        assert persisted.attempts == 0
    finally:
        for m in matching:
            db.delete(m)
        db.commit()
        db.close()
