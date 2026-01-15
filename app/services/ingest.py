import hashlib
import io
import logging
import re
from datetime import date, datetime, timedelta
from typing import Literal

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import DailyDelta, DailySnapshot, IngestRun

logger = logging.getLogger(__name__)


def _normalize_header(value: str) -> str:
    normalized = value.strip().lower().replace("ё", "е")
    return " ".join(normalized.split())


PROJECT_GROUPS = {
    "Корея": {"Корея"},
    "Китай": {"Китай"},
}


REQUIRED_COLUMNS = {"warehouse", "sku", "stock_qty"}

COLUMN_ALIASES = {
    "warehouse": ["warehouse", "склад"],
    "sku": ["sku", "article", "артикул"],
    "manufacturer": ["manufacturer", "производитель"],
    "nomenclature": ["nomenclature", "номенклатура", "name", "item"],
    "stock_qty": ["stock_qty", "остаток", "stock"],
    "price": ["price", "цена"],
    "group": ["group", "группа"],
}

ALLIANCE_COLUMN_ALIASES = {
    "артикул": "sku",
    "наименование": "name",
    "цена": "price",
    "артикул производителя": "mfg_sku",
    "производитель": "manufacturer",
    "марка": "brand",
    "группа": "group",
    "остаток варшавка": "stock_warsawka",
    "остаток люберцы": "stock_lubertsy",
    "остаток кетчерская": "stock_ketcherskaya",
    "остаток дмитровка": "stock_dmitrovka",
}

ALLIANCE_WAREHOUSE_COLUMNS = {
    "stock_warsawka": "Варшавка",
    "stock_lubertsy": "Люберцы",
    "stock_ketcherskaya": "Кетчерская",
    "stock_dmitrovka": "Дмитровка",
}


class IngestError(Exception):
    pass


class IngestConflict(IngestError):
    pass


def date_from_filename(name: str, now: datetime) -> date | None:
    match = re.search(r"(\d{2})\.(\d{2})", name)
    if not match:
        return None
    day = int(match.group(1))
    month = int(match.group(2))
    try:
        candidate = date(now.year, month, day)
    except ValueError:
        return None
    if candidate > now.date() + timedelta(days=7):
        try:
            candidate = date(now.year - 1, month, day)
        except ValueError:
            return None
    return candidate


