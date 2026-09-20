"""Pydantic schemas for product catalog and details."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import PaginatedResponse


class LatestPriceOut(BaseModel):
    """Latest price observation summary for a product."""

    amount: str = Field(..., description="Precio formateado como cadena decimal")
    currency: str = Field(..., description="Código de moneda ISO (PEN, USD)")
    store: str = Field(..., description="Nombre de la tienda donde se observó el precio")


class ProductListItemOut(BaseModel):
    """Catalog item for paginated product list."""

    id: uuid.UUID
    name: str
    brand: str | None = None
    mpn: str | None = None
    category: str = Field(..., description="Nombre de la categoría")
    image_url: str | None = None
    latest_price: LatestPriceOut | None = None

    model_config = ConfigDict(from_attributes=True)


class ProductListResponse(PaginatedResponse[ProductListItemOut]):
    """Response model for paginated products catalog."""

    pass


class CategoryOut(BaseModel):
    """Category basic info."""

    id: uuid.UUID
    name: str
    slug: str

    model_config = ConfigDict(from_attributes=True)


class StoreProductPriceOut(BaseModel):
    """Price observation detail for a specific store product."""

    amount: str | None = None
    currency: str | None = None
    availability: str | None = None
    captured_at: datetime


class ProductStoreOut(BaseModel):
    """Store offering information for a product."""

    store_id: uuid.UUID
    store_name: str
    product_url: str
    external_sku: str | None = None
    latest_price: StoreProductPriceOut | None = None


class ProductDetailOut(BaseModel):
    """Full product detail response."""

    id: uuid.UUID
    name: str
    slug: str
    brand: str | None = None
    model: str | None = None
    mpn: str | None = None
    category: CategoryOut
    image_url: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    stores: list[ProductStoreOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
