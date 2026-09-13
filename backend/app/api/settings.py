from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Album, Artist, DownloadJob
from app.models.schemas import HealthOut, SettingsOut, SettingsUpdate
from app.services.providers import get_provider
from app.services.settings_service import (
    ensure_settings,
    path_is_writable,
    settings_to_out,
    settings_to_out_validated,
    update_settings,
)

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db), validate: bool = False):
    row = ensure_settings(db)
    if validate:
        return settings_to_out_validated(db, row)
    return settings_to_out(row)


@router.put("/settings", response_model=SettingsOut)
def put_settings(payload: SettingsUpdate, db: Session = Depends(get_db)):
    row = update_settings(db, payload)
    return settings_to_out_validated(db, row)


@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)):
    row = ensure_settings(db)
    active = (row.active_provider or "deezer").lower()
    deezer_ok, deezer_error = get_provider(db, "deezer").validate_session()
    tidal_ok, tidal_error = get_provider(db, "tidal").validate_session()
    qobuz_ok, qobuz_error = get_provider(db, "qobuz").validate_session()
    mapping = {
        "deezer": (deezer_ok, deezer_error),
        "tidal": (tidal_ok, tidal_error),
        "qobuz": (qobuz_ok, qobuz_error),
    }
    provider_ok, provider_error = mapping.get(active, (False, "Unknown provider"))
    lib = Path(row.library_path)
    wanted = db.scalar(
        select(func.count())
        .select_from(Album)
        .where(Album.status == "wanted", Album.provider == active)
    ) or 0
    artists = db.scalar(
        select(func.count()).select_from(Artist).where(Artist.monitored.is_(True))
    ) or 0
    queue = db.scalar(
        select(func.count())
        .select_from(DownloadJob)
        .where(DownloadJob.state.in_(["queued", "running"]))
    ) or 0
    return HealthOut(
        status="ok" if path_is_writable(lib) else "degraded",
        active_provider=active,
        provider_ok=provider_ok,
        provider_error=provider_error,
        deezer_ok=deezer_ok,
        deezer_error=deezer_error,
        tidal_ok=tidal_ok,
        tidal_error=tidal_error,
        qobuz_ok=qobuz_ok,
        qobuz_error=qobuz_error,
        library_path=str(lib),
        library_writable=path_is_writable(lib),
        monitored_artists=artists,
        wanted_albums=wanted,
        queue_size=queue,
    )
