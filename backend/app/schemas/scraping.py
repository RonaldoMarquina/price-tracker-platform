"""Pydantic schemas for scraping jobs API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class ScrapingJobDetailResponse(BaseModel):
    """Detailed audit information for a scraping job."""

    id: uuid.UUID = Field(..., description="Identificador único del trabajo")
    store_id: uuid.UUID = Field(..., description="Identificador de la tienda asociada")
    store_name: str | None = Field(default=None, description="Nombre legible de la tienda")
    status: str = Field(..., description="Estado actual del ciclo de vida del trabajo")
    trigger_type: str = Field(..., description="Tipo de disparo: 'scheduled' o 'manual'")
    dispatch_slot: datetime | None = Field(
        default=None, description="Ranura temporal asignada en UTC si fue programado"
    )
    batch_size: int = Field(..., description="Cantidad de productos incluidos en el lote")
    observations_created: int = Field(
        ..., description="Cantidad de observaciones de precio registradas"
    )
    attempts: int = Field(..., description="Cantidad de intentos de procesamiento ejecutados")
    error_reason: str | None = Field(default=None, description="Motivo sanitizado de error o salto")
    created_at: datetime = Field(..., description="Fecha de creación del trabajo en UTC")
    started_at: datetime | None = Field(
        default=None, description="Fecha de inicio de procesamiento en UTC"
    )
    finished_at: datetime | None = Field(
        default=None, description="Fecha de culminación del trabajo en UTC"
    )

    model_config = ConfigDict(from_attributes=True)


class ScrapingJobListResponse(BaseModel):
    """Paginated list of scraping jobs."""

    items: list[ScrapingJobDetailResponse] = Field(..., description="Lista de trabajos paginados")
    total: int = Field(..., ge=0, description="Total de registros coincidentes con los filtros")
    page: int = Field(..., ge=1, description="Número de página actual")
    page_size: int = Field(..., ge=1, description="Cantidad de registros por página")
    total_pages: int = Field(..., ge=0, description="Total de páginas calculadas")


class ScrapingMetricsResponse(BaseModel):
    """Queue live status and historical jobs performance metrics."""

    as_of: datetime = Field(..., description="Fecha y hora del cálculo en UTC")

    # Live queue metrics (from local_queue_messages)
    pending: int = Field(
        ..., ge=0, description="Mensajes activos y visibles listos para ser consumidos"
    )
    processing: int = Field(
        ..., ge=0, description="Mensajes actualmente reclamados con visibilidad vigente"
    )
    retrying: int = Field(
        ..., ge=0, description="Mensajes con intentos previos en espera de backoff"
    )
    dlq: int = Field(..., ge=0, description="Mensajes transferidos a la cola Dead Letter Queue")
    oldest_pending_seconds: float | None = Field(
        default=None,
        description="Antigüedad en segundos del pendiente más antiguo (null si no hay pendientes)",
    )

    # Historical jobs metrics (from scraping_jobs over window_hours)
    window_hours: int = Field(..., description="Ventana de tiempo analizada en horas")
    total_jobs: int = Field(
        ..., ge=0, description="Total de trabajos creados en la ventana temporal"
    )
    completed_jobs: int = Field(..., ge=0, description="Trabajos completados con éxito")
    failed_jobs: int = Field(..., ge=0, description="Trabajos con fallo terminal interno")
    dead_letter_jobs: int = Field(
        ..., ge=0, description="Trabajos enviados a DLQ tras agotar reintentos o error fatal"
    )
    skipped_jobs: int = Field(
        ..., ge=0, description="Trabajos omitidos (tienda desactivada o bloqueada)"
    )
    success_rate_percentage: float | None = Field(
        default=None,
        description="Porcentaje de éxito (completed / total * 100); null si total_jobs es 0",
    )
    average_duration_seconds: float | None = Field(
        default=None,
        description="Duración promedio en segundos de completados; null si no hay completados",
    )
    total_observations_created: int = Field(
        ..., ge=0, description="Total de observaciones de precio registradas en la ventana"
    )


class ManualDispatchRequest(BaseModel):
    """Optional payload to trigger manual scraping dispatch for a specific store."""

    store_id: uuid.UUID | None = Field(
        default=None,
        description="ID opcional de tienda. Si se omite, se despachan todas las tiendas activas.",
    )


class ManualDispatchResponse(BaseModel):
    """Result of a manual scraping dispatch execution."""

    jobs_created: int = Field(..., ge=0, description="Cantidad de trabajos creados y encolados")
    total_products: int = Field(
        ..., ge=0, description="Total de productos catalogados incluidos en los lotes"
    )
    job_ids: list[uuid.UUID] = Field(..., description="Lista de IDs de los trabajos generados")
    skipped_stores: list[uuid.UUID] = Field(
        default_factory=list,
        description="IDs de tiendas omitidas (sin productos o adapter inactivo)",
    )
    failed_stores: list[uuid.UUID] = Field(
        default_factory=list, description="IDs de tiendas que fallaron durante el encolamiento"
    )


class DLQMessageItemResponse(BaseModel):
    """Sanitized item in the DLQ inspection view."""

    message_id: uuid.UUID = Field(..., description="ID del mensaje en la cola")
    job_id: uuid.UUID | None = Field(
        default=None, description="ID del trabajo de scraping asociado"
    )
    store_id: uuid.UUID | None = Field(default=None, description="ID de la tienda")
    store_name: str | None = Field(default=None, description="Nombre de la tienda")
    products_count: int = Field(default=0, ge=0, description="Cantidad de productos en el mensaje")
    attempts: int = Field(..., ge=0, description="Número de intentos de ejecución")
    error_reason: str | None = Field(
        default=None, description="Motivo sanitizado del fallo que envió el mensaje a DLQ"
    )
    created_at: datetime = Field(..., description="Fecha de creación del mensaje original")
    sent_to_dlq_at: datetime | None = Field(
        default=None, description="Fecha de transferencia a la Dead Letter Queue"
    )
    replay_count: int = Field(
        default=0, ge=0, description="Cantidad de veces que el mensaje ha sido reproducido"
    )
    replayed_at: datetime | None = Field(
        default=None, description="Fecha de la última reproducción exitosa"
    )
    replayable: bool = Field(
        ..., description="Indica si el mensaje puede ser reproducido de manera segura"
    )
    replay_block_reason: str | None = Field(
        default=None, description="Motivo por el cual el mensaje no puede reproducirse"
    )


class DLQMessageListResponse(BaseModel):
    """Paginated list of sanitized DLQ messages."""

    items: list[DLQMessageItemResponse] = Field(..., description="Lista de mensajes en DLQ")
    total: int = Field(..., ge=0, description="Total de mensajes coincidentes")
    page: int = Field(..., ge=1, description="Página actual")
    page_size: int = Field(..., ge=1, le=100, description="Tamaño de página")
    total_pages: int = Field(..., ge=0, description="Total de páginas disponibles")


class DLQReplayRequest(BaseModel):
    """Payload to request replay of dead-letter queue messages."""

    message_ids: list[uuid.UUID] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Lista de IDs de mensajes a reproducir (1 a 50 elementos)",
    )

    @field_validator("message_ids")
    @classmethod
    def validate_no_duplicates(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(v) != len(set(v)):
            raise ValueError("message_ids no puede contener identificadores duplicados")
        return v


class DLQReplayResponse(BaseModel):
    """Result of a DLQ replay batch execution."""

    replayed_count: int = Field(
        ..., ge=0, description="Cantidad de mensajes reproducidos con éxito"
    )
    message_ids: list[uuid.UUID] = Field(..., description="IDs de los mensajes reencolados")
    job_ids: list[uuid.UUID] = Field(..., description="IDs de los trabajos correspondientes")
    status: str = Field(default="accepted", description="Estado de la solicitud de replay")
