"""Common generic schemas for pagination and error reporting."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated list envelope."""

    items: list[T]
    page: int = Field(..., ge=1, description="Número de página actual")
    page_size: int = Field(..., ge=1, description="Elementos por página")
    total: int = Field(..., ge=0, description="Total de elementos coincidentes")


class ErrorDetail(BaseModel):
    """Canonical error payload structure."""

    code: str
    message: str
    request_id: str
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    """Uniform error response envelope."""

    error: ErrorDetail
