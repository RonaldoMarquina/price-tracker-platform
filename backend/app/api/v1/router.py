"""API v1 master router."""

from fastapi import APIRouter

from app.api.v1.endpoints.products import router as products_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(products_router)
