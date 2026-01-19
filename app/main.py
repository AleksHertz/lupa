import logging
from datetime import date
from typing import Literal
from urllib.parse import parse_qsl, urlencode

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import NoSuchTableError, OperationalError, ProgrammingError
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from starlette.requests import Request

from app.db import get_session
from app.services.ingest import (
    IngestConflict,
    IngestError,
    IngestPersistenceError,
    ingest_excel,
)
from app.services.query import get_ingest_state, get_series, get_suggestions, get_top_sales


def _normalize_csv_list(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    expanded: list[str] = []
    for value in values:
        if value is None:
            continue
        parts = [part.strip() for part in value.split(",")]
        expanded.extend(part for part in parts if part)
    return expanded or None


def _normalize_query_string(query_string: bytes) -> bytes:
    if not query_string:
        return query_string
    params = parse_qsl(query_string.decode(), keep_blank_values=True)
    filtered = [(key, value) for key, value in params if value != ""]
    if len(filtered) == len(params):
        return query_string
    return urlencode(filtered, doseq=True).encode()


def _is_missing_schema_error(exc: Exception) -> bool:
    if isinstance(exc, NoSuchTableError):
        return True
    orig = getattr(exc, "orig", None)
    if orig is not None:
        pgcode = getattr(orig, "pgcode", None)
        if pgcode == "42P01":
            return True
        if "undefined_table" in str(orig):
            return True
    message = str(exc).lower()
    return "no such table" in message or "relation" in message and "does not exist" in message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Stock Delta Analyzer")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.middleware("http")
async def normalize_query_params(request: Request, call_next):
    request.scope["query_string"] = _normalize_query_string(
        request.scope.get("query_string", b"")
    )
    return await call_next(request)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    origin = request.headers.get("origin")
    logger.info("Request URL: %s; Origin: %s", request.url, origin)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled exception for %s", request.url)
        raise
    status_code = response.status_code
    if status_code >= 500:
        logger.error("Response status %s for %s", status_code, request.url)
    elif status_code >= 400:
        logger.warning("Response status %s for %s", status_code, request.url)
    else:
        logger.info("Response status %s for %s", status_code, request.url)
    return response


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/upload")
def upload_file(
    upload_date: date = Form(...),
    mode: Literal["reject", "bootstrap"] = Form("reject"),
    dry_run: bool = Query(False),
    company: str | None = Form(None),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    current_db = session.execute(text("select current_database()")).scalar()
    logger.debug("Current database: %s", current_db)
    try:
        payload = ingest_excel(
            session=session,
            upload_date=upload_date,
            file_bytes=file.file.read(),
            company=company,
            file_name=file.filename,
            mode=mode,
            dry_run=dry_run,
        )
    except (NoSuchTableError, OperationalError, ProgrammingError) as exc:
        if _is_missing_schema_error(exc):
            logger.exception("Database schema not migrated.")
            raise HTTPException(
                status_code=503,
                detail="DB schema not migrated",
            ) from exc
        raise
    except IngestConflict as exc:
        logger.warning("Upload conflict: %s", exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IngestPersistenceError as exc:
        logger.error("Upload persistence failure: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except IngestError as exc:
        logger.warning("Upload failed: %s", exc)
        if exc.report is not None:
            detail = {"message": str(exc), "validation_report": exc.report}
        else:
            detail = str(exc)
        raise HTTPException(status_code=400, detail=detail) from exc
    return payload


@app.get("/series")
def series(
    sku: str | None = Query(default=None),
    warehouses: list[str] | None = Query(default=None, alias="warehouse"),
    manufacturer: str | None = Query(default=None),
    project_label: str | None = Query(default=None),
    company: str | None = Query(default="alliance"),
    date_from: date = Query(...),
    date_to: date = Query(...),
    session: Session = Depends(get_session),
):
    warehouses = _normalize_csv_list(warehouses)
    return get_series(
        session=session,
        sku=sku,
        warehouses=warehouses,
        manufacturer=manufacturer,
        project_label=project_label,
        company=company,
        date_from=date_from,
        date_to=date_to,
    )


@app.get("/filters/suggestions")
def filter_suggestions(
    field: str = Query(..., description="sku, warehouse, manufacturer, name"),
    q: str = Query(""),
    company: str | None = Query(default="alliance"),
    session: Session = Depends(get_session),
):
    return {"items": get_suggestions(session=session, field=field, query=q, company=company)}


@app.get("/top")
def top_sales(
    limit: Literal[100, 500, 2000] = Query(100),
    company: str | None = Query(default="alliance"),
    warehouses: list[str] | None = Query(default=None, alias="warehouse"),
    sku: str | None = Query(default=None),
    name: str | None = Query(default=None),
    project_label: str | None = Query(default=None),
    group_by_warehouse: bool = Query(default=True),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    session: Session = Depends(get_session),
):
    warehouses = _normalize_csv_list(warehouses)
    return {
        "items": get_top_sales(
            session=session,
            limit=limit,
            company=company,
            warehouses=warehouses,
            sku=sku,
            name=name,
            project_label=project_label,
            group_by_warehouse=group_by_warehouse,
            date_from=date_from,
            date_to=date_to,
        )
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/db")
def health_db(session: Session = Depends(get_session)):
    tables_to_check = ("items", "fact_snapshot", "fact_delta_changes", "ingest_runs")
    try:
        session.execute(text("select 1"))
        tables = {
            table: session.execute(
                text("select to_regclass(:table_name)"),
                {"table_name": f"public.{table}"},
            ).scalar()
            is not None
            for table in tables_to_check
        }
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("Database health check failed.")
        return {"status": "error", "detail": str(exc)}

    missing_tables = [table for table, exists in tables.items() if not exists]
    if missing_tables:
        return {"status": "error", "detail": f"Missing tables: {', '.join(missing_tables)}"}

    return {"status": "ok", "tables": tables}


@app.get("/debug/ingest_state")
def ingest_state(
    company: str = Query(...),
    limit: int = Query(30, ge=1, le=366),
    session: Session = Depends(get_session),
):
    return get_ingest_state(session=session, company=company, limit=limit)
