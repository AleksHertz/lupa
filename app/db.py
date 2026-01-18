import logging
import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def get_database_url() -> str:
    url = (
        os.getenv("DATABASE_URL")
        or os.getenv("DATABASE_PUBLIC_URL")
        or os.getenv("LOCAL_DATABASE_URL")
    )
    if not url:
        raise RuntimeError(
            "DATABASE_URL, DATABASE_PUBLIC_URL, or LOCAL_DATABASE_URL is not set"
        )
    return url


@lru_cache
def get_engine():
    url = get_database_url()
    engine = create_engine(url, pool_pre_ping=True)
    logger.info(
        "Database engine URL: %s", engine.url.render_as_string(hide_password=True)
    )
    return engine


@lru_cache
def get_sessionmaker():
    return sessionmaker(bind=get_engine())


def get_session():
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
