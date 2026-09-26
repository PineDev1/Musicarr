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
    # Read in chunks and bail out as soon as the cap is exceeded, instead of
    # buffering the whole body first — an unbounded upload would otherwise
    # grow the process's memory by the full body size before the 400 is ever
    # returned.
    chunks: list[bytes] = []
    total = 0
    chunk_size = 1024 * 1024
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail="Backup file is too large")
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    try:
        job = backup_service.start_restore(data)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return asdict(job)


@router.get("/restore/job")
def restore_job_status():
    return asdict(backup_service.get_restore_job())
