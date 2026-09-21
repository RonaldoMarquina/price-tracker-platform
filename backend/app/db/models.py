"""SQLAlchemy ORM models defining the database schema."""

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
    scraping_jobs: Mapped[list["ScrapingJob"]] = relationship(
        "ScrapingJob", back_populates="store"
    )

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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    store: Mapped["Store"] = relationship("Store", back_populates="scraping_jobs")

    def __repr__(self) -> str:
        return f"<ScrapingJob(id='{self.id}', store_id='{self.store_id}', status='{self.status}')>"
