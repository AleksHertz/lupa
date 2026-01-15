"""create ingest runs

Revision ID: 0003
Revises: 0002
Create Date: 2025-02-08
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
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
    op.create_index(
        "ix_ingest_runs_company",
        "ingest_runs",
        ["company"],
    )
    op.create_index(
        "ix_ingest_runs_data_date",
        "ingest_runs",
        ["data_date"],
    )
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
