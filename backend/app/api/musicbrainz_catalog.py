from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import mb_catalog_import
from app.services.settings_service import ensure_settings, update_settings
from app.models.schemas import SettingsUpdate

router = APIRouter(prefix="/musicbrainz-catalog", tags=["musicbrainz-catalog"])


class CatalogModeUpdate(BaseModel):
    mode: str


@router.get("/status")
def catalog_status(db: Session = Depends(get_db)):
    settings = ensure_settings(db)
    mode = (getattr(settings, "mb_catalog_mode", None) or "local").strip() or "local"
    return mb_catalog_import.catalog_status(mode=mode)


@router.post("/check-version")
def check_version(db: Session = Depends(get_db)):
    settings = ensure_settings(db)
    mode = (getattr(settings, "mb_catalog_mode", None) or "local").strip() or "local"
    status = mb_catalog_import.catalog_status(mode=mode)
    try:
        latest = mb_catalog_import.fetch_latest_dump_version()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Could not reach MusicBrainz dumps: {exc}") from exc
    installed = status.get("dump_version") or ""
    return {
        "installed": installed,
        "latest": latest,
        "update_available": bool(latest) and latest != installed,
        "ready": status.get("ready"),
    }


@router.post("/update", status_code=202)
def start_update():
    job = mb_catalog_import.get_job()
    if job.state == "running":
        raise HTTPException(status_code=409, detail="Catalog update already running")
    job = mb_catalog_import.start_catalog_update()
    return job.__dict__


@router.get("/job")
def job_status():
    return mb_catalog_import.get_job().__dict__


@router.put("/mode")
def set_mode(payload: CatalogModeUpdate, db: Session = Depends(get_db)):
    mode = (payload.mode or "").strip().lower()
    if mode not in {"local", "live", "local_with_live_fallback"}:
        raise HTTPException(status_code=400, detail="Invalid mode")
    update_settings(db, SettingsUpdate(mb_catalog_mode=mode))  # type: ignore[arg-type]
    from app.services.musicbrainz import clear_cache

    # Cached lookups aren't keyed by mode, so a stale live-mode (or local-mode)
    # response could otherwise be served for up to the cache TTL after switching.
    clear_cache()
    return catalog_status(db)
