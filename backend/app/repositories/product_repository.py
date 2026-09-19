"""Product repository handling database access via SQLAlchemy ORM."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
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
        """Fetch active products with optional multi-field text search and category filter."""
        base_query = select(Product).join(Product.category).where(Product.is_active.is_(True))

        if q and q.strip():
            # Synonyms & typo corrections for PC hardware components
            synonyms_map: dict[str, list[str]] = {
                "gpu": ["tarjeta", "video", "rtx", "gtx", "radeon", "geforce", "gpu"],
                "cpu": ["procesador", "ryzen", "core i", "intel", "amd", "cpu"],
                "motherboard": ["placa", "madre", "motherboard", "b650", "b760", "z790"],
                "motherboards": ["placa", "madre", "motherboard"],
                "placa": ["placa", "madre", "motherboard"],
                "ram": ["ram", "memoria", "ddr4", "ddr5"],
                "memoria": ["ram", "memoria", "ddr4", "ddr5"],
                "memorias": ["ram", "memoria", "ddr4", "ddr5"],
                "meoria": ["ram", "memoria", "ddr4", "ddr5"],  # Corrección tipográfica
                "meorla": ["ram", "memoria", "ddr4", "ddr5"],  # Corrección tipográfica
                "psu": ["fuente", "poder", "modular", "850w", "700w", "gold"],
                "fuente": ["fuente", "poder", "psu", "modular"],
                "fuentes": ["fuente", "poder", "psu", "modular"],
                "cooler": ["refrigeracion", "cooler", "liquida", "aire", "kraken"],
                "coolers": ["refrigeracion", "cooler", "liquida", "aire", "kraken"],
                "refrigeracion": ["refrigeracion", "cooler", "liquida", "aire", "kraken"],
                "refrigeración": ["refrigeracion", "cooler", "liquida", "aire", "kraken"],
                "liquida": ["refrigeracion", "liquida", "kraken"],
                "líquida": ["refrigeracion", "liquida", "kraken"],
                "aire": ["refrigeracion", "aire", "ak620"],
            }

            raw_terms = q.strip().lower().split()
            for term in raw_terms:
                patterns_to_check = [f"%{term}%"]
                if term in synonyms_map:
                    for syn in synonyms_map[term]:
                        patterns_to_check.append(f"%{syn}%")

                term_clauses = []
                for pat in patterns_to_check:
                    term_clauses.extend([
                        Product.name.ilike(pat),
                        Product.brand.ilike(pat),
                        Product.model.ilike(pat),
                        Category.name.ilike(pat),
                    ])
                base_query = base_query.where(or_(*term_clauses))

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
