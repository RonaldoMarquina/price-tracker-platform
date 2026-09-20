"""Versioned scraping message schema shared between API and Worker."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ScrapingMessage(BaseModel):
    """Versioned schema for messages transmitted through the scraping queue."""

    version: int = Field(default=1, description="Versión del esquema del mensaje")
    job_id: uuid.UUID = Field(..., description="ID único del trabajo de scraping")
    store_id: uuid.UUID = Field(..., description="ID de la tienda objetivo")
    product_ids: list[uuid.UUID] = Field(
        ..., min_length=1, description="Lista de IDs de productos a extraer"
    )
    requested_at: datetime = Field(..., description="Marca de tiempo en UTC de la solicitud")
    attempt: int = Field(default=1, ge=1, description="Contador de intentos incluido en el mensaje")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "version": 1,
                "job_id": "c3d4e5f6-7890-4abc-def1-234567890abc",
                "store_id": "a1b2c3d4-5678-490a-bcde-f1234567890a",
                "product_ids": ["b2c3d4e5-6789-40ab-cdef-1234567890ab"],
                "requested_at": "2026-09-19T18:30:00Z",
                "attempt": 1,
            }
        }
    )
