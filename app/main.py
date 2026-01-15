import logging
from datetime import date
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.db import get_session
from app.services.ingest import IngestConflict, IngestError, ingest_excel
from app.services.query import get_series, get_suggestions, get_top_sales

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
    except IngestConflict as exc:
        logger.warning("Upload conflict: %s", exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IngestError as exc:
        logger.warning("Upload failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return payload


@app.get("/series")
def series(
    sku: str | None = Query(default=None),
    warehouse: str | None = Query(default=None),
    manufacturer: str | None = Query(default=None),
    project_label: str | None = Query(default=None),
    company: str | None = Query(default=None),
    date_from: date = Query(...),
    date_to: date = Query(...),
    session: Session = Depends(get_session),
):
    return get_series(
        session=session,
        sku=sku,
        warehouse=warehouse,
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
    session: Session = Depends(get_session),
):
    return {"items": get_suggestions(session=session, field=field, query=q)}


@app.get("/top")
def top_sales(
    limit: Literal[100, 500, 2000] = Query(100),
    company: str | None = Query(default=None),
    warehouses: list[str] | None = Query(default=None, alias="warehouse"),
    sku: str | None = Query(default=None),
    name: str | None = Query(default=None),
    project_label: str | None = Query(default=None),
    group_by_warehouse: bool = Query(default=True),
    session: Session = Depends(get_session),
):
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
        )
    }


@app.get("/health")
def health():
    return {"status": "ok"}
