"""Add scraping_jobs table with constraints and indexes.

Revision ID: 005_add_scraping_jobs_table
Revises: 004_add_price_condition
Create Date: 2026-09-20 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005_add_scraping_jobs_table"
down_revision: str | Sequence[str] | None = "004_add_price_condition"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create scraping_jobs table with check constraints and indexes."""
    op.create_table(
        "scraping_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "store_id",
            sa.Uuid(),
            sa.ForeignKey("stores.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column(
            "batch_size",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "observations_created",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'retrying', "
            "'completed', 'skipped', 'failed', 'dead_letter')",
            name="ck_scraping_jobs_status",
        ),
        sa.CheckConstraint("batch_size > 0", name="ck_scraping_jobs_batch_size_positive"),
        sa.CheckConstraint(
            "observations_created >= 0", name="ck_scraping_jobs_observations_non_negative"
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_scraping_jobs_attempts_non_negative"),
        sa.CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="ck_scraping_jobs_temporal_coherence",
        ),
    )

    op.create_index(
        "ix_scraping_jobs_status",
        "scraping_jobs",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_scraping_jobs_store_id",
        "scraping_jobs",
        ["store_id"],
        unique=False,
    )
    op.create_index(
        "ix_scraping_jobs_created_at_desc",
        "scraping_jobs",
        [sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    """Drop scraping_jobs table and its indexes."""
    op.drop_index("ix_scraping_jobs_created_at_desc", table_name="scraping_jobs")
    op.drop_index("ix_scraping_jobs_store_id", table_name="scraping_jobs")
    op.drop_index("ix_scraping_jobs_status", table_name="scraping_jobs")
    op.drop_table("scraping_jobs")
