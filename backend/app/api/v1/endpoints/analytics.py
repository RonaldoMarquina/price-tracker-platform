"""API router exposing analytical price intelligence endpoints."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.analytics import (
    AnalyticsFiltersResponse,
    AnalyticsSummaryResponse,
    PeriodEnum,
    PriceSpreadResponse,
    PriceTrendsResponse,
    StoresCompetitivenessResponse,
)
from app.services.analytics_service import analytics_service

router = APIRouter(prefix="/analytics", tags=["Analítica de Precios"])


@router.get(
    "/filters",
    response_model=AnalyticsFiltersResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtener opciones de filtros analíticos",
    description=(
        "Devuelve las categorías con productos activos, "
        "tiendas registradas y períodos disponibles."
    ),
)
def get_analytics_filters(
    db: Session = Depends(get_db),
) -> AnalyticsFiltersResponse:
    """Fetch filter options for the analytics dashboard."""
    return analytics_service.get_filters(db=db)


@router.get(
    "/summary",
    response_model=AnalyticsSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtener resumen ejecutivo y KPIs de mercado",
    description=(
        "Calcula métricas clave de ahorro, competitividad de tiendas y frescura de datos "
        "basadas estrictamente en el snapshot más reciente del mercado."
    ),
)
def get_analytics_summary(
    category_id: uuid.UUID | None = Query(
        default=None, description="Filtrar métricas por categoría específica"
    ),
    db: Session = Depends(get_db),
) -> AnalyticsSummaryResponse:
    """Fetch analytics summary KPIs."""
    return analytics_service.get_summary(db=db, category_id=category_id)


@router.get(
    "/price-spread",
    response_model=PriceSpreadResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtener dispersión de precios y ranking de ahorro",
    description=(
        "Devuelve los productos con mayor brecha entre la mejor y la peor oferta válida "
        "en stock en el snapshot actual."
    ),
)
def get_price_spread(
    category_id: uuid.UUID | None = Query(
        default=None, description="Filtrar por categoría específica"
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Límite máximo de productos en el ranking (1-100)",
    ),
    db: Session = Depends(get_db),
) -> PriceSpreadResponse:
    """Fetch top products by savings spread."""
    return analytics_service.get_price_spread(db=db, category_id=category_id, limit=limit)


@router.get(
    "/stores-competitiveness",
    response_model=StoresCompetitivenessResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtener competitividad, stock y cobertura por tienda",
    description=(
        "Desglosa el porcentaje de mejor precio del mercado, tasa de stock y formas de pago "
        "para cada tienda en el snapshot actual."
    ),
)
def get_stores_competitiveness(
    category_id: uuid.UUID | None = Query(
        default=None, description="Filtrar métricas por categoría específica"
    ),
    db: Session = Depends(get_db),
) -> StoresCompetitivenessResponse:
    """Fetch store competitiveness and availability metrics."""
    return analytics_service.get_stores_competitiveness(db=db, category_id=category_id)


@router.get(
    "/price-trends",
    response_model=PriceTrendsResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtener evolución y tendencias diarias de precios",
    description=(
        "Devuelve series temporales con precio promedio, mediana, mínimo y máximo diario, "
        "colapsando observaciones múltiples al último precio válido por día y asociación."
    ),
)
def get_price_trends(
    period: PeriodEnum | None = Query(
        default=None,
        description=(
            "Período predeterminado: 7d, 30d, 90d, all. Incompatible con rango personalizado."
        ),
    ),
    from_date: datetime | None = Query(
        default=None,
        description="Fecha inicial UTC para rango personalizado (requiere to_date).",
    ),
    to_date: datetime | None = Query(
        default=None,
        description="Fecha final UTC para rango personalizado (requiere from_date).",
    ),
    category_id: uuid.UUID | None = Query(
        default=None,
        description="Filtrar por categoría específica.",
    ),
    store_id: uuid.UUID | None = Query(
        default=None,
        description="Filtrar por tienda específica.",
    ),
    db: Session = Depends(get_db),
) -> PriceTrendsResponse:
    """Fetch aggregated daily price trends over time."""
    return analytics_service.get_price_trends(
        db=db,
        period=period,
        from_date=from_date,
        to_date=to_date,
        category_id=category_id,
        store_id=store_id,
    )
