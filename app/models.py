from datetime import datetime

from sqlalchemy import (
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    desc,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DailySnapshot(Base):
    __tablename__ = "daily_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data_date: Mapped[datetime] = mapped_column(Date, index=True)
    company: Mapped[str] = mapped_column(String(100), index=True)
    warehouse: Mapped[str] = mapped_column(String(100), index=True)
    sku: Mapped[str] = mapped_column(Text, index=True)
    mfg_sku: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    manufacturer: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    brand: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    group_name: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    project_label: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    stock_qty: Mapped[int] = mapped_column(Integer)
    price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "data_date", "company", "warehouse", "sku", name="uq_snapshot_key"
        ),
        Index(
            "ix_snapshot_company_wh_sku_data_date_desc",
            "company",
            "warehouse",
            "sku",
            desc("data_date"),
        ),
        Index(
            "ix_snapshot_company_data_date_project_label",
            "company",
            "data_date",
            "project_label",
        ),
    )


class DailyDelta(Base):
    __tablename__ = "daily_delta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data_date: Mapped[datetime] = mapped_column(Date, index=True)
    company: Mapped[str] = mapped_column(String(100), index=True)
    warehouse: Mapped[str] = mapped_column(String(100), index=True)
    sku: Mapped[str] = mapped_column(Text, index=True)
    mfg_sku: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    manufacturer: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    brand: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    group_name: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    project_label: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    stock_qty: Mapped[int] = mapped_column(Integer)
    sold_qty: Mapped[int] = mapped_column(Integer)
    replenished_qty: Mapped[int] = mapped_column(Integer)
    price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("data_date", "company", "warehouse", "sku", name="uq_delta_key"),
        Index(
            "ix_delta_company_wh_sku_data_date_desc",
            "company",
            "warehouse",
            "sku",
            desc("data_date"),
        ),
        Index(
            "ix_delta_company_data_date_project_label",
            "company",
            "data_date",
            "project_label",
        ),
    )


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company: Mapped[str] = mapped_column(String(100), index=True)
    file_name: Mapped[str] = mapped_column(Text)
    file_hash: Mapped[str] = mapped_column(String(64))
    data_date: Mapped[datetime] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_ingest_runs_company_data_date", "company", "data_date"),
        UniqueConstraint(
            "company",
            "file_hash",
            name="uq_ingest_runs_company_file_hash",
        ),
    )
