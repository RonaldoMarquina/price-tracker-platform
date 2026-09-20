"""SQLAlchemy model for local PostgreSQL-backed queue messages."""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class QueueModelBase(DeclarativeBase):
    """Base class for shared queue model."""

    pass


class LocalQueueMessage(QueueModelBase):
    """Represents a message stored in PostgreSQL for the local queue."""

    __tablename__ = "local_queue_messages"
    __table_args__ = (
        Index(
            "ix_local_queue_messages_claim",
            "queue_name",
            "status",
            "visible_at",
        ),
        Index("ix_local_queue_messages_receipt", "receipt_handle"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    queue_name: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    receipt_handle: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", server_default=text("'pending'")
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    visible_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<LocalQueueMessage(id='{self.id}', queue='{self.queue_name}', "
            f"status='{self.status}', attempts={self.attempts})>"
        )
