"""add items and fact tables

Revision ID: 0004_fact_tables_items
Revises: 0003_expand_text_fields
Create Date: 2025-02-19
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0004_fact_tables_items"
down_revision = "0003_expand_text_fields"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "items",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("company", sa.Text(), nullable=False),
        sa.Column("canonical_sku", sa.Text(), nullable=False),
        sa.Column("sku_norm", sa.Text(), nullable=False),
        sa.Column("mfg_sku_norm", sa.Text(), nullable=True),
        sa.Column("manufacturer_norm", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("group_name", sa.Text(), nullable=True),
        sa.Column("project_label", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "company",
            "canonical_sku",
            name="uq_items_company_canonical_sku",
        ),
    )
    op.create_index(
        "ix_items_company_sku_norm",
        "items",
        ["company", "sku_norm"],
    )

    op.create_table(
        "fact_snapshot",
        sa.Column("data_date", sa.Date(), nullable=False),
        sa.Column("company", sa.Text(), nullable=False),
        sa.Column("warehouse", sa.Text(), nullable=False),
        sa.Column(
            "item_id", sa.BigInteger(), sa.ForeignKey("items.id"), nullable=False
        ),
        sa.Column("stock_qty", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "company",
            "data_date",
            "warehouse",
            "item_id",
            name="uq_fact_snapshot_key",
        ),
    )
    op.create_index(
        "ix_fact_snapshot_company_wh_item_data_date_desc",
        "fact_snapshot",
        ["company", "warehouse", "item_id", sa.text("data_date DESC")],
    )
    op.create_index(
        "ix_fact_snapshot_company_data_date_warehouse",
        "fact_snapshot",
        ["company", "data_date", "warehouse"],
    )

    op.create_table(
        "fact_delta_changes",
        sa.Column("data_date", sa.Date(), nullable=False),
        sa.Column("company", sa.Text(), nullable=False),
        sa.Column("warehouse", sa.Text(), nullable=False),
        sa.Column(
            "item_id", sa.BigInteger(), sa.ForeignKey("items.id"), nullable=False
        ),
        sa.Column("sold_qty", sa.Integer(), nullable=False),
        sa.Column("replenished_qty", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "company",
            "data_date",
            "warehouse",
            "item_id",
            name="uq_fact_delta_changes_key",
        ),
    )
    op.create_index(
        "ix_fact_delta_changes_company_wh_item_data_date_desc",
        "fact_delta_changes",
        ["company", "warehouse", "item_id", sa.text("data_date DESC")],
    )
    op.create_index(
        "ix_fact_delta_changes_company_data_date",
        "fact_delta_changes",
        ["company", "data_date"],
    )

    op.alter_column(
        "ingest_runs",
        "error_message",
        existing_type=sa.Text(),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.add_column("ingest_runs", sa.Column("rows_read", sa.Integer(), nullable=True))
    op.add_column("ingest_runs", sa.Column("rows_long", sa.Integer(), nullable=True))
    op.add_column(
        "ingest_runs", sa.Column("rows_snapshot", sa.Integer(), nullable=True)
    )
    op.add_column(
        "ingest_runs", sa.Column("rows_changes", sa.Integer(), nullable=True)
    )
    op.add_column(
        "ingest_runs", sa.Column("duration_ms", sa.Integer(), nullable=True)
    )
    op.create_unique_constraint(
        "uq_ingest_runs_company_data_date",
        "ingest_runs",
        ["company", "data_date"],
    )


def downgrade():
    op.drop_constraint(
        "uq_ingest_runs_company_data_date",
        "ingest_runs",
        type_="unique",
    )
    op.drop_column("ingest_runs", "duration_ms")
    op.drop_column("ingest_runs", "rows_changes")
    op.drop_column("ingest_runs", "rows_snapshot")
    op.drop_column("ingest_runs", "rows_long")
    op.drop_column("ingest_runs", "rows_read")

    op.drop_index(
        "ix_fact_delta_changes_company_data_date",
        table_name="fact_delta_changes",
    )
    op.drop_index(
        "ix_fact_delta_changes_company_wh_item_data_date_desc",
        table_name="fact_delta_changes",
    )
    op.drop_table("fact_delta_changes")

    op.drop_index(
        "ix_fact_snapshot_company_data_date_warehouse",
        table_name="fact_snapshot",
    )
    op.drop_index(
        "ix_fact_snapshot_company_wh_item_data_date_desc",
        table_name="fact_snapshot",
    )
    op.drop_table("fact_snapshot")

    op.drop_index("ix_items_company_sku_norm", table_name="items")
    op.drop_table("items")
