from datetime import date
from typing import Any

from cachetools import TTLCache
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DailyDelta

SERIES_CACHE = TTLCache(maxsize=256, ttl=300)
SUGGESTION_CACHE = TTLCache(maxsize=512, ttl=300)


def _series_cache_key(
    sku: str | None,
    warehouses: tuple[str, ...] | None,
    manufacturer: str | None,
    project_label: str | None,
    company: str | None,
    date_from: date,
    date_to: date,
) -> tuple[Any, ...]:
    return (sku, warehouses, manufacturer, project_label, company, date_from, date_to)


def get_series(
    session: Session,
    sku: str | None,
    warehouses: list[str] | None,
    manufacturer: str | None,
    project_label: str | None,
    company: str | None,
    date_from: date,
    date_to: date,
) -> dict[str, Any]:
    warehouses_key = tuple(sorted(warehouses)) if warehouses else None
    cache_key = _series_cache_key(
        sku, warehouses_key, manufacturer, project_label, company, date_from, date_to
    )
    if cache_key in SERIES_CACHE:
        return SERIES_CACHE[cache_key]

    stmt = (
        select(
            DailyDelta.data_date,
            func.sum(DailyDelta.sold_qty).label("sold_qty"),
            func.sum(DailyDelta.replenished_qty).label("replenished_qty"),
            func.avg(DailyDelta.price).label("price"),
            func.sum(DailyDelta.stock_qty).label("stock_qty"),
        )
        .where(DailyDelta.data_date >= date_from)
        .where(DailyDelta.data_date <= date_to)
        .group_by(DailyDelta.data_date)
        .order_by(DailyDelta.data_date)
    )
    if sku:
        stmt = stmt.where(DailyDelta.sku == sku)
    if warehouses:
        stmt = stmt.where(DailyDelta.warehouse.in_(warehouses))
    if manufacturer:
        stmt = stmt.where(DailyDelta.manufacturer == manufacturer)
    if project_label:
        stmt = stmt.where(DailyDelta.project_label == project_label)
    if company:
        stmt = stmt.where(DailyDelta.company == company)

    rows = session.execute(stmt).all()
    dates = [row.data_date.isoformat() for row in rows]
    sold = [float(row.sold_qty or 0) for row in rows]
    replenished = [float(row.replenished_qty or 0) for row in rows]
    prices = [float(row.price or 0) for row in rows]
    stock_qty = [float(row.stock_qty or 0) for row in rows]

    sold_total = sum(sold)
    replenished_total = sum(replenished)
    max_sold_date = dates[sold.index(max(sold))] if sold else None
    max_repl_date = dates[replenished.index(max(replenished))] if replenished else None

    payload = {
        "dates": dates,
        "sold_qty": sold,
        "replenished_qty": replenished,
        "price": prices,
        "stock_qty": stock_qty,
        "kpi": {
            "sold_total": sold_total,
            "replenished_total": replenished_total,
            "max_sold_date": max_sold_date,
            "max_replenished_date": max_repl_date,
        },
    }
    SERIES_CACHE[cache_key] = payload
    return payload


def _suggestion_cache_key(field: str, query: str, company: str | None) -> tuple[str, str, str | None]:
    return (field, query, company)


def get_suggestions(
    session: Session, field: str, query: str, company: str | None, limit: int = 20
) -> list[str]:
    cache_key = _suggestion_cache_key(field, query, company)
    cacheable_fields = {"sku", "name"}
    if field in cacheable_fields and cache_key in SUGGESTION_CACHE:
        return SUGGESTION_CACHE[cache_key]

    allowed_fields = {
        "sku": DailyDelta.sku,
        "warehouse": DailyDelta.warehouse,
        "manufacturer": DailyDelta.manufacturer,
        "name": DailyDelta.name,
    }
    if field not in allowed_fields:
        return []

    column = allowed_fields[field]
    stmt = (
        select(column)
        .where(column.is_not(None))
        .where(column.ilike(f"%{query}%"))
        .distinct()
        .order_by(column)
        .limit(limit)
    )
    if company:
        stmt = stmt.where(DailyDelta.company == company)
    rows = session.execute(stmt).scalars().all()
    if field in cacheable_fields:
        SUGGESTION_CACHE[cache_key] = rows
    return rows


def get_top_sales(
    session: Session,
    limit: int,
    company: str | None = None,
    warehouses: list[str] | None = None,
    sku: str | None = None,
    name: str | None = None,
    project_label: str | None = None,
    group_by_warehouse: bool = True,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    group_by_columns = [
        DailyDelta.sku,
        DailyDelta.name,
        DailyDelta.manufacturer,
        DailyDelta.brand,
    ]
    if group_by_warehouse:
        warehouse_column = DailyDelta.warehouse
        group_by_columns.append(DailyDelta.warehouse)
    else:
        warehouse_column = func.min(DailyDelta.warehouse)

    stmt = (
        select(
            DailyDelta.sku,
            DailyDelta.name,
            DailyDelta.manufacturer,
            DailyDelta.brand,
            warehouse_column.label("warehouse"),
            func.sum(DailyDelta.sold_qty).label("sold"),
            func.sum(DailyDelta.replenished_qty).label("repl"),
            func.max(DailyDelta.price).label("last_price"),
        )
        .group_by(*group_by_columns)
        .order_by(func.sum(DailyDelta.sold_qty).desc())
        .limit(limit)
    )

    if company:
        stmt = stmt.where(DailyDelta.company == company)
    if warehouses:
        stmt = stmt.where(DailyDelta.warehouse.in_(warehouses))
    if sku:
        stmt = stmt.where(DailyDelta.sku == sku)
    if name:
        stmt = stmt.where(DailyDelta.name.ilike(f"%{name}%"))
    if project_label:
        stmt = stmt.where(DailyDelta.project_label == project_label)
    if date_from:
        stmt = stmt.where(DailyDelta.data_date >= date_from)
    if date_to:
        stmt = stmt.where(DailyDelta.data_date <= date_to)

    rows = session.execute(stmt).mappings().all()
    return [dict(row) for row in rows]
