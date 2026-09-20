"""Unit and statistical tests for analytics calculations, snapshots, and Hare-Niemeyer rounding."""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.math_utils import distribute_percentages
from app.db.models import Category, PriceObservation, Product, Store, StoreProduct
from app.repositories.analytics_repository import AnalyticsRepository
from app.services.analytics_service import AnalyticsService


def test_distribute_percentages_periodic_three_items_sums_to_hundred():
    """Verify that 3 items with equal values (which would normally produce 33.33 * 3 = 99.99%)

    are allocated with the Largest Remainder Method to sum to exactly 100.00%.
    """
    items = [
        ("store_a", Decimal("1")),
        ("store_b", Decimal("1")),
        ("store_c", Decimal("1")),
    ]
    result = distribute_percentages(items)

    assert result["store_a"] + result["store_b"] + result["store_c"] == Decimal("100.00")
    # One item gets 33.34 and the other two get 33.33
    values = sorted(result.values(), reverse=True)
    assert values == [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")]


def test_distribute_percentages_empty_and_zero_totals():
    """Verify edge cases for distribute_percentages."""
    assert distribute_percentages([]) == {}

    zero_items = [("a", Decimal("0")), ("b", Decimal("0"))]
    res_zero = distribute_percentages(zero_items)
    assert res_zero["a"] == Decimal("0.00")
    assert res_zero["b"] == Decimal("0.00")

    single_item = [("store_only", Decimal("45"))]
    res_single = distribute_percentages(single_item)
    assert res_single["store_only"] == Decimal("100.00")


def test_analytics_snapshot_discards_out_of_stock_even_if_previously_in_stock(
    db_session: Session,
):
    """Rule: Select the latest observation per StoreProduct first.

    If Day 1 had S/ 100 in_stock, but Day 2 has out_of_stock,
    the current status must be out_of_stock and NOT compete as in_stock.
    """
    repo = AnalyticsRepository()
    service = AnalyticsService(repo=repo)

    cat = Category(name=f"Cat-{uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
    prod = Product(name="CPU Test", slug=f"cpu-{uuid.uuid4().hex[:6]}", category=cat)
    store = Store(name="Store Active", domain=f"store-{uuid.uuid4().hex[:4]}.pe", is_active=True)
    db_session.add_all([cat, prod, store])
    db_session.commit()

    sp = StoreProduct(product_id=prod.id, store_id=store.id, product_url="https://store.pe/p")
    db_session.add(sp)
    db_session.commit()

    t_day1 = datetime.now(timezone.utc) - timedelta(days=2)
    t_day2 = datetime.now(timezone.utc) - timedelta(days=1)

    # Day 1: in_stock at S/ 100.00
    obs_day1 = PriceObservation(
        store_product_id=sp.id,
        price=Decimal("100.00"),
        currency="PEN",
        availability="in_stock",
        captured_at=t_day1,
    )
    # Day 2: out_of_stock at S/ 100.00
    obs_day2 = PriceObservation(
        store_product_id=sp.id,
        price=Decimal("100.00"),
        currency="PEN",
        availability="out_of_stock",
        captured_at=t_day2,
    )
    db_session.add_all([obs_day1, obs_day2])
    db_session.commit()

    # Query snapshot rows
    rows = repo.get_latest_snapshot_rows(db_session, category_id=cat.id)
    assert len(rows) == 1
    latest_row = rows[0]
    assert latest_row.observation_id == obs_day2.id
    assert latest_row.availability == "out_of_stock"
    assert latest_row.is_valid_in_stock_offer is False

    # Summary should report 0 valid offers and 0 comparable products
    summary = service.get_summary(db_session, category_id=cat.id)
    assert summary.products_with_valid_offer_count == 0
    assert summary.comparable_products_count == 0
    assert summary.savings.average_savings_amount == "0.00"


def test_analytics_savings_requires_at_least_two_in_stock_offers(db_session: Session):
    """A product with only 1 in-stock offer cannot have a price spread and is not comparable."""
    service = AnalyticsService()

    cat = Category(name=f"Cat-{uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
    prod_single = Product(
        name="Single Store Product", slug=f"single-{uuid.uuid4().hex[:6]}", category=cat
    )
    prod_multi = Product(
        name="Multi Store Product", slug=f"multi-{uuid.uuid4().hex[:6]}", category=cat
    )

    store1 = Store(name="Store 1", domain=f"s1-{uuid.uuid4().hex[:4]}.pe", is_active=True)
    store2 = Store(name="Store 2", domain=f"s2-{uuid.uuid4().hex[:4]}.pe", is_active=True)
    store_inactive = Store(
        name="Store Inactive", domain=f"si-{uuid.uuid4().hex[:4]}.pe", is_active=False
    )
    db_session.add_all([cat, prod_single, prod_multi, store1, store2, store_inactive])
    db_session.commit()

    # Product Single: only store 1 in stock, store inactive has cheaper price
    sp_single_1 = StoreProduct(
        product_id=prod_single.id, store_id=store1.id, product_url="https://s1.pe/p1"
    )
    sp_single_inact = StoreProduct(
        product_id=prod_single.id, store_id=store_inactive.id, product_url="https://si.pe/p1"
    )

    # Product Multi: store 1 has S/ 200.00, store 2 has S/ 250.00
    sp_multi_1 = StoreProduct(
        product_id=prod_multi.id, store_id=store1.id, product_url="https://s1.pe/p2"
    )
    sp_multi_2 = StoreProduct(
        product_id=prod_multi.id, store_id=store2.id, product_url="https://s2.pe/p2"
    )

    db_session.add_all([sp_single_1, sp_single_inact, sp_multi_1, sp_multi_2])
    db_session.commit()

    now = datetime.now(timezone.utc)
    # Observations
    obs_single_1 = PriceObservation(
        store_product_id=sp_single_1.id,
        price=Decimal("150.00"),
        currency="PEN",
        availability="in_stock",
        captured_at=now,
    )
    obs_single_inact = PriceObservation(
        store_product_id=sp_single_inact.id,
        price=Decimal("120.00"),
        currency="PEN",
        availability="in_stock",
        captured_at=now,
    )
    obs_multi_1 = PriceObservation(
        store_product_id=sp_multi_1.id,
        price=Decimal("200.00"),
        currency="PEN",
        availability="in_stock",
        captured_at=now,
    )
    obs_multi_2 = PriceObservation(
        store_product_id=sp_multi_2.id,
        price=Decimal("250.00"),
        currency="PEN",
        availability="in_stock",
        captured_at=now,
    )
    db_session.add_all([obs_single_1, obs_single_inact, obs_multi_1, obs_multi_2])
    db_session.commit()

    summary = service.get_summary(db_session, category_id=cat.id)

    # prod_single has 1 valid offer (inactive store offer is excluded!)
    # prod_multi has 2 valid offers
    assert summary.products_with_valid_offer_count == 2
    assert summary.comparable_products_count == 1

    # Savings on prod_multi: 250 - 200 = 50.00 PEN (20.00%)
    assert summary.savings.average_savings_amount == "50.00"
    assert summary.savings.average_savings_percentage == Decimal("20.00")
    assert summary.savings.max_savings_product is not None
    assert summary.savings.max_savings_product.product_id == prod_multi.id
    assert summary.savings.max_savings_product.savings_amount == "50.00"

    # Price spread list
    spread_resp = service.get_price_spread(db_session, category_id=cat.id)
    assert spread_resp.total_comparable_products == 1
    assert len(spread_resp.items) == 1
    assert spread_resp.items[0].product_id == prod_multi.id
    assert spread_resp.items[0].savings_amount == "50.00"


def test_analytics_competitiveness_deterministic_tie_breaker(db_session: Session):
    """When two stores have identical best prices, tie-breaker order resolves:

    1. Price ASC
    2. Captured_at DESC
    3. store_id ASC
    Exactly one winner is declared, and the market shares sum to 100.00%.
    """
    service = AnalyticsService()
    cat = Category(name=f"Cat-{uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
    prod = Product(name="Tie Product", slug=f"tie-{uuid.uuid4().hex[:6]}", category=cat)

    store_a = Store(name="Store A", domain=f"sa-{uuid.uuid4().hex[:4]}.pe", is_active=True)
    store_b = Store(name="Store B", domain=f"sb-{uuid.uuid4().hex[:4]}.pe", is_active=True)
    db_session.add_all([cat, prod, store_a, store_b])
    db_session.commit()

    sp_a = StoreProduct(product_id=prod.id, store_id=store_a.id, product_url="https://sa.pe/p")
    sp_b = StoreProduct(product_id=prod.id, store_id=store_b.id, product_url="https://sb.pe/p")
    db_session.add_all([sp_a, sp_b])
    db_session.commit()

    t_older = datetime.now(timezone.utc) - timedelta(hours=2)
    t_newer = datetime.now(timezone.utc) - timedelta(hours=1)

    # Store A has older capture, Store B has newer capture with identical price
    obs_a = PriceObservation(
        store_product_id=sp_a.id,
        price=Decimal("100.00"),
        currency="PEN",
        availability="in_stock",
        captured_at=t_older,
    )
    obs_b = PriceObservation(
        store_product_id=sp_b.id,
        price=Decimal("100.00"),
        currency="PEN",
        availability="in_stock",
        captured_at=t_newer,
    )
    db_session.add_all([obs_a, obs_b])
    db_session.commit()

    competitiveness = service.get_stores_competitiveness(db_session, category_id=cat.id)
    assert competitiveness.products_with_valid_offer_count == 1

    stores_dict = {s.store_id: s for s in competitiveness.stores}
    assert stores_dict[store_b.id].best_price_count == 1
    assert stores_dict[store_a.id].best_price_count == 0

    # Total market share sums to 100.00%
    active_shares = sum(
        (s.best_price_share_percentage for s in competitiveness.stores if s.is_active),
        Decimal("0.00"),
    )
    assert active_shares == Decimal("100.00")


def test_analytics_daily_trends_aggregation_without_sampling_bias(db_session: Session):
    """Multiple observations of a store product on the same day are collapsed to the last one

    before calculating daily average and median.
    """
    repo = AnalyticsRepository()
    cat = Category(name=f"Cat-{uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
    prod = Product(name="Trend CPU", slug=f"trend-{uuid.uuid4().hex[:6]}", category=cat)
    store = Store(name="Trend Store", domain=f"ts-{uuid.uuid4().hex[:4]}.pe", is_active=True)
    db_session.add_all([cat, prod, store])
    db_session.commit()

    sp = StoreProduct(product_id=prod.id, store_id=store.id, product_url="https://ts.pe/p")
    db_session.add(sp)
    db_session.commit()

    target_day = datetime(2026, 9, 10, 10, 0, 0, tzinfo=timezone.utc)
    target_day_later = datetime(2026, 9, 10, 18, 0, 0, tzinfo=timezone.utc)

    # Observation 1 morning: S/ 500.00
    obs1 = PriceObservation(
        store_product_id=sp.id,
        price=Decimal("500.00"),
        currency="PEN",
        availability="in_stock",
        captured_at=target_day,
    )
    # Observation 2 evening: S/ 450.00 (this is the final price of the day)
    obs2 = PriceObservation(
        store_product_id=sp.id,
        price=Decimal("450.00"),
        currency="PEN",
        availability="in_stock",
        captured_at=target_day_later,
    )
    db_session.add_all([obs1, obs2])
    db_session.commit()

    points = repo.get_daily_price_trends(
        db=db_session,
        start_date=datetime(2026, 9, 9, tzinfo=timezone.utc),
        end_date=datetime(2026, 9, 11, tzinfo=timezone.utc),
        category_id=cat.id,
    )

    assert len(points) == 1
    point = points[0]
    assert point.date == "2026-09-10"
    assert point.associations_count == 1
    assert point.products_count == 1
    # Average must be 450.00, NOT the average of 500 and 450 (475.00)
    assert point.average_price == "450.00"
    assert point.median_price == "450.00"


def test_analytics_freshness_calculated_on_latest_snapshot_not_history(db_session: Session):
    """Freshness must evaluate only the latest observation of each active association."""
    service = AnalyticsService()
    cat = Category(name=f"Cat-{uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
    prod = Product(name="Freshness Prod", slug=f"fresh-{uuid.uuid4().hex[:6]}", category=cat)
    store = Store(name="Fresh Store", domain=f"fs-{uuid.uuid4().hex[:4]}.pe", is_active=True)
    db_session.add_all([cat, prod, store])
    db_session.commit()

    sp = StoreProduct(product_id=prod.id, store_id=store.id, product_url="https://fs.pe/p")
    db_session.add(sp)
    db_session.commit()

    # 10 old stale observations
    now = datetime.now(timezone.utc)
    for i in range(10):
        db_session.add(
            PriceObservation(
                store_product_id=sp.id,
                price=Decimal("100.00"),
                currency="PEN",
                availability="in_stock",
                captured_at=now - timedelta(days=20 + i),
            )
        )
    # 1 recent fresh observation
    db_session.add(
        PriceObservation(
            store_product_id=sp.id,
            price=Decimal("100.00"),
            currency="PEN",
            availability="in_stock",
            captured_at=now - timedelta(hours=2),
        )
    )
    db_session.commit()

    summary = service.get_summary(db_session, category_id=cat.id)
    # Only 1 active association -> evaluated as FRESH (not 10 stale + 1 fresh = 11!)
    assert summary.freshness.total_active_associations == 1
    assert summary.freshness.fresh_count == 1
    assert summary.freshness.stale_count == 0
    assert summary.freshness.freshness_rate == Decimal("100.00")
