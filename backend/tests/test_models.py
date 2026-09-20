"""Tests for SQLAlchemy models, relationships, and constraints."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Category, PriceObservation, Product, Store, StoreProduct
from app.db.session import engine


@pytest.fixture
def db_session():
    """Provide a database session wrapped in an outer transaction that rolls back everything."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def test_create_category(db_session: Session):
    """Verify category creation and attributes."""
    cat_slug = f"test-cat-{uuid.uuid4().hex[:8]}"
    category = Category(name=f"Cat {cat_slug}", slug=cat_slug)
    db_session.add(category)
    db_session.commit()

    saved = db_session.scalar(select(Category).where(Category.slug == cat_slug))
    assert saved is not None
    assert saved.id is not None
    assert saved.name == f"Cat {cat_slug}"


def test_category_unique_slug(db_session: Session):
    """Verify duplicate category slug raises IntegrityError."""
    slug = f"unique-slug-{uuid.uuid4().hex[:8]}"
    name1 = f"Category One {uuid.uuid4().hex[:8]}"
    name2 = f"Category Two {uuid.uuid4().hex[:8]}"
    cat1 = Category(name=name1, slug=slug)
    cat2 = Category(name=name2, slug=slug)

    db_session.add(cat1)
    db_session.commit()

    db_session.add(cat2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_create_product_with_category(db_session: Session):
    """Verify product relationship with category and defaults."""
    cat_slug = f"cat-{uuid.uuid4().hex[:8]}"
    category = Category(name=f"Cat {cat_slug}", slug=cat_slug)
    db_session.add(category)
    db_session.commit()

    prod_slug = f"prod-{uuid.uuid4().hex[:8]}"
    product = Product(
        category_id=category.id,
        name="Test Component",
        slug=prod_slug,
        brand="BrandX",
        model="ModelY",
    )
    db_session.add(product)
    db_session.commit()

    saved = db_session.scalar(select(Product).where(Product.slug == prod_slug))
    assert saved is not None
    assert saved.is_active is True
    assert saved.created_at is not None
    assert saved.category.id == category.id


def test_store_product_unique_constraint(db_session: Session):
    """Verify unique constraint on (product_id, store_id, product_url)."""
    cat = Category(name=f"Cat-{uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
    store = Store(name=f"Store-{uuid.uuid4().hex[:6]}", domain=f"store-{uuid.uuid4().hex[:6]}.com")
    db_session.add_all([cat, store])
    db_session.commit()

    prod = Product(category_id=cat.id, name="GPU", slug=f"gpu-{uuid.uuid4().hex[:6]}")
    db_session.add(prod)
    db_session.commit()

    url = f"https://example.com/p/{uuid.uuid4().hex[:8]}"
    sp1 = StoreProduct(product_id=prod.id, store_id=store.id, product_url=url)
    sp2 = StoreProduct(product_id=prod.id, store_id=store.id, product_url=url)

    db_session.add(sp1)
    db_session.commit()

    db_session.add(sp2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_price_observation_must_be_positive(db_session: Session):
    """Verify CheckConstraint requires price > 0."""
    cat = Category(name=f"Cat-{uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
    store = Store(name=f"Store-{uuid.uuid4().hex[:6]}", domain=f"store-{uuid.uuid4().hex[:6]}.com")
    db_session.add_all([cat, store])
    db_session.commit()

    prod = Product(category_id=cat.id, name="CPU", slug=f"cpu-{uuid.uuid4().hex[:6]}")
    db_session.add(prod)
    db_session.commit()

    url = f"https://example.com/cpu/{uuid.uuid4().hex[:8]}"
    sp = StoreProduct(product_id=prod.id, store_id=store.id, product_url=url)
    db_session.add(sp)
    db_session.commit()

    # Negative price should fail
    bad_obs = PriceObservation(
        store_product_id=sp.id,
        price=Decimal("-10.00"),
        currency="PEN",
    )
    db_session.add(bad_obs)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_price_observation_valid_decimal(db_session: Session):
    """Verify valid price observation with Decimal is persisted accurately."""
    cat = Category(name=f"Cat-{uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
    store = Store(name=f"Store-{uuid.uuid4().hex[:6]}", domain=f"store-{uuid.uuid4().hex[:6]}.com")
    db_session.add_all([cat, store])
    db_session.commit()

    prod = Product(category_id=cat.id, name="RAM", slug=f"ram-{uuid.uuid4().hex[:6]}")
    db_session.add(prod)
    db_session.commit()

    url = f"https://example.com/ram/{uuid.uuid4().hex[:8]}"
    sp = StoreProduct(product_id=prod.id, store_id=store.id, product_url=url)
    db_session.add(sp)
    db_session.commit()

    obs = PriceObservation(
        store_product_id=sp.id,
        price=Decimal("199.99"),
        currency="USD",
        availability="in_stock",
        source_hash=f"testhash-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(obs)
    db_session.commit()

    saved = db_session.scalar(select(PriceObservation).where(PriceObservation.id == obs.id))
    assert saved is not None
    assert saved.price == Decimal("199.99")
    assert saved.currency == "USD"
    assert saved.captured_at is not None
