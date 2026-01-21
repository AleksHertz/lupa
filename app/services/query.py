from datetime import date, timedelta
from typing import Any

from cachetools import TTLCache
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import FactDeltaChange, FactSnapshot, Item

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


def _series_item_ids_stmt(
    sku: str | None,
    manufacturer: str | None,
    project_label: str | None,
    company: str | None,
):
    stmt = select(Item.id)
    if sku:
        sku_filter = or_(
            Item.canonical_sku == sku,
            Item.sku_norm.ilike(f"%{sku}%"),
            Item.name.ilike(f"%{sku}%"),
        )
        stmt = stmt.where(sku_filter)
    if manufacturer:
        stmt = stmt.where(Item.manufacturer_norm == manufacturer)
    if project_label:
        stmt = stmt.where(Item.project_label == project_label)
    if company:
        stmt = stmt.where(Item.company == company)
    return stmt


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

    delta_stmt = (
        select(
            FactDeltaChange.data_date,
            func.sum(FactDeltaChange.sold_qty).label("sold_qty"),
            func.sum(FactDeltaChange.replenished_qty).label("replenished_qty"),
        )
        .where(FactDeltaChange.data_date >= date_from)
        .where(FactDeltaChange.data_date <= date_to)
        .group_by(FactDeltaChange.data_date)
        .order_by(FactDeltaChange.data_date)
    )
    snapshot_stmt = (
        select(
            FactSnapshot.data_date,
            func.avg(FactSnapshot.price).label("price"),
            func.sum(FactSnapshot.stock_qty).label("stock_qty"),
        )
        .where(FactSnapshot.data_date >= date_from)
        .where(FactSnapshot.data_date <= date_to)
        .group_by(FactSnapshot.data_date)
        .order_by(FactSnapshot.data_date)
    )
    if sku or manufacturer or project_label or company:
        item_ids_stmt = _series_item_ids_stmt(
            sku=sku,
            manufacturer=manufacturer,
            project_label=project_label,
            company=company,
        )
        delta_stmt = delta_stmt.where(FactDeltaChange.item_id.in_(item_ids_stmt))
        snapshot_stmt = snapshot_stmt.where(FactSnapshot.item_id.in_(item_ids_stmt))
    if warehouses:
        delta_stmt = delta_stmt.where(FactDeltaChange.warehouse.in_(warehouses))
        snapshot_stmt = snapshot_stmt.where(FactSnapshot.warehouse.in_(warehouses))
    if company:
        delta_stmt = delta_stmt.where(FactDeltaChange.company == company)
        snapshot_stmt = snapshot_stmt.where(FactSnapshot.company == company)

    delta_rows = session.execute(delta_stmt).all()
    snapshot_rows = session.execute(snapshot_stmt).all()
    delta_map = {
        row.data_date: {
            "sold_qty": row.sold_qty,
            "replenished_qty": row.replenished_qty,
        }
        for row in delta_rows
    }
    snapshot_map = {
        row.data_date: {"price": row.price, "stock_qty": row.stock_qty}
        for row in snapshot_rows
    }
    dates_sorted = sorted(set(delta_map) | set(snapshot_map))
    dates = [day.isoformat() for day in dates_sorted]
    sold = [float(delta_map.get(day, {}).get("sold_qty") or 0) for day in dates_sorted]
    replenished = [
        float(delta_map.get(day, {}).get("replenished_qty") or 0)
        for day in dates_sorted
    ]
    prices = [
        float(snapshot_map.get(day, {}).get("price") or 0) for day in dates_sorted
    ]
    stock_qty = [
        float(snapshot_map.get(day, {}).get("stock_qty") or 0)
        for day in dates_sorted
    ]

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
        "sku": Item.canonical_sku,
        "warehouse": FactDeltaChange.warehouse,
        "manufacturer": Item.manufacturer_norm,
        "name": Item.name,
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
    if field == "warehouse":
        if company:
            stmt = stmt.where(FactDeltaChange.company == company)
    else:
        if company:
            stmt = stmt.where(Item.company == company)
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
    manufacturer: str | None = None,
    name: str | None = None,
    project_label: str | None = None,
    group_by_warehouse: bool = True,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    group_by_columns = [
        Item.canonical_sku,
        Item.name,
        Item.manufacturer_norm,
        Item.brand,
    ]
    if group_by_warehouse:
        warehouse_column = FactDeltaChange.warehouse
        group_by_columns.append(FactDeltaChange.warehouse)
    else:
        warehouse_column = func.min(FactDeltaChange.warehouse)

    snapshot_group_columns = [FactSnapshot.item_id]
    snapshot_select_columns = [
        FactSnapshot.item_id.label("item_id"),
        func.max(FactSnapshot.price).label("last_price"),
    ]
    if group_by_warehouse:
        snapshot_group_columns.append(FactSnapshot.warehouse)
        snapshot_select_columns.append(FactSnapshot.warehouse.label("warehouse"))
    snapshot_stmt = select(*snapshot_select_columns).join(
        Item, Item.id == FactSnapshot.item_id
    )

    if company:
        snapshot_stmt = snapshot_stmt.where(FactSnapshot.company == company).where(
            Item.company == company
        )
    if warehouses:
        snapshot_stmt = snapshot_stmt.where(FactSnapshot.warehouse.in_(warehouses))
    if sku:
        snapshot_stmt = snapshot_stmt.where(Item.canonical_sku == sku)
    if manufacturer:
        snapshot_stmt = snapshot_stmt.where(Item.manufacturer_norm == manufacturer)
    if name:
        snapshot_stmt = snapshot_stmt.where(Item.name.ilike(f"%{name}%"))
    if project_label:
        snapshot_stmt = snapshot_stmt.where(Item.project_label == project_label)
    if date_from:
        snapshot_stmt = snapshot_stmt.where(FactSnapshot.data_date >= date_from)
    if date_to:
        snapshot_stmt = snapshot_stmt.where(FactSnapshot.data_date <= date_to)

    snapshot_subq = snapshot_stmt.group_by(*snapshot_group_columns).subquery()

    join_condition = FactDeltaChange.item_id == snapshot_subq.c.item_id
    if group_by_warehouse:
        join_condition = join_condition & (
            FactDeltaChange.warehouse == snapshot_subq.c.warehouse
        )

    stmt = (
        select(
            Item.canonical_sku.label("sku"),
            Item.name,
            Item.manufacturer_norm.label("manufacturer"),
            Item.brand,
            warehouse_column.label("warehouse"),
            func.sum(FactDeltaChange.sold_qty).label("sold"),
            func.sum(FactDeltaChange.replenished_qty).label("repl"),
            func.max(snapshot_subq.c.last_price).label("last_price"),
        )
        .join(Item, Item.id == FactDeltaChange.item_id)
        .outerjoin(snapshot_subq, join_condition)
        .group_by(*group_by_columns)
        .order_by(func.sum(FactDeltaChange.sold_qty).desc())
        .limit(limit)
    )

    if company:
        stmt = stmt.where(FactDeltaChange.company == company).where(Item.company == company)
    if warehouses:
        stmt = stmt.where(FactDeltaChange.warehouse.in_(warehouses))
    if sku:
        stmt = stmt.where(Item.canonical_sku == sku)
    if manufacturer:
        stmt = stmt.where(Item.manufacturer_norm == manufacturer)
    if name:
        stmt = stmt.where(Item.name.ilike(f"%{name}%"))
    if project_label:
        stmt = stmt.where(Item.project_label == project_label)
    if date_from:
        stmt = stmt.where(FactDeltaChange.data_date >= date_from)
    if date_to:
        stmt = stmt.where(FactDeltaChange.data_date <= date_to)

    rows = session.execute(stmt).mappings().all()
    return [dict(row) for row in rows]


