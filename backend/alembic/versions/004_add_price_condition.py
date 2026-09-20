"""Add price_condition to price_observations with check constraint.

Revision ID: 004_add_price_condition
Revises: 003_add_mpn_nullable_price
Create Date: 2026-09-20 15:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_add_price_condition"
down_revision: str | Sequence[str] | None = "003_add_mpn_nullable_price"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable price_condition column and check constraint."""
    # 1. Add price_condition column
    op.add_column(
        "price_observations",
        sa.Column("price_condition", sa.String(length=40), nullable=True),
    )

    # 2. Add check constraint for allowed conditions
    op.create_check_constraint(
        "ck_price_observations_price_condition",
        "price_observations",
        "price_condition IS NULL OR price_condition IN ('standard', 'cash_or_bank_transfer')",
    )


def downgrade() -> None:
    """Revert price_condition column and check constraint while preserving all observations."""
    op.drop_constraint(
        "ck_price_observations_price_condition",
        "price_observations",
        type_="check",
    )
    op.drop_column("price_observations", "price_condition")
