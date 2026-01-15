from datetime import datetime

from sqlalchemy import Date, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DailySnapshot(Base):
    __tablename__ = "daily_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[datetime] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(100), index=True)
    warehouse: Mapped[str] = mapped_column(String(100), index=True)
    sku: Mapped[str] = mapped_column(String(100), index=True)
    mfg_sku: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    group: Mapped[str | None] = mapped_column("group", String(100), nullable=True, index=True)
    project_label: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    stock_qty: Mapped[float] = mapped_column(Float)
    price_start_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_end_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("date", "source", "warehouse", "sku", name="uq_snapshot_key"),
        Index("ix_snapshot_date_source_wh_sku", "date", "source", "warehouse", "sku"),
    )


class DailyDelta(Base):
    __tablename__ = "daily_delta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[datetime] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(100), index=True)
    warehouse: Mapped[str] = mapped_column(String(100), index=True)
    sku: Mapped[str] = mapped_column(String(100), index=True)
    mfg_sku: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    group: Mapped[str | None] = mapped_column("group", String(100), nullable=True, index=True)
    project_label: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    sold_qty: Mapped[float] = mapped_column(Float)
    replenished_qty: Mapped[float] = mapped_column(Float)
    price_start_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_end_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("date", "source", "warehouse", "sku", name="uq_delta_key"),
        Index("ix_delta_date_source_wh_sku", "date", "source", "warehouse", "sku"),
        Index("ix_delta_source_wh_sku_date", "source", "warehouse", "sku", "date"),
        Index("ix_delta_date_project_label", "date", "project_label"),
    )


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company: Mapped[str] = mapped_column(String(100), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_hash: Mapped[str] = mapped_column(String(64))
    data_date: Mapped[datetime] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        Index("ix_ingest_runs_company_data_date", "company", "data_date"),
        UniqueConstraint(
            "company",
            "file_hash",
            name="uq_ingest_runs_company_file_hash",
        ),
    )
