"""Integration tests for analytical HTTP endpoints, parameter validation, and query performance."""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db.models import Category, PriceObservation, Product, Store, StoreProduct
from app.db.session import engine, get_db
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def override_get_db(db_session: Session):
    """Override get_db dependency so endpoints share the transactional test session."""
    def _db_override():
        yield db_session

    app.dependency_overrides[get_db] = _db_override
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def analytics_seed_data(db_session: Session):
    """Seed controlled data for analytics testing."""
    # Create categories
    cat_active = Category(
        name=f"Analytics Cat {uuid.uuid4().hex[:6]}",
        slug=f"analytics-cat-{uuid.uuid4().hex[:6]}",
    )
    cat_empty = Category(
        name=f"Empty Cat {uuid.uuid4().hex[:6]}",
        slug=f"empty-cat-{uuid.uuid4().hex[:6]}",
    )
    db_session.add_all([cat_active, cat_empty])
    db_session.flush()

    # Create stores: 2 active, 1 inactive
    store_a = Store(
        name=f"Store Alpha {uuid.uuid4().hex[:4]}",
        domain=f"alpha-{uuid.uuid4().hex[:4]}.pe",
        is_active=True,
    )
    store_b = Store(
        name=f"Store Beta {uuid.uuid4().hex[:4]}",
        domain=f"beta-{uuid.uuid4().hex[:4]}.pe",
        is_active=True,
    )
    store_inact = Store(
        name=f"Store Inactive {uuid.uuid4().hex[:4]}",
        domain=f"inactive-{uuid.uuid4().hex[:4]}.pe",
        is_active=False,
    )
    db_session.add_all([store_a, store_b, store_inact])
    db_session.flush()

    # Create product in cat_active
    prod1 = Product(
        category_id=cat_active.id,
        name=f"Product 1 {uuid.uuid4().hex[:6]}",
        slug=f"prod-1-{uuid.uuid4().hex[:6]}",
        brand="BrandA",
        model="Model1",
        is_active=True,
    )
    prod2 = Product(
        category_id=cat_active.id,
        name=f"Product 2 {uuid.uuid4().hex[:6]}",
        slug=f"prod-2-{uuid.uuid4().hex[:6]}",
        brand="BrandB",
        model="Model2",
        is_active=True,
    )
    db_session.add_all([prod1, prod2])
    db_session.flush()

    # Associations
    sp1_a = StoreProduct(
        product_id=prod1.id,
        store_id=store_a.id,
        product_url=f"https://alpha.pe/p1-{uuid.uuid4().hex[:4]}",
        external_sku="SKU1A",
    )
    sp1_b = StoreProduct(
        product_id=prod1.id,
        store_id=store_b.id,
        product_url=f"https://beta.pe/p1-{uuid.uuid4().hex[:4]}",
        external_sku="SKU1B",
    )
    sp2_a = StoreProduct(
        product_id=prod2.id,
        store_id=store_a.id,
        product_url=f"https://alpha.pe/p2-{uuid.uuid4().hex[:4]}",
        external_sku="SKU2A",
    )
    sp2_inact = StoreProduct(
        product_id=prod2.id,
        store_id=store_inact.id,
        product_url=f"https://inactive.pe/p2-{uuid.uuid4().hex[:4]}",
        external_sku="SKU2INACT",
    )
    db_session.add_all([sp1_a, sp1_b, sp2_a, sp2_inact])
    db_session.flush()

    # Observations
    now = datetime.now(timezone.utc)
    t_yesterday = now - timedelta(days=1)
    t_two_days_ago = now - timedelta(days=2)

    # Product 1: Store A has 100.00, Store B has 120.00 -> Spread is 20.00 (16.67%)
    obs1_a = PriceObservation(
        store_product_id=sp1_a.id,
        price=Decimal("100.00"),
        currency="PEN",
        availability="in_stock",
        price_condition="standard",
        captured_at=now,
    )
    obs1_b = PriceObservation(
        store_product_id=sp1_b.id,
        price=Decimal("120.00"),
        currency="PEN",
        availability="in_stock",
        price_condition="cash_or_bank_transfer",
        captured_at=now,
    )

    # Product 2: Store A has 250.00 (in_stock), Inactive Store has 200.00 (in_stock)
    obs2_a = PriceObservation(
        store_product_id=sp2_a.id,
        price=Decimal("250.00"),
        currency="PEN",
        availability="in_stock",
        price_condition="standard",
        captured_at=now,
    )
    obs2_inact = PriceObservation(
        store_product_id=sp2_inact.id,
        price=Decimal("200.00"),
        currency="PEN",
        availability="in_stock",
        price_condition="standard",
        captured_at=now,
    )

    # Historical observations for trends
    obs1_a_hist1 = PriceObservation(
        store_product_id=sp1_a.id,
        price=Decimal("105.00"),
        currency="PEN",
        availability="in_stock",
        price_condition="standard",
        captured_at=t_yesterday,
    )
    obs1_a_hist2 = PriceObservation(
        store_product_id=sp1_a.id,
        price=Decimal("110.00"),
        currency="PEN",
        availability="in_stock",
        price_condition="standard",
        captured_at=t_two_days_ago,
    )

    db_session.add_all([obs1_a, obs1_b, obs2_a, obs2_inact, obs1_a_hist1, obs1_a_hist2])
    db_session.flush()

    return {
        "cat_active": cat_active,
        "cat_empty": cat_empty,
        "store_a": store_a,
        "store_b": store_b,
        "store_inact": store_inact,
        "prod1": prod1,
        "prod2": prod2,
    }


