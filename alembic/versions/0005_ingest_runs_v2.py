"""add ingest runs v2

Revision ID: 0005_ingest_runs_v2
Revises: 0004_fact_tables_items
Create Date: 2025-02-19
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0005_ingest_runs_v2"
down_revision = "0004_fact_tables_items"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ingest_runs_v2",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("company", sa.Text(), nullable=False),
        sa.Column("data_date", sa.Date(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("file_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("rows_read", sa.Integer(), nullable=True),
        sa.Column("rows_long", sa.Integer(), nullable=True),
        sa.Column("rows_snapshot", sa.Integer(), nullable=True),
        sa.Column("rows_changes", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.UniqueConstraint(
            "company",
            "data_date",
            name="uq_ingest_runs_v2_company_data_date",
        ),
    )
    op.create_index(
        "ix_ingest_runs_v2_company_data_date_desc",
        "ingest_runs_v2",
        ["company", sa.text("data_date DESC")],
    )


def downgrade():
    op.drop_index(
        "ix_ingest_runs_v2_company_data_date_desc",
        table_name="ingest_runs_v2",
    )
    op.drop_table("ingest_runs_v2")
