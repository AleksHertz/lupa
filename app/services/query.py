import logging
import os
import unicodedata
from datetime import date, timedelta
from typing import Any

from cachetools import TTLCache
from sqlalchemy import and_, bindparam, func, literal, or_, select, text
from sqlalchemy.orm import Session

from app.models import FactDeltaChange, FactSnapshot, Item

PROJECT_GROUPS = {
    "Корея": [
        "ПРОЕКТ ЭЛЕКТРИКА\\СТАРТВОЛЬТ-ИНОМАРКИ",
        "ПРОЕКТ KOREA ЛЕГКОВЫЕ ОПТ\\MANDO-ЛЕГКОВОЙ ОБЩАЯ\\MANDO-КОНТРОЛЬ",
        "ПРОЕКТ CHINA\\CHINA-РТИ ОБЩАЯ\\CHINA-ПРОКЛАДКИ СИЛ",
        "ПРОЕКТ ИНОМАРКИ ГРУЗОВЫЕ ОПТ\\SAMPA",
        "ПРОЕКТ ИНОМАРКИ ГРУЗОВЫЕ ОПТ\\LUZAR-ИНОМАРКИ ГРУЗОВЫЕ",
        "ПРОЕКТ АВТОКОМПОНЕНТЫ\\PSP",
        "ПРОЕКТ ИНОМАРКИ ЛЕГКОВЫЕ ОПТ\\BOSCH ОБЩАЯ\\BOSCH ИНОМАРКИ ГРУЗ",
        "ПРОЕКТ РОЗНИЦА\\*ГРУППА ИНОМАРКИ ЛЕГКОВЫЕ ОБЩАЯ\\ECO-ИНОМАРКИ",
        "ПРОЕКТ KOREA ГРУЗОВЫЕ ОПТ\\HYUNDAI/KIA-ГРУЗОВОЙ ОБЩАЯ\\MOBIS KOREA-ГРУЗОВОЙ",
        "ПРОЕКТ MEGAPOWER ЗАПЧАСТИ\\MR-РК ТОРМ.НАКЛАДКИ",
        "ПРОЕКТ ЭЛЕКТРИКА\\ПРОЕКТ ЭЛЕКТРОСИЛА ОБЩАЯ\\TESLA-ГЕНЕРАТОРЫ СТАРТЕРА",
    ],
    "Китай": [
        "ПРОЕКТ КАМАЗ ГОРОД\\КИТАЙ-КАМАЗ",
        "ПРОЕКТ КИТАЙ ГРУЗОВЫЕ ОПТ\\SHACMAN OE",
        "ПРОЕКТ КИТАЙ ГРУЗОВЫЕ ОПТ\\HOWO SITRAK",
        "ПРОЕКТ КИТАЙ ГРУЗОВЫЕ ОПТ\\ПОДПРОЕКТ JAC ОБЩАЯ\\JAC-ГРУЗОВОЙ OE",
        "ПРОЕКТ КИТАЙ ГРУЗОВЫЕ ОПТ\\FAW OE",
        "ПРОЕКТ КИТАЙ ГРУЗОВЫЕ ОПТ\\ПОДПРОЕКТ JAC ОБЩАЯ\\JAC-ЛЕГКОВОЙ OE",
        "ПРОЕКТ КИТАЙ ГРУЗОВЫЕ ОПТ\\DONGFENG ОБЩАЯ\\DONGFENG OE",
        "ПРОЕКТ КИТАЙ ГРУЗОВЫЕ ОПТ\\FOTON OE",
        "ПРОЕКТ КИТАЙ ГРУЗОВЫЕ ОПТ\\MOVELEX-КИТАЙ ОБЩАЯ\\MOVELEX-JAC",
        "ПРОЕКТ КИТАЙ ГРУЗОВЫЕ ОПТ\\ПОДПРОЕКТ JAC ОБЩАЯ\\JAC-ЦС",
        "ПРОЕКТ КИТАЙ ГРУЗОВЫЕ ОПТ\\MOVELEX-КИТАЙ ОБЩАЯ\\MOVELEX-SHACMAN",
        "ПРОЕКТ КИТАЙ ГРУЗОВЫЕ ОПТ\\MOVELEX-КИТАЙ ОБЩАЯ\\MOVELEX-SITRAK",
        "ПРОЕКТ КИТАЙ ГРУЗОВЫЕ ОПТ\\ПОДПРОЕКТ JAC ОБЩАЯ\\КАМАЗ КОМПАС",
        "ПРОЕКТ КИТАЙ ГРУЗОВЫЕ ОПТ\\+КИТАЙ ГРУЗОВЫЕ ОПТ-УЦЕНКА",
        "ПРОЕКТ КИТАЙ ГРУЗОВЫЕ ОПТ\\+КИТАЙ ГРУЗОВЫЕ ОПТ-ЗАКРЫТО",
        "ПРОЕКТ КИТАЙ ГРУЗОВЫЕ ОПТ\\CREATEK",
        "ПРОЕКТ МАЗ\\КИТАЙ-МАЗ",
        "ПРОЕКТ ПНЕВМО\\ПНЕВМО-КИТАЙ",
        "ПРОЕКТ КИТАЙ ГРУЗОВЫЕ ОПТ\\WEICHAI",
    ],
}

