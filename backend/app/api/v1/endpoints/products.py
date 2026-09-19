"""Products catalog and price history endpoints."""

import uuid
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.price_history import ProductPriceHistoryResponse
from app.schemas.product import ProductDetailOut, ProductListResponse
from app.services.product_service import product_service

router = APIRouter(prefix="/products", tags=["Products"])


@router.get(
    "",
    response_model=ProductListResponse,
    summary="Listar productos del catálogo",
    description=(
        "Obtiene un listado paginado de productos con filtros opcionales de nombre y categoría."
    ),
)
def list_products(
    q: str | None = Query(None, description="Búsqueda por nombre del producto", max_length=100),
    category: str | None = Query(None, description="Filtrar por slug de categoría", max_length=100),
    page: int = Query(1, ge=1, description="Número de página"),
    page_size: int = Query(20, ge=1, le=100, description="Cantidad de productos por página"),
    db: Session = Depends(get_db),
) -> ProductListResponse:
    """Retrieve paginated products catalog."""
    return product_service.list_products(
        db=db,
        q=q,
        category=category,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{product_id}",
    response_model=ProductDetailOut,
    summary="Obtener detalle de un producto",
    description=(
        "Obtiene información técnica y el último precio registrado en cada tienda disponible."
    ),
)
def get_product(
    product_id: uuid.UUID = Path(..., description="ID del producto en formato UUID"),
    db: Session = Depends(get_db),
) -> ProductDetailOut:
    """Retrieve product detail by ID."""
    return product_service.get_product_detail(db=db, product_id=product_id)


@router.get(
    "/{product_id}/price-history",
    response_model=ProductPriceHistoryResponse,
    summary="Obtener historial de precios de un producto",
    description="Serie temporal de precios por tienda con filtros opcionales de tienda y fecha.",
)
def get_price_history(
    product_id: uuid.UUID = Path(..., description="ID del producto en formato UUID"),
    store_id: uuid.UUID | None = Query(None, description="Filtrar por ID de tienda específica"),
    from_date: date | None = Query(None, alias="from", description="Fecha de inicio (YYYY-MM-DD)"),
    to_date: date | None = Query(None, alias="to", description="Fecha de fin (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> ProductPriceHistoryResponse:
    """Retrieve historical price timeline for a product."""
    date_from_dt: datetime | None = None
    if from_date:
        date_from_dt = datetime.combine(from_date, time.min, tzinfo=timezone.utc)

    date_to_dt: datetime | None = None
    if to_date:
        date_to_dt = datetime.combine(to_date, time.max, tzinfo=timezone.utc)

    return product_service.get_product_price_history(
        db=db,
        product_id=product_id,
        store_id=store_id,
        date_from=date_from_dt,
        date_to=date_to_dt,
    )
