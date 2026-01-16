"""baseline schema

Revision ID: 0001_baseline
Revises:
Create Date: 2025-02-09
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "daily_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("data_date", sa.Date(), nullable=False),
        sa.Column("company", sa.String(length=100), nullable=False),
        sa.Column("warehouse", sa.String(length=100), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("mfg_sku", sa.String(length=100), nullable=True),
        sa.Column("manufacturer", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("brand", sa.String(length=100), nullable=True),
        sa.Column("group_name", sa.String(length=100), nullable=True),
        sa.Column("project_label", sa.String(length=100), nullable=True),
        sa.Column("stock_qty", sa.Integer(), nullable=False),
        sa.Column("price_start_day", sa.Numeric(12, 2), nullable=True),
        sa.Column("price_end_day", sa.Numeric(12, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "data_date", "company", "warehouse", "sku", name="uq_snapshot_key"
        ),
    )
    op.create_index("ix_daily_snapshot_date", "daily_snapshot", ["data_date"])
    op.create_index("ix_daily_snapshot_company", "daily_snapshot", ["company"])
    op.create_index("ix_daily_snapshot_warehouse", "daily_snapshot", ["warehouse"])
    op.create_index("ix_daily_snapshot_sku", "daily_snapshot", ["sku"])
    op.create_index(
        "ix_daily_snapshot_manufacturer", "daily_snapshot", ["manufacturer"]
    )
    op.create_index("ix_daily_snapshot_mfg_sku", "daily_snapshot", ["mfg_sku"])
    op.create_index("ix_daily_snapshot_name", "daily_snapshot", ["name"])
    op.create_index("ix_daily_snapshot_brand", "daily_snapshot", ["brand"])
    op.create_index("ix_daily_snapshot_group_name", "daily_snapshot", ["group_name"])
    op.create_index(
        "ix_daily_snapshot_project_label", "daily_snapshot", ["project_label"]
    )
    op.create_index(
        "ix_snapshot_company_wh_sku_data_date_desc",
        "daily_snapshot",
        ["company", "warehouse", "sku", sa.text("data_date DESC")],
    )
    op.create_index(
        "ix_snapshot_company_data_date_project_label",
        "daily_snapshot",
        ["company", "data_date", "project_label"],
    )

    op.create_table(
        "daily_delta",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("data_date", sa.Date(), nullable=False),
        sa.Column("company", sa.String(length=100), nullable=False),
        sa.Column("warehouse", sa.String(length=100), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("mfg_sku", sa.String(length=100), nullable=True),
        sa.Column("manufacturer", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("brand", sa.String(length=100), nullable=True),
        sa.Column("group_name", sa.String(length=100), nullable=True),
        sa.Column("project_label", sa.String(length=100), nullable=True),
        sa.Column("stock_qty", sa.Integer(), nullable=False),
        sa.Column("sold_qty", sa.Integer(), nullable=False),
        sa.Column("replenished_qty", sa.Integer(), nullable=False),
        sa.Column("price_start_day", sa.Numeric(12, 2), nullable=True),
        sa.Column("price_end_day", sa.Numeric(12, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "data_date", "company", "warehouse", "sku", name="uq_delta_key"
        ),
    )
    op.create_index("ix_daily_delta_date", "daily_delta", ["data_date"])
    op.create_index("ix_daily_delta_company", "daily_delta", ["company"])
    op.create_index("ix_daily_delta_warehouse", "daily_delta", ["warehouse"])
    op.create_index("ix_daily_delta_sku", "daily_delta", ["sku"])
    op.create_index("ix_daily_delta_manufacturer", "daily_delta", ["manufacturer"])
    op.create_index("ix_daily_delta_mfg_sku", "daily_delta", ["mfg_sku"])
    op.create_index("ix_daily_delta_name", "daily_delta", ["name"])
    op.create_index("ix_daily_delta_brand", "daily_delta", ["brand"])
    op.create_index("ix_daily_delta_group_name", "daily_delta", ["group_name"])
    op.create_index(
        "ix_daily_delta_project_label", "daily_delta", ["project_label"]
    )
    op.create_index(
        "ix_delta_company_wh_sku_data_date_desc",
        "daily_delta",
        ["company", "warehouse", "sku", sa.text("data_date DESC")],
    )
    op.create_index(
        "ix_delta_company_data_date_project_label",
        "daily_delta",
        ["company", "data_date", "project_label"],
    )

    op.create_table(
        "ingest_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company", sa.String(length=100), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("data_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingest_runs_company", "ingest_runs", ["company"])
    op.create_index("ix_ingest_runs_data_date", "ingest_runs", ["data_date"])
    op.create_index(
        "ix_ingest_runs_company_data_date",
        "ingest_runs",
        ["company", "data_date"],
    )
    op.create_unique_constraint(
        "uq_ingest_runs_company_file_hash",
        "ingest_runs",
        ["company", "file_hash"],
    )


def downgrade():
    op.drop_constraint(
        "uq_ingest_runs_company_file_hash",
        "ingest_runs",
        type_="unique",
    )
    op.drop_index("ix_ingest_runs_company_data_date", table_name="ingest_runs")
    op.drop_index("ix_ingest_runs_data_date", table_name="ingest_runs")
    op.drop_index("ix_ingest_runs_company", table_name="ingest_runs")
    op.drop_table("ingest_runs")

    op.drop_index(
        "ix_delta_company_data_date_project_label", table_name="daily_delta"
    )
    op.drop_index(
        "ix_delta_company_wh_sku_data_date_desc", table_name="daily_delta"
    )
    op.drop_index("ix_daily_delta_project_label", table_name="daily_delta")
    op.drop_index("ix_daily_delta_group_name", table_name="daily_delta")
    op.drop_index("ix_daily_delta_brand", table_name="daily_delta")
    op.drop_index("ix_daily_delta_name", table_name="daily_delta")
    op.drop_index("ix_daily_delta_mfg_sku", table_name="daily_delta")
    op.drop_index("ix_daily_delta_manufacturer", table_name="daily_delta")
    op.drop_index("ix_daily_delta_sku", table_name="daily_delta")
    op.drop_index("ix_daily_delta_warehouse", table_name="daily_delta")
    op.drop_index("ix_daily_delta_company", table_name="daily_delta")
    op.drop_index("ix_daily_delta_date", table_name="daily_delta")
    op.drop_table("daily_delta")

    op.drop_index(
        "ix_snapshot_company_data_date_project_label", table_name="daily_snapshot"
    )
    op.drop_index(
        "ix_snapshot_company_wh_sku_data_date_desc", table_name="daily_snapshot"
    )
    op.drop_index("ix_daily_snapshot_project_label", table_name="daily_snapshot")
    op.drop_index("ix_daily_snapshot_group_name", table_name="daily_snapshot")
    op.drop_index("ix_daily_snapshot_brand", table_name="daily_snapshot")
    op.drop_index("ix_daily_snapshot_name", table_name="daily_snapshot")
    op.drop_index("ix_daily_snapshot_mfg_sku", table_name="daily_snapshot")
    op.drop_index("ix_daily_snapshot_manufacturer", table_name="daily_snapshot")
    op.drop_index("ix_daily_snapshot_sku", table_name="daily_snapshot")
    op.drop_index("ix_daily_snapshot_warehouse", table_name="daily_snapshot")
    op.drop_index("ix_daily_snapshot_company", table_name="daily_snapshot")
    op.drop_index("ix_daily_snapshot_date", table_name="daily_snapshot")
    op.drop_table("daily_snapshot")
