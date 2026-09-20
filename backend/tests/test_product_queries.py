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
