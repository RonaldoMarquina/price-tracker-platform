"""Add scraping outbox, dlq ledger and quarantine tables.

Revision ID: 008_scraping_outbox_and_dlq_ledger
Revises: 007_dlq_audit_and_replay
Create Date: 2026-09-21 19:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008_outbox_and_dlq_ledger"
down_revision: str | Sequence[str] | None = "007_dlq_audit_and_replay"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create quarantine, dlq_ledger, outbox tables and add payload to scraping_jobs."""
    # 1. Columna payload en scraping_jobs
    op.add_column(
        "scraping_jobs",
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # 2. Tabla scraping_quarantine
    op.create_table(
        "scraping_quarantine",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("provider_message_id", sa.String(length=100), nullable=True),
        sa.Column("body_sha256", sa.String(length=64), nullable=False),
        sa.Column("error_reason", sa.Text(), nullable=False),
        sa.Column("quarantine_type", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'quarantined'"),
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "quarantine_type IN ('invalid_payload', 'missing_job', 'orphaned_message')",
            name="ck_scraping_quarantine_type",
        ),
        sa.CheckConstraint(
            "status IN ('quarantined', 'reviewed', 'discarded')",
            name="ck_scraping_quarantine_status",
        ),
        sa.CheckConstraint("attempts >= 1", name="ck_scraping_quarantine_attempts_positive"),
    )
    op.create_index(
        "ix_scraping_quarantine_status_received",
        "scraping_quarantine",
        ["status", sa.text("received_at DESC")],
    )

    # 3. Tabla scraping_dlq_ledger
    op.create_table(
        "scraping_dlq_ledger",
        # id es el logical_message_id del ciclo fallido
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("root_logical_message_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("replayed_from_message_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "job_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("scraping_jobs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "store_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("stores.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("store_name", sa.String(length=100), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("products_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.Column("sent_to_dlq_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'in_dlq'"),
        ),
        sa.Column("replay_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("replayed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('in_dlq', 'replay_pending', 'replayed', 'discarded')",
            name="ck_scraping_dlq_ledger_status",
        ),
        sa.CheckConstraint(
            "products_count >= 0",
            name="ck_scraping_dlq_ledger_products_count_non_negative",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_scraping_dlq_ledger_attempts_non_negative"),
        sa.CheckConstraint(
            "replay_count >= 0",
            name="ck_scraping_dlq_ledger_replay_count_non_negative",
        ),
    )
    op.create_index(
        "ix_scraping_dlq_ledger_status_sent_at",
        "scraping_dlq_ledger",
        ["status", sa.text("sent_to_dlq_at DESC")],
    )
    op.create_index("ix_scraping_dlq_ledger_job_id", "scraping_dlq_ledger", ["job_id"])
    op.create_index(
        "ix_scraping_dlq_ledger_root_id",
        "scraping_dlq_ledger",
        ["root_logical_message_id"],
    )

    # 4. Tabla scraping_outbox
    op.create_table(
        "scraping_outbox",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "aggregate_type",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'scraping_job'"),
        ),
        sa.Column(
            "aggregate_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("scraping_jobs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'initial_dispatch'"),
        ),
        sa.Column(
            "source_ledger_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("scraping_dlq_ledger.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("queue_name", sa.String(length=80), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("locked_by", sa.String(length=100), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_message_id", sa.String(length=100), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'publishing', 'published', 'failed', 'exhausted')",
            name="ck_scraping_outbox_status",
        ),
        sa.CheckConstraint(
            "event_type IN ('initial_dispatch', 'replay')",
            name="ck_scraping_outbox_event_type",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_scraping_outbox_attempts_non_negative"),
        sa.CheckConstraint(
            "lease_until IS NULL OR locked_at IS NULL OR lease_until >= locked_at",
            name="ck_scraping_outbox_lease_coherence",
        ),
        sa.CheckConstraint(
            "(event_type = 'replay' AND source_ledger_id IS NOT NULL) OR "
            "(event_type = 'initial_dispatch' AND source_ledger_id IS NULL)",
            name="ck_scraping_outbox_source_ledger_coherence",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_scraping_outbox_idempotency_key"),
    )
    op.create_index(
        "ix_scraping_outbox_claim",
        "scraping_outbox",
        ["status", "available_at", "attempts"],
        postgresql_where=sa.text("status IN ('pending', 'failed', 'publishing')"),
    )
    op.create_index("ix_scraping_outbox_aggregate_id", "scraping_outbox", ["aggregate_id"])
    op.create_index("ix_scraping_outbox_source_ledger_id", "scraping_outbox", ["source_ledger_id"])


def downgrade() -> None:
    """Drop outbox, dlq_ledger, quarantine tables and payload column."""
    op.drop_table("scraping_outbox")
    op.drop_table("scraping_dlq_ledger")
    op.drop_table("scraping_quarantine")
    op.drop_column("scraping_jobs", "payload")
