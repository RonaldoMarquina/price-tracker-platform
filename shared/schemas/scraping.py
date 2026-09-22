"""Versioned scraping message schema shared between API and Worker."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

LEGACY_MESSAGE_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


class ScrapingMessage(BaseModel):
    """Versioned schema for messages transmitted through the scraping queue."""

    version: Literal[1] = Field(
        default=1,
        description="Versión entera estricta del esquema del mensaje (solo 1 permitido)",
    )
    job_id: uuid.UUID = Field(..., description="ID único del trabajo de scraping")
    logical_message_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Identidad lógica del ciclo de mensaje asignada por la app",
    )
    root_logical_message_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Identidad del mensaje raíz que originó los reintentos o replays",
    )
    replayed_from_message_id: uuid.UUID | None = Field(
        default=None,
        description="ID del ciclo de mensaje que falló inmediatamente antes de este replay",
    )
    store_id: uuid.UUID = Field(..., description="ID de la tienda objetivo")
    product_ids: list[uuid.UUID] = Field(
        ..., min_length=1, description="Lista de IDs de productos a extraer"
    )
    requested_at: datetime = Field(..., description="Marca de tiempo en UTC de la solicitud")
    attempt: int = Field(default=1, ge=1, description="Contador de intentos incluido en el mensaje")

    @model_validator(mode="before")
    @classmethod
    def set_identities_and_legacy_fallback(cls, data: Any) -> Any:
        """Derive deterministic identities for legacy messages and maintain root linkage."""
        if isinstance(data, dict):
            # Normalizar para evitar mutaciones externas inesperadas
            data = dict(data)
            logical_id = data.get("logical_message_id")
            if not logical_id:
                raw_job = data.get("job_id")
                if raw_job:
                    logical_id = uuid.uuid5(LEGACY_MESSAGE_NAMESPACE, f"legacy-{raw_job}")
                else:
                    logical_id = uuid.uuid4()
                data["logical_message_id"] = logical_id

            if not data.get("root_logical_message_id"):
                data["root_logical_message_id"] = logical_id

        return data

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "version": 1,
                "job_id": "c3d4e5f6-7890-4abc-def1-234567890abc",
                "logical_message_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
                "root_logical_message_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
                "replayed_from_message_id": None,
                "store_id": "a1b2c3d4-5678-490a-bcde-f1234567890a",
                "product_ids": ["b2c3d4e5-6789-40ab-cdef-1234567890ab"],
                "requested_at": "2026-09-19T18:30:00Z",
                "attempt": 1,
            }
        }
    )
