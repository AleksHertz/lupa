"""create tables

Revision ID: 0001
Revises: 
Create Date: 2024-01-14
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "daily_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("warehouse", sa.String(length=100), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("manufacturer", sa.String(length=100), nullable=True),
        sa.Column("nomenclature", sa.String(length=255), nullable=True),
        sa.Column("stock_qty", sa.Float(), nullable=False),
        sa.Column("price_start_day", sa.Float(), nullable=True),
        sa.Column("price_end_day", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "date", "warehouse", "sku", "manufacturer", name="uq_snapshot_key"
        ),
    )
    op.create_index(
        "ix_snapshot_date_wh_sku", "daily_snapshot", ["date", "warehouse", "sku"]
    )
    op.create_index("ix_daily_snapshot_date", "daily_snapshot", ["date"])
    op.create_index("ix_daily_snapshot_warehouse", "daily_snapshot", ["warehouse"])
    op.create_index("ix_daily_snapshot_sku", "daily_snapshot", ["sku"])
    op.create_index("ix_daily_snapshot_manufacturer", "daily_snapshot", ["manufacturer"])
    op.create_index("ix_daily_snapshot_nomenclature", "daily_snapshot", ["nomenclature"])

    op.create_table(
        "daily_delta",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("warehouse", sa.String(length=100), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("manufacturer", sa.String(length=100), nullable=True),
        sa.Column("nomenclature", sa.String(length=255), nullable=True),
        sa.Column("sold_qty", sa.Float(), nullable=False),
        sa.Column("replenished_qty", sa.Float(), nullable=False),
        sa.Column("price_start_day", sa.Float(), nullable=True),
        sa.Column("price_end_day", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "date", "warehouse", "sku", "manufacturer", name="uq_delta_key"
        ),
    )
    op.create_index(
        "ix_delta_date_wh_sku", "daily_delta", ["date", "warehouse", "sku"]
    )
    op.create_index("ix_daily_delta_date", "daily_delta", ["date"])
    op.create_index("ix_daily_delta_warehouse", "daily_delta", ["warehouse"])
    op.create_index("ix_daily_delta_sku", "daily_delta", ["sku"])
    op.create_index("ix_daily_delta_manufacturer", "daily_delta", ["manufacturer"])
    op.create_index("ix_daily_delta_nomenclature", "daily_delta", ["nomenclature"])


def downgrade():
    op.drop_index("ix_delta_date_wh_sku", table_name="daily_delta")
    op.drop_index("ix_daily_delta_nomenclature", table_name="daily_delta")
    op.drop_index("ix_daily_delta_manufacturer", table_name="daily_delta")
    op.drop_index("ix_daily_delta_sku", table_name="daily_delta")
    op.drop_index("ix_daily_delta_warehouse", table_name="daily_delta")
    op.drop_index("ix_daily_delta_date", table_name="daily_delta")
    op.drop_table("daily_delta")

    op.drop_index("ix_snapshot_date_wh_sku", table_name="daily_snapshot")
    op.drop_index("ix_daily_snapshot_nomenclature", table_name="daily_snapshot")
    op.drop_index("ix_daily_snapshot_manufacturer", table_name="daily_snapshot")
    op.drop_index("ix_daily_snapshot_sku", table_name="daily_snapshot")
    op.drop_index("ix_daily_snapshot_warehouse", table_name="daily_snapshot")
    op.drop_index("ix_daily_snapshot_date", table_name="daily_snapshot")
    op.drop_table("daily_snapshot")
