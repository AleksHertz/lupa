"""drop legacy daily tables

Revision ID: 0006_drop_legacy_daily_tables
Revises: 0005_ingest_runs_v2
Create Date: 2025-02-19
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0006_drop_legacy_daily_tables"
down_revision = "0005_ingest_runs_v2"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP TABLE IF EXISTS daily_snapshot CASCADE;")
    op.execute("DROP TABLE IF EXISTS daily_delta CASCADE;")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_items_group_name ON items (group_name);"
    )



def downgrade():
    # No-op: legacy tables were dropped and the index addition is non-destructive.
    pass
