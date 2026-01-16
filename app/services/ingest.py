import hashlib
import io
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Literal

import pandas as pd
from sqlalchemy import delete, func, select
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
        for idx in raw[invalid].index:
            _add_validation_error(
                report,
                "Цена должна быть числом.",
                row=idx,
                column=column,
            )
    return numeric


def _coerce_stock_column(
    df: pd.DataFrame, report: dict[str, Any], column: str
) -> pd.Series:
    numeric = pd.to_numeric(df[column], errors="coerce").fillna(0)
    negative = numeric < 0
    if negative.any():
        for idx in numeric[negative].index:
            _add_validation_error(
                report,
                "Остаток не может быть отрицательным.",
                row=idx,
                column=column,
            )
        numeric = numeric.mask(negative, 0)
    return numeric.astype(int)


def _validate_alliance_df(
    df: pd.DataFrame, report: dict[str, Any]
) -> pd.DataFrame:
    df = df.rename(columns=ALLIANCE_COLUMN_ALIASES)
    required = {"sku", "name", "price", "manufacturer", "brand", "group_name"}
    missing = required - set(df.columns)
    if missing:
        expected_columns = ", ".join(sorted(required))
        found_columns = ", ".join(
            sorted(report["normalized_mapping"].keys() or df.columns)
        )
        raise IngestError(
            "Не найдены обязательные колонки. "
            f"Ожидались: {expected_columns}. "
            f"Найдены: {found_columns}.",
            report=report,
        )
    warehouse_columns = set(ALLIANCE_WAREHOUSE_COLUMNS.keys())
    for column in warehouse_columns:
        if column not in df.columns:
            df[column] = 0
            _add_validation_warning(
                report,
                f"Отсутствует складская колонка '{column}', заполнено нулями.",
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
            _add_validation_error(
                report,
                "Пустые sku/mfg_sku.",
                row=idx,
                column="sku",
            )
        report["rows_dropped"] += int(empty_sku_and_mfg.sum())
        df = df.loc[~empty_sku_and_mfg].copy()

    df.loc[df["mfg_sku"].isna() & df["sku"].notna(), "mfg_sku"] = df["sku"]
    df.loc[df["sku"].isna() & df["mfg_sku"].notna(), "sku"] = df["mfg_sku"]

    empty_sku = df["sku"].isna()
    if empty_sku.any():
        for idx in df[empty_sku].index:
            _add_validation_error(
                report, "Артикул обязателен.", row=idx, column="sku"
            )
        report["rows_dropped"] += int(empty_sku.sum())
        df = df.loc[~empty_sku].copy()

    df["price"] = _coerce_price_column(df, report, column="price")
    for column in warehouse_columns:
        df[column] = _coerce_stock_column(df, report, column=column)

    report["recognized_columns"] = sorted(df.columns)

    id_vars = [col for col in df.columns if col not in warehouse_columns]
    df = df.melt(
        id_vars=id_vars,
        value_vars=list(warehouse_columns),
        var_name="warehouse_key",
        value_name="stock_qty",
    )
    df["warehouse"] = df["warehouse_key"].map(ALLIANCE_WAREHOUSE_COLUMNS)
    df = df.drop(columns=["warehouse_key"])
    df["nomenclature"] = df["name"]
    df["group_name"] = df.get("group_name")
    df["manufacturer"] = df.get("manufacturer")
    return df


def _validate_default_df(
    df: pd.DataFrame, report: dict[str, Any]
) -> pd.DataFrame:
    mapping = _apply_column_aliases(df.columns.tolist(), COLUMN_ALIASES)
    df = df.rename(columns=mapping)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise IngestError(
            f"Не найдены обязательные колонки: {', '.join(sorted(missing))}.",
            report=report,
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
            _add_validation_error(
                report, "Артикул обязателен.", row=idx, column="sku"
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
    is_alliance = normalized_company == "альянс"
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
            price=("price", "last"),
            nomenclature=("nomenclature", "first"),
            group_name=("group_name", "first"),
            project_label=("project_label", "first"),
        )
        .reset_index()
    )
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
            DailySnapshot.warehouse,
            DailySnapshot.sku,
            DailySnapshot.manufacturer,
            DailySnapshot.stock_qty,
        )
        .where(DailySnapshot.company == company)
        .where(DailySnapshot.data_date == prev_date)
        .where(DailySnapshot.warehouse.in_(warehouses))
    )
    rows = session.execute(stmt).all()
    if not rows:
        return pd.DataFrame(columns=["warehouse", "sku", "manufacturer", "stock_qty"])
    return pd.DataFrame(rows, columns=["warehouse", "sku", "manufacturer", "stock_qty"])


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
            DailySnapshot.warehouse,
            DailySnapshot.sku,
            DailySnapshot.manufacturer,
            DailySnapshot.price,
        )
        .where(DailySnapshot.company == company)
        .where(DailySnapshot.data_date == upload_date)
        .where(DailySnapshot.warehouse.in_(warehouses))
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
            DailySnapshot.id,
            DailySnapshot.warehouse,
            DailySnapshot.sku,
            DailySnapshot.manufacturer,
            DailySnapshot.price,
        )
        .where(DailySnapshot.company == company)
        .where(DailySnapshot.data_date == upload_date)
    )
    rows = session.execute(stmt).all()
    return {
        (row.warehouse, row.sku, row.manufacturer): {
            "id": row.id,
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
            DailyDelta.id,
            DailyDelta.warehouse,
            DailyDelta.sku,
            DailyDelta.manufacturer,
            DailyDelta.price,
        )
        .where(DailyDelta.company == company)
        .where(DailyDelta.data_date == upload_date)
    )
    rows = session.execute(stmt).all()
    return {
        (row.warehouse, row.sku, row.manufacturer): {
            "id": row.id,
            "price": row.price,
        }
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
    is_alliance_company = normalized_company in {"alliance", "альянс"}
    if is_alliance and file_name:
        parsed_date = date_from_filename(file_name, datetime.now())
        if parsed_date is not None:
            upload_date = parsed_date

    file_hash = hashlib.sha256(file_bytes).hexdigest()
    ingest_run_id: int | None = None
    ingest_run_payload: dict[str, object] | None = None
    try:
        alliance_existing_date = None
        if is_alliance_company and mode != "replace":
            alliance_existing_date = session.scalar(
                select(DailySnapshot.id)
                .where(DailySnapshot.company == company)
                .where(DailySnapshot.data_date == upload_date)
            )
            if alliance_existing_date and not dry_run:
                raise IngestConflict(
                    "Данные за эту дату уже загружены для компании Alliance. "
                    "Передайте replace=true, чтобы перезаписать."
                )

        logger.info("Starting ingest for %s", upload_date)
        df = pd.read_excel(
            io.BytesIO(file_bytes),
            engine="openpyxl",
        )
        df, validation_report = validate_ingest_df(
            df=df, file_name=file_name, company=company
        )
        if validation_report["errors"]:
            raise IngestError(
                "Файл содержит ошибки. Проверьте отчет.",
                report=validation_report,
            )
        if alliance_existing_date and dry_run:
            _add_validation_warning(
                validation_report,
                "Данные за эту дату уже загружены для компании Alliance. "
                "Передайте replace=true, чтобы перезаписать.",
            )
        df["project_label"] = df["group_name"].map(_project_label_for_group)
        aggregated = _aggregate_daily(df)

        warehouses = aggregated["warehouse"].dropna().unique().tolist()

        existing = _load_existing_snapshot(session, company, upload_date, warehouses)
        if not existing.empty and mode == "reject":
            if dry_run:
                _add_validation_warning(
                    validation_report,
                    "Данные за эту дату и склад уже загружены. "
                    "Используйте mode=merge для обновления или mode=replace для перезаписи.",
                )
            else:
                raise IngestConflict(
                    "Данные за эту дату и склад уже загружены. "
                    "Используйте mode=merge для обновления или mode=replace для перезаписи."
                )

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

        prev_date = session.scalar(
            select(func.max(DailySnapshot.data_date))
            .where(DailySnapshot.company == company)
            .where(DailySnapshot.data_date < upload_date)
        )
        if prev_date is None:
            merged = aggregated.copy()
            merged["sold_qty"] = 0
            merged["replenished_qty"] = 0
        else:
            prev_df = _load_prev_snapshot(session, company, prev_date, warehouses)
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
            merged["stock_qty_prev"] = merged["stock_qty_prev"].fillna(0).astype(int)
            merged["sold_qty"] = (
                merged["stock_qty_prev"] - merged["stock_qty"]
            ).clip(lower=0)
            merged["replenished_qty"] = (
                merged["stock_qty"] - merged["stock_qty_prev"]
            ).clip(lower=0)
            merged["sold_qty"] = merged["sold_qty"].astype(int)
            merged["replenished_qty"] = merged["replenished_qty"].astype(int)

        qa_report = _build_qa_report(merged)
        qa_errors: list[dict[str, Any]] = []
        negative_mask = (merged["sold_qty"] < 0) | (merged["replenished_qty"] < 0)
        if negative_mask.any():
            examples = (
                merged.loc[
                    negative_mask,
                    [
                        "warehouse",
                        "sku",
                        "manufacturer",
                        "sold_qty",
                        "replenished_qty",
                    ],
                ]
                .head(10)
                .to_dict("records")
            )
            qa_errors.append(
                {
                    "type": "negative_quantities",
                    "count": int(negative_mask.sum()),
                    "examples": examples,
                }
            )
        simultaneous_mask = (merged["sold_qty"] > 0) & (
            merged["replenished_qty"] > 0
        )
        if simultaneous_mask.any():
            examples = (
                merged.loc[
                    simultaneous_mask,
                    [
                        "warehouse",
                        "sku",
                        "manufacturer",
                        "sold_qty",
                        "replenished_qty",
                    ],
                ]
                .head(10)
                .to_dict("records")
            )
            qa_errors.append(
                {
                    "type": "simultaneous_sold_replenished",
                    "count": int(simultaneous_mask.sum()),
                    "examples": examples,
                }
            )
        if prev_date is not None:
            balance = (
                merged.groupby(["warehouse", "sku"], dropna=False)
                .agg(
                    prev_stock=("stock_qty_prev", "sum"),
                    replenished=("replenished_qty", "sum"),
                    sold=("sold_qty", "sum"),
                    curr_stock=("stock_qty", "sum"),
                )
                .reset_index()
            )
            balance["expected_stock"] = (
                balance["prev_stock"] + balance["replenished"] - balance["sold"]
            )
            mismatch = balance[balance["expected_stock"] != balance["curr_stock"]]
            if not mismatch.empty:
                examples = mismatch.head(10).to_dict("records")
                qa_errors.append(
                    {
                        "type": "stock_balance_mismatch",
                        "count": int(len(mismatch)),
                        "examples": examples,
                    }
                )
        if qa_errors:
            logger.error("QA validation failed: %s", qa_errors)
            raise IngestError(
                "Проверка качества данных не пройдена.",
                report={"qa_report": qa_report, "qa_errors": qa_errors},
            )

        snapshot_records = merged[
            [
                "warehouse",
                "sku",
                "manufacturer",
                "nomenclature",
                "group_name",
                "project_label",
                "stock_qty",
                "price",
            ]
        ].to_dict("records")
        for record in snapshot_records:
            record["data_date"] = upload_date
            record["company"] = company

        delta_records = merged[
            [
                "warehouse",
                "sku",
                "manufacturer",
                "nomenclature",
                "group_name",
                "project_label",
                "stock_qty",
                "sold_qty",
                "replenished_qty",
                "price",
            ]
        ].to_dict("records")
        for record in delta_records:
            record["data_date"] = upload_date
            record["company"] = company

        if not dry_run:
            with session.begin():
                existing_hash = session.scalar(
                    select(IngestRun.id)
                    .where(IngestRun.company == company)
                    .where(IngestRun.file_hash == file_hash)
                )
                if existing_hash:
                    raise IngestConflict("Этот файл уже был загружен ранее.")

                ingest_run_payload = {
                    "company": company,
                    "file_name": file_name or "unknown",
                    "file_hash": file_hash,
                    "data_date": upload_date,
                }
                ingest_run = IngestRun(
                    **ingest_run_payload,
                    status="failed",
                )
                session.add(ingest_run)
                session.flush()
                ingest_run_id = ingest_run.id

                existing_date = session.scalar(
                    select(DailySnapshot.id)
                    .where(DailySnapshot.company == company)
                    .where(DailySnapshot.data_date == upload_date)
                )
                if existing_date and mode == "reject":
                    ingest_run.error_message = "Данные за эту дату уже загружены."
                    raise IngestConflict(ingest_run.error_message)

                existing_date = session.scalar(
                    select(IngestRun.id)
                    .where(IngestRun.company == company)
                    .where(IngestRun.data_date == upload_date)
                    .where(IngestRun.id != ingest_run.id)
                )
                if existing_date:
                    ingest_run.error_message = "Загрузка за эту дату уже выполнялась."
                    raise IngestConflict(ingest_run.error_message)

                if mode == "replace":
                    session.execute(
                        delete(DailySnapshot)
                        .where(DailySnapshot.company == company)
                        .where(DailySnapshot.data_date == upload_date)
                    )
                    session.execute(
                        delete(DailyDelta)
                        .where(DailyDelta.company == company)
                        .where(DailyDelta.data_date == upload_date)
                    )
                    session.bulk_insert_mappings(DailySnapshot, snapshot_records)
                    session.bulk_insert_mappings(DailyDelta, delta_records)
                elif mode == "merge":
                    snapshot_existing_map = _load_existing_snapshot_map(
                        session, company, upload_date
                    )
                    delta_existing_map = _load_existing_delta_map(
                        session, company, upload_date
                    )
                    snapshot_updates = []
                    snapshot_inserts = []
                    for record in snapshot_records:
                        key = (record["warehouse"], record["sku"], record["manufacturer"])
                        existing_row = snapshot_existing_map.get(key)
                        if existing_row:
                            if existing_row["price"] is not None:
                                record["price"] = existing_row["price"]
                            record["id"] = existing_row["id"]
                            snapshot_updates.append(record)
                        else:
                            snapshot_inserts.append(record)
                    delta_updates = []
                    delta_inserts = []
                    for record in delta_records:
                        key = (record["warehouse"], record["sku"], record["manufacturer"])
                        existing_row = delta_existing_map.get(key)
                        if existing_row:
                            if existing_row["price"] is not None:
                                record["price"] = existing_row["price"]
                            record["id"] = existing_row["id"]
                            delta_updates.append(record)
                        else:
                            delta_inserts.append(record)
                    if snapshot_updates:
                        session.bulk_update_mappings(DailySnapshot, snapshot_updates)
                    if snapshot_inserts:
                        session.bulk_insert_mappings(DailySnapshot, snapshot_inserts)
                    if delta_updates:
                        session.bulk_update_mappings(DailyDelta, delta_updates)
                    if delta_inserts:
                        session.bulk_insert_mappings(DailyDelta, delta_inserts)
                else:
                    if warehouses:
                        session.execute(
                            delete(DailySnapshot)
                            .where(DailySnapshot.company == company)
                            .where(DailySnapshot.data_date == upload_date)
                            .where(DailySnapshot.warehouse.in_(warehouses))
                        )
                        session.execute(
                            delete(DailyDelta)
                            .where(DailyDelta.company == company)
                            .where(DailyDelta.data_date == upload_date)
                            .where(DailyDelta.warehouse.in_(warehouses))
                        )
                    session.bulk_insert_mappings(DailySnapshot, snapshot_records)
                    session.bulk_insert_mappings(DailyDelta, delta_records)
                ingest_run.status = "ok"

        logger.info("Ingest complete: %s rows", len(snapshot_records))
        return {
            "data_date": upload_date,
            "prev_date": prev_date,
            "row_stats": {
                "rows_read": validation_report["rows_read"],
                "rows_dropped": validation_report["rows_dropped"],
                "snapshots": len(snapshot_records),
                "deltas": len(delta_records),
            },
            "recognized_columns": validation_report["recognized_columns"],
            "column_mapping": validation_report["normalized_mapping"],
            "validation_report": validation_report,
            "qa_report": qa_report,
            "qa_errors": qa_errors,
            "warnings": validation_report["warnings"],
            "errors": validation_report["errors"],
        }
    except Exception as exc:
        session.rollback()
        if ingest_run_payload is not None:
            with session.begin():
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
                existing_run.error_message = str(exc)
                existing_run.status = "failed"
        raise
