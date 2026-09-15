from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import backup_service

router = APIRouter(prefix="/backup", tags=["backup"])

MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # generous cap; a real backup is a DB snapshot, not media


@router.get("/export")
def export_backup(db: Session = Depends(get_db)):
    data, filename = backup_service.export_backup(db)
    return StreamingResponse(
        iter([data]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/restore", status_code=202)
async def restore_backup(file: UploadFile):
    if backup_service.get_restore_job().state == "running":
        raise HTTPException(status_code=409, detail="A restore is already running")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Backup file is too large")
    try:
        job = backup_service.start_restore(data)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return asdict(job)


@router.get("/restore/job")
def restore_job_status():
    return asdict(backup_service.get_restore_job())
