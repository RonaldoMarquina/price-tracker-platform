"""Pydantic schemas for the Price Analytics Dashboard."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class PeriodEnum(str, Enum):
    """Supported historical analysis period presets."""

    SEVEN_DAYS = "7d"
    THIRTY_DAYS = "30d"
    NINETY_DAYS = "90d"
    ALL = "all"


class CategoryFilterItem(BaseModel):
    """Category filter option with at least one active product."""

    id: uuid.UUID
    name: str


class StoreFilterItem(BaseModel):
    """Store filter option with operational status."""

    id: uuid.UUID
    name: str
    is_active: bool


class AnalyticsFiltersResponse(BaseModel):
    """Available filters contract for the analytics dashboard."""

    categories: list[CategoryFilterItem]
    stores: list[StoreFilterItem]
    periods: list[str] = Field(default_factory=lambda: ["7d", "30d", "90d", "all"])


class OfferSnapshotOut(BaseModel):
    """Snapshot detail of a store offer for comparison."""

    amount: str = Field(description="Price amount formatted with 2 decimals in PEN")
    currency: str = "PEN"
    store_id: uuid.UUID
    store_name: str
    price_condition: str | None = None
    captured_at: datetime


class MaxSavingsProductOut(BaseModel):
    """Product with the highest monetary price spread in the current snapshot."""

    product_id: uuid.UUID
    product_name: str
    best_price: str
    best_store: str
    best_price_condition: str | None = None
    worst_price: str
    worst_store: str
    worst_price_condition: str | None = None
    savings_amount: str
    savings_percentage: Decimal


class SavingsSummaryOut(BaseModel):
    """Summary of savings across comparable products."""

    average_savings_amount: str
    average_savings_percentage: Decimal
    max_savings_product: MaxSavingsProductOut | None = None


class MostCompetitiveStoreOut(BaseModel):
    """Store offering the highest share of market best prices."""

    store_id: uuid.UUID
    store_name: str
    best_price_count: int
    best_price_share_percentage: Decimal


class DataFreshnessOut(BaseModel):
    """Freshness audit over the latest observation of each active store product association."""

    total_active_associations: int
    fresh_count: int
    stale_count: int
    unknown_count: int
    no_observation_count: int
    freshness_rate: Decimal


class AnalyticsSummaryResponse(BaseModel):
    """High-level KPIs for the analytics dashboard."""

    as_of: datetime
    category_id: uuid.UUID | None = None
    total_products_tracked: int
    products_with_valid_offer_count: int
    comparable_products_count: int
    savings: SavingsSummaryOut
    most_competitive_store: MostCompetitiveStoreOut | None = None
    freshness: DataFreshnessOut


class PriceSpreadItemOut(BaseModel):
    """Individual product comparison between best and worst active in-stock offers."""

    product_id: uuid.UUID
    product_name: str
    category_name: str
    best_offer: OfferSnapshotOut
    worst_offer: OfferSnapshotOut
    savings_amount: str
    savings_percentage: Decimal
    valid_offers_count: int


class PriceSpreadResponse(BaseModel):
    """Ranking of products with greatest price dispersion and savings opportunities."""

    as_of: datetime
    total_comparable_products: int
    limit: int
    items: list[PriceSpreadItemOut]


class StoreCompetitivenessItemOut(BaseModel):
    """Competitiveness, stock availability, and catalog coverage breakdown per store."""

    store_id: uuid.UUID
    store_name: str
    is_active: bool
    total_associations: int
    observed_associations: int
    no_observation_count: int
    best_price_count: int
    best_price_share_percentage: Decimal
    in_stock_count: int
    in_stock_percentage: Decimal
    out_of_stock_count: int
    out_of_stock_percentage: Decimal
    unknown_count: int
    unknown_percentage: Decimal
    price_conditions: dict[str, int]


class StoresCompetitivenessResponse(BaseModel):
    """Market competitiveness and coverage breakdown across all stores."""

    as_of: datetime
    category_id: uuid.UUID | None = None
    products_with_valid_offer_count: int
    stores: list[StoreCompetitivenessItemOut]


class DailyTrendPointOut(BaseModel):
    """Daily aggregated price metric across unique store-product associations."""

    date: str = Field(description="Date in YYYY-MM-DD format")
    average_price: str
    median_price: str
    min_price: str
    max_price: str
    associations_count: int
    products_count: int


class PriceTrendsResponse(BaseModel):
    """Historical aggregated daily price trends over time."""

    as_of: datetime
    period: str | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None
    category_id: uuid.UUID | None = None
    store_id: uuid.UUID | None = None
    points: list[DailyTrendPointOut]