def _normalize_columns(columns: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    lowered = {_normalize_header(col): col for col in columns}
    for target, variants in COLUMN_ALIASES.items():
        for variant in variants:
            key = _normalize_header(variant)
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
    if "group" not in df.columns:
        df["group"] = None
    return df


def _prepare_alliance_df(df: pd.DataFrame) -> pd.DataFrame:
    normalized_columns = {col: _normalize_header(col) for col in df.columns}
    df = df.rename(columns=normalized_columns)
    df = df.rename(columns=ALLIANCE_COLUMN_ALIASES)
    if "sku" not in df.columns:
        raise IngestError("Missing required columns: sku")
    for column in ALLIANCE_WAREHOUSE_COLUMNS:
        if column not in df.columns:
            df[column] = 0
    df["source"] = "альянс"
    id_vars = [col for col in df.columns if col not in ALLIANCE_WAREHOUSE_COLUMNS]
    df = df.melt(
        id_vars=id_vars,
        value_vars=list(ALLIANCE_WAREHOUSE_COLUMNS.keys()),
        var_name="warehouse_key",
        value_name="stock_qty",
    )
    df["warehouse"] = df["warehouse_key"].map(ALLIANCE_WAREHOUSE_COLUMNS)
    df = df.drop(columns=["warehouse_key"])
    df["stock_qty"] = pd.to_numeric(df["stock_qty"], errors="coerce").fillna(0).astype(int)
    if "price" in df.columns:
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
    else:
        df["price"] = None
    df["nomenclature"] = df.get("name")
    if "manufacturer" not in df.columns:
        df["manufacturer"] = None
    if "nomenclature" not in df.columns:
        df["nomenclature"] = None
    if "group" not in df.columns:
        df["group"] = None
    return df


def _project_label_for_group(group: str | None) -> str | None:
    if group is None or pd.isna(group):
        return None
    normalized = str(group).strip()
    if normalized in PROJECT_GROUPS["Корея"]:
        return "Корея"
    if normalized in PROJECT_GROUPS["Китай"]:
        return "Китай"
    return None


def _aggregate_daily(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["stock_qty"] = pd.to_numeric(df["stock_qty"], errors="coerce").fillna(0).astype(int)
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
            group=("group", "first"),
            project_label=("project_label", "first"),
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
    source: str | None = None,
    file_name: str | None = None,
    mode: Literal["reject", "merge", "replace"] = "reject",
) -> dict[str, int]:
    normalized_source = source.strip().lower() if source else None
    company = normalized_source or "default"
    is_alliance = normalized_source == "альянс"
    if is_alliance and file_name:
        parsed_date = date_from_filename(file_name, datetime.now())
        if parsed_date is not None:
            upload_date = parsed_date

    file_hash = hashlib.sha256(file_bytes).hexdigest()
    existing_hash = session.scalar(
        select(IngestRun.id)
        .where(IngestRun.company == company)
        .where(IngestRun.file_hash == file_hash)
    )
    if existing_hash:
        raise IngestConflict("This file has already been uploaded.")

    ingest_run = IngestRun(
        company=company,
        file_name=file_name or "unknown",
        file_hash=file_hash,
        data_date=upload_date,
        status="failed",
    )
    session.add(ingest_run)
    session.commit()

    existing_date = session.scalar(
        select(IngestRun.id)
        .where(IngestRun.company == company)
        .where(IngestRun.data_date == upload_date)
        .where(IngestRun.id != ingest_run.id)
    )
    if existing_date:
        ingest_run.error_message = "Data for this date is already uploaded."
        session.commit()
        raise IngestConflict(ingest_run.error_message)

    logger.info("Starting ingest for %s", upload_date)
    try:
        df = pd.read_excel(
            io.BytesIO(file_bytes),
            engine="openpyxl",
        )
        if is_alliance:
            df = _prepare_alliance_df(df)
        else:
            df = _validate_columns(df)
        df["project_label"] = df["group"].map(_project_label_for_group)
        aggregated = _aggregate_daily(df)

        warehouses = aggregated["warehouse"].dropna().unique().tolist()

        existing = _load_existing_snapshot(session, upload_date, warehouses)
        if not existing.empty and mode == "reject":
            raise IngestConflict(
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
        if is_alliance:
            key_columns = ["warehouse", "sku", "manufacturer"]
            prev_keys = prev_df[key_columns] if not prev_df.empty else prev_df
            all_keys = pd.concat(
                [aggregated[key_columns], prev_keys],
                ignore_index=True,
            ).drop_duplicates()
            merged = all_keys.merge(aggregated, on=key_columns, how="left")
            merged["stock_qty"] = merged["stock_qty"].fillna(0).astype(int)
        else:
            merged = aggregated.copy()

        merged = merged.merge(
            prev_df,
            on=["warehouse", "sku", "manufacturer"],
            how="left",
            suffixes=("", "_prev"),
        )
        merged["stock_qty_prev"] = (
            merged["stock_qty_prev"].fillna(0.0).astype(float)
        )
        merged["sold_qty"] = (
            merged["stock_qty_prev"] - merged["stock_qty"]
        ).clip(lower=0.0)
        merged["replenished_qty"] = (
            merged["stock_qty"] - merged["stock_qty_prev"]
        ).clip(lower=0.0)

        snapshot_records = merged[
            [
                "warehouse",
                "sku",
                "manufacturer",
                "nomenclature",
                "group",
                "project_label",
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
                "group",
                "project_label",
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
        ingest_run.status = "ok"
        session.commit()

        logger.info("Ingest complete: %s rows", len(snapshot_records))
        return {"snapshots": len(snapshot_records), "deltas": len(delta_records)}
    except Exception as exc:
        session.rollback()
        existing_run = session.get(IngestRun, ingest_run.id)
        if existing_run is not None:
            existing_run.error_message = str(exc)
            session.commit()
        raise
