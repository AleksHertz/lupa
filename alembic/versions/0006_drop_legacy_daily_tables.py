"""drop legacy daily tables

Revision ID: 0006_drop_legacy_daily_tables
Revises: 0005_ingest_runs_v2
Create Date: 2026-02-11
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0006_drop_legacy_daily_tables"
down_revision = "0005_ingest_runs_v2"
branch_labels = None
depends_on = None


def upgrade():
    # Legacy tables were already removed in production; keep revision as a no-op.
    op.execute("-- noop legacy drop already done")


def downgrade():
    # Legacy tables are intentionally not recreated during downgrade.
    pass
