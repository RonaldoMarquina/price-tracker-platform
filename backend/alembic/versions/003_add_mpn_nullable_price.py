"""Add product mpn and allow nullable price/currency on price_observations.

Revision ID: 003_add_product_mpn_and_nullable_price
Revises: 002_local_queue_and_idempotency
Create Date: 2026-09-19 20:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_add_mpn_nullable_price"
down_revision: str | Sequence[str] | None = "002_local_queue_and_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add mpn to products and allow nullable price/currency for out_of_stock events."""
    # 1. Add mpn column to products
    op.add_column("products", sa.Column("mpn", sa.String(length=100), nullable=True))
    op.create_index("ix_products_mpn", "products", ["mpn"], unique=False)

    # 2. Make price and currency nullable on price_observations
    op.alter_column(
        "price_observations",
        "price",
        existing_type=sa.Numeric(precision=12, scale=2),
        nullable=True,
    )
    op.alter_column(
        "price_observations",
        "currency",
        existing_type=sa.String(length=3),
        nullable=True,
    )

    # 3. Replace check constraint to allow NULL price/currency or strictly positive price
    op.drop_constraint("ck_price_observations_price_positive", "price_observations", type_="check")
    op.create_check_constraint(
        "ck_price_observations_price_currency_valid",
        "price_observations",
        "(price IS NULL AND currency IS NULL) OR "
        "(price IS NOT NULL AND price > 0 AND currency IS NOT NULL)",
    )


def downgrade() -> None:
    """Revert mpn column and restore NOT NULL price/currency constraint."""
    # 1. Drop updated constraint and delete any null price rows before restoring NOT NULL
    op.drop_constraint(
        "ck_price_observations_price_currency_valid", "price_observations", type_="check"
    )
    op.execute("DELETE FROM price_observations WHERE price IS NULL OR currency IS NULL")

    # 2. Restore price and currency as NOT NULL
    op.alter_column(
        "price_observations",
        "currency",
        existing_type=sa.String(length=3),
        nullable=False,
    )
    op.alter_column(
        "price_observations",
        "price",
        existing_type=sa.Numeric(precision=12, scale=2),
        nullable=False,
    )
    op.create_check_constraint(
        "ck_price_observations_price_positive",
        "price_observations",
        "price > 0",
    )

    # 3. Drop mpn index and column
    op.drop_index("ix_products_mpn", table_name="products")
    op.drop_column("products", "mpn")
