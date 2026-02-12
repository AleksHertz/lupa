"""add items name_tsv for russian fts

Revision ID: 0007_items_name_tsv_fts
Revises: 0006_drop_legacy_daily_tables
Create Date: 2026-02-12
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0007_items_name_tsv_fts"
down_revision = "0006_drop_legacy_daily_tables"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("items", sa.Column("name_tsv", sa.dialects.postgresql.TSVECTOR(), nullable=True))
    op.execute(
        """
        UPDATE items
        SET name_tsv = to_tsvector('russian', coalesce(name, ''))
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION items_name_tsv_update_trigger() RETURNS trigger AS $$
        BEGIN
          NEW.name_tsv := to_tsvector('russian', coalesce(NEW.name, ''));
          RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_items_name_tsv_update
        BEFORE INSERT OR UPDATE OF name
        ON items
        FOR EACH ROW
        EXECUTE FUNCTION items_name_tsv_update_trigger();
        """
    )
    op.create_index("ix_items_name_tsv", "items", ["name_tsv"], postgresql_using="gin")


def downgrade():
    op.drop_index("ix_items_name_tsv", table_name="items")
    op.execute("DROP TRIGGER IF EXISTS trg_items_name_tsv_update ON items;")
    op.execute("DROP FUNCTION IF EXISTS items_name_tsv_update_trigger();")
    op.drop_column("items", "name_tsv")
