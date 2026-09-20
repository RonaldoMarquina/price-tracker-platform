"""Pydantic schemas for product catalog and details."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import PaginatedResponse

PriceCondition = Literal["standard", "cash_or_bank_transfer"]


class BestPriceOut(BaseModel):
    """Mejor oferta actual para un producto entre tiendas activas en stock."""

    amount: str = Field(..., description="Precio formateado como cadena decimal")
    currency: str = Field(..., description="Código de moneda ISO (PEN)")
    store_id: uuid.UUID = Field(..., description="ID de la tienda con mejor oferta")
    store_name: str = Field(..., description="Nombre de la tienda con mejor oferta")
    price_condition: PriceCondition | None = Field(
        None, description="Condición comercial del precio (ej. 'cash_or_bank_transfer', 'standard')"
    )
    captured_at: datetime = Field(..., description="Fecha de captura de la observación")


class LatestPriceOut(BaseModel):
    """Última observación de precio registrada (obsoleto: use best_price)."""

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
    best_price: BestPriceOut | None = Field(
        None, description="Mejor oferta actual activa y disponible"
    )
    latest_price: LatestPriceOut | None = Field(
        None, description="Última observación de precio (obsoleto: use best_price)"
    )

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
    price_condition: PriceCondition | None = None
    is_provisional: bool = False
    captured_at: datetime


class ProductStoreOut(BaseModel):
    """Store offering information for a product."""

    store_id: uuid.UUID
    store_name: str
    product_url: str
    external_sku: str | None = None
    is_store_active: bool = Field(True, description="Estado de activación de la tienda")
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
    best_price: BestPriceOut | None = Field(
        None, description="Mejor oferta actual activa y disponible"
    )
    stores: list[ProductStoreOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
