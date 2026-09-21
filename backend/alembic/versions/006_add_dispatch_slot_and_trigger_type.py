"""Add dispatch_slot and trigger_type to scraping_jobs.

Revision ID: 006_add_dispatch_slot_and_trigger_type
Revises: 005_add_scraping_jobs_table
Create Date: 2026-09-20 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006_dispatch_slot_trigger_type"
down_revision: str | Sequence[str] | None = "005_add_scraping_jobs_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add trigger_type, dispatch_slot, coherence constraints, and unique index."""
    op.add_column(
        "scraping_jobs",
        sa.Column(
            "trigger_type",
            sa.String(length=20),
            server_default=sa.text("'manual'"),
            nullable=False,
        ),
    )
    op.add_column(
        "scraping_jobs",
        sa.Column(
            "dispatch_slot",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_check_constraint(
        "ck_scraping_jobs_trigger_type",
        "scraping_jobs",
        "trigger_type IN ('scheduled', 'manual')",
    )

    op.create_check_constraint(
        "ck_scraping_jobs_dispatch_slot_coherence",
        "scraping_jobs",
        "(trigger_type = 'scheduled' AND dispatch_slot IS NOT NULL) "
        "OR (trigger_type = 'manual' AND dispatch_slot IS NULL)",
    )

    op.create_index(
        "uq_scraping_jobs_store_dispatch_slot",
        "scraping_jobs",
        ["store_id", "dispatch_slot"],
        unique=True,
        postgresql_where=sa.text("dispatch_slot IS NOT NULL"),
    )


def downgrade() -> None:
    """Remove unique index, check constraints, and added columns."""
    op.drop_index(
        "uq_scraping_jobs_store_dispatch_slot",
        table_name="scraping_jobs",
        postgresql_where=sa.text("dispatch_slot IS NOT NULL"),
    )
    op.drop_constraint("ck_scraping_jobs_dispatch_slot_coherence", "scraping_jobs", type_="check")
    op.drop_constraint("ck_scraping_jobs_trigger_type", "scraping_jobs", type_="check")
    op.drop_column("scraping_jobs", "dispatch_slot")
    op.drop_column("scraping_jobs", "trigger_type")
