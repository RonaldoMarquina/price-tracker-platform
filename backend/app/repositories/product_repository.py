"""Product repository handling database access via SQLAlchemy ORM."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db.models import Category, PriceObservation, Product, Store, StoreProduct


class ProductRepository:
    """Repository for querying product catalog and price records."""

    def get_paginated(
        self,
        db: Session,
        q: str | None = None,
        category_slug: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Product], int]:
        """Fetch active products with optional text search and category filter."""
        base_query = select(Product).join(Product.category).where(Product.is_active.is_(True))

        if q and q.strip():
            base_query = base_query.where(Product.name.ilike(f"%{q.strip()}%"))

        if category_slug and category_slug.strip():
            base_query = base_query.where(Category.slug == category_slug.strip().lower())

        count_stmt = select(func.count()).select_from(base_query.subquery())
        total = db.scalar(count_stmt) or 0

        paginated_stmt = (
            base_query.options(joinedload(Product.category))
            .order_by(Product.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        products = list(db.scalars(paginated_stmt).all())
        return products, total

    def get_latest_price_for_product(
        self, db: Session, product_id: uuid.UUID
    ) -> tuple[Decimal, str, str] | None:
        """Find the most recent price observation for a product across all stores."""
        stmt = (
            select(
                PriceObservation.price,
                PriceObservation.currency,
                Store.name,
            )
            .join(StoreProduct, PriceObservation.store_product_id == StoreProduct.id)
            .join(Store, StoreProduct.store_id == Store.id)
            .where(
                StoreProduct.product_id == product_id,
                StoreProduct.is_active.is_(True),
                Store.is_active.is_(True),
            )
            .order_by(PriceObservation.captured_at.desc())
            .limit(1)
        )
        row = db.execute(stmt).first()
        if row:
            return (row[0], row[1], row[2])
        return None

    def get_by_id(self, db: Session, product_id: uuid.UUID) -> Product | None:
        """Fetch active product by UUID including category and active store relations."""
        stmt = (
            select(Product)
            .options(
                joinedload(Product.category),
                selectinload(Product.store_products).joinedload(StoreProduct.store),
            )
            .where(Product.id == product_id, Product.is_active.is_(True))
        )
        return db.scalar(stmt)

    def get_latest_price_for_store_product(
        self, db: Session, store_product_id: uuid.UUID
    ) -> PriceObservation | None:
        """Fetch latest price observation for a specific store product."""
        stmt = (
            select(PriceObservation)
            .where(PriceObservation.store_product_id == store_product_id)
            .order_by(PriceObservation.captured_at.desc())
            .limit(1)
        )
        return db.scalar(stmt)

    def get_store_products(
        self, db: Session, product_id: uuid.UUID, store_id: uuid.UUID | None = None
    ) -> list[StoreProduct]:
        """Fetch active store associations for a product, optionally filtered by store."""
        stmt = (
            select(StoreProduct)
            .options(joinedload(StoreProduct.store))
            .join(StoreProduct.store)
            .where(
                StoreProduct.product_id == product_id,
                StoreProduct.is_active.is_(True),
                Store.is_active.is_(True),
            )
        )
        if store_id:
            stmt = stmt.where(StoreProduct.store_id == store_id)

        return list(db.scalars(stmt).all())

    def get_price_points_for_store_product(
        self,
        db: Session,
        store_product_id: uuid.UUID,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[PriceObservation]:
        """Fetch price points in chronological order within an optional date range."""
        stmt = select(PriceObservation).where(PriceObservation.store_product_id == store_product_id)
        if date_from:
            stmt = stmt.where(PriceObservation.captured_at >= date_from)
        if date_to:
            stmt = stmt.where(PriceObservation.captured_at <= date_to)

        stmt = stmt.order_by(PriceObservation.captured_at.asc())
        return list(db.scalars(stmt).all())


product_repository = ProductRepository()
