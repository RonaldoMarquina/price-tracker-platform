"""Scraping jobs API endpoints reserved for internal operations."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.security import verify_internal_api_key
from app.db.session import get_db
from app.schemas.scraping import ScrapingJobCreate, ScrapingJobResponse
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
