"""Pydantic schemas for scraping jobs API."""

import uuid

from pydantic import BaseModel, ConfigDict, Field


class ScrapingJobCreate(BaseModel):
    """Payload for requesting a scraping job."""

    store_id: uuid.UUID = Field(..., description="Identificador único de la tienda a consultar")
    product_ids: list[uuid.UUID] = Field(
        ..., min_length=1, description="Lista no vacía de IDs de productos del catálogo"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "store_id": "00000000-0000-0000-0000-000000000001",
                "product_ids": ["00000000-0000-0000-0000-000000000002"],
            }
        }
    )


class ScrapingJobResponse(BaseModel):
    """Response returned when a scraping job is successfully queued."""

    job_id: uuid.UUID = Field(..., description="Identificador único generado para el trabajo")
    status: str = Field(default="queued", description="Estado inicial del trabajo")