PROJECT_PRESET_MAP = {
    "korea": PROJECT_GROUPS["Корея"],
    "china": PROJECT_GROUPS["Китай"],
}

SPRING_BASE_PATTERN = r'(^|[^а-яё])рессор(а|ы)?([^а-яё]|$)'
SPRING_TURBO_EXCLUDE_PATTERN = r'турбокомпрессор(а|ы|ов)?'
SPRING_SUBPRESET_PATTERNS = {
    "leaf": r"((^|[^а-яё])лист([^а-яё]|$).*(^|[^а-яё])рессор(а|ы)?([^а-яё]|$))|((^|[^а-яё])рессор(а|ы)?([^а-яё]|$).*(^|[^а-яё])лист([^а-яё]|$))",
    "bushing": r"((^|[^а-яё])втулк[аи]([^а-яё]|$).*(^|[^а-яё])рессор(а|ы)?([^а-яё]|$))|((^|[^а-яё])рессор(а|ы)?([^а-яё]|$).*(^|[^а-яё])втулк[аи]([^а-яё]|$))",
    "u_bolt": r"((^|[^а-яё])стремянк[аи]([^а-яё]|$).*(^|[^а-яё])рессор(а|ы)?([^а-яё]|$))|((^|[^а-яё])рессор(а|ы)?([^а-яё]|$).*(^|[^а-яё])стремянк[аи]([^а-яё]|$))",
    "spring": SPRING_BASE_PATTERN,
}
SPRING_EXTRA_EXCLUDE_KEYS = ("leaf", "bushing", "u_bolt")
DEBUG_PRESET = os.getenv("DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def resolve_project_groups(preset: str | None) -> list[str] | None:
    if not preset:
        return None
    return PROJECT_PRESET_MAP.get(preset.lower())


def _resolve_spring_filter(
    name_preset: str | None,
    spring_subpreset: str | None,
) -> tuple[str | None, tuple[str, ...], str | None]:
    if name_preset == "spring":
        if not spring_subpreset:
            return None, (), "spring_subpreset is required for name_preset='spring'"
        if spring_subpreset not in SPRING_SUBPRESET_PATTERNS:
            return None, (), "spring_subpreset must be one of: leaf, bushing, u_bolt, spring"
        return SPRING_SUBPRESET_PATTERNS[spring_subpreset], (), None
    if name_preset == "spring_extra":
        return (
            SPRING_BASE_PATTERN,
            tuple(SPRING_SUBPRESET_PATTERNS[key] for key in SPRING_EXTRA_EXCLUDE_KEYS),
            None,
        )
    return None, (), None




def _is_spring_query(q_norm: str | None, name_preset: str | None) -> bool:
    if name_preset in {"spring", "spring_extra"}:
        return True
    if not q_norm:
        return False
    return 'рессора' in q_norm.casefold() or 'рессоры' in q_norm.casefold()


def _apply_spring_name_regex(stmt: Any, *, param_prefix: str, include: bool) -> tuple[Any, str | None]:
    if not include:
        return stmt, None
    include_param = f"{param_prefix}_spring_word_pattern"
    exclude_param = f"{param_prefix}_spring_exclude_pattern"
    stmt = stmt.where(text(f"items.name ~* :{include_param}")).params(**{include_param: SPRING_BASE_PATTERN})
    stmt = stmt.where(text(f"NOT (items.name ~* :{exclude_param})")).params(**{exclude_param: SPRING_TURBO_EXCLUDE_PATTERN})
    return stmt, SPRING_BASE_PATTERN

def apply_name_presets(stmt: Any, name_preset: str | None, spring_subpreset: str | None) -> tuple[Any, dict[str, Any]]:
    logger.info(
        "Preset tunnel received: name_preset=%s spring_subpreset=%s",
        name_preset,
        spring_subpreset,
    )
    spring_pattern, spring_exclude_patterns, spring_error = _resolve_spring_filter(name_preset, spring_subpreset)
    if spring_error:
        raise ValueError(spring_error)
    applied = bool(spring_pattern)
    if spring_pattern:
        stmt = stmt.where(text("items.name ~* :spring_pattern")).params(spring_pattern=spring_pattern)
    for idx, exclude_pattern in enumerate(spring_exclude_patterns):
        stmt = stmt.where(text(f"NOT (items.name ~* :spring_exclude_pattern_{idx})")).params(
            **{f"spring_exclude_pattern_{idx}": exclude_pattern}
        )
    if spring_pattern:
        stmt = stmt.where(text("NOT (items.name ~* :spring_exclude_turbo_pattern)")).params(
            spring_exclude_turbo_pattern=SPRING_TURBO_EXCLUDE_PATTERN
        )
    logger.info(
        "Spring preset applied: %s pattern=%s",
        "yes" if applied else "no",
        spring_pattern or "—",
    )
    return stmt, {
        "spring_filter_applied": applied,
        "pattern": spring_pattern,
        "exclude_patterns": spring_exclude_patterns,
    }


def _log_spring_count_estimate(session: Session, item_ids_stmt: Any, name_preset: str | None, spring_subpreset: str | None) -> None:
    if not DEBUG_PRESET:
        return
    count_stmt = select(func.count()).select_from(item_ids_stmt.subquery())
    count_value = int(session.execute(count_stmt).scalar() or 0)
    logger.info(
        "Rows after spring preset filter (count estimate): %s",
        count_value,
        extra={"name_preset": name_preset, "spring_subpreset": spring_subpreset},
    )

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
    name_preset: str | None,
    spring_subpreset: str | None,
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
        name_preset,
        spring_subpreset,
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
    name_preset: str | None = None,
    spring_subpreset: str | None = None,
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
    stmt, _ = apply_name_presets(stmt, name_preset, spring_subpreset)
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
    name_preset: str | None = None,
    spring_subpreset: str | None = None,
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
        name_preset,
        spring_subpreset,
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
            name_preset=name_preset,
            spring_subpreset=spring_subpreset,
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
            name_preset=name_preset,
            spring_subpreset=spring_subpreset,
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


def build_series_query(
    session: Session,
    item_id: int | None,
    company: str | None,
    warehouses: list[str] | None,
    date_from: date,
    date_to: date,
    project_groups: list[str] | None = None,
    name_preset: str | None = None,
    spring_subpreset: str | None = None,
) -> tuple[Any | None, list[str], dict[str, str | None]]:
    if item_id is None:
        return None, [], {"min": None, "max": None}

    item_filter_stmt = select(Item.id).where(Item.id == item_id)
    if company:
        item_filter_stmt = item_filter_stmt.where(Item.company == company)
    item_filter_stmt, preset_meta = apply_name_presets(item_filter_stmt, name_preset, spring_subpreset)
    logger.info(
        "Series spring filter applied: %s pattern=%s",
        "yes" if preset_meta["spring_filter_applied"] else "no",
        preset_meta["pattern"] or "—",
    )
    if session.execute(item_filter_stmt.limit(1)).scalar() is None:
        return None, [], {"min": None, "max": None}

    project_item_ids_stmt = None
    if project_groups:
        project_item_ids_stmt = select(Item.id).where(Item.group_name.in_(project_groups))
        if company:
            project_item_ids_stmt = project_item_ids_stmt.where(Item.company == company)

    availability_filters = [FactSnapshot.item_id == item_id]
    delta_availability_filters = [FactDeltaChange.item_id == item_id]
    if company:
        availability_filters.append(FactSnapshot.company == company)
        delta_availability_filters.append(FactDeltaChange.company == company)
    if warehouses:
        availability_filters.append(FactSnapshot.warehouse.in_(warehouses))
        delta_availability_filters.append(FactDeltaChange.warehouse.in_(warehouses))
    if project_item_ids_stmt is not None:
        availability_filters.append(FactSnapshot.item_id.in_(project_item_ids_stmt))
        delta_availability_filters.append(FactDeltaChange.item_id.in_(project_item_ids_stmt))

    availability_snapshot = select(FactSnapshot.data_date.label("data_date")).where(
        *availability_filters
    )
    availability_delta = select(FactDeltaChange.data_date.label("data_date")).where(
        *delta_availability_filters
    )
    availability_subq = availability_snapshot.union_all(availability_delta).subquery()
    availability_row = session.execute(
        select(
            func.min(availability_subq.c.data_date).label("min_date"),
            func.max(availability_subq.c.data_date).label("max_date"),
        )
    ).one()
    availability_range = {
        "min": availability_row.min_date.isoformat() if availability_row.min_date else None,
        "max": availability_row.max_date.isoformat() if availability_row.max_date else None,
    }

    if warehouses:
        resolved_warehouses = list(warehouses)
    else:
        warehouse_snapshot_stmt = (
            select(FactSnapshot.warehouse.label("warehouse"))
            .where(FactSnapshot.item_id == item_id)
            .where(FactSnapshot.data_date >= date_from)
            .where(FactSnapshot.data_date <= date_to)
        )
        warehouse_delta_stmt = (
            select(FactDeltaChange.warehouse.label("warehouse"))
            .where(FactDeltaChange.item_id == item_id)
            .where(FactDeltaChange.data_date >= date_from)
            .where(FactDeltaChange.data_date <= date_to)
        )
        if company:
            warehouse_snapshot_stmt = warehouse_snapshot_stmt.where(
                FactSnapshot.company == company
            )
            warehouse_delta_stmt = warehouse_delta_stmt.where(
                FactDeltaChange.company == company
            )
        warehouse_union = warehouse_snapshot_stmt.union(warehouse_delta_stmt).subquery()
        resolved_warehouses = (
            session.execute(
                select(warehouse_union.c.warehouse)
                .distinct()
                .order_by(warehouse_union.c.warehouse)
            )
            .scalars()
            .all()
        )

    snapshot_filters = [
        FactSnapshot.item_id == item_id,
        FactSnapshot.data_date >= date_from,
        FactSnapshot.data_date <= date_to,
    ]
    delta_filters = [
        FactDeltaChange.item_id == item_id,
        FactDeltaChange.data_date >= date_from,
        FactDeltaChange.data_date <= date_to,
    ]
    if company:
        snapshot_filters.append(FactSnapshot.company == company)
        delta_filters.append(FactDeltaChange.company == company)
    if resolved_warehouses:
        snapshot_filters.append(FactSnapshot.warehouse.in_(resolved_warehouses))
        delta_filters.append(FactDeltaChange.warehouse.in_(resolved_warehouses))
    if project_item_ids_stmt is not None:
        snapshot_filters.append(FactSnapshot.item_id.in_(project_item_ids_stmt))
        delta_filters.append(FactDeltaChange.item_id.in_(project_item_ids_stmt))

    snapshot_subq = (
        select(
            FactSnapshot.data_date.label("data_date"),
            FactSnapshot.company.label("company"),
            FactSnapshot.warehouse.label("warehouse"),
            FactSnapshot.item_id.label("item_id"),
            func.sum(FactSnapshot.stock_qty).label("stock_qty"),
            func.avg(FactSnapshot.price).label("price"),
        )
        .where(*snapshot_filters)
        .group_by(
            FactSnapshot.data_date,
            FactSnapshot.company,
            FactSnapshot.warehouse,
            FactSnapshot.item_id,
        )
        .subquery()
    )
    delta_subq = (
        select(
            FactDeltaChange.data_date.label("data_date"),
            FactDeltaChange.company.label("company"),
            FactDeltaChange.warehouse.label("warehouse"),
            FactDeltaChange.item_id.label("item_id"),
            func.sum(FactDeltaChange.sold_qty).label("sold_qty"),
            func.sum(FactDeltaChange.replenished_qty).label("replenished_qty"),
        )
        .where(*delta_filters)
        .group_by(
            FactDeltaChange.data_date,
            FactDeltaChange.company,
            FactDeltaChange.warehouse,
            FactDeltaChange.item_id,
        )
        .subquery()
    )

    stmt = (
        select(
            snapshot_subq.c.data_date.label("data_date"),
            snapshot_subq.c.warehouse.label("warehouse"),
            snapshot_subq.c.stock_qty.label("stock_qty"),
            snapshot_subq.c.price.label("price"),
            func.coalesce(delta_subq.c.sold_qty, 0).label("sold_qty"),
            func.coalesce(delta_subq.c.replenished_qty, 0).label("replenished_qty"),
        )
        .select_from(
            snapshot_subq.outerjoin(
                delta_subq,
                and_(
                    snapshot_subq.c.data_date == delta_subq.c.data_date,
                    snapshot_subq.c.company == delta_subq.c.company,
                    snapshot_subq.c.warehouse == delta_subq.c.warehouse,
                    snapshot_subq.c.item_id == delta_subq.c.item_id,
                ),
            )
        )
        .order_by(snapshot_subq.c.data_date.asc(), snapshot_subq.c.warehouse.asc())
    )
    return stmt, resolved_warehouses, availability_range


def get_series_v2(
    session: Session,
    item_id: int | None,
    company: str | None,
    warehouses: list[str] | None,
    date_from: date,
    date_to: date,
    project_groups: list[str] | None = None,
    name_preset: str | None = None,
    spring_subpreset: str | None = None,
) -> dict[str, Any]:
    stmt, resolved_warehouses, availability_range = build_series_query(
        session=session,
        item_id=item_id,
        company=company,
        warehouses=warehouses,
        date_from=date_from,
        date_to=date_to,
        project_groups=project_groups,
        name_preset=name_preset,
        spring_subpreset=spring_subpreset,
    )
    if stmt is None:
        return {
            "item_id": None,
            "company": company,
            "warehouses": warehouses or [],
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "available_range": {"min": None, "max": None},
            "series": [],
        }

    logger.info(
        "Series normalized params",
        extra={
            "item_id": item_id,
            "company": company,
            "warehouses": warehouses,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        },
    )

    rows = session.execute(stmt).mappings().all()
    series = [
        {
            "date": row["data_date"].isoformat(),
            "warehouse": row["warehouse"],
            "stock_qty": int(row["stock_qty"]) if row["stock_qty"] is not None else 0,
            "price": float(row["price"]) if row["price"] is not None else 0.0,
            "sold_qty": int(row["sold_qty"] or 0),
            "replenished_qty": int(row["replenished_qty"] or 0),
        }
        for row in rows
    ]
    warehouses_seen = {entry["warehouse"] for entry in series}
    logger.info(
        "Series result summary",
        extra={
            "rows_count": len(series),
            "warehouses_count": len(warehouses_seen),
            "available_min": availability_range["min"],
            "available_max": availability_range["max"],
        },
    )

    return {
        "item_id": item_id,
        "company": company,
        "warehouses": resolved_warehouses,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "available_range": availability_range,
        "series": series,
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


def get_item_summary(
    session: Session,
    item_id: int,
    company: str | None = None,
) -> dict[str, Any] | None:
    stmt = (
        select(
            Item.id.label("item_id"),
            Item.canonical_sku.label("canonical_sku"),
            Item.name.label("name"),
            Item.manufacturer_norm.label("manufacturer"),
            Item.group_name.label("group_name"),
        )
        .where(Item.id == item_id)
        .limit(1)
    )
    if company:
        stmt = stmt.where(Item.company == company)
    row = session.execute(stmt).mappings().first()
    return dict(row) if row else None


def get_top_sales(
    session: Session,
    limit: int,
    offset: int = 0,
    company: str | None = None,
    warehouses: list[str] | None = None,
    sku: str | None = None,
    manufacturer: str | None = None,
    name: str | None = None,
    project: str | None = None,
    project_groups: list[str] | None = None,
    group_by_warehouse: bool = False,
    date_from: date | None = None,
    date_to: date | None = None,
    name_preset: str | None = None,
    spring_subpreset: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    q_norm = (q or "").strip()
    search_pattern = f"%{q_norm}%" if q_norm else None
    spring_query_filter = _is_spring_query(q_norm, name_preset)
    logger.info(
        "Top search input: q=%r normalized=%r filter_applied=%s spring_query_filter=%s",
        q,
        q_norm,
        bool(q_norm),
        spring_query_filter,
    )

    item_ids_stmt = None
    if sku or manufacturer or name or project or project_groups or company or name_preset or q_norm:
        item_ids_stmt = select(Item.id)
        if sku:
            sku_filter = or_(
                Item.canonical_sku == sku,
                Item.sku_norm.ilike(f"%{sku}%"),
            )
            item_ids_stmt = item_ids_stmt.where(sku_filter)
        if manufacturer:
            item_ids_stmt = item_ids_stmt.where(
                Item.manufacturer_norm.ilike(f"%{manufacturer}%")
            )
        if name:
            item_ids_stmt = item_ids_stmt.where(Item.name.ilike(f"%{name}%"))
        if project:
            item_ids_stmt = item_ids_stmt.where(Item.project_label == project)
        if project_groups:
            item_ids_stmt = item_ids_stmt.where(Item.group_name.in_(project_groups))
        if company:
            item_ids_stmt = item_ids_stmt.where(Item.company == company)
        item_ids_stmt, preset_meta = apply_name_presets(item_ids_stmt, name_preset, spring_subpreset)
        item_ids_stmt, q_spring_pattern = _apply_spring_name_regex(item_ids_stmt, param_prefix="top_item_ids", include=spring_query_filter)
        logger.info(
            "Top spring filter applied: %s pattern=%s q_spring_pattern=%s",
            "yes" if preset_meta["spring_filter_applied"] else "no",
            preset_meta["pattern"] or "—",
            q_spring_pattern or "—",
        )
        _log_spring_count_estimate(session, item_ids_stmt, name_preset, spring_subpreset)

    delta_filters = []
    if company:
        delta_filters.append(FactDeltaChange.company == company)
    if warehouses:
        delta_filters.append(FactDeltaChange.warehouse.in_(warehouses))
    if date_from:
        delta_filters.append(FactDeltaChange.data_date >= date_from)
    if date_to:
        delta_filters.append(FactDeltaChange.data_date <= date_to)
    if item_ids_stmt is not None:
        delta_filters.append(FactDeltaChange.item_id.in_(item_ids_stmt))

    agg_columns = [
        FactDeltaChange.item_id.label("item_id"),
        func.sum(FactDeltaChange.sold_qty).label("sold_total"),
        func.sum(FactDeltaChange.replenished_qty).label("replenished_total"),
    ]
    group_by_columns = [FactDeltaChange.item_id]
    if group_by_warehouse:
        agg_columns.insert(1, FactDeltaChange.warehouse.label("warehouse"))
        group_by_columns.append(FactDeltaChange.warehouse)

    agg_stmt = select(*agg_columns).select_from(FactDeltaChange)
    if delta_filters:
        agg_stmt = agg_stmt.where(and_(*delta_filters))
    agg_stmt = agg_stmt.group_by(*group_by_columns)
    agg_subq = agg_stmt.subquery()

    price_columns = [
        FactSnapshot.item_id.label("item_id"),
        FactSnapshot.price.label("last_price"),
        FactSnapshot.data_date.label("data_date"),
    ]
    price_distinct = [FactSnapshot.item_id]
    price_order_by = [FactSnapshot.item_id, FactSnapshot.data_date.desc()]
    if group_by_warehouse:
        price_columns.insert(1, FactSnapshot.warehouse.label("warehouse"))
        price_distinct.append(FactSnapshot.warehouse)
        price_order_by.insert(1, FactSnapshot.warehouse)

    price_stmt = (
        select(*price_columns)
        .select_from(FactSnapshot)
        .distinct(*price_distinct)
        .order_by(*price_order_by)
    )
    if company:
        price_stmt = price_stmt.where(FactSnapshot.company == company)
    if warehouses:
        price_stmt = price_stmt.where(FactSnapshot.warehouse.in_(warehouses))
    if date_from:
        price_stmt = price_stmt.where(FactSnapshot.data_date >= date_from)
    if date_to:
        price_stmt = price_stmt.where(FactSnapshot.data_date <= date_to)
    if item_ids_stmt is not None:
        price_stmt = price_stmt.where(FactSnapshot.item_id.in_(item_ids_stmt))

    last_price_subq = price_stmt.subquery()

    warehouse_column = (
        agg_subq.c.warehouse if group_by_warehouse else literal("ALL").label("warehouse")
    )
    join_condition = agg_subq.c.item_id == last_price_subq.c.item_id
    if group_by_warehouse:
        join_condition = and_(
            join_condition, agg_subq.c.warehouse == last_price_subq.c.warehouse
        )

    final_base_stmt = (
        select(
            agg_subq.c.item_id,
            Item.canonical_sku.label("canonical_sku"),
            Item.name,
            Item.group_name.label("group_name"),
            warehouse_column,
            agg_subq.c.sold_total,
            agg_subq.c.replenished_total,
            last_price_subq.c.last_price,
        )
        .select_from(agg_subq)
        .join(Item, Item.id == agg_subq.c.item_id)
        .outerjoin(last_price_subq, join_condition)
    )
    if company:
        final_base_stmt = final_base_stmt.where(Item.company == company)

    base_stmt = final_base_stmt

    if q_norm:
        if spring_query_filter:
            base_stmt, q_regex = _apply_spring_name_regex(base_stmt, param_prefix="top_base", include=True)
            logger.info("Top q spring regex applied: pattern=%s", q_regex)
        else:
            q_bind = bindparam("top_search_q_pattern", value=search_pattern)
            q_clauses = [
                Item.canonical_sku.ilike(q_bind),
                Item.name.ilike(q_bind),
            ]
            manufacturer_column = getattr(Item, "manufacturer", None)
            if manufacturer_column is not None:
                q_clauses.append(manufacturer_column.ilike(q_bind))
            elif hasattr(Item, "manufacturer_norm"):
                q_clauses.append(Item.manufacturer_norm.ilike(q_bind))
            base_stmt = base_stmt.where(or_(*q_clauses))

    count_subq = base_stmt.order_by(None).subquery()
    total_count = (
        session.execute(select(func.count()).select_from(count_subq)).scalar() or 0
    )
    logger.info("Top total_count(after all filters incl. q)=%s", total_count)

    base_subq = base_stmt.subquery()
    paged_stmt = (
        select(
            base_subq.c.item_id,
            base_subq.c.canonical_sku,
            base_subq.c.name,
            base_subq.c.group_name,
            base_subq.c.warehouse,
            base_subq.c.sold_total,
            base_subq.c.replenished_total,
            base_subq.c.last_price,
            func.dense_rank()
            .over(order_by=base_subq.c.sold_total.desc())
            .label("rank"),
        )
        .order_by(base_subq.c.sold_total.desc())
        .limit(limit)
        .offset(offset)
    )

    try:
        count_sql = str(
            select(func.count()).select_from(count_subq).compile(
                session.bind,
                compile_kwargs={"literal_binds": True},
            )
        )
        paged_sql = str(
            paged_stmt.compile(
                session.bind,
                compile_kwargs={"literal_binds": True},
            )
        )
    except Exception:
        logger.exception("Top SQL compile failed")
        count_sql = "<unavailable>"
        paged_sql = "<unavailable>"

    logger.info("Top count SQL: %s", count_sql)
    logger.info("Top paged SQL: %s", paged_sql)

    rows = session.execute(paged_stmt).mappings().all()
    logger.info(
        "Top page rows returned=%s filter_applied=%s",
        len(rows),
        bool(q_norm),
    )
    logger.info(
        "Top sales result summary",
        extra={"rows_count": len(rows), "total_count": total_count},
    )
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
    return {"items": items, "total_count": int(total_count)}


def get_latest_loaded_date(session: Session, company: str | None) -> str | None:
    stmt = select(func.max(FactSnapshot.data_date))
    if company:
        stmt = stmt.where(FactSnapshot.company == company)
    latest_date = session.execute(stmt).scalar()
    return latest_date.isoformat() if latest_date else None


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
