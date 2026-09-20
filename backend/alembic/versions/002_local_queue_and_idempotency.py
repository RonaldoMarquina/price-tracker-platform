"""Add local_queue_messages table and unique constraint on price_observations.source_hash.

Revision ID: 002_local_queue_and_idempotency
Revises: 001_initial_schema
Create Date: 2026-09-19 18:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_local_queue_and_idempotency"
down_revision: str | Sequence[str] | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create local_queue_messages table and unique constraint for idempotency."""
    op.create_table(
        "local_queue_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("queue_name", sa.String(length=100), nullable=False),
        sa.Column("payload", JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("receipt_handle", sa.Uuid(), nullable=True),
        sa.Column(
            "status", sa.String(length=30), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "visible_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_local_queue_messages_claim",
        "local_queue_messages",
        ["queue_name", "status", "visible_at"],
        unique=False,
    )
    op.create_index(
        "ix_local_queue_messages_receipt",
        "local_queue_messages",
        ["receipt_handle"],
        unique=False,
    )

    op.create_unique_constraint(
        "uq_price_observations_source_hash",
        "price_observations",
        ["source_hash"],
    )


def downgrade() -> None:
    """Revert local_queue_messages and idempotency constraint."""
    op.drop_constraint(
        "uq_price_observations_source_hash",
        "price_observations",
        type_="unique",
    )
    op.drop_index("ix_local_queue_messages_receipt", table_name="local_queue_messages")
    op.drop_index("ix_local_queue_messages_claim", table_name="local_queue_messages")
    op.drop_table("local_queue_messages")
