import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase


class Base(DeclarativeBase):
    pass


def get_database_url() -> str:
    url = os.getenv(postgresql://postgres:XkwoRmsBLYLiynUZHPqVOxZGibLSLUJQ@postgres.railway.internal:5432/railway)
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


def create_db_engine():
    url = get_database_url()
    return create_engine(url, pool_pre_ping=True)


engine = create_db_engine()
SessionLocal = sessionmaker(bind=engine)


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
