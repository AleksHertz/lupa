import io
import logging
from datetime import date, timedelta
from typing import Literal

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import DailyDelta, DailySnapshot

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"warehouse", "sku", "stock_qty"}

COLUMN_ALIASES = {
    "warehouse": ["warehouse", "склад"],
    "sku": ["sku", "article", "артикул"],
    "manufacturer": ["manufacturer", "производитель"],
    "nomenclature": ["nomenclature", "номенклатура", "name", "item"],
    "stock_qty": ["stock_qty", "остаток", "stock"],
    "price": ["price", "цена"],
}


class IngestError(Exception):
    pass


def _normalize_columns(columns: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    lowered = {col.lower().strip(): col for col in columns}
    for target, variants in COLUMN_ALIASES.items():
        for variant in variants:
            key = variant.lower()
            if key in lowered:
                mapping[lowered[key]] = target
                break
    return mapping


def _validate_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapping = _normalize_columns(df.columns.tolist())
    df = df.rename(columns=mapping)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise IngestError(f"Missing required columns: {', '.join(sorted(missing))}")
    if "manufacturer" not in df.columns:
        df["manufacturer"] = None
    if "nomenclature" not in df.columns:
        df["nomenclature"] = None
    if "price" not in df.columns:
        df["price"] = None
    return df


def _aggregate_daily(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["stock_qty"] = pd.to_numeric(df["stock_qty"], errors="coerce").fillna(0.0)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.sort_index()
    keys = ["warehouse", "sku", "manufacturer"]
    aggregated = (
        df.groupby(keys, dropna=False)
        .agg(
            stock_qty=("stock_qty", "last"),
            price_start_day=("price", "first"),
            price_end_day=("price", "last"),
            nomenclature=("nomenclature", "first"),
        )
        .reset_index()
    )
    return aggregated


def _load_prev_snapshot(session: Session, prev_date: date, warehouses: list[str]) -> pd.DataFrame:
    if not warehouses:
        return pd.DataFrame(columns=["warehouse", "sku", "manufacturer", "stock_qty"])
    stmt = (
        select(
            DailySnapshot.warehouse,
            DailySnapshot.sku,
            DailySnapshot.manufacturer,
            DailySnapshot.stock_qty,
        )
        .where(DailySnapshot.date == prev_date)
        .where(DailySnapshot.warehouse.in_(warehouses))
    )
    rows = session.execute(stmt).all()
    if not rows:
        return pd.DataFrame(columns=["warehouse", "sku", "manufacturer", "stock_qty"])
    return pd.DataFrame(rows, columns=["warehouse", "sku", "manufacturer", "stock_qty"])


def _load_existing_snapshot(
    session: Session,
    upload_date: date,
    warehouses: list[str],
) -> pd.DataFrame:
    if not warehouses:
        return pd.DataFrame(
            columns=["warehouse", "sku", "manufacturer", "price_start_day"]
        )
    stmt = (
        select(
            DailySnapshot.warehouse,
            DailySnapshot.sku,
            DailySnapshot.manufacturer,
            DailySnapshot.price_start_day,
        )
        .where(DailySnapshot.date == upload_date)
        .where(DailySnapshot.warehouse.in_(warehouses))
    )
    rows = session.execute(stmt).all()
    if not rows:
        return pd.DataFrame(
            columns=["warehouse", "sku", "manufacturer", "price_start_day"]
        )
    return pd.DataFrame(
        rows, columns=["warehouse", "sku", "manufacturer", "price_start_day"]
    )


def ingest_excel(
    session: Session,
    upload_date: date,
    file_bytes: bytes,
    mode: Literal["reject", "merge", "replace"] = "reject",
) -> dict[str, int]:
    logger.info("Starting ingest for %s", upload_date)
    df = pd.read_excel(
        io.BytesIO(file_bytes),
        engine="openpyxl",
    )
    df = _validate_columns(df)
    aggregated = _aggregate_daily(df)

    warehouses = aggregated["warehouse"].dropna().unique().tolist()

    existing = _load_existing_snapshot(session, upload_date, warehouses)
    if not existing.empty and mode == "reject":
        raise IngestError(
            "Data for this date and warehouse already loaded. "
            "Use mode=merge to update or mode=replace to overwrite."
        )

    if not existing.empty and mode == "merge":
        existing = existing.dropna(subset=["price_start_day"])
        if not existing.empty:
            aggregated = aggregated.merge(
                existing,
                on=["warehouse", "sku", "manufacturer"],
                how="left",
                suffixes=("", "_existing"),
            )
            aggregated["price_start_day"] = aggregated[
                "price_start_day_existing"
            ].combine_first(aggregated["price_start_day"])
            aggregated = aggregated.drop(columns=["price_start_day_existing"])

    prev_date = upload_date - timedelta(days=1)
    prev_df = _load_prev_snapshot(session, prev_date, warehouses)

    merged = aggregated.merge(
        prev_df,
        on=["warehouse", "sku", "manufacturer"],
        how="left",
        suffixes=("", "_prev"),
    )
    merged["stock_qty_prev"] = (
        merged["stock_qty_prev"].fillna(0.0).astype(float)
    )
    merged["sold_qty"] = (merged["stock_qty_prev"] - merged["stock_qty"]).clip(
        lower=0.0
    )
    merged["replenished_qty"] = (
        merged["stock_qty"] - merged["stock_qty_prev"]
    ).clip(lower=0.0)

    snapshot_records = merged[
        [
            "warehouse",
            "sku",
            "manufacturer",
            "nomenclature",
            "stock_qty",
            "price_start_day",
            "price_end_day",
        ]
    ].to_dict("records")
    for record in snapshot_records:
        record["date"] = upload_date

    delta_records = merged[
        [
            "warehouse",
            "sku",
            "manufacturer",
            "nomenclature",
            "sold_qty",
            "replenished_qty",
            "price_start_day",
            "price_end_day",
        ]
    ].to_dict("records")
    for record in delta_records:
        record["date"] = upload_date

    if warehouses:
        session.execute(
            delete(DailySnapshot)
            .where(DailySnapshot.date == upload_date)
            .where(DailySnapshot.warehouse.in_(warehouses))
        )
        session.execute(
            delete(DailyDelta)
            .where(DailyDelta.date == upload_date)
            .where(DailyDelta.warehouse.in_(warehouses))
        )

    session.bulk_insert_mappings(DailySnapshot, snapshot_records)
    session.bulk_insert_mappings(DailyDelta, delta_records)
    session.commit()

    logger.info("Ingest complete: %s rows", len(snapshot_records))
    return {"snapshots": len(snapshot_records), "deltas": len(delta_records)}
