import logging
import unicodedata
from datetime import date, timedelta
from typing import Any

from cachetools import TTLCache
from sqlalchemy import Date, and_, func, literal, or_, select, text, true, union_all
from sqlalchemy.orm import Session

from app.models import FactDeltaChange, FactSnapshot, Item

SERIES_CACHE = TTLCache(maxsize=256, ttl=300)
SUGGESTION_CACHE = TTLCache(maxsize=512, ttl=300)
logger = logging.getLogger(__name__)


def _series_cache_key(
    item_id: int | None,
    sku: str | None,
    warehouses: tuple[str, ...] | None,
    manufacturer: str | None,
    project_label: str | None,
    company: str | None,
    date_from: date,
    date_to: date,
) -> tuple[Any, ...]:
    return (
        item_id,
        sku,
        warehouses,
        manufacturer,
        project_label,
        company,
        date_from,
        date_to,
    )


def _normalize_sku(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return normalized.strip().casefold()


def resolve_item_id(session: Session, sku: str, company: str | None = None) -> int | None:
    sku_clean = sku.strip()
    sku_norm = _normalize_sku(sku_clean)
    exact_stmt = select(Item.id).where(
        or_(Item.canonical_sku == sku_clean, Item.sku_norm == sku_norm)
    )
    if company:
        exact_stmt = exact_stmt.where(Item.company == company)
    exact_matches = session.execute(exact_stmt.order_by(Item.id)).scalars().all()
    if len(exact_matches) > 1:
        logger.warning(
            "Multiple exact matches for sku '%s' (company=%s); using first match.",
            sku_clean,
            company,
        )
    if exact_matches:
        return exact_matches[0]

    name_stmt = select(Item.id, Item.name).where(Item.name.ilike(f"%{sku_clean}%"))
    if company:
        name_stmt = name_stmt.where(Item.company == company)
    name_matches = session.execute(
        name_stmt.order_by(func.length(Item.name), Item.name).limit(2)
    ).all()
    if len(name_matches) > 1:
        logger.warning(
            "Multiple name matches for sku '%s' (company=%s); using best match '%s'.",
            sku_clean,
            company,
            name_matches[0].name,
        )
    if name_matches:
        return name_matches[0].id
    return None


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
    item_id: int | None,
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
        item_id,
        sku,
        warehouses_key,
        manufacturer,
        project_label,
        company,
        date_from,
        date_to,
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
    if item_id is not None:
        delta_stmt = delta_stmt.where(FactDeltaChange.item_id == item_id)
        snapshot_stmt = snapshot_stmt.where(FactSnapshot.item_id == item_id)
    elif sku or manufacturer or project_label or company:
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

    availability_range = {"min": None, "max": None}
    delta_dates_stmt = select(FactDeltaChange.data_date.label("data_date"))
    snapshot_dates_stmt = select(FactSnapshot.data_date.label("data_date"))
    if item_id is not None:
        delta_dates_stmt = delta_dates_stmt.where(FactDeltaChange.item_id == item_id)
        snapshot_dates_stmt = snapshot_dates_stmt.where(FactSnapshot.item_id == item_id)
    elif sku or manufacturer or project_label or company:
        item_ids_stmt = _series_item_ids_stmt(
            sku=sku,
            manufacturer=manufacturer,
            project_label=project_label,
            company=company,
        )
        delta_dates_stmt = delta_dates_stmt.where(FactDeltaChange.item_id.in_(item_ids_stmt))
        snapshot_dates_stmt = snapshot_dates_stmt.where(
            FactSnapshot.item_id.in_(item_ids_stmt)
        )
    if warehouses:
        delta_dates_stmt = delta_dates_stmt.where(FactDeltaChange.warehouse.in_(warehouses))
        snapshot_dates_stmt = snapshot_dates_stmt.where(
            FactSnapshot.warehouse.in_(warehouses)
        )
    if company:
        delta_dates_stmt = delta_dates_stmt.where(FactDeltaChange.company == company)
        snapshot_dates_stmt = snapshot_dates_stmt.where(FactSnapshot.company == company)
    availability_subq = delta_dates_stmt.union_all(snapshot_dates_stmt).subquery()
    availability_stmt = select(
        func.min(availability_subq.c.data_date).label("min_date"),
        func.max(availability_subq.c.data_date).label("max_date"),
    )
    availability_row = session.execute(availability_stmt).one()
    availability_range = {
        "min": availability_row.min_date.isoformat() if availability_row.min_date else None,
        "max": availability_row.max_date.isoformat() if availability_row.max_date else None,
    }

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
        "available_range": availability_range,
        "kpi": {
            "sold_total": sold_total,
            "replenished_total": replenished_total,
            "max_sold_date": max_sold_date,
            "max_replenished_date": max_repl_date,
        },
    }
    SERIES_CACHE[cache_key] = payload
    return payload


