from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Album, Artist, DownloadJob
from app.models.schemas import HealthOut, NotifyTestRequest, SettingsOut, SettingsUpdate
from app.services import app_auth
from app.services.download_queue import ACTIVE_JOB_STATES
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
def put_settings(
    payload: SettingsUpdate,
    response: Response,
    db: Session = Depends(get_db),
):
    was_enabled = app_auth.auth_enabled(db)
    try:
        row = update_settings(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    out = settings_to_out_validated(db, row)
    # When turning auth on, keep the current browser signed in
    if row.auth_enabled and (not was_enabled or payload.auth_password or payload.auth_username):
        username = (row.auth_username or "admin").strip() or "admin"
        token = app_auth.create_session_token(db, username)
        app_auth.set_session_cookie(response, token, db)
    if was_enabled and not row.auth_enabled:
        app_auth.clear_session_cookie(response, db)
    return out


@router.post("/settings/notify-test")
def notify_test(payload: NotifyTestRequest | None = None, db: Session = Depends(get_db)):
    from app.services.notifications import send_test_notification

    payload = payload or NotifyTestRequest()
    # Prefer whatever's currently in the form (even if unsaved) over the persisted value,
    # so "Send test notification" actually tests what the user is looking at.
    url = (payload.notify_webhook_url or "").strip()
    if not url:
        row = ensure_settings(db)
        url = (getattr(row, "notify_webhook_url", None) or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="Set a notification URL first")
    try:
        send_test_notification(
            db,
            webhook_url=payload.notify_webhook_url,
            channel=payload.notify_channel,
            token=payload.notify_token,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True}


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
        .where(DownloadJob.state.in_(ACTIVE_JOB_STATES))
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
