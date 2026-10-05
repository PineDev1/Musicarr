from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import server_tools
from app.services.history import audit

router = APIRouter(tags=["server-tools"])


@router.get("/system/update")
def update_status(refresh: bool = False, db: Session = Depends(get_db)):
    """Is a newer Musicarr release available? (Cached; off when the setting is off.)"""
    return server_tools.update_status(db, force=refresh)


@router.get("/system/checklist")
def setup_checklist(db: Session = Depends(get_db)):
    return server_tools.setup_checklist(db)


@router.get("/system/diagnostics")
def download_diagnostics(logs: int = 300, db: Session = Depends(get_db)):
    """Secrets-masked JSON for bug reports (version, counts, settings, logs)."""
    bundle = server_tools.diagnostics_bundle(db, log_lines=logs)
    audit(db, "Diagnostics bundle downloaded")
    stamp = bundle["generated_at"][:19].replace(":", "").replace("-", "").replace("T", "-")
    return Response(
        content=json.dumps(bundle, indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="musicarr-diagnostics-{stamp}.json"'},
    )


@router.get("/fs/browse")
def browse_folders(path: str | None = None, db: Session = Depends(get_db)):
    """Sub-folders of `path` (folders only) for the folder picker."""
    try:
        return server_tools.browse_directories(db, path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