def get_series_v2(
    session: Session,
    item_id: int | None,
    company: str | None,
    warehouses: list[str] | None,
    date_from: date,
    date_to: date,
) -> dict[str, Any]:
    item_data: dict[str, Any] | None = None
    if item_id is not None:
        item_stmt = select(
            Item.canonical_sku,
            Item.name,
            Item.manufacturer_norm.label("manufacturer"),
            Item.group_name,
            Item.project_label,
        ).where(Item.id == item_id)
        if company:
            item_stmt = item_stmt.where(Item.company == company)
        item_row = session.execute(item_stmt).mappings().first()
        if item_row:
            item_data = dict(item_row)

    availability_range = {"min": None, "max": None}
    if item_id is not None:
        delta_dates_stmt = select(FactDeltaChange.data_date.label("data_date")).where(
            FactDeltaChange.item_id == item_id
        )
        snapshot_dates_stmt = select(FactSnapshot.data_date.label("data_date")).where(
            FactSnapshot.item_id == item_id
        )
        if company:
            delta_dates_stmt = delta_dates_stmt.where(FactDeltaChange.company == company)
            snapshot_dates_stmt = snapshot_dates_stmt.where(
                FactSnapshot.company == company
            )
        if warehouses:
            delta_dates_stmt = delta_dates_stmt.where(
                FactDeltaChange.warehouse.in_(warehouses)
            )
            snapshot_dates_stmt = snapshot_dates_stmt.where(
                FactSnapshot.warehouse.in_(warehouses)
            )
        availability_subq = delta_dates_stmt.union_all(snapshot_dates_stmt).subquery()
        availability_stmt = select(
            func.min(availability_subq.c.data_date).label("min_date"),
            func.max(availability_subq.c.data_date).label("max_date"),
        )
        availability_row = session.execute(availability_stmt).one()
        availability_range = {
            "min": availability_row.min_date.isoformat()
            if availability_row.min_date
            else None,
            "max": availability_row.max_date.isoformat()
            if availability_row.max_date
            else None,
        }

    def _empty_series_response() -> dict[str, Any]:
        return {
            "item": item_data,
            "summary": {"rank": None, "sold_total": 0, "replenished_total": 0},
            "series": [],
            "available_range": availability_range,
        }

    if availability_range["min"] is None and availability_range["max"] is None:
        return _empty_series_response()

    calendar = (
        select(
            func.generate_series(
                date_from,
                date_to,
                text("interval '1 day'"),
            )
            .cast(Date)
            .label("data_date")
        )
        .subquery()
    )

    if warehouses:
        warehouse_subq = union_all(
            *[select(literal(warehouse).label("warehouse")) for warehouse in warehouses]
        ).subquery()
    else:
        snapshot_warehouses = (
            select(FactSnapshot.warehouse.label("warehouse"))
            .where(FactSnapshot.data_date >= date_from)
            .where(FactSnapshot.data_date <= date_to)
            .where(FactSnapshot.item_id == item_id)
        )
        delta_warehouses = (
            select(FactDeltaChange.warehouse.label("warehouse"))
            .where(FactDeltaChange.data_date >= date_from)
            .where(FactDeltaChange.data_date <= date_to)
            .where(FactDeltaChange.item_id == item_id)
        )
        if company:
            snapshot_warehouses = snapshot_warehouses.where(FactSnapshot.company == company)
            delta_warehouses = delta_warehouses.where(FactDeltaChange.company == company)
        warehouse_subq = snapshot_warehouses.union(delta_warehouses).subquery()

    delta_stmt = (
        select(
            FactDeltaChange.data_date.label("data_date"),
            FactDeltaChange.warehouse.label("warehouse"),
            func.sum(FactDeltaChange.sold_qty).label("sold"),
            func.sum(FactDeltaChange.replenished_qty).label("repl"),
        )
        .where(FactDeltaChange.data_date >= date_from)
        .where(FactDeltaChange.data_date <= date_to)
        .where(FactDeltaChange.item_id == item_id)
    )
    snapshot_stmt = (
        select(
            FactSnapshot.data_date.label("data_date"),
            FactSnapshot.warehouse.label("warehouse"),
            func.sum(FactSnapshot.stock_qty).label("stock"),
            func.avg(FactSnapshot.price).label("price"),
        )
        .where(FactSnapshot.data_date >= date_from)
        .where(FactSnapshot.data_date <= date_to)
        .where(FactSnapshot.item_id == item_id)
    )
    if company:
        delta_stmt = delta_stmt.where(FactDeltaChange.company == company)
        snapshot_stmt = snapshot_stmt.where(FactSnapshot.company == company)
    if warehouses:
        delta_stmt = delta_stmt.where(FactDeltaChange.warehouse.in_(warehouses))
        snapshot_stmt = snapshot_stmt.where(FactSnapshot.warehouse.in_(warehouses))

    delta_exists_stmt = (
        select(FactDeltaChange.data_date)
        .where(FactDeltaChange.data_date >= date_from)
        .where(FactDeltaChange.data_date <= date_to)
        .where(FactDeltaChange.item_id == item_id)
    )
    snapshot_exists_stmt = (
        select(FactSnapshot.data_date)
        .where(FactSnapshot.data_date >= date_from)
        .where(FactSnapshot.data_date <= date_to)
        .where(FactSnapshot.item_id == item_id)
    )
    if company:
        delta_exists_stmt = delta_exists_stmt.where(FactDeltaChange.company == company)
        snapshot_exists_stmt = snapshot_exists_stmt.where(
            FactSnapshot.company == company
        )
    if warehouses:
        delta_exists_stmt = delta_exists_stmt.where(
            FactDeltaChange.warehouse.in_(warehouses)
        )
        snapshot_exists_stmt = snapshot_exists_stmt.where(
            FactSnapshot.warehouse.in_(warehouses)
        )
    has_delta = session.execute(delta_exists_stmt.limit(1)).first()
    has_snapshot = session.execute(snapshot_exists_stmt.limit(1)).first()

    if not has_delta and not has_snapshot:
        return _empty_series_response()

    delta_stmt = (
        delta_stmt.group_by(FactDeltaChange.data_date, FactDeltaChange.warehouse)
        .subquery()
    )
    snapshot_stmt = (
        snapshot_stmt.group_by(FactSnapshot.data_date, FactSnapshot.warehouse)
        .subquery()
    )

    stmt = (
        select(
            calendar.c.data_date,
            warehouse_subq.c.warehouse,
            func.coalesce(delta_stmt.c.sold, 0).label("sold"),
            func.coalesce(delta_stmt.c.repl, 0).label("repl"),
            snapshot_stmt.c.stock,
            snapshot_stmt.c.price,
        )
        .select_from(calendar.join(warehouse_subq, true()))
        .outerjoin(
            delta_stmt,
            and_(
                delta_stmt.c.data_date == calendar.c.data_date,
                delta_stmt.c.warehouse == warehouse_subq.c.warehouse,
            ),
        )
        .outerjoin(
            snapshot_stmt,
            and_(
                snapshot_stmt.c.data_date == calendar.c.data_date,
                snapshot_stmt.c.warehouse == warehouse_subq.c.warehouse,
            ),
        )
        .order_by(warehouse_subq.c.warehouse, calendar.c.data_date)
    )
    rows = session.execute(stmt).mappings().all()
    series: list[dict[str, Any]] = []
    sold_total = 0
    replenished_total = 0
    for row in rows:
        sold_value = int(row.sold or 0)
        repl_value = int(row.repl or 0)
        sold_total += sold_value
        replenished_total += repl_value
        series.append(
            {
                "date": row.data_date.isoformat(),
                "warehouse": row.warehouse,
                "stock": int(row.stock) if row.stock is not None else None,
                "sold": sold_value,
                "repl": repl_value,
                "price": float(row.price) if row.price is not None else None,
            }
        )

    rank = None
    if item_id is not None:
        rank_stmt = (
            select(
                FactDeltaChange.item_id.label("item_id"),
                func.dense_rank()
                .over(order_by=func.sum(FactDeltaChange.sold_qty).desc())
                .label("rank"),
            )
            .where(FactDeltaChange.data_date >= date_from)
            .where(FactDeltaChange.data_date <= date_to)
        )
        if company:
            rank_stmt = rank_stmt.where(FactDeltaChange.company == company)
        if warehouses:
            rank_stmt = rank_stmt.where(FactDeltaChange.warehouse.in_(warehouses))
        rank_stmt = rank_stmt.group_by(FactDeltaChange.item_id).subquery()
        rank = session.execute(
            select(rank_stmt.c.rank).where(rank_stmt.c.item_id == item_id)
        ).scalar()
        if rank is not None:
            rank = int(rank)

    return {
        "item": item_data,
        "summary": {
            "rank": rank,
            "sold_total": sold_total,
            "replenished_total": replenished_total,
        },
        "series": series,
        "available_range": availability_range,
    }


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


