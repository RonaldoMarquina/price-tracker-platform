"""API v1 master router."""

from fastapi import APIRouter

from app.api.v1.endpoints.analytics import router as analytics_router
from app.api.v1.endpoints.products import router as products_router
from app.api.v1.endpoints.scraping import router as scraping_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(products_router)
api_v1_router.include_router(scraping_router)
api_v1_router.include_router(analytics_router)
