"""Tests for product queries: best price calculations, out-of-stock exclusion, and canonical MPN."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models import Category, PriceObservation, Product, Store, StoreProduct
from app.repositories.product_repository import ProductRepository
from app.services.product_service import ProductService


def test_get_best_price_excludes_out_of_stock_and_nulls(db_session: Session):
    """Best price query must ignore out_of_stock items and null prices."""
    repo = ProductRepository()

    # Create category, product with canonical MPN
    cat = Category(name=f"Cat-{uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
    prod = Product(
        name="Mainboard MSI PRO H610M-A DDR4",
        slug=f"msi-h610m-{uuid.uuid4().hex[:6]}",
        brand="MSI",
        model="PRO H610M-A DDR4",
        mpn="PRO H610M-A DDR4",
        category=cat,
        is_active=True,
    )
    # Store 1: In stock at 290.00 PEN
    store1 = Store(name=f"NECS-{uuid.uuid4().hex[:4]}", domain=f"necs-{uuid.uuid4().hex[:4]}.pe")
    # Store 2: Out of stock at 262.04 PEN (cheaper numeric price, but out of stock!)
    store2 = Store(
        name=f"Sercoplus-{uuid.uuid4().hex[:4]}", domain=f"sercoplus-{uuid.uuid4().hex[:4]}.com"
    )
    # Store 3: Out of stock with NULL price
    store3 = Store(
        name=f"Tienda3-{uuid.uuid4().hex[:4]}", domain=f"store3-{uuid.uuid4().hex[:4]}.com"
    )

    db_session.add_all([cat, prod, store1, store2, store3])
    db_session.commit()

    sp1 = StoreProduct(product_id=prod.id, store_id=store1.id, product_url="https://necs.pe/p/1")
    sp2 = StoreProduct(
        product_id=prod.id, store_id=store2.id, product_url="https://sercoplus.com/p/2"
    )
    sp3 = StoreProduct(product_id=prod.id, store_id=store3.id, product_url="https://store3.com/p/3")
    db_session.add_all([sp1, sp2, sp3])
    db_session.commit()

    # Insert observations
    obs1 = PriceObservation(
        store_product_id=sp1.id,
        price=Decimal("290.00"),
        currency="PEN",
        availability="in_stock",
        captured_at=datetime.now(timezone.utc),
    )
    obs2 = PriceObservation(
        store_product_id=sp2.id,
        price=Decimal("262.04"),
        currency="PEN",
        availability="out_of_stock",
        captured_at=datetime.now(timezone.utc),
    )
    obs3 = PriceObservation(
        store_product_id=sp3.id,
        price=None,
        currency=None,
        availability="out_of_stock",
        captured_at=datetime.now(timezone.utc),
    )
    db_session.add_all([obs1, obs2, obs3])
    db_session.commit()

    # Query best price
    best = repo.get_best_price_for_product(db_session, prod.id)

    assert best is not None
    best_price, best_currency, store_name = best

    # Out of stock at 262.04 must NEVER be selected as best price!
    assert best_price == Decimal("290.00")
    assert best_currency == "PEN"
    assert store_name == store1.name


def test_get_best_price_returns_none_when_all_out_of_stock(db_session: Session):
    """When all stores have out_of_stock items, best price returns None."""
    repo = ProductRepository()

    cat = Category(name=f"Cat-{uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
    prod = Product(
        name="Agotado Total",
        slug=f"agotado-{uuid.uuid4().hex[:6]}",
        category=cat,
        is_active=True,
    )
    store = Store(name=f"Store-{uuid.uuid4().hex[:4]}", domain=f"store-{uuid.uuid4().hex[:4]}.com")
    db_session.add_all([cat, prod, store])
    db_session.commit()

    sp = StoreProduct(
        product_id=prod.id, store_id=store.id, product_url="https://store.com/agotado"
    )
    db_session.add(sp)
    db_session.commit()

    obs = PriceObservation(
        store_product_id=sp.id,
        price=Decimal("100.00"),
        currency="PEN",
        availability="out_of_stock",
        captured_at=datetime.now(timezone.utc),
    )
    db_session.add(obs)
    db_session.commit()

    best = repo.get_best_price_for_product(db_session, prod.id)
    assert best is None


def test_canonical_mpn_retrieval_and_integrity(db_session: Session):
    """Canonical MPN is strictly retrieved from Product and is never mutated by observations."""
    service = ProductService()

    cat = Category(name=f"Cat-{uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
    prod = Product(
        name="Monitor ASUS VY279HGR",
        slug=f"asus-{uuid.uuid4().hex[:6]}",
        brand="ASUS",
        model="VY279HGR",
        mpn="VY279HGR",
        category=cat,
        is_active=True,
    )
    db_session.add_all([cat, prod])
    db_session.commit()

    detail = service.get_product_detail(db_session, prod.id)
    assert detail.mpn == "VY279HGR"
    assert detail.name == "Monitor ASUS VY279HGR"


def test_get_best_price_excludes_unknown_availability(db_session: Session):
    """Observations with availability='unknown' must never compete as best available price."""
    repo = ProductRepository()

    cat = Category(name=f"Cat-{uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
    prod = Product(
        name="Case ASUS ProArt",
        slug=f"asus-proart-{uuid.uuid4().hex[:6]}",
        category=cat,
        is_active=True,
    )
    store_unknown = Store(
        name=f"CS-{uuid.uuid4().hex[:4]}", domain=f"cs-{uuid.uuid4().hex[:4]}.com"
    )
    store_instock = Store(
        name=f"NECS-{uuid.uuid4().hex[:4]}", domain=f"necs-{uuid.uuid4().hex[:4]}.pe"
    )
    db_session.add_all([cat, prod, store_unknown, store_instock])
    db_session.commit()

    sp_unknown = StoreProduct(
        product_id=prod.id, store_id=store_unknown.id, product_url="https://cs.com/p"
    )
    sp_instock = StoreProduct(
        product_id=prod.id, store_id=store_instock.id, product_url="https://necs.pe/p"
    )
    db_session.add_all([sp_unknown, sp_instock])
    db_session.commit()

    # Store unknown has cheaper price (200.00 PEN), but status is unknown (consultar disponibilidad)
    obs_unknown = PriceObservation(
        store_product_id=sp_unknown.id,
        price=Decimal("200.00"),
        currency="PEN",
        availability="unknown",
        captured_at=datetime.now(timezone.utc),
    )
    # Store instock has higher price (250.00 PEN), but status is in_stock
    obs_instock = PriceObservation(
        store_product_id=sp_instock.id,
        price=Decimal("250.00"),
        currency="PEN",
        availability="in_stock",
        captured_at=datetime.now(timezone.utc),
    )
    db_session.add_all([obs_unknown, obs_instock])
    db_session.commit()

    best = repo.get_best_price_for_product(db_session, prod.id)
    assert best is not None
    best_price, best_currency, store_name = best

    # Unknown availability at 200.00 must NOT be selected!
    assert best_price == Decimal("250.00")
    assert store_name == store_instock.name


def test_get_best_price_excludes_inactive_store_even_if_in_stock_and_cheaper(
    db_session: Session,
):
    """When a deactivated store has a lower in-stock price, best price selects the active store."""
    repo = ProductRepository()

    cat = Category(name=f"Cat-{uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
    prod = Product(
        name="Placa MSI B760",
        slug=f"msi-b760-{uuid.uuid4().hex[:6]}",
        category=cat,
        is_active=True,
    )
    # Deactivated store (e.g. Sercoplus or blocked store) with lower price and in_stock
    store_inactive = Store(
        name=f"InactiveStore-{uuid.uuid4().hex[:4]}",
        domain=f"inactive-{uuid.uuid4().hex[:4]}.com",
        is_active=False,
    )
    # Active store with higher price and in_stock
    store_active = Store(
        name=f"ActiveStore-{uuid.uuid4().hex[:4]}",
        domain=f"active-{uuid.uuid4().hex[:4]}.pe",
        is_active=True,
    )
    db_session.add_all([cat, prod, store_inactive, store_active])
    db_session.commit()

    sp_inactive = StoreProduct(
        product_id=prod.id,
        store_id=store_inactive.id,
        product_url="https://inactive.com/p",
        is_active=True,
    )
    sp_active = StoreProduct(
        product_id=prod.id,
        store_id=store_active.id,
        product_url="https://active.pe/p",
        is_active=True,
    )
    db_session.add_all([sp_inactive, sp_active])
    db_session.commit()

    # Inactive store has lower price S/ 150.00 and is in_stock
    obs_inactive = PriceObservation(
        store_product_id=sp_inactive.id,
        price=Decimal("150.00"),
        currency="PEN",
        availability="in_stock",
        captured_at=datetime.now(timezone.utc),
    )
    # Active store has higher price S/ 200.00 and is in_stock
    obs_active = PriceObservation(
        store_product_id=sp_active.id,
        price=Decimal("200.00"),
        currency="PEN",
        availability="in_stock",
        captured_at=datetime.now(timezone.utc),
    )
    db_session.add_all([obs_inactive, obs_active])
    db_session.commit()

    best = repo.get_best_price_for_product(db_session, prod.id)
    assert best is not None
    best_price, best_currency, store_name = best

    # Inactive store offer at 150.00 must NOT be selected!
    assert best_price == Decimal("200.00")
    assert best_currency == "PEN"
    assert store_name == store_active.name


def test_deterministic_tie_breaker_order(db_session: Session):
    """Verify deterministic tie-breaking:
    1. Lowest price (price ASC)
    2. Most recent capture (captured_at DESC)
    3. Store ID (store.id ASC)
    """
    repo = ProductRepository()

    cat = Category(name=f"Cat-{uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
    prod = Product(name="Tie Break Product", slug=f"tie-{uuid.uuid4().hex[:6]}", category=cat)

    # Create two stores
    store_a = Store(name="Store A", domain=f"store-a-{uuid.uuid4().hex[:4]}.com")
    store_b = Store(name="Store B", domain=f"store-b-{uuid.uuid4().hex[:4]}.com")
    db_session.add_all([cat, prod, store_a, store_b])
    db_session.commit()

    sp_a = StoreProduct(product_id=prod.id, store_id=store_a.id, product_url="https://a.com/p")
    sp_b = StoreProduct(product_id=prod.id, store_id=store_b.id, product_url="https://b.com/p")
    db_session.add_all([sp_a, sp_b])
    db_session.commit()

    # Case 1: Same price, different captured_at -> most recent capture wins
    t_older = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
    t_newer = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)

    obs_a = PriceObservation(
        store_product_id=sp_a.id,
        price=Decimal("150.00"),
        currency="PEN",
        availability="in_stock",
        price_condition="standard",
        captured_at=t_older,
    )
    obs_b = PriceObservation(
        store_product_id=sp_b.id,
        price=Decimal("150.00"),
        currency="PEN",
        availability="in_stock",
        price_condition="cash_or_bank_transfer",
        captured_at=t_newer,
    )
    db_session.add_all([obs_a, obs_b])
    db_session.commit()

    best = repo.get_best_price_for_product(db_session, prod.id)
    assert best is not None
    assert best.price == Decimal("150.00")
    assert best.store_id == store_b.id
    assert best.store_name == "Store B"
    assert best.price_condition == "cash_or_bank_transfer"
    assert best.captured_at == t_newer


def test_price_history_excludes_invalid_observations(db_session: Session):
    """Price history must strictly exclude:
    - inactive stores
    - out_of_stock observations
    - unknown availability observations
    - null or non-positive prices (<= 0)
    - currencies other than PEN
    """
    repo = ProductRepository()
    cat = Category(name=f"Cat-{uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
    prod = Product(
        name="History Test Product", slug=f"history-{uuid.uuid4().hex[:6]}", category=cat
    )

    store_active = Store(
        name="Active Store", domain=f"active-{uuid.uuid4().hex[:4]}.com", is_active=True
    )
    store_inactive = Store(
        name="Inactive Store", domain=f"inactive-{uuid.uuid4().hex[:4]}.com", is_active=False
    )
    db_session.add_all([cat, prod, store_active, store_inactive])
    db_session.commit()

    sp_active = StoreProduct(
        product_id=prod.id, store_id=store_active.id, product_url="https://active.com/p"
    )
    sp_inactive = StoreProduct(
        product_id=prod.id, store_id=store_inactive.id, product_url="https://inactive.com/p"
    )
    db_session.add_all([sp_active, sp_inactive])
    db_session.commit()

    # 1. Inactive store should not even have its store_product returned by get_store_products
    active_sps = repo.get_store_products(db_session, prod.id)
    assert len(active_sps) == 1
    assert active_sps[0].store_id == store_active.id

    # 2. Add observations for active store:
    now = datetime.now(timezone.utc)
    obs_valid = PriceObservation(
        store_product_id=sp_active.id,
        price=Decimal("199.90"),
        currency="PEN",
        availability="in_stock",
        captured_at=now,
    )
    obs_out_of_stock = PriceObservation(
        store_product_id=sp_active.id,
        price=Decimal("150.00"),
        currency="PEN",
        availability="out_of_stock",
        captured_at=now,
    )
    obs_unknown = PriceObservation(
        store_product_id=sp_active.id,
        price=Decimal("120.00"),
        currency="PEN",
        availability="unknown",
        captured_at=now,
    )
    obs_null_price = PriceObservation(
        store_product_id=sp_active.id,
        price=None,
        currency=None,
        availability="out_of_stock",
        captured_at=now,
    )
    obs_usd = PriceObservation(
        store_product_id=sp_active.id,
        price=Decimal("50.00"),
        currency="USD",
        availability="in_stock",
        captured_at=now,
    )
    db_session.add_all([obs_valid, obs_out_of_stock, obs_unknown, obs_null_price, obs_usd])
    db_session.commit()

    # Query price points for store product
    points = repo.get_price_points_for_store_product(db_session, sp_active.id)
    assert len(points) == 1
    assert points[0].id == obs_valid.id
    assert points[0].price == Decimal("199.90")


def test_active_offers_count_and_has_multiple_offers(db_session: Session):
    """Verify active_offers_count and has_multiple_offers semantics:
    - Out of stock, null price, unknown availability, inactive stores or store_products
      do not count.
    - Exactly 1 valid in-stock offer -> active_offers_count = 1, has_multiple_offers = False.
    - 2 or more valid in-stock offers -> active_offers_count >= 2, has_multiple_offers = True.
    """
    repo = ProductRepository()
    service = ProductService()

    cat = Category(name=f"Cat-{uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
    prod = Product(name="Offer Test Product", slug=f"offers-{uuid.uuid4().hex[:6]}", category=cat)

    store1 = Store(
        name=f"S1-{uuid.uuid4().hex[:4]}", domain=f"s1-{uuid.uuid4().hex[:4]}.pe", is_active=True
    )
    store2 = Store(
        name=f"S2-{uuid.uuid4().hex[:4]}", domain=f"s2-{uuid.uuid4().hex[:4]}.pe", is_active=True
    )
    store3 = Store(
        name=f"S3-{uuid.uuid4().hex[:4]}", domain=f"s3-{uuid.uuid4().hex[:4]}.pe", is_active=True
    )
    db_session.add_all([cat, prod, store1, store2, store3])
    db_session.commit()

    sp1 = StoreProduct(product_id=prod.id, store_id=store1.id, product_url="https://s1.pe/p")
    sp2 = StoreProduct(product_id=prod.id, store_id=store2.id, product_url="https://s2.pe/p")
    sp3 = StoreProduct(product_id=prod.id, store_id=store3.id, product_url="https://s3.pe/p")
    db_session.add_all([sp1, sp2, sp3])
    db_session.commit()

    # Step 1: No observations -> active_offers = 0, has_multiple = False
    assert repo.get_active_offers_count(db_session, prod.id) == 0
    detail = service.get_product_detail(db_session, prod.id)
    assert detail.active_offers_count == 0
    assert detail.has_multiple_offers is False

    # Step 2: Store 1 has in_stock observation, Store 2 has out_of_stock, Store 3 has NULL price
    t1 = datetime.now(timezone.utc)
    obs1 = PriceObservation(
        store_product_id=sp1.id,
        price=Decimal("100.00"),
        currency="PEN",
        availability="in_stock",
        captured_at=t1,
    )
    obs2 = PriceObservation(
        store_product_id=sp2.id,
        price=Decimal("90.00"),
        currency="PEN",
        availability="out_of_stock",
        captured_at=t1,
    )
    obs3 = PriceObservation(
        store_product_id=sp3.id,
        price=None,
        currency=None,
        availability="out_of_stock",
        captured_at=t1,
    )
    db_session.add_all([obs1, obs2, obs3])
    db_session.commit()

    # Out of stock and null prices MUST NOT count as active offers
    assert repo.get_active_offers_count(db_session, prod.id) == 1
    detail = service.get_product_detail(db_session, prod.id)
    assert detail.active_offers_count == 1
    assert detail.has_multiple_offers is False

    # Also check catalog listing
    res = service.list_products(db_session, q=prod.name)
    assert res.total >= 1
    target_item = next(p for p in res.items if p.id == prod.id)
    assert target_item.active_offers_count == 1
    assert target_item.has_multiple_offers is False

    # Step 3: Store 2 gets updated with in_stock observation -> now 2 stores active
    t2 = datetime.now(timezone.utc)
    obs2_new = PriceObservation(
        store_product_id=sp2.id,
        price=Decimal("95.00"),
        currency="PEN",
        availability="in_stock",
        captured_at=t2,
    )
    db_session.add(obs2_new)
    db_session.commit()

    assert repo.get_active_offers_count(db_session, prod.id) == 2
    detail = service.get_product_detail(db_session, prod.id)
    assert detail.active_offers_count == 2
    assert detail.has_multiple_offers is True

    res2 = service.list_products(db_session, q=prod.name)
    target_item = next(p for p in res2.items if p.id == prod.id)
    assert target_item.active_offers_count == 2
    assert target_item.has_multiple_offers is True

    # Step 4: Deactivate store 1 -> drops back to 1 active offer
    store1.is_active = False
    db_session.commit()

    assert repo.get_active_offers_count(db_session, prod.id) == 1
    detail = service.get_product_detail(db_session, prod.id)
    assert detail.active_offers_count == 1
    assert detail.has_multiple_offers is False
