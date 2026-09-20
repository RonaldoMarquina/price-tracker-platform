"""Analytical service implementing statistical rules, determinism and snapshot evaluations."""

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    IncompatibleDateParametersError,
    IncompleteDateRangeError,
    InvalidDateRangeError,
    StoreNotFoundError,
)
from app.core.math_utils import (
    distribute_percentages,
    quantize_currency,
    quantize_percentage,
)
from app.db.models import Store
from app.repositories.analytics_repository import (
    AnalyticsRepository,
    SnapshotRow,
    analytics_repository,
)
from app.schemas.analytics import (
    AnalyticsFiltersResponse,
    AnalyticsSummaryResponse,
    DataFreshnessOut,
    MaxSavingsProductOut,
    MostCompetitiveStoreOut,
    OfferSnapshotOut,
    PeriodEnum,
    PriceSpreadItemOut,
    PriceSpreadResponse,
    PriceTrendsResponse,
    SavingsSummaryOut,
    StoreCompetitivenessItemOut,
    StoresCompetitivenessResponse,
)


class AnalyticsService:
    """Orchestrates analytics computations over PostgreSQL data."""

    def __init__(self, repo: AnalyticsRepository | None = None) -> None:
        self.repo = repo or analytics_repository

    def get_filters(self, db: Session) -> AnalyticsFiltersResponse:
        """Fetch available filters (categories with active products, all stores, periods)."""
        return self.repo.get_filter_options(db)

    def _resolve_period_and_dates(
        self,
        period: PeriodEnum | str | None,
        from_date: datetime | None,
        to_date: datetime | None,
    ) -> tuple[str | None, datetime, datetime]:
        """Validate mutually exclusive period vs custom date range and return UTC timestamps.

        Rules:
        - If neither period nor from_date/to_date are provided: default to '30d'.
        - If period is provided: reject custom dates with 422.
        - For custom range: require both from_date and to_date; if missing one, 422.
        - If from_date > to_date: 422.
        - All dates converted to UTC.
        """
        now_utc = datetime.now(timezone.utc)

        # 1. Mutually exclusive check
        if period is not None and (from_date is not None or to_date is not None):
            raise IncompatibleDateParametersError()

        # 2. Incomplete custom range check
        if period is None and (from_date is not None or to_date is not None):
            if from_date is None or to_date is None:
                raise IncompleteDateRangeError()

            if from_date.tzinfo is None:
                from_date = from_date.replace(tzinfo=timezone.utc)
            if to_date.tzinfo is None:
                to_date = to_date.replace(tzinfo=timezone.utc)

            if from_date > to_date:
                raise InvalidDateRangeError()

            return None, from_date, to_date

        # 3. Period preset handling
        effective_period = period.value if isinstance(period, PeriodEnum) else (period or "30d")

        if effective_period == "7d":
            start_dt = now_utc - timedelta(days=7)
        elif effective_period == "90d":
            start_dt = now_utc - timedelta(days=90)
        elif effective_period == "all":
            start_dt = datetime(2020, 1, 1, tzinfo=timezone.utc)
        else:  # default "30d"
            effective_period = "30d"
            start_dt = now_utc - timedelta(days=30)

        return effective_period, start_dt, now_utc

    def get_summary(
        self, db: Session, category_id: uuid.UUID | None = None
    ) -> AnalyticsSummaryResponse:
        """Compute high-level KPIs based strictly on the current latest snapshot."""
        as_of = datetime.now(timezone.utc)
        rows = self.repo.get_latest_snapshot_rows(db, category_id=category_id)

        # 1. Total distinct tracked products
        total_products_tracked = len({r.product_id for r in rows})

        # 2. Freshness audit across active associations
        active_associations = [r for r in rows if r.store_is_active and r.sp_is_active]
        total_active_assoc = len(active_associations)
        fresh_count = 0
        stale_count = 0
        unknown_count = 0
        no_observation_count = 0

        for r in active_associations:
            if r.observation_id is None:
                no_observation_count += 1
                unknown_count += 1
            elif r.captured_at is None:
                unknown_count += 1
            else:
                age_seconds = (as_of - r.captured_at).total_seconds()
                if age_seconds <= 7 * 86400:
                    fresh_count += 1
                else:
                    stale_count += 1

        freshness_rate = (
            quantize_percentage(
                (Decimal(fresh_count) / Decimal(total_active_assoc)) * Decimal("100")
            )
            if total_active_assoc > 0
            else Decimal("0.00")
        )

        freshness_out = DataFreshnessOut(
            total_active_associations=total_active_assoc,
            fresh_count=fresh_count,
            stale_count=stale_count,
            unknown_count=unknown_count,
            no_observation_count=no_observation_count,
            freshness_rate=freshness_rate,
        )

        # 3. Group by product to evaluate valid offers, best price, and savings
        products_map: dict[uuid.UUID, list[SnapshotRow]] = defaultdict(list)
        for r in rows:
            products_map[r.product_id].append(r)

        products_with_valid_offer_count = 0
        comparable_products_count = 0
        savings_items: list[tuple[SnapshotRow, SnapshotRow, Decimal, Decimal]] = []
        store_best_counts: dict[uuid.UUID, int] = defaultdict(int)
        store_names: dict[uuid.UUID, str] = {}

        for p_id, p_rows in products_map.items():
            valid_offers = [r for r in p_rows if r.is_valid_in_stock_offer]
            if not valid_offers:
                continue

            products_with_valid_offer_count += 1

            # Deterministic best offer tie-breaker: price ASC, captured_at DESC, store_id ASC
            valid_offers.sort(
                key=lambda o: (
                    o.price,
                    -(o.captured_at.timestamp() if o.captured_at else 0),
                    str(o.store_id),
                )
            )
            best_offer = valid_offers[0]
            store_best_counts[best_offer.store_id] += 1
            store_names[best_offer.store_id] = best_offer.store_name

            # Evaluate comparable products with at least 2 valid in-stock offers
            if len(valid_offers) >= 2:
                comparable_products_count += 1
                # Worst offer tie-breaker: highest price, oldest capture, store_id ASC
                worst_sorted = sorted(
                    valid_offers,
                    key=lambda o: (
                        -o.price,
                        o.captured_at.timestamp() if o.captured_at else 0,
                        str(o.store_id),
                    ),
                )
                worst_offer = worst_sorted[0]
                diff = worst_offer.price - best_offer.price
                pct = (
                    (diff / worst_offer.price) * Decimal("100")
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                savings_items.append((best_offer, worst_offer, diff, pct))

        # 4. Savings summary
        if comparable_products_count > 0:
            total_savings_amt = sum((item[2] for item in savings_items), Decimal("0.00"))
            total_savings_pct = sum((item[3] for item in savings_items), Decimal("0.00"))
            denom = Decimal(comparable_products_count)
            avg_amt = (total_savings_amt / denom).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            avg_pct = (total_savings_pct / denom).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            # Max savings product
            savings_items.sort(key=lambda x: (x[2], x[3], str(x[0].product_id)), reverse=True)
            top = savings_items[0]
            max_prod = MaxSavingsProductOut(
                product_id=top[0].product_id,
                product_name=top[0].product_name,
                best_price=quantize_currency(top[0].price),
                best_store=top[0].store_name,
                best_price_condition=top[0].price_condition,
                worst_price=quantize_currency(top[1].price),
                worst_store=top[1].store_name,
                worst_price_condition=top[1].price_condition,
                savings_amount=quantize_currency(top[2]),
                savings_percentage=top[3],
            )
        else:
            avg_amt = Decimal("0.00")
            avg_pct = Decimal("0.00")
            max_prod = None

        savings_out = SavingsSummaryOut(
            average_savings_amount=quantize_currency(avg_amt),
            average_savings_percentage=avg_pct,
            max_savings_product=max_prod,
        )

        # 5. Most competitive store
        most_competitive_store: MostCompetitiveStoreOut | None = None
        if products_with_valid_offer_count > 0 and store_best_counts:
            # Sort stores by (best_price_count DESC, store_name ASC)
            sorted_stores = sorted(
                store_best_counts.items(),
                key=lambda x: (x[1], -ord(store_names[x[0]][0])),
                reverse=True,
            )
            top_store_id, top_count = sorted_stores[0]
            top_share = (
                (Decimal(top_count) / Decimal(products_with_valid_offer_count)) * Decimal("100")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            most_competitive_store = MostCompetitiveStoreOut(
                store_id=top_store_id,
                store_name=store_names[top_store_id],
                best_price_count=top_count,
                best_price_share_percentage=top_share,
            )

        return AnalyticsSummaryResponse(
            as_of=as_of,
            category_id=category_id,
            total_products_tracked=total_products_tracked,
            products_with_valid_offer_count=products_with_valid_offer_count,
            comparable_products_count=comparable_products_count,
            savings=savings_out,
            most_competitive_store=most_competitive_store,
            freshness=freshness_out,
        )

    def get_price_spread(
        self, db: Session, category_id: uuid.UUID | None = None, limit: int = 10
    ) -> PriceSpreadResponse:
        """Fetch ranking of products with greatest price spread between valid offers."""
        as_of = datetime.now(timezone.utc)
        rows = self.repo.get_latest_snapshot_rows(db, category_id=category_id)

        products_map: dict[uuid.UUID, list[SnapshotRow]] = defaultdict(list)
        for r in rows:
            products_map[r.product_id].append(r)

        spread_items: list[PriceSpreadItemOut] = []

        for p_id, p_rows in products_map.items():
            valid_offers = [r for r in p_rows if r.is_valid_in_stock_offer]
            if len(valid_offers) < 2:
                continue

            # Deterministic best offer: price ASC, captured_at DESC, store_id ASC
            valid_offers.sort(
                key=lambda o: (
                    o.price,
                    -(o.captured_at.timestamp() if o.captured_at else 0),
                    str(o.store_id),
                )
            )
            best_offer = valid_offers[0]

            # Deterministic worst offer: price DESC, captured_at ASC, store_id ASC
            worst_sorted = sorted(
                valid_offers,
                key=lambda o: (
                    -o.price,
                    o.captured_at.timestamp() if o.captured_at else 0,
                    str(o.store_id),
                ),
            )
            worst_offer = worst_sorted[0]

            diff = worst_offer.price - best_offer.price
            pct = (
                (diff / worst_offer.price) * Decimal("100")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            best_out = OfferSnapshotOut(
                amount=quantize_currency(best_offer.price),
                currency=best_offer.currency or "PEN",
                store_id=best_offer.store_id,
                store_name=best_offer.store_name,
                price_condition=best_offer.price_condition,
                captured_at=best_offer.captured_at or as_of,
            )
            worst_out = OfferSnapshotOut(
                amount=quantize_currency(worst_offer.price),
                currency=worst_offer.currency or "PEN",
                store_id=worst_offer.store_id,
                store_name=worst_offer.store_name,
                price_condition=worst_offer.price_condition,
                captured_at=worst_offer.captured_at or as_of,
            )

            spread_items.append(
                PriceSpreadItemOut(
                    product_id=p_id,
                    product_name=best_offer.product_name,
                    category_name=best_offer.category_name,
                    best_offer=best_out,
                    worst_offer=worst_out,
                    savings_amount=quantize_currency(diff),
                    savings_percentage=pct,
                    valid_offers_count=len(valid_offers),
                )
            )

        # Sort descending by savings_amount, then savings_percentage, then product_name
        spread_items.sort(
            key=lambda x: (Decimal(x.savings_amount), x.savings_percentage, x.product_name),
            reverse=True,
        )

        total_comparable = len(spread_items)
        limited_items = spread_items[:limit]

        return PriceSpreadResponse(
            as_of=as_of,
            total_comparable_products=total_comparable,
            limit=limit,
            items=limited_items,
        )

    def get_stores_competitiveness(
        self, db: Session, category_id: uuid.UUID | None = None
    ) -> StoresCompetitivenessResponse:
        """Break down catalog coverage, stock availability, and best price share per store."""
        as_of = datetime.now(timezone.utc)
        rows = self.repo.get_latest_snapshot_rows(db, category_id=category_id)

        # 1. Calculate best price per product to determine store victories
        products_map: dict[uuid.UUID, list[SnapshotRow]] = defaultdict(list)
        for r in rows:
            products_map[r.product_id].append(r)

        products_with_valid_offer_count = 0
        store_best_counts: dict[uuid.UUID, int] = defaultdict(int)

        for p_id, p_rows in products_map.items():
            valid_offers = [r for r in p_rows if r.is_valid_in_stock_offer]
            if not valid_offers:
                continue

            products_with_valid_offer_count += 1
            valid_offers.sort(
                key=lambda o: (
                    o.price,
                    -(o.captured_at.timestamp() if o.captured_at else 0),
                    str(o.store_id),
                )
            )
            best_offer = valid_offers[0]
            store_best_counts[best_offer.store_id] += 1

        # 2. Group by store to calculate coverage and availability rates
        store_rows: dict[uuid.UUID, list[SnapshotRow]] = defaultdict(list)
        for r in rows:
            store_rows[r.store_id].append(r)

        # Also get all stores from DB to guarantee all stores (including inactive) appear
        all_stores = db.scalars(
            select(Store).order_by(Store.is_active.desc(), Store.name.asc())
        ).all()

        store_items: list[StoreCompetitivenessItemOut] = []

        # Calculate exact best_price_share_percentage across active stores with best prices
        active_stores_best: list[tuple[uuid.UUID, Decimal]] = []
        for s in all_stores:
            if s.is_active:
                active_stores_best.append((s.id, Decimal(store_best_counts[s.id])))

        shares_map = (
            distribute_percentages(active_stores_best)
            if products_with_valid_offer_count > 0
            else {s.id: Decimal("0.00") for s in all_stores}
        )

        for s in all_stores:
            s_rows = store_rows.get(s.id, [])
            total_assoc = len(s_rows)
            observed_assoc = sum(1 for r in s_rows if r.observation_id is not None)
            no_obs_count = total_assoc - observed_assoc

            in_stock_count = 0
            out_of_stock_count = 0
            unknown_count = no_obs_count  # Associations without observations count as unknown

            conditions_count: dict[str, int] = defaultdict(int)

            for r in s_rows:
                if r.observation_id is None:
                    continue

                if r.availability == "in_stock" and r.price is not None and r.price > 0:
                    in_stock_count += 1
                elif r.availability == "out_of_stock":
                    out_of_stock_count += 1
                else:
                    unknown_count += 1

                cond_key = r.price_condition or "standard"
                conditions_count[cond_key] += 1

            # Distribute availability percentages to sum to exactly 100.00%
            avail_pairs = [
                ("in_stock", Decimal(in_stock_count)),
                ("out_of_stock", Decimal(out_of_stock_count)),
                ("unknown", Decimal(unknown_count)),
            ]
            avail_pcts = distribute_percentages(avail_pairs) if total_assoc > 0 else {
                "in_stock": Decimal("0.00"),
                "out_of_stock": Decimal("0.00"),
                "unknown": Decimal("0.00"),
            }

            store_items.append(
                StoreCompetitivenessItemOut(
                    store_id=s.id,
                    store_name=s.name,
                    is_active=s.is_active,
                    total_associations=total_assoc,
                    observed_associations=observed_assoc,
                    no_observation_count=no_obs_count,
                    best_price_count=store_best_counts[s.id] if s.is_active else 0,
                    best_price_share_percentage=shares_map.get(s.id, Decimal("0.00")),
                    in_stock_count=in_stock_count,
                    in_stock_percentage=avail_pcts["in_stock"],
                    out_of_stock_count=out_of_stock_count,
                    out_of_stock_percentage=avail_pcts["out_of_stock"],
                    unknown_count=unknown_count,
                    unknown_percentage=avail_pcts["unknown"],
                    price_conditions=dict(conditions_count),
                )
            )

        return StoresCompetitivenessResponse(
            as_of=as_of,
            category_id=category_id,
            products_with_valid_offer_count=products_with_valid_offer_count,
            stores=store_items,
        )

    def get_price_trends(
        self,
        db: Session,
        period: PeriodEnum | str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        category_id: uuid.UUID | None = None,
        store_id: uuid.UUID | None = None,
    ) -> PriceTrendsResponse:
        """Fetch historical aggregated daily price trends over time."""
        as_of = datetime.now(timezone.utc)
        resolved_period, start_dt, end_dt = self._resolve_period_and_dates(
            period=period, from_date=from_date, to_date=to_date
        )

        if store_id:
            store = db.get(Store, store_id)
            if not store:
                raise StoreNotFoundError(str(store_id))

        points = self.repo.get_daily_price_trends(
            db=db,
            start_date=start_dt,
            end_date=end_dt,
            category_id=category_id,
            store_id=store_id,
        )

        return PriceTrendsResponse(
            as_of=as_of,
            period=resolved_period,
            from_date=start_dt if resolved_period is None else None,
            to_date=end_dt if resolved_period is None else None,
            category_id=category_id,
            store_id=store_id,
            points=points,
        )


analytics_service = AnalyticsService()
