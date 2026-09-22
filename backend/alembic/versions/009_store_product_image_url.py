"""Add image_url to store_products table.

Revision ID: 009_store_product_image_url
Revises: 008_outbox_and_dlq_ledger
Create Date: 2026-09-22 14:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009_store_product_image_url"
down_revision: str | Sequence[str] | None = "008_outbox_and_dlq_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable image_url column to store_products table."""
    op.add_column(
        "store_products",
        sa.Column("image_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop image_url column from store_products table."""
    op.drop_column("store_products", "image_url")
