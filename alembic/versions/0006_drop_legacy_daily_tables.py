"""drop legacy daily tables

Revision ID: 0006_drop_legacy_daily_tables
Revises: 0005_ingest_runs_v2
Create Date: 2026-02-11
"""

import logging

from alembic import op

# revision identifiers, used by Alembic.
revision = "0006_drop_legacy_daily_tables"
down_revision = "0005_ingest_runs_v2"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade():
    logger.info("Applying migration 0006_drop_legacy_daily_tables")
    logger.info("Setting lock_timeout=5s and statement_timeout=5min for legacy table drops")
    op.execute("SET lock_timeout = '5s';")
    op.execute("SET statement_timeout = '5min';")

    logger.info("Dropping legacy table daily_snapshot (if exists)")
    op.execute("DROP TABLE IF EXISTS daily_snapshot CASCADE;")
    logger.info("Dropping legacy table daily_delta (if exists)")
    op.execute("DROP TABLE IF EXISTS daily_delta CASCADE;")


def downgrade():
    # Legacy tables are intentionally not recreated during downgrade.
    pass
