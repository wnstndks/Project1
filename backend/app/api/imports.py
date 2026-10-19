import os
from dataclasses import asdict

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.config import get_settings
from app.deps import get_import_service
from app.schemas.imports import CommitIn, CommitOut, ImportStatusOut, PreviewOut
from app.services.screenshot_extractor import Image
from app.services.statement_import import MAX_IMAGE_BYTES, CommitRow, StatementImportService

router = APIRouter(prefix="/imports", tags=["imports"])


@router.get("/status", response_model=ImportStatusOut)
def status() -> ImportStatusOut:
    settings = get_settings()
    if settings.import_extractor == "fake":
        return ImportStatusOut(configured=True, model="demo (fake extractor)")
    configured = settings.anthropic_api_key is not None or bool(os.environ.get("ANTHROPIC_API_KEY"))
    return ImportStatusOut(configured=configured, model=settings.import_model)


@router.post("/screenshot", response_model=PreviewOut)
async def preview_screenshot(
    files: list[UploadFile] = File(...),
    service: StatementImportService = Depends(get_import_service),
):
    # The app never stores screenshots; Starlette's temporary upload buffer is discarded
    # when the request ends.
    images = [
        Image(data=await f.read(MAX_IMAGE_BYTES + 1), media_type=f.content_type or "")
        for f in files
    ]
    # The Claude call blocks for several seconds; keep it off the event loop.
    return asdict(await run_in_threadpool(service.preview, images))


@router.post("/commit", response_model=CommitOut)
def commit(body: CommitIn, service: StatementImportService = Depends(get_import_service)):
    rows = [CommitRow(**r.model_dump()) for r in body.rows]
    return CommitOut(created=len(service.commit(rows, body.trade_date)))