def get_availability(session: Session, company: str | None) -> dict[str, str | None]:
    stmt = select(
        func.min(FactSnapshot.data_date).label("min_date"),
        func.max(FactSnapshot.data_date).label("max_date"),
    )
    if company:
        stmt = stmt.where(FactSnapshot.company == company)
    row = session.execute(stmt).one()
    min_date = row.min_date.isoformat() if row.min_date else None
    max_date = row.max_date.isoformat() if row.max_date else None
    return {"min": min_date, "max": max_date}


def get_top_sales(
    session: Session,
    limit: int,
    company: str | None = None,
    warehouses: list[str] | None = None,
    sku: str | None = None,
    manufacturer: str | None = None,
    name: str | None = None,
    project: str | None = None,
    group_by_warehouse: bool = True,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    group_by_columns = [
        Item.id,
        Item.canonical_sku,
        Item.name,
        Item.group_name,
    ]
    if group_by_warehouse:
        group_by_columns.append(FactDeltaChange.warehouse)

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
        sku_filter = or_(
            Item.canonical_sku == sku,
            Item.sku_norm.ilike(f"%{sku}%"),
        )
        snapshot_stmt = snapshot_stmt.where(sku_filter)
    if manufacturer:
        snapshot_stmt = snapshot_stmt.where(
            Item.manufacturer_norm.ilike(f"%{manufacturer}%")
        )
    if name:
        snapshot_stmt = snapshot_stmt.where(Item.name.ilike(f"%{name}%"))
    if project:
        snapshot_stmt = snapshot_stmt.where(Item.project_label == project)
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
        warehouse_column = func.coalesce(
            snapshot_subq.c.warehouse, FactDeltaChange.warehouse
        )
    else:
        warehouse_column = func.min(FactDeltaChange.warehouse)

    sold_total_expr = func.sum(FactDeltaChange.sold_qty)
    replenished_total_expr = func.sum(FactDeltaChange.replenished_qty)
    stmt = (
        select(
            Item.id.label("item_id"),
            Item.canonical_sku.label("canonical_sku"),
            Item.name,
            Item.group_name.label("group_name"),
            warehouse_column.label("warehouse"),
            sold_total_expr.label("sold_total"),
            replenished_total_expr.label("replenished_total"),
            func.max(snapshot_subq.c.last_price).label("last_price"),
            func.dense_rank()
            .over(order_by=sold_total_expr.desc())
            .label("rank"),
        )
        .join(Item, Item.id == FactDeltaChange.item_id)
        .outerjoin(snapshot_subq, join_condition)
        .group_by(*group_by_columns)
        .order_by(sold_total_expr.desc())
        .limit(limit)
    )

    if company:
        stmt = stmt.where(FactDeltaChange.company == company).where(Item.company == company)
    if warehouses:
        stmt = stmt.where(FactDeltaChange.warehouse.in_(warehouses))
    if sku:
        sku_filter = or_(
            Item.canonical_sku == sku,
            Item.sku_norm.ilike(f"%{sku}%"),
        )
        stmt = stmt.where(sku_filter)
    if manufacturer:
        stmt = stmt.where(Item.manufacturer_norm.ilike(f"%{manufacturer}%"))
    if name:
        stmt = stmt.where(Item.name.ilike(f"%{name}%"))
    if project:
        stmt = stmt.where(Item.project_label == project)
    if date_from:
        stmt = stmt.where(FactDeltaChange.data_date >= date_from)
    if date_to:
        stmt = stmt.where(FactDeltaChange.data_date <= date_to)

    rows = session.execute(stmt).mappings().all()
    items = []
    required_keys = (
        "rank",
        "item_id",
        "canonical_sku",
        "name",
        "group_name",
        "warehouse",
        "sold_total",
        "replenished_total",
        "last_price",
    )
    for row in rows:
        data = dict(row)
        for key in required_keys:
            data.setdefault(key, None)
        items.append(data)
    return items


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