def test_get_analytics_filters(analytics_seed_data):
    """GET /api/v1/analytics/filters returns categories with active products and all stores."""
    response = client.get("/api/v1/analytics/filters")
    assert response.status_code == 200
    data = response.json()

    assert "categories" in data
    assert "stores" in data
    assert "periods" in data

    # Validate categories: only categories with active products
    cat_ids = [c["id"] for c in data["categories"]]
    cat_active = analytics_seed_data["cat_active"]
    cat_empty = analytics_seed_data["cat_empty"]
    assert str(cat_active.id) in cat_ids
    assert str(cat_empty.id) not in cat_ids

    # Validate stores: contains active and inactive
    store_ids = [s["id"] for s in data["stores"]]
    store_a = analytics_seed_data["store_a"]
    store_inact = analytics_seed_data["store_inact"]
    assert str(store_a.id) in store_ids
    assert str(store_inact.id) in store_ids

    # Inactive store has is_active == False
    inact_entry = next(s for s in data["stores"] if s["id"] == str(store_inact.id))
    assert inact_entry["is_active"] is False

    # Periods
    assert data["periods"] == ["7d", "30d", "90d", "all"]


def test_get_analytics_summary(analytics_seed_data):
    """GET /api/v1/analytics/summary returns correct KPI snapshot structures."""
    response = client.get("/api/v1/analytics/summary")
    assert response.status_code == 200
    data = response.json()

    assert "as_of" in data
    assert "savings" in data
    assert "most_competitive_store" in data
    assert "freshness" in data
    assert data["comparable_products_count"] >= 1

    savings = data["savings"]
    assert Decimal(str(savings["average_savings_percentage"])) > Decimal("0.00")

    comp = data["most_competitive_store"]
    assert comp is not None
    assert "store_name" in comp

    freshness = data["freshness"]
    assert "fresh_count" in freshness
    assert "stale_count" in freshness
    assert "unknown_count" in freshness
    assert "freshness_rate" in freshness


