"""update daily tables

Revision ID: 0002
Revises: 0001
Create Date: 2025-02-08
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "daily_snapshot",
        sa.Column("source", sa.String(length=100), nullable=False, server_default=""),
    )
    op.add_column(
        "daily_delta",
        sa.Column("source", sa.String(length=100), nullable=False, server_default=""),
    )
    op.add_column(
        "daily_snapshot", sa.Column("mfg_sku", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "daily_delta", sa.Column("mfg_sku", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "daily_snapshot", sa.Column("brand", sa.String(length=100), nullable=True)
    )
    op.add_column("daily_delta", sa.Column("brand", sa.String(length=100), nullable=True))
    op.add_column(
        "daily_snapshot", sa.Column("group", sa.String(length=100), nullable=True)
    )
    op.add_column("daily_delta", sa.Column("group", sa.String(length=100), nullable=True))
    op.add_column(
        "daily_snapshot", sa.Column("project_label", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "daily_delta", sa.Column("project_label", sa.String(length=100), nullable=True)
    )
    op.drop_index("ix_daily_snapshot_nomenclature", table_name="daily_snapshot")
    op.drop_index("ix_daily_delta_nomenclature", table_name="daily_delta")
    op.alter_column("daily_snapshot", "nomenclature", new_column_name="name")
    op.alter_column("daily_delta", "nomenclature", new_column_name="name")
    op.alter_column("daily_snapshot", "source", server_default=None)
    op.alter_column("daily_delta", "source", server_default=None)

    op.drop_constraint("uq_snapshot_key", "daily_snapshot", type_="unique")
    op.drop_constraint("uq_delta_key", "daily_delta", type_="unique")
    op.create_unique_constraint(
        "uq_snapshot_key", "daily_snapshot", ["date", "source", "warehouse", "sku"]
    )
    op.create_unique_constraint(
        "uq_delta_key", "daily_delta", ["date", "source", "warehouse", "sku"]
    )

    op.drop_index("ix_snapshot_date_wh_sku", table_name="daily_snapshot")
    op.drop_index("ix_delta_date_wh_sku", table_name="daily_delta")

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
        "ix_delta_date_project_label", "daily_delta", ["date", "project_label"]
    )

    op.create_index("ix_daily_snapshot_source", "daily_snapshot", ["source"])
    op.create_index("ix_daily_delta_source", "daily_delta", ["source"])
    op.create_index("ix_daily_snapshot_mfg_sku", "daily_snapshot", ["mfg_sku"])
    op.create_index("ix_daily_delta_mfg_sku", "daily_delta", ["mfg_sku"])
    op.create_index("ix_daily_snapshot_name", "daily_snapshot", ["name"])
    op.create_index("ix_daily_delta_name", "daily_delta", ["name"])
    op.create_index("ix_daily_snapshot_brand", "daily_snapshot", ["brand"])
    op.create_index("ix_daily_delta_brand", "daily_delta", ["brand"])
    op.create_index("ix_daily_snapshot_group", "daily_snapshot", ["group"])
    op.create_index("ix_daily_delta_group", "daily_delta", ["group"])
    op.create_index(
        "ix_daily_snapshot_project_label", "daily_snapshot", ["project_label"]
    )
    op.create_index(
        "ix_daily_delta_project_label", "daily_delta", ["project_label"]
    )


def downgrade():
    op.drop_index("ix_daily_delta_project_label", table_name="daily_delta")
    op.drop_index("ix_daily_snapshot_project_label", table_name="daily_snapshot")
    op.drop_index("ix_daily_delta_group", table_name="daily_delta")
    op.drop_index("ix_daily_snapshot_group", table_name="daily_snapshot")
    op.drop_index("ix_daily_delta_brand", table_name="daily_delta")
    op.drop_index("ix_daily_snapshot_brand", table_name="daily_snapshot")
    op.drop_index("ix_daily_delta_name", table_name="daily_delta")
    op.drop_index("ix_daily_snapshot_name", table_name="daily_snapshot")
    op.drop_index("ix_daily_delta_mfg_sku", table_name="daily_delta")
    op.drop_index("ix_daily_snapshot_mfg_sku", table_name="daily_snapshot")
    op.drop_index("ix_daily_delta_source", table_name="daily_delta")
    op.drop_index("ix_daily_snapshot_source", table_name="daily_snapshot")

    op.drop_index("ix_delta_date_project_label", table_name="daily_delta")
    op.drop_index("ix_delta_source_wh_sku_date", table_name="daily_delta")
    op.drop_index("ix_delta_date_source_wh_sku", table_name="daily_delta")
    op.drop_index("ix_snapshot_date_source_wh_sku", table_name="daily_snapshot")

    op.drop_constraint("uq_delta_key", "daily_delta", type_="unique")
    op.drop_constraint("uq_snapshot_key", "daily_snapshot", type_="unique")
    op.create_unique_constraint(
        "uq_delta_key", "daily_delta", ["date", "warehouse", "sku", "manufacturer"]
    )
    op.create_unique_constraint(
        "uq_snapshot_key", "daily_snapshot", ["date", "warehouse", "sku", "manufacturer"]
    )

    op.create_index(
        "ix_delta_date_wh_sku", "daily_delta", ["date", "warehouse", "sku"]
    )
    op.create_index(
        "ix_snapshot_date_wh_sku", "daily_snapshot", ["date", "warehouse", "sku"]
    )

    op.alter_column("daily_delta", "name", new_column_name="nomenclature")
    op.alter_column("daily_snapshot", "name", new_column_name="nomenclature")
    op.create_index(
        "ix_daily_delta_nomenclature", "daily_delta", ["nomenclature"]
    )
    op.create_index(
        "ix_daily_snapshot_nomenclature", "daily_snapshot", ["nomenclature"]
    )

    op.drop_column("daily_delta", "project_label")
    op.drop_column("daily_snapshot", "project_label")
    op.drop_column("daily_delta", "group")
    op.drop_column("daily_snapshot", "group")
    op.drop_column("daily_delta", "brand")
    op.drop_column("daily_snapshot", "brand")
    op.drop_column("daily_delta", "mfg_sku")
    op.drop_column("daily_snapshot", "mfg_sku")
    op.drop_column("daily_delta", "source")
    op.drop_column("daily_snapshot", "source")
