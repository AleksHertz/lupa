from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    desc,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company: Mapped[str] = mapped_column(Text)
    canonical_sku: Mapped[str] = mapped_column(Text)
    sku_norm: Mapped[str] = mapped_column(Text)
    mfg_sku_norm: Mapped[str | None] = mapped_column(Text, nullable=True)
    manufacturer_norm: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(Text, nullable=True)
    group_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint(
            "company",
            "canonical_sku",
            name="uq_items_company_canonical_sku",
        ),
        Index(
            "ix_items_company_sku_norm",
            "company",
            "sku_norm",
        ),
    )


class FactSnapshot(Base):
    __tablename__ = "fact_snapshot"

    data_date: Mapped[datetime] = mapped_column(Date, primary_key=True)
    company: Mapped[str] = mapped_column(Text, primary_key=True)
    warehouse: Mapped[str] = mapped_column(Text, primary_key=True)
    item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("items.id"), primary_key=True
    )
    stock_qty: Mapped[int] = mapped_column(Integer)
    price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint(
            "company",
            "data_date",
            "warehouse",
            "item_id",
            name="uq_fact_snapshot_key",
        ),
        Index(
            "ix_fact_snapshot_company_wh_item_data_date_desc",
            "company",
            "warehouse",
            "item_id",
            desc("data_date"),
        ),
        Index(
            "ix_fact_snapshot_company_data_date_warehouse",
            "company",
            "data_date",
            "warehouse",
        ),
    )


class FactDeltaChange(Base):
    __tablename__ = "fact_delta_changes"

    data_date: Mapped[datetime] = mapped_column(Date, primary_key=True)
    company: Mapped[str] = mapped_column(Text, primary_key=True)
    warehouse: Mapped[str] = mapped_column(Text, primary_key=True)
    item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("items.id"), primary_key=True
    )
    sold_qty: Mapped[int] = mapped_column(Integer)
    replenished_qty: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint(
            "company",
            "data_date",
            "warehouse",
            "item_id",
            name="uq_fact_delta_changes_key",
        ),
        Index(
            "ix_fact_delta_changes_company_wh_item_data_date_desc",
            "company",
            "warehouse",
            "item_id",
            desc("data_date"),
        ),
        Index(
            "ix_fact_delta_changes_company_data_date",
            "company",
            "data_date",
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
    rows_read: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_long: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_changes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_ingest_runs_company_data_date", "company", "data_date"),
        UniqueConstraint(
            "company",
            "data_date",
            name="uq_ingest_runs_company_data_date",
        ),
        UniqueConstraint(
            "company",
            "file_hash",
            name="uq_ingest_runs_company_file_hash",
        ),
    )
