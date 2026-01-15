"""update daily tables for company fields

Revision ID: 0004
Revises: 0003
Create Date: 2025-02-09
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("ix_snapshot_date_source_wh_sku", table_name="daily_snapshot")
    op.drop_index("ix_delta_date_source_wh_sku", table_name="daily_delta")
    op.drop_index("ix_delta_source_wh_sku_date", table_name="daily_delta")
    op.drop_index("ix_delta_date_project_label", table_name="daily_delta")
    op.drop_index("ix_daily_snapshot_source", table_name="daily_snapshot")
    op.drop_index("ix_daily_delta_source", table_name="daily_delta")
    op.drop_index("ix_daily_snapshot_group", table_name="daily_snapshot")
    op.drop_index("ix_daily_delta_group", table_name="daily_delta")

    op.drop_constraint("uq_snapshot_key", "daily_snapshot", type_="unique")
    op.drop_constraint("uq_delta_key", "daily_delta", type_="unique")

    op.alter_column("daily_snapshot", "date", new_column_name="data_date")
    op.alter_column("daily_delta", "date", new_column_name="data_date")
    op.alter_column("daily_snapshot", "source", new_column_name="company")
    op.alter_column("daily_delta", "source", new_column_name="company")
    op.alter_column("daily_snapshot", "group", new_column_name="group_name")
    op.alter_column("daily_delta", "group", new_column_name="group_name")

    op.alter_column(
        "daily_snapshot",
        "stock_qty",
        existing_type=sa.Float(),
        type_=sa.Integer(),
    )
    op.add_column(
        "daily_delta",
        sa.Column("stock_qty", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("daily_delta", "stock_qty", server_default=None)
    op.alter_column(
        "daily_delta",
        "sold_qty",
        existing_type=sa.Float(),
        type_=sa.Integer(),
    )
    op.alter_column(
        "daily_delta",
        "replenished_qty",
        existing_type=sa.Float(),
        type_=sa.Integer(),
    )

    op.alter_column(
        "daily_snapshot",
        "price_start_day",
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
    )
    op.alter_column(
        "daily_snapshot",
        "price_end_day",
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
    )
    op.alter_column(
        "daily_delta",
        "price_start_day",
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
    )
    op.alter_column(
        "daily_delta",
        "price_end_day",
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
    )

    op.create_unique_constraint(
        "uq_snapshot_key",
        "daily_snapshot",
        ["data_date", "company", "warehouse", "sku"],
    )
    op.create_unique_constraint(
        "uq_delta_key",
        "daily_delta",
        ["data_date", "company", "warehouse", "sku"],
    )

    op.create_index("ix_daily_snapshot_company", "daily_snapshot", ["company"])
    op.create_index("ix_daily_delta_company", "daily_delta", ["company"])
    op.create_index(
        "ix_daily_snapshot_group_name", "daily_snapshot", ["group_name"]
    )
    op.create_index("ix_daily_delta_group_name", "daily_delta", ["group_name"])

    op.create_index(
        "ix_snapshot_company_wh_sku_data_date_desc",
        "daily_snapshot",
        ["company", "warehouse", "sku", sa.text("data_date DESC")],
    )
    op.create_index(
        "ix_delta_company_wh_sku_data_date_desc",
        "daily_delta",
        ["company", "warehouse", "sku", sa.text("data_date DESC")],
    )
    op.create_index(
        "ix_snapshot_company_data_date_project_label",
        "daily_snapshot",
        ["company", "data_date", "project_label"],
    )
    op.create_index(
        "ix_delta_company_data_date_project_label",
        "daily_delta",
        ["company", "data_date", "project_label"],
    )


def downgrade():
    op.drop_index(
        "ix_delta_company_data_date_project_label", table_name="daily_delta"
    )
    op.drop_index(
        "ix_snapshot_company_data_date_project_label", table_name="daily_snapshot"
    )
    op.drop_index(
        "ix_delta_company_wh_sku_data_date_desc", table_name="daily_delta"
    )
    op.drop_index(
        "ix_snapshot_company_wh_sku_data_date_desc", table_name="daily_snapshot"
    )
    op.drop_index("ix_daily_delta_group_name", table_name="daily_delta")
    op.drop_index("ix_daily_snapshot_group_name", table_name="daily_snapshot")
    op.drop_index("ix_daily_delta_company", table_name="daily_delta")
    op.drop_index("ix_daily_snapshot_company", table_name="daily_snapshot")

    op.drop_constraint("uq_delta_key", "daily_delta", type_="unique")
    op.drop_constraint("uq_snapshot_key", "daily_snapshot", type_="unique")

    op.alter_column(
        "daily_delta",
        "price_end_day",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Float(),
    )
    op.alter_column(
        "daily_delta",
        "price_start_day",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Float(),
    )
    op.alter_column(
        "daily_snapshot",
        "price_end_day",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Float(),
    )
    op.alter_column(
        "daily_snapshot",
        "price_start_day",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Float(),
    )

    op.alter_column(
        "daily_delta",
        "replenished_qty",
        existing_type=sa.Integer(),
        type_=sa.Float(),
    )
    op.alter_column(
        "daily_delta",
        "sold_qty",
        existing_type=sa.Integer(),
        type_=sa.Float(),
    )
    op.drop_column("daily_delta", "stock_qty")
    op.alter_column(
        "daily_snapshot",
        "stock_qty",
        existing_type=sa.Integer(),
        type_=sa.Float(),
    )

    op.alter_column("daily_delta", "group_name", new_column_name="group")
    op.alter_column("daily_snapshot", "group_name", new_column_name="group")
    op.alter_column("daily_delta", "company", new_column_name="source")
    op.alter_column("daily_snapshot", "company", new_column_name="source")
    op.alter_column("daily_delta", "data_date", new_column_name="date")
    op.alter_column("daily_snapshot", "data_date", new_column_name="date")

    op.create_unique_constraint(
        "uq_snapshot_key",
        "daily_snapshot",
        ["date", "source", "warehouse", "sku"],
    )
    op.create_unique_constraint(
        "uq_delta_key",
        "daily_delta",
        ["date", "source", "warehouse", "sku"],
    )

    op.create_index(
        "ix_snapshot_date_source_wh_sku",
        "daily_snapshot",
        ["date", "source", "warehouse", "sku"],
    )
    op.create_index(
        "ix_delta_date_source_wh_sku",
        "daily_delta",
        ["date", "source", "warehouse", "sku"],
    )
    op.create_index(
        "ix_delta_source_wh_sku_date",
        "daily_delta",
        ["source", "warehouse", "sku", "date"],
    )
    op.create_index(
        "ix_delta_date_project_label",
        "daily_delta",
        ["date", "project_label"],
    )

    op.create_index("ix_daily_snapshot_source", "daily_snapshot", ["source"])
    op.create_index("ix_daily_delta_source", "daily_delta", ["source"])
    op.create_index("ix_daily_snapshot_group", "daily_snapshot", ["group"])
    op.create_index("ix_daily_delta_group", "daily_delta", ["group"])
