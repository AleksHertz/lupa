import os
import logging
from logging.config import fileConfig

import sqlalchemy as sa
from sqlalchemy import engine_from_config, pool
from alembic import context

from app.db import Base
from app import models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")


def get_url():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


def run_migrations_offline():
    logger.info("Running migrations to head (offline mode)...")
    context.configure(
        url=get_url(),
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=False,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    alembic_echo = os.getenv("ALEMBIC_ECHO", "0") == "1"
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        url=get_url(),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        echo=alembic_echo,
    )

    with connectable.connect() as connection:
        current_rev = "unknown"
        try:
            current_rev = connection.execute(
                sa.text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
            current_rev = current_rev or "<empty>"
        except Exception as exc:
            current_rev = f"unavailable ({exc.__class__.__name__})"

        logger.info("Running migrations to head...")
        logger.info("Current rev: %s", current_rev)
        logger.info("SQL echo enabled: %s", alembic_echo)

        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            compare_type=True,
            render_as_batch=False,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
