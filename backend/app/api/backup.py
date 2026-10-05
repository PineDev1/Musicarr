from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import backup_service
from app.services.history import add_history

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


@router.get("/files")
def list_saved_backups():
    """Backups already on disk (the nightly job's output plus 'Back up now')."""
    return {"files": backup_service.list_backup_files()}


@router.post("/run")
def run_backup_now(db: Session = Depends(get_db)):
    if backup_service.get_restore_job().state == "running":
        raise HTTPException(status_code=409, detail="A restore is running")
    path = backup_service.save_backup_file(db)
    add_history(db, "backup_manual", f"Backup saved ({path.name})")
    return {"ok": True, "name": path.name, "size": path.stat().st_size}


def _saved_backup(name: str):
    try:
        return backup_service.backup_file_path(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Backup not found") from exc


@router.get("/files/{name}")
def download_saved_backup(name: str):
    path = _saved_backup(name)
    return FileResponse(path, media_type="application/zip", filename=path.name)


@router.delete("/files/{name}")
def delete_saved_backup(name: str, db: Session = Depends(get_db)):
    path = _saved_backup(name)
    path.unlink(missing_ok=True)
    add_history(db, "audit", f"Deleted saved backup {name}")
    return {"ok": True}


@router.post("/files/{name}/restore", status_code=202)
def restore_saved_backup(name: str, db: Session = Depends(get_db)):
    path = _saved_backup(name)
    try:
        job = backup_service.start_restore(path.read_bytes())
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    add_history(db, "audit", f"Restore started from saved backup {name}")
    return asdict(job)


@router.get("/restore/job")
def restore_job_status():
    return asdict(backup_service.get_restore_job())
