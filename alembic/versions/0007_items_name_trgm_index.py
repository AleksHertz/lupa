"""enable pg_trgm and add trigram index for items.name

Revision ID: 0007_items_name_trgm_index
Revises: 0006_drop_legacy_daily_tables
Create Date: 2026-02-12
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0007_items_name_trgm_index"
down_revision = "0006_drop_legacy_daily_tables"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_items_name_trgm "
            "ON items USING gin (name gin_trgm_ops)"
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_items_name_trgm")
