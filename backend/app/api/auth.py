from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas import (
    AppAuthStatus,
    AppLoginRequest,
    QobuzLoginRequest,
    QobuzTokenLoginRequest,
    SettingsOut,
    TidalDeviceOut,
)
from app.services import app_auth
from app.services.history import add_history
from app.services.providers import get_provider
from app.services.providers.base import ProviderError
from app.services.providers.qobuz import QobuzProvider
from app.services.providers.tidal import poll_tidal_device_login, start_tidal_device_login
from app.services.settings_service import ensure_settings, settings_to_out_validated

router = APIRouter(prefix="/auth", tags=["auth"])

KNOWN_PROVIDERS = {"deezer", "tidal", "qobuz"}


@router.get("/status", response_model=AppAuthStatus)
def app_auth_status(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(app_auth.COOKIE_NAME)
    return AppAuthStatus(**app_auth.auth_status(db, token))


@router.post("/login", response_model=AppAuthStatus)
def app_login(payload: AppLoginRequest, response: Response, db: Session = Depends(get_db)):
    if not app_auth.auth_enabled(db):
        raise HTTPException(status_code=400, detail="Login is disabled")
    settings = ensure_settings(db)
    expected_user = (getattr(settings, "auth_username", None) or "admin").strip() or "admin"
    username = (payload.username or "").strip()
    if not username or not hmac_compare(username, expected_user):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not app_auth.verify_password(payload.password, getattr(settings, "auth_password_hash", "") or ""):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = app_auth.create_session_token(db, expected_user)
    app_auth.set_session_cookie(response, token, db)
    add_history(db, "app_login", f"Signed in as {expected_user}")
    return AppAuthStatus(**app_auth.auth_status(db, token))


def hmac_compare(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(a, b)


@router.post("/logout-session", response_model=AppAuthStatus)
def app_logout_session(response: Response, db: Session = Depends(get_db)):
    app_auth.clear_session_cookie(response, db)
    return AppAuthStatus(**app_auth.auth_status(db, None))


@router.post("/{provider}/logout", response_model=SettingsOut)
def logout(provider: str, db: Session = Depends(get_db)):
    if provider not in KNOWN_PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider")
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
