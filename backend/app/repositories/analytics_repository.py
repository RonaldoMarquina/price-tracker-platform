"""Repository for executing optimized analytical SQL queries on PostgreSQL."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import Category, Product, Store
from app.schemas.analytics import (
    AnalyticsFiltersResponse,
    CategoryFilterItem,
    DailyTrendPointOut,
    StoreFilterItem,
)


@dataclass
class SnapshotRow:
    """Represents a row from the latest observation snapshot query."""

    store_product_id: uuid.UUID
    product_id: uuid.UUID
    store_id: uuid.UUID
    sp_is_active: bool
    store_name: str
    store_is_active: bool
    product_name: str
    category_id: uuid.UUID
    category_name: str
    observation_id: uuid.UUID | None
    price: Decimal | None
    currency: str | None
    availability: str | None
    price_condition: str | None
    captured_at: datetime | None

    @property
    def is_valid_in_stock_offer(self) -> bool:
        """Evaluate if this observation represents an authoritative valid in-stock offer."""
        return (
            self.store_is_active
            and self.sp_is_active
            and self.observation_id is not None
            and self.availability == "in_stock"
            and self.price is not None
            and self.price > Decimal("0")
            and self.currency == "PEN"
        )


class AnalyticsRepository:
    """SQL repository executing set-based queries for the analytics dashboard."""

    def get_filter_options(self, db: Session) -> AnalyticsFiltersResponse:
        """Fetch categories that have active products and all registered stores."""
        cat_stmt = (
            select(Category)
            .join(Product, Product.category_id == Category.id)
            .where(Product.is_active.is_(True))
            .distinct()
            .order_by(Category.name.asc())
        )
        categories = [
            CategoryFilterItem(id=c.id, name=c.name) for c in db.scalars(cat_stmt).all()
        ]

        store_stmt = select(Store).order_by(Store.is_active.desc(), Store.name.asc())
        stores = [
            StoreFilterItem(id=s.id, name=s.name, is_active=s.is_active)
            for s in db.scalars(store_stmt).all()
        ]

        return AnalyticsFiltersResponse(categories=categories, stores=stores)

    def get_latest_snapshot_rows(
        self, db: Session, category_id: uuid.UUID | None = None
    ) -> list[SnapshotRow]:
        """Fetch the latest observation for every active StoreProduct using DISTINCT ON.

        Rule: Selects the most recent observation of each StoreProduct first.
        Subsequent filtering on availability, active status and valid price happens
        strictly on this latest observation, guaranteeing that previous in-stock
        observations are never resurrected when a product is currently out-of-stock.
        """
        sql = """
        WITH latest_obs AS (
            SELECT DISTINCT ON (po.store_product_id)
                po.id AS observation_id,
                po.store_product_id,
                po.price,
                po.currency,
                po.availability,
                po.price_condition,
                po.captured_at
            FROM price_observations po
            ORDER BY po.store_product_id, po.captured_at DESC, po.id DESC
        )
        SELECT
            sp.id AS store_product_id,
            sp.product_id,
            sp.store_id,
            sp.is_active AS sp_is_active,
            s.name AS store_name,
            s.is_active AS store_is_active,
            p.name AS product_name,
            p.category_id,
            c.name AS category_name,
            lo.observation_id,
            lo.price,
            lo.currency,
            lo.availability,
            lo.price_condition,
            lo.captured_at
        FROM store_products sp
        JOIN stores s ON sp.store_id = s.id
        JOIN products p ON sp.product_id = p.id
        JOIN categories c ON p.category_id = c.id
        LEFT JOIN latest_obs lo ON sp.id = lo.store_product_id
        WHERE sp.is_active = true
          AND p.is_active = true
        """
        params: dict[str, object] = {}
        if category_id:
            sql += " AND p.category_id = :category_id"
            params["category_id"] = str(category_id)

        sql += " ORDER BY p.name ASC, s.name ASC"

        rows = db.execute(text(sql), params).fetchall()

        result: list[SnapshotRow] = []
        for r in rows:
            captured_at_val = r.captured_at
            if captured_at_val is not None and captured_at_val.tzinfo is None:
                captured_at_val = captured_at_val.replace(tzinfo=timezone.utc)

            result.append(
                SnapshotRow(
                    store_product_id=r.store_product_id,
                    product_id=r.product_id,
                    store_id=r.store_id,
                    sp_is_active=r.sp_is_active,
                    store_name=r.store_name,
                    store_is_active=r.store_is_active,
                    product_name=r.product_name,
                    category_id=r.category_id,
                    category_name=r.category_name,
                    observation_id=r.observation_id,
                    price=r.price,
                    currency=r.currency,
                    availability=r.availability,
                    price_condition=r.price_condition,
                    captured_at=captured_at_val,
                )
            )

        return result

    def get_daily_price_trends(
        self,
        db: Session,
        start_date: datetime,
        end_date: datetime,
        category_id: uuid.UUID | None = None,
        store_id: uuid.UUID | None = None,
    ) -> list[DailyTrendPointOut]:
        """Fetch daily aggregated price metrics across unique store-product associations.

        Aggregates the single latest valid observation per store_product and per calendar day
        to eliminate sampling frequency bias.
        """
        sql = """
        WITH daily_latest AS (
            SELECT DISTINCT ON (po.store_product_id, (po.captured_at AT TIME ZONE 'UTC')::date)
                (po.captured_at AT TIME ZONE 'UTC')::date AS obs_date,
                po.store_product_id,
                po.price,
                sp.product_id
            FROM price_observations po
            JOIN store_products sp ON po.store_product_id = sp.id
            JOIN stores s ON sp.store_id = s.id
            JOIN products p ON sp.product_id = p.id
            WHERE s.is_active = true
              AND sp.is_active = true
              AND p.is_active = true
              AND po.availability = 'in_stock'
              AND po.price IS NOT NULL
              AND po.price > 0
              AND po.currency = 'PEN'
              AND po.captured_at >= :start_date
              AND po.captured_at <= :end_date
        """
        params: dict[str, object] = {
            "start_date": start_date,
            "end_date": end_date,
        }

        if category_id:
            sql += " AND p.category_id = :category_id"
            params["category_id"] = str(category_id)

        if store_id:
            sql += " AND sp.store_id = :store_id"
            params["store_id"] = str(store_id)

        sql += """
            ORDER BY po.store_product_id, (po.captured_at AT TIME ZONE 'UTC')::date,
                     po.captured_at DESC, po.id DESC
        )
        SELECT 
            obs_date::text AS date_str,
            count(DISTINCT store_product_id) AS associations_count,
            count(DISTINCT product_id) AS products_count,
            round(avg(price), 2) AS average_price,
            percentile_cont(0.5) WITHIN GROUP (ORDER BY price) AS median_price,
            min(price) AS min_price,
            max(price) AS max_price
        FROM daily_latest
        GROUP BY obs_date
        ORDER BY obs_date ASC;
        """

        rows = db.execute(text(sql), params).fetchall()

        points: list[DailyTrendPointOut] = []
        for r in rows:
            points.append(
                DailyTrendPointOut(
                    date=str(r.date_str),
                    average_price=f"{r.average_price:.2f}",
                    median_price=f"{r.median_price:.2f}",
                    min_price=f"{r.min_price:.2f}",
                    max_price=f"{r.max_price:.2f}",
                    associations_count=r.associations_count,
                    products_count=r.products_count,
                )
            )

        return points


analytics_repository = AnalyticsRepository()
