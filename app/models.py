from datetime import datetime

from sqlalchemy import Date, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DailySnapshot(Base):
    __tablename__ = "daily_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[datetime] = mapped_column(Date, index=True)
    warehouse: Mapped[str] = mapped_column(String(100), index=True)
    sku: Mapped[str] = mapped_column(String(100), index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    nomenclature: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    stock_qty: Mapped[float] = mapped_column(Float)
    price_start_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_end_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("date", "warehouse", "sku", "manufacturer", name="uq_snapshot_key"),
        Index("ix_snapshot_date_wh_sku", "date", "warehouse", "sku"),
    )


class DailyDelta(Base):
    __tablename__ = "daily_delta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[datetime] = mapped_column(Date, index=True)
    warehouse: Mapped[str] = mapped_column(String(100), index=True)
    sku: Mapped[str] = mapped_column(String(100), index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    nomenclature: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    sold_qty: Mapped[float] = mapped_column(Float)
    replenished_qty: Mapped[float] = mapped_column(Float)
    price_start_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_end_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("date", "warehouse", "sku", "manufacturer", name="uq_delta_key"),
        Index("ix_delta_date_wh_sku", "date", "warehouse", "sku"),
    )
