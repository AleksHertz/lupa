import hashlib
import io
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Literal

import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import FactDeltaChange, FactSnapshot, IngestRun, Item

logger = logging.getLogger(__name__)
_BULK_BATCH_SIZE = 10000


def _normalize_header(value: str) -> str:
    normalized = value.strip().lower().replace("ё", "е")
    return " ".join(normalized.split())


def _normalize_item_value(value: str | None) -> str | None:
    if value is None or pd.isna(value):
        return None
    normalized = re.sub(r"\s+", " ", str(value).strip().lower())
    return normalized or None


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
    "group_name": ["group", "группа"],
}

ALLIANCE_COLUMN_ALIASES = {
    "артикул": "sku",
    "наименование": "name",
    "цена": "price",
    "артикул производителя": "mfg_sku",
    "производитель": "manufacturer",
    "марка": "brand",
    "группа": "group_name",
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
    def __init__(self, message: str, report: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.report = report


class IngestConflict(IngestError):
    pass


class IngestPersistenceError(IngestError):
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
    return {col: _normalize_header(col) for col in columns}


def _apply_column_aliases(
    normalized_columns: list[str],
    aliases: dict[str, list[str]],
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    lowered = {_normalize_header(col): col for col in normalized_columns}
    for target, variants in aliases.items():
        for variant in variants:
            key = _normalize_header(variant)
            if key in lowered:
                mapping[lowered[key]] = target
                break
    return mapping


def _init_validation_report(
    df: pd.DataFrame, normalized_mapping: dict[str, str]
) -> dict[str, Any]:
    return {
        "rows_read": len(df),
        "rows_dropped": 0,
        "normalized_mapping": normalized_mapping,
        "recognized_columns": [],
        "warehouse_stats": [],
        "errors": [],
        "warnings": [],
    }


def _add_validation_error(
    report: dict[str, Any],
    message: str,
    row: int | None = None,
    column: str | None = None,
) -> None:
    entry: dict[str, Any] = {"message": message}
    if row is not None:
        entry["row"] = int(row)
    if column is not None:
        entry["column"] = column
    report["errors"].append(entry)


def _add_validation_warning(report: dict[str, Any], message: str) -> None:
    report["warnings"].append({"message": message})


def _coerce_text_column(df: pd.DataFrame, column: str) -> pd.Series:
    series = df[column].fillna("").astype(str).str.strip()
    return series.replace("", None)


def _coerce_price_column(
    df: pd.DataFrame, report: dict[str, Any], column: str = "price"
) -> pd.Series:
    raw = df[column]
    numeric = pd.to_numeric(raw, errors="coerce")
    raw_str = raw.fillna("").astype(str).str.strip()
    invalid = raw_str.eq("") | numeric.isna()
    if invalid.any():
        examples = [
            {"row": int(idx), "value": raw.loc[idx]}
            for idx in raw[invalid].index[:5]
        ]
        report["errors"].append(
            {
                "type": "invalid_price",
                "message": "Цена должна быть числом.",
                "column": column,
                "count": int(invalid.sum()),
                "examples": examples,
            }
        )
    return numeric


def _coerce_stock_column(
    df: pd.DataFrame, report: dict[str, Any], column: str
) -> pd.Series:
    raw = df[column]
    numeric = pd.to_numeric(raw, errors="coerce").fillna(0)
    negative = numeric < 0
    if negative.any():
        examples = [
            {"row": int(idx), "value": raw.loc[idx]}
            for idx in numeric[negative].index[:5]
        ]
        report["errors"].append(
            {
                "type": "negative_stock",
                "message": "Остаток не может быть отрицательным.",
                "column": column,
                "count": int(negative.sum()),
                "examples": examples,
            }
        )
    return numeric.astype(int)


def _validate_alliance_df(
    df: pd.DataFrame, report: dict[str, Any]
) -> pd.DataFrame:
    df = df.rename(columns=ALLIANCE_COLUMN_ALIASES)
    required = {"sku", "name", "price", "manufacturer", "brand", "group_name"}
    missing = required - set(df.columns)
    if missing:
        expected_columns = ", ".join(sorted(required))
        found_columns = ", ".join(df.columns[:30])
        error_report = {
            **report,
            "expected_columns": sorted(required),
            "missing_columns": sorted(missing),
            "found_columns": list(df.columns[:30]),
            "normalized_mapping": report["normalized_mapping"],
            "alias_mapping": ALLIANCE_COLUMN_ALIASES,
        }
        raise IngestError(
            "Не найдены обязательные колонки. "
            f"Ожидались: {expected_columns}. "
            f"Найдены: {found_columns}.",
            report=error_report,
        )
    warehouse_columns = list(ALLIANCE_WAREHOUSE_COLUMNS.keys())
    for column in warehouse_columns:
        if column not in df.columns:
            df[column] = 0
            warehouse_label = ALLIANCE_WAREHOUSE_COLUMNS[column]
            _add_validation_warning(
                report,
                f"Отсутствует складская колонка 'Остаток {warehouse_label}', "
                "заполнено нулями.",
            )

    df["sku"] = _coerce_text_column(df, "sku")
    df["name"] = _coerce_text_column(df, "name")
    df["group_name"] = _coerce_text_column(df, "group_name")
    for optional in ("manufacturer", "brand", "mfg_sku"):
        if optional in df.columns:
            df[optional] = _coerce_text_column(df, optional)
        else:
            df[optional] = None

    sku_missing = df["sku"].isna()
    mfg_missing = df["mfg_sku"].isna()
    empty_sku_and_mfg = sku_missing & mfg_missing
    if empty_sku_and_mfg.any():
        for idx in df[empty_sku_and_mfg].index:
            _add_validation_warning(
                report,
                f"Пустые sku/mfg_sku в строке {int(idx)}. Строка удалена.",
            )
        report["rows_dropped"] += int(empty_sku_and_mfg.sum())
        df = df.loc[~empty_sku_and_mfg].copy()

    df.loc[df["mfg_sku"].isna(), "mfg_sku"] = df["sku"]
    df.loc[df["sku"].isna(), "sku"] = df["mfg_sku"]

    df["price"] = _coerce_price_column(df, report, column="price")
    report["recognized_columns"] = sorted(df.columns)
    items = len(df)
    rows_long = items * len(warehouse_columns)
    logger.info(
        "Alliance ingest stats: rows_read=%s items=%s rows_long=%s",
        report["rows_read"],
        items,
        rows_long,
    )

    id_vars = [col for col in df.columns if col not in warehouse_columns]
    df = df.melt(
        id_vars=id_vars,
        value_vars=warehouse_columns,
        var_name="warehouse_key",
        value_name="stock_qty",
    )
    logger.info("Wide->Long produced rows: %s", len(df))
    df["stock_qty"] = _coerce_stock_column(df, report, column="stock_qty")
    df["warehouse"] = df["warehouse_key"].map(ALLIANCE_WAREHOUSE_COLUMNS)
    df = df.drop(columns=["warehouse_key"])
    df["company"] = "alliance"
    df = df[
        [
            "company",
            "warehouse",
            "sku",
            "mfg_sku",
            "name",
            "manufacturer",
            "brand",
            "group_name",
            "price",
            "stock_qty",
        ]
    ]
    report["recognized_columns"] = list(df.columns)
    report["warehouse_stats"] = (
        df.groupby("warehouse", dropna=False)
        .agg(rows=("stock_qty", "size"), total_stock=("stock_qty", "sum"))
        .reset_index()
        .to_dict("records")
    )
    return df


def _validate_default_df(
    df: pd.DataFrame, report: dict[str, Any]
) -> pd.DataFrame:
    mapping = _apply_column_aliases(df.columns.tolist(), COLUMN_ALIASES)
    df = df.rename(columns=mapping)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        error_report = {
            **report,
            "expected_columns": sorted(REQUIRED_COLUMNS),
            "missing_columns": sorted(missing),
            "found_columns": list(df.columns[:30]),
            "normalized_mapping": report["normalized_mapping"],
            "alias_mapping": mapping,
        }
        raise IngestError(
            f"Не найдены обязательные колонки: {', '.join(sorted(missing))}.",
            report=error_report,
        )
    has_price = "price" in df.columns
    if "manufacturer" not in df.columns:
        df["manufacturer"] = None
    if "nomenclature" not in df.columns:
        df["nomenclature"] = None
    if "price" not in df.columns:
        df["price"] = None
    if "group_name" not in df.columns:
        df["group_name"] = None

    df["sku"] = _coerce_text_column(df, "sku")
    for column in ("manufacturer", "nomenclature", "group_name"):
        df[column] = _coerce_text_column(df, column)
    empty_sku = df["sku"].isna()
    if empty_sku.any():
        for idx in df[empty_sku].index:
            _add_validation_warning(
                report,
                f"Пустой артикул в строке {int(idx)}. Строка удалена.",
            )
        report["rows_dropped"] += int(empty_sku.sum())
        df = df.loc[~empty_sku].copy()

    df["stock_qty"] = _coerce_stock_column(df, report, column="stock_qty")
    if has_price:
        df["price"] = _coerce_price_column(df, report, column="price")

    report["recognized_columns"] = sorted(df.columns)
    return df


def validate_ingest_df(
    df: pd.DataFrame, file_name: str | None, company: str | None
) -> tuple[pd.DataFrame, dict[str, Any]]:
    normalized_mapping = _normalize_columns(df.columns.tolist())
    df = df.rename(columns=normalized_mapping)
    report = _init_validation_report(df, normalized_mapping)
    normalized_company = company.strip().lower() if company else None
    is_alliance = normalized_company in {"alliance", "альянс"} or normalized_company is None
    if is_alliance:
        df = _validate_alliance_df(df, report)
    else:
        df = _validate_default_df(df, report)
    return df, report


def _project_label_for_group(group_name: str | None) -> str | None:
    if group_name is None or pd.isna(group_name):
        return None
    normalized = str(group_name).strip()
    if normalized in PROJECT_GROUPS["Корея"]:
        return "Корея"
    if normalized in PROJECT_GROUPS["Китай"]:
        return "Китай"
    return None


def _chunk_records(records: list[dict[str, Any]], batch_size: int) -> list[list[dict[str, Any]]]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    return [records[idx : idx + batch_size] for idx in range(0, len(records), batch_size)]


def _insert_batches(
    session: Session,
    model: type[FactSnapshot] | type[FactDeltaChange],
    records: list[dict[str, Any]],
) -> None:
    if not records:
        return
    table = model.__table__
    insert_stmt = table.insert()
    for batch in _chunk_records(records, _BULK_BATCH_SIZE):
        session.execute(insert_stmt, batch)


def _upsert_items(session: Session, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    table = Item.__table__
    insert_stmt = insert(table)
    update_columns = [
        "manufacturer_norm",
        "name",
        "brand",
        "group_name",
        "project_label",
        "updated_at",
    ]
    stmt = insert_stmt.on_conflict_do_update(
        index_elements=["company", "canonical_sku"],
        set_={
            column: (
                func.now() if column == "updated_at" else getattr(insert_stmt.excluded, column)
            )
            for column in update_columns
        },
    )
    for batch in _chunk_records(records, _BULK_BATCH_SIZE):
        session.execute(stmt, batch)


def _load_item_map(session: Session, company: str, skus: list[str]) -> dict[str, int]:
    if not skus:
        return {}
    stmt = (
        select(Item.id, Item.canonical_sku)
        .where(Item.company == company)
        .where(Item.canonical_sku.in_(skus))
    )
    rows = session.execute(stmt).all()
    return {row.canonical_sku: row.id for row in rows}


def _aggregate_daily(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "nomenclature" not in df.columns and "name" in df.columns:
        df["nomenclature"] = df["name"]
    df["stock_qty"] = pd.to_numeric(df["stock_qty"], errors="coerce").fillna(0).astype(int)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.sort_index()
    keys = ["warehouse", "sku", "manufacturer"]
    aggregations: dict[str, tuple[str, str]] = {
        "stock_qty": ("stock_qty", "last"),
        "price": ("price", "last"),
        "nomenclature": ("nomenclature", "first"),
        "group_name": ("group_name", "first"),
        "project_label": ("project_label", "first"),
    }
    if "mfg_sku" in df.columns:
        aggregations["mfg_sku"] = ("mfg_sku", "first")
    if "brand" in df.columns:
        aggregations["brand"] = ("brand", "first")
    aggregated = df.groupby(keys, dropna=False).agg(**aggregations).reset_index()
    return aggregated


def _qa_top_rows(
    merged: pd.DataFrame, qty_column: str, limit: int = 5
) -> list[dict[str, Any]]:
    if merged.empty or qty_column not in merged.columns:
        return []
    subset = merged.loc[merged[qty_column] > 0]
    if subset.empty:
        return []
    columns = [
        column
        for column in (
            "warehouse",
            "sku",
            "manufacturer",
            "stock_qty_prev",
            "stock_qty",
            "sold_qty",
            "replenished_qty",
        )
        if column in subset.columns
    ]
    return (
        subset.sort_values(qty_column, ascending=False)
        .head(limit)[columns]
        .to_dict("records")
    )


def _build_qa_report(merged: pd.DataFrame) -> dict[str, Any]:
    return {
        "rows": len(merged),
        "sold_rows": int((merged["sold_qty"] > 0).sum()),
        "replenished_rows": int((merged["replenished_qty"] > 0).sum()),
        "top_sold": _qa_top_rows(merged, "sold_qty"),
        "top_replenished": _qa_top_rows(merged, "replenished_qty"),
    }


def _load_prev_snapshot(
    session: Session,
    company: str,
    prev_date: date,
    warehouses: list[str],
) -> pd.DataFrame:
    if not warehouses:
        return pd.DataFrame(columns=["warehouse", "sku", "manufacturer", "stock_qty"])
    stmt = (
        select(
            FactSnapshot.warehouse,
            Item.canonical_sku,
            Item.manufacturer_norm,
            FactSnapshot.stock_qty,
        )
        .join(Item, Item.id == FactSnapshot.item_id)
        .where(FactSnapshot.company == company)
        .where(FactSnapshot.data_date == prev_date)
        .where(FactSnapshot.warehouse.in_(warehouses))
    )
    rows = session.execute(stmt).all()
    if not rows:
        return pd.DataFrame(columns=["warehouse", "sku", "manufacturer", "stock_qty"])
    return pd.DataFrame(
        rows, columns=["warehouse", "sku", "manufacturer", "stock_qty"]
    )


def _load_existing_snapshot(
    session: Session,
    company: str,
    upload_date: date,
    warehouses: list[str],
) -> pd.DataFrame:
    if not warehouses:
        return pd.DataFrame(columns=["warehouse", "sku", "manufacturer", "price"])
    stmt = (
        select(
            FactSnapshot.warehouse,
            Item.canonical_sku,
            Item.manufacturer_norm,
            FactSnapshot.price,
        )
        .join(Item, Item.id == FactSnapshot.item_id)
        .where(FactSnapshot.company == company)
        .where(FactSnapshot.data_date == upload_date)
        .where(FactSnapshot.warehouse.in_(warehouses))
    )
    rows = session.execute(stmt).all()
    if not rows:
        return pd.DataFrame(columns=["warehouse", "sku", "manufacturer", "price"])
    return pd.DataFrame(rows, columns=["warehouse", "sku", "manufacturer", "price"])


def _load_existing_snapshot_map(
    session: Session,
    company: str,
    upload_date: date,
) -> dict[tuple[str, str, str | None], dict[str, object]]:
    stmt = (
        select(
            FactSnapshot.item_id,
            FactSnapshot.warehouse,
            Item.canonical_sku,
            Item.manufacturer_norm,
            FactSnapshot.price,
        )
        .join(Item, Item.id == FactSnapshot.item_id)
        .where(FactSnapshot.company == company)
        .where(FactSnapshot.data_date == upload_date)
    )
    rows = session.execute(stmt).all()
    return {
        (row.warehouse, row.canonical_sku, row.manufacturer_norm): {
            "item_id": row.item_id,
            "price": row.price,
        }
        for row in rows
    }


def _load_existing_delta_map(
    session: Session,
    company: str,
    upload_date: date,
) -> dict[tuple[str, str, str | None], dict[str, object]]:
    stmt = (
        select(
            FactDeltaChange.item_id,
            FactDeltaChange.warehouse,
            Item.canonical_sku,
            Item.manufacturer_norm,
        )
        .join(Item, Item.id == FactDeltaChange.item_id)
        .where(FactDeltaChange.company == company)
        .where(FactDeltaChange.data_date == upload_date)
    )
    rows = session.execute(stmt).all()
    return {
        (row.warehouse, row.canonical_sku, row.manufacturer_norm): {"item_id": row.item_id}
        for row in rows
    }


def ingest_excel(
    session: Session,
    upload_date: date,
    file_bytes: bytes,
    company: str | None = None,
    file_name: str | None = None,
    mode: Literal["reject", "merge", "replace"] = "reject",
    dry_run: bool = False,
) -> dict[str, object]:
    normalized_company = company.strip().lower() if company else None
    company = normalized_company or "default"
    is_alliance = normalized_company == "альянс"
    if is_alliance and file_name:
        parsed_date = date_from_filename(file_name, datetime.now())
        if parsed_date is not None:
            upload_date = parsed_date

    file_hash = hashlib.sha256(file_bytes).hexdigest()
    ingest_run_id: int | None = None
    ingest_run_payload: dict[str, object] | None = None
    started_at = datetime.utcnow()
    try:
        logger.info("Starting ingest for %s", upload_date)
        df = pd.read_excel(
            io.BytesIO(file_bytes),
            engine="openpyxl",
        )
        df, validation_report = validate_ingest_df(
            df=df, file_name=file_name, company=company
        )
        logger.info(
            "Recognized columns mapping: %s",
            validation_report["normalized_mapping"],
        )
        if validation_report["errors"]:
            raise IngestError(
                "Файл содержит ошибки в данных. Проверьте отчет.",
                report=validation_report,
            )
        df["sku_norm"] = df["sku"].map(_normalize_item_value)
        if "manufacturer" in df.columns:
            df["manufacturer"] = df["manufacturer"].map(_normalize_item_value)
        if "mfg_sku" in df.columns:
            df["mfg_sku_norm"] = df["mfg_sku"].map(_normalize_item_value)
        else:
            df["mfg_sku_norm"] = None
        df.loc[df["mfg_sku_norm"].isna(), "mfg_sku_norm"] = df["sku_norm"]
        df.loc[df["sku_norm"].isna(), "sku_norm"] = df["mfg_sku_norm"]
        df["canonical_sku"] = df["mfg_sku_norm"].where(
            df["mfg_sku_norm"].notna(), df["sku_norm"]
        )
        empty_canonical = df["canonical_sku"].isna()
        if empty_canonical.any():
            dropped = int(empty_canonical.sum())
            validation_report["rows_dropped"] += dropped
            logger.info(
                "Dropping rows with empty canonical_sku after normalization: %s",
                dropped,
            )
            df = df.loc[~empty_canonical].copy()
        rows_long = len(df)
        dup_count = int(df.duplicated(subset=["warehouse", "canonical_sku"]).sum())
        logger.info("Duplicate canonical_sku rows detected: %s", dup_count)
        df = df.sort_index().drop_duplicates(
            subset=["warehouse", "canonical_sku"], keep="last"
        )
        logger.info("Rows after canonical_sku dedupe: %s", len(df))
        df["sku"] = df["canonical_sku"]
        df["project_label"] = df["group_name"].map(_project_label_for_group)
        aggregated = _aggregate_daily(df)

        warehouses = aggregated["warehouse"].dropna().unique().tolist()

        existing_snapshot_date = session.scalar(
            select(FactSnapshot.item_id)
            .where(FactSnapshot.company == company)
            .where(FactSnapshot.data_date == upload_date)
        )
        if existing_snapshot_date and mode != "replace":
            raise IngestConflict(
                "Данные за эту дату уже загружены. "
                "Передайте replace=true, чтобы перезаписать."
            )

        existing = _load_existing_snapshot(session, company, upload_date, warehouses)
        if not existing.empty and mode == "merge":
            existing = existing.dropna(subset=["price"])
            if not existing.empty:
                aggregated = aggregated.merge(
                    existing,
                    on=["warehouse", "sku", "manufacturer"],
                    how="left",
                    suffixes=("", "_existing"),
                )
                aggregated["price"] = aggregated["price_existing"].combine_first(
                    aggregated["price"]
                )
                aggregated = aggregated.drop(columns=["price_existing"])

        merged_records = aggregated.rename(columns={"nomenclature": "name"})
        item_columns = [
            "name",
            "group_name",
            "project_label",
            "canonical_sku",
            "sku_norm",
            "mfg_sku_norm",
            "manufacturer",
        ]
        if "brand" in merged_records.columns:
            item_columns.append("brand")
        item_source = df.copy()
        if "nomenclature" in item_source.columns and "name" not in item_source.columns:
            item_source["name"] = item_source["nomenclature"]
        item_columns = [column for column in item_columns if column in item_source.columns]
        item_records = (
            item_source[item_columns]
            .sort_index()
            .drop_duplicates(subset=["canonical_sku"], keep="last")
            .to_dict("records")
        )
        for record in item_records:
            record["company"] = company
            record["canonical_sku"] = record.pop("canonical_sku")
            record["sku_norm"] = record.pop("sku_norm", None)
            record["mfg_sku_norm"] = record.pop("mfg_sku_norm", None)
            record["manufacturer_norm"] = record.pop("manufacturer", None)

        item_skus = df["canonical_sku"].dropna().unique().tolist()
        if dry_run:
            item_map = {sku: idx for idx, sku in enumerate(item_skus, start=1)}
        else:
            _upsert_items(session, item_records)
            item_map = _load_item_map(session, company, item_skus)

        snapshot_existing_map = None
        if mode == "merge":
            snapshot_existing_map = _load_existing_snapshot_map(
                session, company, upload_date
            )

        snapshot_records = []
        for record in merged_records[
            ["warehouse", "sku", "manufacturer", "stock_qty", "price"]
        ].to_dict("records"):
            item_id = item_map.get(record["sku"])
            if item_id is None:
                continue
            if snapshot_existing_map:
                key = (record["warehouse"], record["sku"], record["manufacturer"])
                existing_row = snapshot_existing_map.get(key)
                if existing_row and existing_row["price"] is not None:
                    record["price"] = existing_row["price"]
            snapshot_records.append(
                {
                    "data_date": upload_date,
                    "company": company,
                    "warehouse": record["warehouse"],
                    "item_id": item_id,
                    "stock_qty": record["stock_qty"],
                    "price": record.get("price"),
                }
            )

        prev_date = session.scalar(
            select(func.max(FactSnapshot.data_date))
            .where(FactSnapshot.company == company)
            .where(FactSnapshot.data_date < upload_date)
        )
        delta_records = []
        rows_changes = 0
        if prev_date is not None:
            prev_rows = session.execute(
                select(
                    FactSnapshot.warehouse,
                    FactSnapshot.item_id,
                    FactSnapshot.stock_qty,
                )
                .where(FactSnapshot.company == company)
                .where(FactSnapshot.data_date == prev_date)
            ).all()
            prev_df = pd.DataFrame(
                prev_rows, columns=["warehouse", "item_id", "stock_qty_prev"]
            )
            curr_df = merged_records[["warehouse", "sku", "stock_qty"]].copy()
            curr_df["item_id"] = curr_df["sku"].map(item_map)
            curr_df = curr_df.dropna(subset=["item_id"]).copy()
            curr_df["item_id"] = curr_df["item_id"].astype(int)
            curr_df = curr_df.rename(columns={"stock_qty": "stock_qty_curr"})
            merged_delta = prev_df.merge(
                curr_df,
                on=["warehouse", "item_id"],
                how="outer",
            )
            merged_delta["stock_qty_prev"] = (
                merged_delta["stock_qty_prev"].fillna(0).astype(int)
            )
            merged_delta["stock_qty_curr"] = (
                merged_delta["stock_qty_curr"].fillna(0).astype(int)
            )
            merged_delta["sold_qty"] = (
                merged_delta["stock_qty_prev"] - merged_delta["stock_qty_curr"]
            ).clip(lower=0)
            merged_delta["replenished_qty"] = (
                merged_delta["stock_qty_curr"] - merged_delta["stock_qty_prev"]
            ).clip(lower=0)
            changes = merged_delta[
                (merged_delta["sold_qty"] > 0)
                | (merged_delta["replenished_qty"] > 0)
            ]
            delta_records = [
                {
                    "data_date": upload_date,
                    "company": company,
                    "warehouse": record["warehouse"],
                    "item_id": int(record["item_id"]),
                    "sold_qty": int(record["sold_qty"]),
                    "replenished_qty": int(record["replenished_qty"]),
                }
                for record in changes.to_dict("records")
            ]
            rows_changes = len(delta_records)

        if not dry_run:
            ingest_run_payload = {
                "company": company,
                "file_name": file_name or "unknown",
                "file_hash": file_hash,
                "data_date": upload_date,
            }
            existing_hash = session.scalar(
                select(IngestRun.id)
                .where(IngestRun.company == company)
                .where(IngestRun.file_hash == file_hash)
            )
            if existing_hash:
                raise IngestConflict("Этот файл уже был загружен ранее.")

            with session.begin_nested():
                # Use SAVEPOINT to stay compatible with SQLAlchemy 2.0 nested transactions.
                ingest_run = IngestRun(
                    **ingest_run_payload,
                    status="failed",
                )
                session.add(ingest_run)
                session.flush()
                ingest_run_id = ingest_run.id

                if mode == "replace":
                    session.execute(
                        delete(FactSnapshot)
                        .where(FactSnapshot.company == company)
                        .where(FactSnapshot.data_date == upload_date)
                    )
                    session.execute(
                        delete(FactDeltaChange)
                        .where(FactDeltaChange.company == company)
                        .where(FactDeltaChange.data_date == upload_date)
                    )
                    _insert_batches(session, FactSnapshot, snapshot_records)
                    if prev_date is not None:
                        _insert_batches(session, FactDeltaChange, delta_records)
                elif mode == "merge":
                    _insert_batches(session, FactSnapshot, snapshot_records)
                    if prev_date is not None:
                        _insert_batches(session, FactDeltaChange, delta_records)
                else:
                    if warehouses:
                        session.execute(
                            delete(FactSnapshot)
                            .where(FactSnapshot.company == company)
                            .where(FactSnapshot.data_date == upload_date)
                            .where(FactSnapshot.warehouse.in_(warehouses))
                        )
                        session.execute(
                            delete(FactDeltaChange)
                            .where(FactDeltaChange.company == company)
                            .where(FactDeltaChange.data_date == upload_date)
                            .where(FactDeltaChange.warehouse.in_(warehouses))
                        )
                    _insert_batches(session, FactSnapshot, snapshot_records)
                    if prev_date is not None:
                        _insert_batches(session, FactDeltaChange, delta_records)
                ingest_run.status = "ok"
                ingest_run.rows_read = int(validation_report.get("rows_read", 0))
                ingest_run.rows_long = rows_long
                ingest_run.rows_snapshot = len(snapshot_records)
                ingest_run.rows_changes = rows_changes
                duration = datetime.utcnow() - started_at
                ingest_run.duration_ms = int(duration.total_seconds() * 1000)

            snapshot_count = session.scalar(
                select(func.count())
                .select_from(FactSnapshot)
                .where(FactSnapshot.company == company)
                .where(FactSnapshot.data_date == upload_date)
            )
            delta_count = session.scalar(
                select(func.count())
                .select_from(FactDeltaChange)
                .where(FactDeltaChange.company == company)
                .where(FactDeltaChange.data_date == upload_date)
            )
            if ingest_run_id is not None:
                ingest_run_count_query = (
                    select(func.count())
                    .select_from(IngestRun)
                    .where(IngestRun.id == ingest_run_id)
                )
            else:
                ingest_run_count_query = (
                    select(func.count())
                    .select_from(IngestRun)
                    .where(IngestRun.company == company)
                    .where(IngestRun.data_date == upload_date)
                )
            ingest_run_count = session.scalar(ingest_run_count_query)

            snapshot_count = int(snapshot_count or 0)
            delta_count = int(delta_count or 0)
            ingest_run_count = int(ingest_run_count or 0)

            logger.info(
                "Persisted fact_snapshot rows: %s for %s/%s",
                snapshot_count,
                company,
                upload_date,
            )
            logger.info(
                "Persisted fact_delta_changes rows: %s for %s/%s",
                delta_count,
                company,
                upload_date,
            )
            logger.info(
                "Persisted ingest_runs rows: %s for %s/%s",
                ingest_run_count,
                company,
                upload_date,
            )

            snapshot_expected = len(snapshot_records) > 0
            delta_expected = len(delta_records) > 0
            ingest_run_expected = True
            if (
                (snapshot_expected and snapshot_count == 0)
                or (delta_expected and delta_count == 0)
                or (ingest_run_expected and ingest_run_count == 0)
            ):
                raise IngestPersistenceError(
                    "Ingest reported success but no rows persisted"
                )
            session.commit()

        logger.info("Ingest complete: %s rows", len(snapshot_records))
        duration = datetime.utcnow() - started_at
        return {
            "status": "ok",
            "company": company,
            "data_date": upload_date.isoformat(),
            "prev_date": prev_date.isoformat() if prev_date else None,
            "rows_read": int(validation_report.get("rows_read", 0)),
            "rows_snapshot": len(snapshot_records),
            "rows_changes": rows_changes,
            "rows_long": rows_long,
            "dup_count": dup_count,
            "duration_ms": int(duration.total_seconds() * 1000),
        }
    except Exception as exc:
        session.rollback()
        if ingest_run_payload is not None:
            with session.begin_nested():
                # Use SAVEPOINT to stay compatible with SQLAlchemy 2.0 nested transactions.
                existing_run = None
                if ingest_run_id is not None:
                    existing_run = session.get(IngestRun, ingest_run_id)
                if existing_run is None:
                    existing_run = IngestRun(
                        **ingest_run_payload,
                        status="failed",
                    )
                    if ingest_run_id is not None:
                        existing_run.id = ingest_run_id
                    session.add(existing_run)
                error_message = str(exc)
                if len(error_message) > 4000:
                    error_message = error_message[:4000] + "…(truncated)"
                existing_run.error_message = error_message
                existing_run.status = "failed"
                if "validation_report" in locals():
                    existing_run.rows_read = int(validation_report.get("rows_read", 0))
                if "snapshot_records" in locals():
                    existing_run.rows_long = rows_long
                    existing_run.rows_snapshot = len(snapshot_records)
                if "rows_changes" in locals():
                    existing_run.rows_changes = rows_changes
                duration = datetime.utcnow() - started_at
                existing_run.duration_ms = int(duration.total_seconds() * 1000)
            session.commit()
        raise
