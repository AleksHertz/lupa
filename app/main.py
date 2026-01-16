import logging
from datetime import date
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import NoSuchTableError, OperationalError, ProgrammingError
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.db import get_session
from app.services.ingest import IngestConflict, IngestError, ingest_excel
from app.services.query import get_series, get_suggestions, get_top_sales


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
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/upload")
def upload_file(
    upload_date: date = Form(...),
    mode: Literal["reject", "merge", "replace"] = Form("reject"),
    company: str | None = Form(None),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    try:
        payload = ingest_excel(
            session=session,
            upload_date=upload_date,
            file_bytes=file.file.read(),
            company=company,
            file_name=file.filename,
            mode=mode,
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
