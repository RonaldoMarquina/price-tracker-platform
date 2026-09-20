"""Unit and integration tests for ObservationRepository.

Verifies:
- Persistence of standard, cash_or_bank_transfer, and NULL (historical).
- Idempotency via source_hash (same job does not duplicate).
- Different jobs create historical observations even if price does not change.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Category, PriceObservation, Product, Store, StoreProduct
from app.db.session import SessionLocal
from app.repositories.observation_repository import ObservationRepository


def test_observation_repository_persists_price_conditions():
    """ObservationRepository must persist standard, cash_or_bank_transfer, and NULL conditions."""
    repo = ObservationRepository()
    db: Session = SessionLocal()
    sp = None
    prod = None
    cat = None
    store = None

    try:
        # Create isolated fixtures
        cat = Category(name=f"Cat-{uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
        db.add(cat)
        db.flush()

        prod = Product(
            name="Test Observation Product",
            slug=f"prod-{uuid.uuid4().hex[:6]}",
            category_id=cat.id,
        )
        store = Store(name=f"Store-{uuid.uuid4().hex[:4]}", domain=f"st-{uuid.uuid4().hex[:4]}.com")
        db.add_all([prod, store])
        db.flush()

        sp = StoreProduct(
            product_id=prod.id, store_id=store.id, product_url="https://store.com/item"
        )
        db.add(sp)
        db.commit()

        # 1. Persist 'standard'
        hash_standard = f"hash-{uuid.uuid4().hex}"
        inserted_std = repo.insert_observation_idempotent(
            db=db,
            store_product_id=sp.id,
            price=Decimal("120.50"),
            currency="PEN",
            availability="in_stock",
            captured_at=datetime.now(timezone.utc),
            source_hash=hash_standard,
            price_condition="standard",
        )
        assert inserted_std is True

        # 2. Persist 'cash_or_bank_transfer'
        hash_cash = f"hash-{uuid.uuid4().hex}"
        inserted_cash = repo.insert_observation_idempotent(
            db=db,
            store_product_id=sp.id,
            price=Decimal("114.48"),
            currency="PEN",
            availability="in_stock",
            captured_at=datetime.now(timezone.utc),
            source_hash=hash_cash,
            price_condition="cash_or_bank_transfer",
        )
        assert inserted_cash is True

        # 3. Persist NULL (representing historical observations captured before migration 004)
        hash_null = f"hash-{uuid.uuid4().hex}"
        inserted_null = repo.insert_observation_idempotent(
            db=db,
            store_product_id=sp.id,
            price=Decimal("130.00"),
            currency="PEN",
            availability="in_stock",
            captured_at=datetime.now(timezone.utc),
            source_hash=hash_null,
            price_condition=None,
        )
        assert inserted_null is True

        # Verify in DB
        obs_std = db.scalar(
            select(PriceObservation).where(PriceObservation.source_hash == hash_standard)
        )
        assert obs_std is not None
        assert obs_std.price_condition == "standard"
        assert obs_std.price == Decimal("120.50")

        obs_cash_record = db.scalar(
            select(PriceObservation).where(PriceObservation.source_hash == hash_cash)
        )
        assert obs_cash_record is not None
        assert obs_cash_record.price_condition == "cash_or_bank_transfer"
        assert obs_cash_record.price == Decimal("114.48")

        obs_null_record = db.scalar(
            select(PriceObservation).where(PriceObservation.source_hash == hash_null)
        )
        assert obs_null_record is not None
        assert obs_null_record.price_condition is None
        assert obs_null_record.price == Decimal("130.00")

    finally:
        if sp:
            db.query(PriceObservation).filter(PriceObservation.store_product_id == sp.id).delete()
            db.delete(sp)
            db.flush()
        if prod:
            db.delete(prod)
            db.flush()
        if cat:
            db.delete(cat)
            db.flush()
        if store:
            db.delete(store)
            db.flush()
        db.commit()
        db.close()


def test_observation_repository_idempotency_and_distinct_jobs():
    """Verify same job_id (hash) does not duplicate, but different job_ids create history."""
    repo = ObservationRepository()
    db: Session = SessionLocal()
    sp = None
    prod = None
    cat = None
    store = None

    try:
        cat = Category(name=f"Cat-{uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
        db.add(cat)
        db.flush()

        prod = Product(
            name="Idempotency Product",
            slug=f"prod-{uuid.uuid4().hex[:6]}",
            category_id=cat.id,
        )
        store = Store(name=f"Store-{uuid.uuid4().hex[:4]}", domain=f"st-{uuid.uuid4().hex[:4]}.com")
        db.add_all([prod, store])
        db.flush()

        sp = StoreProduct(
            product_id=prod.id, store_id=store.id, product_url="https://store.com/idem"
        )
        db.add(sp)
        db.commit()

        job1_hash = f"job1:{sp.id}"
        # Job 1 execution
        inserted1 = repo.insert_observation_idempotent(
            db=db,
            store_product_id=sp.id,
            price=Decimal("200.00"),
            currency="PEN",
            availability="in_stock",
            captured_at=datetime.now(timezone.utc),
            source_hash=job1_hash,
            price_condition="cash_or_bank_transfer",
        )
        assert inserted1 is True

        # Reprocess Job 1 with same source_hash -> must be skipped
        re_inserted1 = repo.insert_observation_idempotent(
            db=db,
            store_product_id=sp.id,
            price=Decimal("200.00"),
            currency="PEN",
            availability="in_stock",
            captured_at=datetime.now(timezone.utc),
            source_hash=job1_hash,
            price_condition="cash_or_bank_transfer",
        )
        assert re_inserted1 is False

        # Job 2 execution with different job_id but identical price -> must insert new observation
        job2_hash = f"job2:{sp.id}"
        inserted2 = repo.insert_observation_idempotent(
            db=db,
            store_product_id=sp.id,
            price=Decimal("200.00"),
            currency="PEN",
            availability="in_stock",
            captured_at=datetime.now(timezone.utc),
            source_hash=job2_hash,
            price_condition="cash_or_bank_transfer",
        )
        assert inserted2 is True

        # Total observations must be 2
        total_obs = db.scalars(
            select(PriceObservation).where(PriceObservation.store_product_id == sp.id)
        ).all()
        assert len(total_obs) == 2

    finally:
        if sp:
            db.query(PriceObservation).filter(PriceObservation.store_product_id == sp.id).delete()
            db.delete(sp)
            db.flush()
        if prod:
            db.delete(prod)
            db.flush()
        if cat:
            db.delete(cat)
            db.flush()
        if store:
            db.delete(store)
            db.flush()
        db.commit()
        db.close()
