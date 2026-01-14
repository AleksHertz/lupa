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
    warehouse: str | None,
    manufacturer: str | None,
    project_label: str | None,
    date_from: date,
    date_to: date,
) -> tuple[Any, ...]:
    return (sku, warehouse, manufacturer, project_label, date_from, date_to)


def get_series(
    session: Session,
    sku: str | None,
    warehouse: str | None,
    manufacturer: str | None,
    project_label: str | None,
    date_from: date,
    date_to: date,
) -> dict[str, Any]:
    cache_key = _series_cache_key(
        sku, warehouse, manufacturer, project_label, date_from, date_to
    )
    if cache_key in SERIES_CACHE:
        return SERIES_CACHE[cache_key]

    stmt = (
        select(
            DailyDelta.date,
            func.sum(DailyDelta.sold_qty).label("sold_qty"),
            func.sum(DailyDelta.replenished_qty).label("replenished_qty"),
            func.avg(DailyDelta.price_start_day).label("price_start_day"),
        )
        .where(DailyDelta.date >= date_from)
        .where(DailyDelta.date <= date_to)
        .group_by(DailyDelta.date)
        .order_by(DailyDelta.date)
    )
    if sku:
        stmt = stmt.where(DailyDelta.sku == sku)
    if warehouse:
        stmt = stmt.where(DailyDelta.warehouse == warehouse)
    if manufacturer:
        stmt = stmt.where(DailyDelta.manufacturer == manufacturer)
    if project_label:
        stmt = stmt.where(DailyDelta.project_label == project_label)

    rows = session.execute(stmt).all()
    dates = [row.date.isoformat() for row in rows]
    sold = [float(row.sold_qty or 0) for row in rows]
    replenished = [float(row.replenished_qty or 0) for row in rows]
    prices = [float(row.price_start_day or 0) for row in rows]

    sold_total = sum(sold)
    replenished_total = sum(replenished)
    max_sold_date = dates[sold.index(max(sold))] if sold else None
    max_repl_date = dates[replenished.index(max(replenished))] if replenished else None

    payload = {
        "dates": dates,
        "sold_qty": sold,
        "replenished_qty": replenished,
        "price_start_day": prices,
        "kpi": {
            "sold_total": sold_total,
            "replenished_total": replenished_total,
            "max_sold_date": max_sold_date,
            "max_replenished_date": max_repl_date,
        },
    }
    SERIES_CACHE[cache_key] = payload
    return payload


def _suggestion_cache_key(field: str, query: str) -> tuple[str, str]:
    return (field, query)


def get_suggestions(session: Session, field: str, query: str, limit: int = 20) -> list[str]:
    cache_key = _suggestion_cache_key(field, query)
    if cache_key in SUGGESTION_CACHE:
        return SUGGESTION_CACHE[cache_key]

    allowed_fields = {
        "sku": DailyDelta.sku,
        "warehouse": DailyDelta.warehouse,
        "manufacturer": DailyDelta.manufacturer,
        "nomenclature": DailyDelta.nomenclature,
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
    rows = session.execute(stmt).scalars().all()
    SUGGESTION_CACHE[cache_key] = rows
    return rows