def test_get_analytics_summary_with_category_filter(analytics_seed_data):
    """GET /api/v1/analytics/summary filtered by category."""
    cat_active = analytics_seed_data["cat_active"]
    response = client.get(f"/api/v1/analytics/summary?category_id={cat_active.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["category_id"] == str(cat_active.id)

    # Empty category returns 200 with zero metrics
    cat_empty = analytics_seed_data["cat_empty"]
    resp_empty = client.get(f"/api/v1/analytics/summary?category_id={cat_empty.id}")
    assert resp_empty.status_code == 200
    data_empty = resp_empty.json()
    assert data_empty["comparable_products_count"] == 0
    assert data_empty["most_competitive_store"] is None


def test_get_price_spread(analytics_seed_data):
    """GET /api/v1/analytics/price-spread returns top products with savings."""
    response = client.get("/api/v1/analytics/price-spread?limit=5")
    assert response.status_code == 200
    data = response.json()

    assert "as_of" in data
    assert "items" in data
    items = data["items"]
    assert len(items) >= 1

    top_item = items[0]
    assert "product_id" in top_item
    assert "savings_amount" in top_item
    assert "savings_percentage" in top_item
    assert "best_offer" in top_item
    assert "worst_offer" in top_item

    # Verify best_offer price is less than worst_offer price
    best_amt = Decimal(str(top_item["best_offer"]["amount"]))
    worst_amt = Decimal(str(top_item["worst_offer"]["amount"]))
    assert best_amt < worst_amt
    assert Decimal(str(top_item["savings_amount"])) > Decimal("0.00")


def test_get_price_spread_limit_validation():
    """GET /api/v1/analytics/price-spread validates limit constraints (1 <= limit <= 100)."""
    # limit = 0
    resp_zero = client.get("/api/v1/analytics/price-spread?limit=0")
    assert resp_zero.status_code == 422

    # limit = 101
    resp_high = client.get("/api/v1/analytics/price-spread?limit=101")
    assert resp_high.status_code == 422


def test_get_stores_competitiveness(analytics_seed_data):
    """GET /api/v1/analytics/stores-competitiveness returns store shares summing to 100.00%."""
    response = client.get("/api/v1/analytics/stores-competitiveness")
    assert response.status_code == 200
    data = response.json()

    assert "stores" in data
    stores = data["stores"]
    assert len(stores) >= 3

    # Inactive store has 0 best price count and 0.00 share
    inactive_item = next(s for s in stores if s["store_name"].startswith("Store Inactive"))
    assert inactive_item["is_active"] is False
    assert inactive_item["best_price_count"] == 0
    assert Decimal(str(inactive_item["best_price_share_percentage"])) == Decimal("0.00")

    # Sum of active store best_price_share_percentage must be exactly 100.00% (Hare-Niemeyer)
    active_shares_sum = sum(
        Decimal(str(s["best_price_share_percentage"])) for s in stores if s["is_active"]
    )
    assert active_shares_sum == Decimal("100.00")

    # For each store, in_stock + out_of_stock + unknown percentages must sum to 100.00%
    for s in stores:
        avail_sum = (
            Decimal(str(s["in_stock_percentage"]))
            + Decimal(str(s["out_of_stock_percentage"]))
            + Decimal(str(s["unknown_percentage"]))
        )
        assert avail_sum == Decimal("100.00")


def test_get_price_trends_default_and_presets(analytics_seed_data):
    """GET /api/v1/analytics/price-trends works with default (30d) and presets."""
    # Default without params
    resp_default = client.get("/api/v1/analytics/price-trends")
    assert resp_default.status_code == 200
    data_def = resp_default.json()
    assert data_def["period"] == "30d"
    assert data_def["from_date"] is None
    assert data_def["to_date"] is None
    assert isinstance(data_def["points"], list)

    # Preset 7d
    resp_7d = client.get("/api/v1/analytics/price-trends?period=7d")
    assert resp_7d.status_code == 200
    data_7d = resp_7d.json()
    assert data_7d["period"] == "7d"


def test_get_price_trends_custom_date_range(analytics_seed_data):
    """GET /api/v1/analytics/price-trends works with valid custom date range."""
    now = datetime.now(timezone.utc)
    t_start = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t_end = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    response = client.get(f"/api/v1/analytics/price-trends?from_date={t_start}&to_date={t_end}")
    assert response.status_code == 200
    data = response.json()
    assert data["period"] is None
    assert data["from_date"] is not None
    assert data["to_date"] is not None


def test_get_price_trends_date_validation_rules():
    """Verify all date range validation rules returning HTTP 422."""
    now = datetime.now(timezone.utc)
    t_start = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t_end = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Rule 1: period + custom dates -> 422 INCOMPATIBLE_DATE_PARAMETERS
    resp_incompat = client.get(
        f"/api/v1/analytics/price-trends?period=30d&from_date={t_start}&to_date={t_end}"
    )
    assert resp_incompat.status_code == 422
    err_incompat = resp_incompat.json()["error"]
    assert err_incompat["code"] == "INCOMPATIBLE_DATE_PARAMETERS"

    # Rule 2: incomplete custom range (missing to_date) -> 422 INCOMPLETE_DATE_RANGE
    resp_miss_to = client.get(f"/api/v1/analytics/price-trends?from_date={t_start}")
    assert resp_miss_to.status_code == 422
    err_miss_to = resp_miss_to.json()["error"]
    assert err_miss_to["code"] == "INCOMPLETE_DATE_RANGE"

    # Rule 3: incomplete custom range (missing from_date) -> 422 INCOMPLETE_DATE_RANGE
    resp_miss_from = client.get(f"/api/v1/analytics/price-trends?to_date={t_end}")
    assert resp_miss_from.status_code == 422
    err_miss_from = resp_miss_from.json()["error"]
    assert err_miss_from["code"] == "INCOMPLETE_DATE_RANGE"

    # Rule 4: from_date > to_date -> 422 INVALID_DATE_RANGE
    resp_reversed = client.get(
        f"/api/v1/analytics/price-trends?from_date={t_end}&to_date={t_start}"
    )
    assert resp_reversed.status_code == 422
    err_reversed = resp_reversed.json()["error"]
    assert err_reversed["code"] == "INVALID_DATE_RANGE"


def test_get_price_trends_store_validation(analytics_seed_data):
    """GET /api/v1/analytics/price-trends validates store existence."""
    # Existing store
    store_a = analytics_seed_data["store_a"]
    resp_ok = client.get(f"/api/v1/analytics/price-trends?store_id={store_a.id}")
    assert resp_ok.status_code == 200

    # Non-existent store
    fake_id = uuid.uuid4()
    resp_404 = client.get(f"/api/v1/analytics/price-trends?store_id={fake_id}")
    assert resp_404.status_code == 404
    err_404 = resp_404.json()["error"]
    assert err_404["code"] == "STORE_NOT_FOUND"


def test_analytics_endpoints_query_count_limit(analytics_seed_data):
    """Verify that each analytics endpoint executes at most 2 SQL queries (no N+1)."""
    endpoints = [
        "/api/v1/analytics/filters",
        "/api/v1/analytics/summary",
        "/api/v1/analytics/price-spread",
        "/api/v1/analytics/stores-competitiveness",
        "/api/v1/analytics/price-trends",
    ]

    for ep in endpoints:
        query_count = 0

        def count_queries(conn, cursor, statement, parameters, context, executemany):
            nonlocal query_count
            # Ignore transaction savepoints or rollbacks
            if not statement.strip().upper().startswith(("SAVEPOINT", "RELEASE", "ROLLBACK")):
                query_count += 1

        event.listen(engine, "before_cursor_execute", count_queries)
        try:
            resp = client.get(ep)
            assert resp.status_code == 200, (
                f"Endpoint {ep} failed with {resp.status_code}: {resp.text}"
            )
            assert query_count <= 2, (
                f"Endpoint {ep} executed {query_count} queries, exceeding limit of 2!"
            )
        finally:
            event.remove(engine, "before_cursor_execute", count_queries)
