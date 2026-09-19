"""API v1 endpoints package."""

from app.api.v1.endpoints.products import router as products_router

__all__ = ["products_router"]
