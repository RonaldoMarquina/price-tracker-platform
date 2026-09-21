"""Add DLQ audit and replay tracking fields to local_queue_messages and scraping_jobs.

Revision ID: 007_dlq_audit_and_replay
Revises: 006_dispatch_slot_trigger_type
Create Date: 2026-09-21 19:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007_dlq_audit_and_replay"
down_revision: str | Sequence[str] | None = "006_dispatch_slot_trigger_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add sent_to_dlq_at, replay_count, replayed_at, last_dlq_reason and constraints."""
    # 1. local_queue_messages
    op.add_column(
        "local_queue_messages",
        sa.Column("sent_to_dlq_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "local_queue_messages",
        sa.Column("replay_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "local_queue_messages",
        sa.Column("replayed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_local_queue_messages_replay_count_non_negative",
        "local_queue_messages",
        "replay_count >= 0",
    )
    op.create_index(
        "ix_local_queue_messages_dlq_browse",
        "local_queue_messages",
        ["queue_name", "status", "sent_to_dlq_at"],
    )

    # Backfill sent_to_dlq_at for existing messages in DLQ
    op.execute(
        "UPDATE local_queue_messages "
        "SET sent_to_dlq_at = COALESCE(processed_at, created_at) "
        "WHERE status = 'dlq' OR queue_name = 'scraping-jobs-dlq'"
    )

    # 2. scraping_jobs
    op.add_column(
        "scraping_jobs",
        sa.Column("sent_to_dlq_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "scraping_jobs",
        sa.Column("last_dlq_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "scraping_jobs",
        sa.Column("replay_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "scraping_jobs",
        sa.Column("replayed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_scraping_jobs_replay_count_non_negative",
        "scraping_jobs",
        "replay_count >= 0",
    )

    # Backfill sent_to_dlq_at and last_dlq_reason for existing dead_letter jobs
    op.execute(
        "UPDATE scraping_jobs "
        "SET sent_to_dlq_at = finished_at, last_dlq_reason = error_reason "
        "WHERE status = 'dead_letter'"
    )


def downgrade() -> None:
    """Remove DLQ audit and replay tracking columns and constraints."""
    # 2. scraping_jobs
    op.drop_constraint("ck_scraping_jobs_replay_count_non_negative", "scraping_jobs", type_="check")
    op.drop_column("scraping_jobs", "replayed_at")
    op.drop_column("scraping_jobs", "replay_count")
    op.drop_column("scraping_jobs", "last_dlq_reason")
    op.drop_column("scraping_jobs", "sent_to_dlq_at")

    # 1. local_queue_messages
    op.drop_index("ix_local_queue_messages_dlq_browse", table_name="local_queue_messages")
    op.drop_constraint(
        "ck_local_queue_messages_replay_count_non_negative", "local_queue_messages", type_="check"
    )
    op.drop_column("local_queue_messages", "replayed_at")
    op.drop_column("local_queue_messages", "replay_count")
    op.drop_column("local_queue_messages", "sent_to_dlq_at")