def get_ingest_state(
    session: Session, company: str, limit: int = 30
) -> dict[str, Any]:
    normalized_company = company.strip().lower()
    limit = max(limit, 1)
    snapshot_dates = (
        session.execute(
            select(FactSnapshot.data_date)
            .where(FactSnapshot.company == normalized_company)
            .distinct()
            .order_by(FactSnapshot.data_date.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )

    if snapshot_dates:
        snapshot_counts = dict(
            session.execute(
                select(
                    FactSnapshot.data_date,
                    func.count().label("snapshot_rows"),
                )
                .where(FactSnapshot.company == normalized_company)
                .where(FactSnapshot.data_date.in_(snapshot_dates))
                .group_by(FactSnapshot.data_date)
            ).all()
        )
        delta_counts = dict(
            session.execute(
                select(
                    FactDeltaChange.data_date,
                    func.count().label("delta_rows"),
                )
                .where(FactDeltaChange.company == normalized_company)
                .where(FactDeltaChange.data_date.in_(snapshot_dates))
                .group_by(FactDeltaChange.data_date)
            ).all()
        )
    else:
        snapshot_counts = {}
        delta_counts = {}

    max_date = session.scalar(
        select(func.max(FactSnapshot.data_date)).where(
            FactSnapshot.company == normalized_company
        )
    )
    today = date.today()
    if max_date is None:
        next_upload_date = today
    elif max_date >= today:
        next_upload_date = max_date + timedelta(days=1)
    else:
        next_upload_date = today

    prev_date = session.scalar(
        select(func.max(FactSnapshot.data_date))
        .where(FactSnapshot.company == normalized_company)
        .where(FactSnapshot.data_date < next_upload_date)
    )

    items = []
    for snapshot_date in snapshot_dates:
        items.append(
            {
                "date": snapshot_date.isoformat(),
                "snapshot_rows": int(snapshot_counts.get(snapshot_date, 0)),
                "delta_rows": int(delta_counts.get(snapshot_date, 0)),
            }
        )

    return {
        "company": normalized_company,
        "limit": limit,
        "dates": items,
        "next_upload_date": next_upload_date.isoformat() if next_upload_date else None,
        "prev_date": prev_date.isoformat() if prev_date else None,
    }
