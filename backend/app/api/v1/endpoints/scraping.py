"""Scraping jobs API endpoints reserved for internal operations."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.security import verify_internal_api_key
from app.db.session import get_db
from app.schemas.scraping import (
    ManualDispatchRequest,
    ManualDispatchResponse,
    ScrapingJobCreate,
    ScrapingJobDetailResponse,
    ScrapingJobListResponse,
    ScrapingJobResponse,
    ScrapingMetricsResponse,
)
from app.services.dispatch_service import dispatch_service
from app.services.scraping_service import scraping_service

router = APIRouter(prefix="/scraping", tags=["Scraping (Operador Interno)"])


@router.post(
    "/jobs",
    response_model=ScrapingJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Crear trabajo manual de scraping",
    description=(
        "Encola un trabajo manual de extracción para una tienda y un conjunto de productos. "
        "Reservado exclusivamente para el operador interno autenticado mediante "
        "token de autorización."
    ),
)
def create_scraping_job(
    payload: ScrapingJobCreate,
    db: Session = Depends(get_db),
    _: str = Depends(verify_internal_api_key),
) -> ScrapingJobResponse:
    """Validate request, enqueue scraping job to PostgreSQL queue, and return 202 Accepted."""
    return scraping_service.create_scraping_job(db=db, payload=payload)


@router.get(
    "/jobs",
    response_model=ScrapingJobListResponse,
    status_code=status.HTTP_200_OK,
    summary="Listar historial de trabajos de scraping",
    description=(
        "Consulta trabajos de scraping con paginación, filtros por estado, tienda "
        "y rango temporal. Orden predeterminado created_at DESC con desempate por id."
    ),
)
def list_scraping_jobs(
    page: int = Query(default=1, ge=1, description="Número de página"),
    page_size: int = Query(default=20, ge=1, le=100, description="Registros por página"),
    status: str | None = Query(default=None, description="Filtrar por estado del trabajo"),
    store_id: uuid.UUID | None = Query(default=None, description="Filtrar por tienda específica"),
    from_date: datetime | None = Query(
        default=None, description="Fecha inicio UTC para filtro de creación"
    ),
    to_date: datetime | None = Query(
        default=None, description="Fecha fin UTC para filtro de creación"
    ),
    db: Session = Depends(get_db),
    _: str = Depends(verify_internal_api_key),
) -> ScrapingJobListResponse:
    """List scraping jobs matching query filters."""
    return dispatch_service.list_jobs(
        db=db,
        page=page,
        page_size=page_size,
        status_filter=status,
        store_id=store_id,
        from_date=from_date,
        to_date=to_date,
    )


@router.get(
    "/jobs/{job_id}",
    response_model=ScrapingJobDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Consultar detalle de un trabajo de scraping",
    description="Retorna la información completa de auditoría de un trabajo específico.",
)
def get_scraping_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(verify_internal_api_key),
) -> ScrapingJobDetailResponse:
    """Retrieve detailed scraping job information by ID."""
    return dispatch_service.get_job(db=db, job_id=job_id)


@router.get(
    "/queue/metrics",
    response_model=ScrapingMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Métricas de cola viva y rendimiento de trabajos",
    description=(
        "Devuelve el estado vivo de mensajes en cola (pending, processing, retrying, dlq) "
        "junto con estadísticas consolidadas de trabajos en una ventana temporal."
    ),
)
def get_scraping_queue_metrics(
    window_hours: int = Query(
        default=24, ge=1, le=720, description="Ventana de tiempo en horas (1 a 720)"
    ),
    db: Session = Depends(get_db),
    _: str = Depends(verify_internal_api_key),
) -> ScrapingMetricsResponse:
    """Calculate and return operational queue and job performance metrics."""
    return dispatch_service.get_queue_metrics(db=db, window_hours=window_hours)


@router.post(
    "/dispatch",
    response_model=ManualDispatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Disparo manual de scraping por lotes",
    description=(
        "Dispara manualmente la extracción para todas las tiendas activas o una específica. "
        "Protegido contra ejecuciones manuales concurrentes (HTTP 409)."
    ),
)
def trigger_manual_dispatch(
    payload: ManualDispatchRequest = Body(default_factory=ManualDispatchRequest),
    _: str = Depends(verify_internal_api_key),
) -> ManualDispatchResponse:
    """Trigger manual batch scraping dispatch across active stores."""
    return dispatch_service.dispatch_manual(store_id=payload.store_id)
