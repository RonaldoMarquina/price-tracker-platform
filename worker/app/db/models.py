"""Database models for worker persistence."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

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
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Category(Base):
    """Product category in database."""

    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)


class Product(Base):
    """Catalog product in database."""

    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, nullable=False)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    mpn: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Store(Base):
    """Store entity in database."""

    __tablename__ = "stores"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class StoreProduct(Base):
    """Link between catalog product and specific store URL."""

    __tablename__ = "store_products"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    external_sku: Mapped[str | None] = mapped_column(String(150), nullable=True)
    product_url: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PriceObservation(Base):
    """Captured price observation for a product in a store."""

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
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
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


class ScrapingJob(Base):
    """Auditing and lifecycle tracking for a scraping batch."""

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
