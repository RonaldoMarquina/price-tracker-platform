"""SQLAlchemy ORM models defining the database schema."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from shared.queue.models import LocalQueueMessage  # noqa: F401
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Category(Base):
    """Categoría a la que pertenece un componente tecnológico."""

    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)

    products: Mapped[list["Product"]] = relationship(
        "Product", back_populates="category", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Category(name='{self.name}', slug='{self.slug}')>"


class Product(Base):
    """Componente tecnológico incluido en el catálogo."""

    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, nullable=False)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    mpn: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    category: Mapped["Category"] = relationship("Category", back_populates="products")
    store_products: Mapped[list["StoreProduct"]] = relationship(
        "StoreProduct", back_populates="product", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Product(name='{self.name}', slug='{self.slug}')>"


class Store(Base):
    """Comercio electrónico del que se obtiene información de precios."""

    __tablename__ = "stores"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    store_products: Mapped[list["StoreProduct"]] = relationship(
        "StoreProduct", back_populates="store", cascade="all, delete-orphan"
    )
    scraping_jobs: Mapped[list["ScrapingJob"]] = relationship("ScrapingJob", back_populates="store")

    def __repr__(self) -> str:
        return f"<Store(name='{self.name}', domain='{self.domain}')>"


class StoreProduct(Base):
    """Relación entre un producto del catálogo y su ficha en una tienda."""

    __tablename__ = "store_products"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "store_id", "product_url", name="uq_store_products_product_store_url"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    store_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False
    )
    external_sku: Mapped[str | None] = mapped_column(String(150), nullable=True)
    product_url: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    product: Mapped["Product"] = relationship("Product", back_populates="store_products")
    store: Mapped["Store"] = relationship("Store", back_populates="store_products")
    price_observations: Mapped[list["PriceObservation"]] = relationship(
        "PriceObservation", back_populates="store_product", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<StoreProduct(product_id='{self.product_id}', store_id='{self.store_id}')>"


class PriceObservation(Base):
    """Precio capturado para un producto y una tienda en una fecha determinada."""

    __tablename__ = "price_observations"
    __table_args__ = (
        CheckConstraint(
            "(price IS NULL AND currency IS NULL) OR "
            "(price IS NOT NULL AND price > 0 AND currency IS NOT NULL)",
            name="ck_price_observations_price_currency_valid",
        ),
        CheckConstraint(
            "price_condition IS NULL OR price_condition IN ('standard', 'cash_or_bank_transfer')",
            name="ck_price_observations_price_condition",
        ),
        UniqueConstraint("source_hash", name="uq_price_observations_source_hash"),
        Index(
            "ix_price_observations_store_product_captured_at",
            "store_product_id",
            text("captured_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("store_products.id", ondelete="CASCADE"), nullable=False
    )
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    availability: Mapped[str | None] = mapped_column(String(40), nullable=True)
    price_condition: Mapped[str | None] = mapped_column(String(40), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    store_product: Mapped["StoreProduct"] = relationship(
        "StoreProduct", back_populates="price_observations"
    )

    def __repr__(self) -> str:
        return f"<PriceObservation(price={self.price} {self.currency})>"


class ScrapingJob(Base):
    """Registro de auditoría y ciclo de vida de un lote de extracción."""

    __tablename__ = "scraping_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'processing', 'retrying', "
            "'completed', 'skipped', 'failed', 'dead_letter')",
            name="ck_scraping_jobs_status",
        ),
        CheckConstraint("batch_size > 0", name="ck_scraping_jobs_batch_size_positive"),
        CheckConstraint(
            "observations_created >= 0", name="ck_scraping_jobs_observations_non_negative"
        ),
        CheckConstraint("attempts >= 0", name="ck_scraping_jobs_attempts_non_negative"),
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="ck_scraping_jobs_temporal_coherence",
        ),
        CheckConstraint(
            "trigger_type IN ('scheduled', 'manual')",
            name="ck_scraping_jobs_trigger_type",
        ),
        CheckConstraint(
            "(trigger_type = 'scheduled' AND dispatch_slot IS NOT NULL) "
            "OR (trigger_type = 'manual' AND dispatch_slot IS NULL)",
            name="ck_scraping_jobs_dispatch_slot_coherence",
        ),
        CheckConstraint("replay_count >= 0", name="ck_scraping_jobs_replay_count_non_negative"),
        Index("ix_scraping_jobs_created_at_desc", text("created_at DESC")),
        Index(
            "uq_scraping_jobs_store_dispatch_slot",
            "store_id",
            "dispatch_slot",
            unique=True,
            postgresql_where=text("dispatch_slot IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("stores.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30), default="queued", server_default=text("'queued'"), nullable=False, index=True
    )
    trigger_type: Mapped[str] = mapped_column(
        String(20), default="manual", server_default=text("'manual'"), nullable=False
    )
    dispatch_slot: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    batch_size: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )
    observations_created: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_to_dlq_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_dlq_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    replay_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    replayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    store: Mapped["Store"] = relationship("Store", back_populates="scraping_jobs")
    dlq_ledger_entries: Mapped[list["ScrapingDlqLedger"]] = relationship(
        "ScrapingDlqLedger", back_populates="job"
    )
    outbox_entries: Mapped[list["ScrapingOutbox"]] = relationship(
        "ScrapingOutbox", back_populates="job"
    )

    def __repr__(self) -> str:
        return f"<ScrapingJob(id='{self.id}', store_id='{self.store_id}', status='{self.status}')>"


class ScrapingQuarantine(Base):
    """Registro de cuarentena para mensajes DLQ con payload corrupto o job inexistente."""

    __tablename__ = "scraping_quarantine"
    __table_args__ = (
        CheckConstraint(
            "quarantine_type IN ('invalid_payload', 'missing_job', 'orphaned_message')",
            name="ck_scraping_quarantine_type",
        ),
        CheckConstraint(
            "status IN ('quarantined', 'reviewed', 'discarded')",
            name="ck_scraping_quarantine_status",
        ),
        CheckConstraint("attempts >= 1", name="ck_scraping_quarantine_attempts_positive"),
        Index("ix_scraping_quarantine_status_received", "status", text("received_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_message_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    body_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    error_reason: Mapped[str] = mapped_column(Text, nullable=False)
    quarantine_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="quarantined", server_default=text("'quarantined'"), nullable=False
    )
    attempts: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<ScrapingQuarantine(id='{self.id}', status='{self.status}')>"


class ScrapingDlqLedger(Base):
    """Ledger operativo canónico de auditoría de mensajes en Dead Letter Queue."""

    __tablename__ = "scraping_dlq_ledger"
    __table_args__ = (
        CheckConstraint(
            "status IN ('in_dlq', 'replay_pending', 'replayed', 'discarded')",
            name="ck_scraping_dlq_ledger_status",
        ),
        CheckConstraint(
            "products_count >= 0", name="ck_scraping_dlq_ledger_products_count_non_negative"
        ),
        CheckConstraint("attempts >= 0", name="ck_scraping_dlq_ledger_attempts_non_negative"),
        CheckConstraint(
            "replay_count >= 0", name="ck_scraping_dlq_ledger_replay_count_non_negative"
        ),
        Index("ix_scraping_dlq_ledger_status_sent_at", "status", text("sent_to_dlq_at DESC")),
        Index("ix_scraping_dlq_ledger_job_id", "job_id"),
        Index("ix_scraping_dlq_ledger_root_id", "root_logical_message_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    root_logical_message_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    replayed_from_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("scraping_jobs.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    store_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    products_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_to_dlq_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="in_dlq", server_default=text("'in_dlq'"), nullable=False
    )
    replay_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    replayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    job: Mapped["ScrapingJob"] = relationship("ScrapingJob", back_populates="dlq_ledger_entries")
    store: Mapped["Store"] = relationship("Store")
    outbox_entries: Mapped[list["ScrapingOutbox"]] = relationship(
        "ScrapingOutbox", back_populates="source_ledger"
    )

    def __repr__(self) -> str:
        return f"<ScrapingDlqLedger(id='{self.id}', status='{self.status}')>"


class ScrapingOutbox(Base):
    """Transactional outbox para publicación confiable y desacoplada hacia SQS."""

    __tablename__ = "scraping_outbox"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'publishing', 'published', 'failed', 'exhausted')",
            name="ck_scraping_outbox_status",
        ),
        CheckConstraint(
            "event_type IN ('initial_dispatch', 'replay')", name="ck_scraping_outbox_event_type"
        ),
        CheckConstraint("attempts >= 0", name="ck_scraping_outbox_attempts_non_negative"),
        CheckConstraint(
            "lease_until IS NULL OR locked_at IS NULL OR lease_until >= locked_at",
            name="ck_scraping_outbox_lease_coherence",
        ),
        CheckConstraint(
            "(event_type = 'replay' AND source_ledger_id IS NOT NULL) "
            "OR (event_type = 'initial_dispatch' AND source_ledger_id IS NULL)",
            name="ck_scraping_outbox_source_ledger_coherence",
        ),
        UniqueConstraint("idempotency_key", name="uq_scraping_outbox_idempotency_key"),
        Index(
            "ix_scraping_outbox_claim",
            "status",
            "available_at",
            "attempts",
            postgresql_where=text("status IN ('pending', 'failed', 'publishing')"),
        ),
        Index("ix_scraping_outbox_aggregate_id", "aggregate_id"),
        Index("ix_scraping_outbox_source_ledger_id", "source_ledger_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aggregate_type: Mapped[str] = mapped_column(
        String(50), default="scraping_job", server_default=text("'scraping_job'"), nullable=False
    )
    aggregate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("scraping_jobs.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(
        String(30),
        default="initial_dispatch",
        server_default=text("'initial_dispatch'"),
        nullable=False,
    )
    source_ledger_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("scraping_dlq_ledger.id", ondelete="RESTRICT"),
        nullable=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    queue_name: Mapped[str] = mapped_column(
        String(80), default="scraping-jobs", server_default=text("'scraping-jobs'"), nullable=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default=text("'pending'"), nullable=False
    )
    attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    locked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    job: Mapped["ScrapingJob"] = relationship("ScrapingJob", back_populates="outbox_entries")
    source_ledger: Mapped["ScrapingDlqLedger | None"] = relationship(
        "ScrapingDlqLedger", back_populates="outbox_entries"
    )

    def __repr__(self) -> str:
        return f"<ScrapingOutbox(id='{self.id}', status='{self.status}')>"
