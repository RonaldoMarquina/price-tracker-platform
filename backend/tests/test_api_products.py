"""Integration tests for reading catalog and price history endpoints."""

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Category, PriceObservation, Product, Store, StoreProduct
from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)


def get_seeded_product() -> tuple[Product, Store, StoreProduct, PriceObservation]:
    """Helper to retrieve or ensure a product with price history exists in database."""
    db: Session = SessionLocal()
    try:
        product = db.scalars(select(Product).where(Product.slug == "amd-ryzen-7-5800x")).first()
        if not product:
            category = Category(name="Test Cat", slug=f"test-cat-{uuid.uuid4().hex[:6]}")
            db.add(category)
            db.flush()
            product = Product(
                category_id=category.id,
                name="AMD Ryzen 7 5800X",
                slug=f"amd-ryzen-7-5800x-{uuid.uuid4().hex[:6]}",
                brand="AMD",
                model="5800X",
            )
            db.add(product)
            db.flush()

        store = db.scalars(select(Store)).first()
        if not store:
            store = Store(name="Test Store", domain=f"test-{uuid.uuid4().hex[:6]}.com")
            db.add(store)
            db.flush()

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

        obs = db.scalars(
            select(PriceObservation).where(PriceObservation.store_product_id == sp.id)
        ).first()
        if not obs:
            obs = PriceObservation(
                store_product_id=sp.id,
                price=Decimal("799.90"),
                currency="PEN",
            )
            db.add(obs)
            db.flush()

        db.commit()
        db.refresh(product)
        db.refresh(store)
        db.refresh(sp)
        db.refresh(obs)
        return product, store, sp, obs
    finally:
        db.close()


def test_list_products_default_pagination():
    """Verify GET /api/v1/products returns paginated list with total."""
    get_seeded_product()
    response = client.get("/api/v1/products")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "page" in data
    assert "page_size" in data
    assert "total" in data
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert len(data["items"]) > 0

    item = data["items"][0]
    assert "id" in item
    assert "name" in item
    assert "category" in item
    assert "latest_price" in item


def test_list_products_search_filter():
    """Verify search filter ?q= parameter."""
    get_seeded_product()
    response = client.get("/api/v1/products?q=Ryzen")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    for item in data["items"]:
        assert "ryzen" in item["name"].lower()


def test_list_products_category_filter():
    """Verify category filter ?category= parameter."""
    get_seeded_product()
    response = client.get("/api/v1/products?category=procesadores")
    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert item["category"].lower() == "procesadores"


def test_list_products_pagination_boundaries():
    """Verify custom page and page_size."""
    get_seeded_product()
    response = client.get("/api/v1/products?page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["items"]) <= 2


def test_list_products_invalid_pagination_returns_422():
    """Verify invalid pagination returns 422 with uniform error format."""
    response = client.get("/api/v1/products?page=0")
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "request_id" in data["error"]

    response_huge = client.get("/api/v1/products?page_size=200")
    assert response_huge.status_code == 422


def test_get_product_detail_success():
    """Verify GET /api/v1/products/{product_id} returns full detail."""
    product, store, _, _ = get_seeded_product()
    response = client.get(f"/api/v1/products/{product.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(product.id)
    assert data["name"] == product.name
    assert "category" in data
    assert "stores" in data
    assert isinstance(data["stores"], list)

    if data["stores"]:
        first_store = data["stores"][0]
        assert "store_id" in first_store
        assert "store_name" in first_store
        assert "product_url" in first_store


def test_get_product_detail_not_found_returns_404():
    """Verify GET /api/v1/products/{product_id} returns 404 for unknown UUID."""
    random_uuid = uuid.uuid4()
    response = client.get(f"/api/v1/products/{random_uuid}")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "PRODUCT_NOT_FOUND"
    assert "request_id" in data["error"]


def test_get_product_invalid_uuid_returns_422():
    """Verify GET /api/v1/products/{invalid-uuid} returns 422 validation error."""
    response = client.get("/api/v1/products/not-a-valid-uuid")
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_get_price_history_success():
    """Verify GET /api/v1/products/{product_id}/price-history returns series."""
    product, store, _, _ = get_seeded_product()
    response = client.get(f"/api/v1/products/{product.id}/price-history")
    assert response.status_code == 200
    data = response.json()
    assert data["product_id"] == str(product.id)
    assert "series" in data
    assert isinstance(data["series"], list)
    if data["series"]:
        series_item = data["series"][0]
        assert "store_id" in series_item
        assert "store_name" in series_item
        assert "currency" in series_item
        assert "points" in series_item
        if series_item["points"]:
            point = series_item["points"][0]
            assert "captured_at" in point
            assert "price" in point


def test_get_price_history_filtered_by_store():
    """Verify price history filtered by store_id."""
    product, store, _, _ = get_seeded_product()
    response = client.get(f"/api/v1/products/{product.id}/price-history?store_id={store.id}")
    assert response.status_code == 200
    data = response.json()
    for s in data["series"]:
        assert s["store_id"] == str(store.id)


def test_get_price_history_date_range_filter():
    """Verify price history filtered by from and to dates."""
    product, _, _, _ = get_seeded_product()
    response = client.get(
        f"/api/v1/products/{product.id}/price-history?from=2026-01-01&to=2026-12-31"
    )
    assert response.status_code == 200


def test_get_price_history_not_found_returns_404():
    """Verify price history on non-existent product returns 404."""
    random_uuid = uuid.uuid4()
    response = client.get(f"/api/v1/products/{random_uuid}/price-history")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "PRODUCT_NOT_FOUND"


def test_openapi_schema_documents_all_endpoints():
    """Verify OpenAPI documentation includes all three v1 product endpoints."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    paths = schema.get("paths", {})
    assert "/api/v1/products" in paths
    assert "/api/v1/products/{product_id}" in paths
    assert "/api/v1/products/{product_id}/price-history" in paths
