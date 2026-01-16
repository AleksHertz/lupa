"""replace start/end price with single price

Revision ID: 0002_price_single_column
Revises: 0001_baseline
Create Date: 2025-02-18
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002_price_single_column"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("daily_snapshot", sa.Column("price", sa.Numeric(12, 2), nullable=True))
    op.add_column("daily_delta", sa.Column("price", sa.Numeric(12, 2), nullable=True))

    op.execute(
        """
        UPDATE daily_snapshot
        SET price = COALESCE(price_end_day, price_start_day)
        """
    )
    op.execute(
        """
        UPDATE daily_delta
        SET price = COALESCE(price_end_day, price_start_day)
        """
    )

    op.drop_column("daily_snapshot", "price_start_day")
    op.drop_column("daily_snapshot", "price_end_day")
    op.drop_column("daily_delta", "price_start_day")
    op.drop_column("daily_delta", "price_end_day")


def downgrade():
    op.add_column(
        "daily_snapshot",
        sa.Column("price_start_day", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "daily_snapshot",
        sa.Column("price_end_day", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "daily_delta",
        sa.Column("price_start_day", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "daily_delta",
        sa.Column("price_end_day", sa.Numeric(12, 2), nullable=True),
    )

    op.execute(
        """
        UPDATE daily_snapshot
        SET price_start_day = price,
            price_end_day = price
        """
    )
    op.execute(
        """
        UPDATE daily_delta
        SET price_start_day = price,
            price_end_day = price
        """
    )

    op.drop_column("daily_snapshot", "price")
    op.drop_column("daily_delta", "price")
