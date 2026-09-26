from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas import (
    AdminUserCreate,
    AdminUserOut,
    AdminUserUpdate,
    ApiKeyCreated,
    ApiKeyCreateRequest,
    ApiKeyOut,
    AppAuthStatus,
    AppLoginRequest,
    QobuzLoginRequest,
    QobuzTokenLoginRequest,
    SettingsOut,
    TidalDeviceOut,
    TotpConfirmRequest,
    TotpDisableRequest,
    TotpSetupOut,
)
from app.services import admin_auth, api_keys, app_auth
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
    token: str | None = None
    if (
        username
        and hmac_compare(username, expected_user)
        and app_auth.verify_password(payload.password, getattr(settings, "auth_password_hash", "") or "")
    ):
        token = app_auth.create_session_token(db, expected_user)
        add_history(db, "app_login", f"Signed in as {expected_user}")
    else:
        admin_user = admin_auth.authenticate(db, username, payload.password)
        if admin_user:
            if not admin_auth.verify_totp_for_login(admin_user, payload.totp_code):
                raise HTTPException(status_code=401, detail="totp_required")
            token = app_auth.create_session_token(db, admin_user.username, user_id=admin_user.id)
            add_history(db, "app_login", f"Signed in as {admin_user.username}")
    if not token:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    app_auth.set_session_cookie(response, token, db)
    return AppAuthStatus(**app_auth.auth_status(db, token))


def hmac_compare(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(a, b)


@router.post("/logout-session", response_model=AppAuthStatus)
def app_logout_session(response: Response, db: Session = Depends(get_db)):
    app_auth.clear_session_cookie(response, db)
    return AppAuthStatus(**app_auth.auth_status(db, None))


@router.get("/users", response_model=list[AdminUserOut])
def list_admin_users(db: Session = Depends(get_db)):
    return [admin_auth.admin_user_out(u) for u in admin_auth.list_users(db)]


@router.post("/users", response_model=AdminUserOut)
def create_admin_user(payload: AdminUserCreate, db: Session = Depends(get_db)):
    try:
        user = admin_auth.create_user(
            db, username=payload.username, password=payload.password, display_name=payload.display_name
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    add_history(db, "admin_user_added", f"Added admin user {user.username}")
    return admin_auth.admin_user_out(user)


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_admin_user(user_id: int, payload: AdminUserUpdate, db: Session = Depends(get_db)):
    try:
        user = admin_auth.update_user(
            db,
            user_id,
            password=payload.password,
            display_name=payload.display_name,
            is_active=payload.is_active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return admin_auth.admin_user_out(user)


@router.delete("/users/{user_id}")
def delete_admin_user(user_id: int, db: Session = Depends(get_db)):
    try:
        admin_auth.delete_user(db, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


def _current_admin_user_id(request: Request, db: Session) -> int:
    token = request.cookies.get(app_auth.COOKIE_NAME)
    user_id = app_auth.current_admin_user_id(db, token)
    if not user_id:
        raise HTTPException(
            status_code=400,
            detail="Two-factor login is only available for a named admin account "
            "(Settings → Security → Admin users), not the legacy admin/password login.",
        )
    return user_id


@router.post("/totp/setup", response_model=TotpSetupOut)
def totp_setup(request: Request, db: Session = Depends(get_db)):
    user_id = _current_admin_user_id(request, db)
    secret, url = admin_auth.start_totp_setup(db, user_id)
    return TotpSetupOut(secret=secret, otpauth_url=url)


@router.post("/totp/confirm")
def totp_confirm(payload: TotpConfirmRequest, request: Request, db: Session = Depends(get_db)):
    user_id = _current_admin_user_id(request, db)
    try:
        admin_auth.confirm_totp(db, user_id, payload.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    add_history(db, "totp_enabled", "Two-factor authentication enabled")
    return {"ok": True}


@router.post("/totp/disable")
def totp_disable(payload: TotpDisableRequest, request: Request, db: Session = Depends(get_db)):
    user_id = _current_admin_user_id(request, db)
    try:
        admin_auth.disable_totp(db, user_id, payload.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    add_history(db, "totp_disabled", "Two-factor authentication disabled")
    return {"ok": True}


@router.get("/api-keys", response_model=list[ApiKeyOut])
def list_api_keys(db: Session = Depends(get_db)):
    return [api_keys.api_key_out(k) for k in api_keys.list_keys(db)]


@router.post("/api-keys", response_model=ApiKeyCreated)
def create_api_key(payload: ApiKeyCreateRequest, db: Session = Depends(get_db)):
    try:
        raw, row = api_keys.create_key(db, name=payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    add_history(db, "api_key_created", f"Created API key '{row.name}'")
    return ApiKeyCreated(key=raw, info=api_keys.api_key_out(row))


@router.delete("/api-keys/{key_id}")
def delete_api_key(key_id: int, db: Session = Depends(get_db)):
    try:
        api_keys.revoke_key(db, key_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


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
