"""expand text fields for ingest

Revision ID: 0003_expand_text_fields
Revises: 0002_price_single_column
Create Date: 2025-02-19
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003_expand_text_fields"
down_revision = "0002_price_single_column"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "daily_snapshot",
        "sku",
        existing_type=sa.String(length=100),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "daily_snapshot",
        "mfg_sku",
        existing_type=sa.String(length=100),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "daily_snapshot",
        "manufacturer",
        existing_type=sa.String(length=100),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "daily_snapshot",
        "name",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "daily_snapshot",
        "brand",
        existing_type=sa.String(length=100),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "daily_snapshot",
        "group_name",
        existing_type=sa.String(length=100),
        type_=sa.Text(),
        existing_nullable=True,
    )

    op.alter_column(
        "daily_delta",
        "sku",
        existing_type=sa.String(length=100),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "daily_delta",
        "mfg_sku",
        existing_type=sa.String(length=100),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "daily_delta",
        "manufacturer",
        existing_type=sa.String(length=100),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "daily_delta",
        "name",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "daily_delta",
        "brand",
        existing_type=sa.String(length=100),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "daily_delta",
        "group_name",
        existing_type=sa.String(length=100),
        type_=sa.Text(),
        existing_nullable=True,
    )

    op.alter_column(
        "ingest_runs",
        "file_name",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "ingest_runs",
        "error_message",
        existing_type=sa.String(length=500),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade():
    op.alter_column(
        "ingest_runs",
        "error_message",
        existing_type=sa.Text(),
        type_=sa.String(length=500),
        existing_nullable=True,
    )
    op.alter_column(
        "ingest_runs",
        "file_name",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=False,
    )

    op.alter_column(
        "daily_delta",
        "group_name",
        existing_type=sa.Text(),
        type_=sa.String(length=100),
        existing_nullable=True,
    )
    op.alter_column(
        "daily_delta",
        "brand",
        existing_type=sa.Text(),
        type_=sa.String(length=100),
        existing_nullable=True,
    )
    op.alter_column(
        "daily_delta",
        "name",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "daily_delta",
        "manufacturer",
        existing_type=sa.Text(),
        type_=sa.String(length=100),
        existing_nullable=True,
    )
    op.alter_column(
        "daily_delta",
        "mfg_sku",
        existing_type=sa.Text(),
        type_=sa.String(length=100),
        existing_nullable=True,
    )
    op.alter_column(
        "daily_delta",
        "sku",
        existing_type=sa.Text(),
        type_=sa.String(length=100),
        existing_nullable=False,
    )

    op.alter_column(
        "daily_snapshot",
        "group_name",
        existing_type=sa.Text(),
        type_=sa.String(length=100),
        existing_nullable=True,
    )
    op.alter_column(
        "daily_snapshot",
        "brand",
        existing_type=sa.Text(),
        type_=sa.String(length=100),
        existing_nullable=True,
    )
    op.alter_column(
        "daily_snapshot",
        "name",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "daily_snapshot",
        "manufacturer",
        existing_type=sa.Text(),
        type_=sa.String(length=100),
        existing_nullable=True,
    )
    op.alter_column(
        "daily_snapshot",
        "mfg_sku",
        existing_type=sa.Text(),
        type_=sa.String(length=100),
        existing_nullable=True,
    )
    op.alter_column(
        "daily_snapshot",
        "sku",
        existing_type=sa.Text(),
        type_=sa.String(length=100),
        existing_nullable=False,
    )
