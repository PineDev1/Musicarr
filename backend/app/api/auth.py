from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas import QobuzLoginRequest, QobuzTokenLoginRequest, SettingsOut, TidalDeviceOut
from app.services.history import add_history
from app.services.providers import get_provider
from app.services.providers.base import ProviderError
from app.services.providers.qobuz import QobuzProvider
from app.services.providers.tidal import poll_tidal_device_login, start_tidal_device_login
from app.services.settings_service import ensure_settings, settings_to_out_validated

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/{provider}/logout", response_model=SettingsOut)
def logout(provider: str, db: Session = Depends(get_db)):
    try:
        get_provider(db, provider).logout()
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    add_history(db, "logout", f"Logged out of {provider}")
    return settings_to_out_validated(db, ensure_settings(db))


@router.post("/tidal/device", response_model=TidalDeviceOut)
def tidal_device_start(db: Session = Depends(get_db)):
    try:
        data = start_tidal_device_login(db)
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TidalDeviceOut(**data)


@router.get("/tidal/device/status")
def tidal_device_status(db: Session = Depends(get_db)):
    result = poll_tidal_device_login(db)
    if result.get("status") == "authenticated":
        add_history(db, "login", "Logged in to Tidal")
    return result


@router.post("/qobuz/token", response_model=SettingsOut)
def qobuz_token_login(payload: QobuzTokenLoginRequest, db: Session = Depends(get_db)):
    provider = get_provider(db, "qobuz")
    if not isinstance(provider, QobuzProvider):
        raise HTTPException(status_code=500, detail="Qobuz provider unavailable")
    try:
        provider.login_with_token(
            token=payload.token,
            user_id=payload.user_id,
            app_id=payload.app_id,
            app_secret=payload.app_secret,
        )
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    add_history(db, "login", "Logged in to Qobuz with token")
    return settings_to_out_validated(db, ensure_settings(db))


@router.post("/qobuz/login", response_model=SettingsOut)
def qobuz_login(payload: QobuzLoginRequest, db: Session = Depends(get_db)):
    provider = get_provider(db, "qobuz")
    if not isinstance(provider, QobuzProvider):
        raise HTTPException(status_code=500, detail="Qobuz provider unavailable")
    try:
        provider.login(payload.email, payload.password)
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    add_history(db, "login", f"Logged in to Qobuz as {payload.email}")
    return settings_to_out_validated(db, ensure_settings(db))
