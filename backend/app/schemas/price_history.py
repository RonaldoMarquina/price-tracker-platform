"""Pydantic schemas for price history series."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PricePointOut(BaseModel):
    """A point in the price history timeline."""

    captured_at: datetime
    price: str = Field(..., description="Precio formateado como cadena decimal")


class StorePriceSeriesOut(BaseModel):
    """Time-series of price observations for a given store."""

    store_id: uuid.UUID
    store_name: str
    currency: str
    points: list[PricePointOut] = Field(default_factory=list)


class ProductPriceHistoryResponse(BaseModel):
    """Response model for historical price observations of a product."""

    product_id: uuid.UUID
    series: list[StorePriceSeriesOut] = Field(default_factory=list)
