from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings as app_config
from app.models import AppSettings
from app.models.schemas import SettingsOut, SettingsUpdate
from app.services.deezer_client import deezer_session, default_library_path


def ensure_settings(db: Session) -> AppSettings:
    row = db.get(AppSettings, 1)
    if row is None:
        row = AppSettings(
            id=1,
            library_path=default_library_path(),
            active_provider="deezer",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    elif not row.library_path:
        row.library_path = default_library_path()
        db.commit()
        db.refresh(row)
    if not getattr(row, "active_provider", None):
        row.active_provider = "deezer"
        db.commit()
        db.refresh(row)
    return row


def mask_arl(arl: str) -> str:
    if not arl:
        return ""
    if len(arl) <= 8:
        return "••••"
    return f"{arl[:4]}…{arl[-4:]}"


def settings_to_out(row: AppSettings, validate: bool = False) -> SettingsOut:
    return SettingsOut(
        active_provider=row.active_provider or "deezer",
        arl_set=bool(row.arl),
        arl_masked=mask_arl(row.arl or ""),
        tidal_logged_in=bool(row.tidal_access_token),
        qobuz_logged_in=bool(row.qobuz_user_auth_token),
        qobuz_email=row.qobuz_email or "",
        qobuz_user_id=getattr(row, "qobuz_user_id", "") or "",
        qobuz_app_id=row.qobuz_app_id or "",
        qobuz_app_secret_set=bool(row.qobuz_app_secret),
        qobuz_token_set=bool(row.qobuz_user_auth_token),
        library_path=row.library_path or default_library_path(),
        bitrate=row.bitrate,
        folder_template=row.folder_template,
        track_template=row.track_template,
        monitor_interval_minutes=row.monitor_interval_minutes,
        include_albums=row.include_albums,
        include_eps=row.include_eps,
        include_singles=row.include_singles,
        include_compilations=row.include_compilations,
        min_track_count=int(getattr(row, "min_track_count", 0) or 0),
        ignore_junk_titles=bool(getattr(row, "ignore_junk_titles", True)),
        ignore_live_releases=bool(getattr(row, "ignore_live_releases", False)),
        notify_webhook_url=getattr(row, "notify_webhook_url", "") or "",
        notify_on_complete=bool(getattr(row, "notify_on_complete", True)),
        notify_on_failure=bool(getattr(row, "notify_on_failure", True)),
        upgrade_enabled=bool(getattr(row, "upgrade_enabled", True)),
        media_refresh_url=getattr(row, "media_refresh_url", "") or "",
        media_refresh_token_set=bool(getattr(row, "media_refresh_token", "") or ""),
        media_refresh_type=getattr(row, "media_refresh_type", None) or "webhook",
        auth_enabled=bool(getattr(row, "auth_enabled", False)),
        auth_username=(getattr(row, "auth_username", None) or "admin"),
        auth_password_set=bool((getattr(row, "auth_password_hash", None) or "").strip()),
        ssl_enabled=bool(getattr(row, "ssl_enabled", False)),
        public_domain=(getattr(row, "public_domain", None) or ""),
        player_enabled=bool(getattr(row, "player_enabled", False)),
        download_concurrency=row.download_concurrency,
        max_retries=row.max_retries,
    )


def settings_to_out_validated(db: Session, row: AppSettings) -> SettingsOut:
    from app.services.providers import get_provider

    out = settings_to_out(row, validate=False)
    deezer_ok, deezer_error = get_provider(db, "deezer").validate_session()
    tidal_ok, tidal_error = get_provider(db, "tidal").validate_session()
    qobuz_ok, qobuz_error = get_provider(db, "qobuz").validate_session()
    active = (row.active_provider or "deezer").lower()
    mapping = {
        "deezer": (deezer_ok, deezer_error),
        "tidal": (tidal_ok, tidal_error),
        "qobuz": (qobuz_ok, qobuz_error),
    }
    provider_ok, provider_error = mapping.get(active, (False, "Unknown provider"))
    return out.model_copy(
        update={
            "deezer_ok": deezer_ok,
            "deezer_error": deezer_error,
            "tidal_ok": tidal_ok,
            "tidal_error": tidal_error,
            "qobuz_ok": qobuz_ok,
            "qobuz_error": qobuz_error,
            "provider_ok": provider_ok,
            "provider_error": provider_error,
        }
    )


def update_settings(db: Session, payload: SettingsUpdate) -> AppSettings:
    row = ensure_settings(db)
    data = payload.model_dump(exclude_unset=True)
    if "arl" in data:
        new_arl = (data.pop("arl") or "").strip()
        row.arl = new_arl
        deezer_session.invalidate()
    if "media_refresh_token" in data:
        token = (data.pop("media_refresh_token") or "").strip()
        if token:
            row.media_refresh_token = token
    if "auth_password" in data:
        password = (data.pop("auth_password") or "").strip()
        if password:
            from app.services.app_auth import hash_password

            row.auth_password_hash = hash_password(password)
    if "auth_username" in data:
        username = (data.pop("auth_username") or "").strip() or "admin"
        row.auth_username = username[:128]
    if "public_domain" in data:
        from app.services.proxy import normalize_public_domain

        row.public_domain = normalize_public_domain(data.pop("public_domain") or "")
    enabling = data.get("auth_enabled") is True
    for key, value in data.items():
        setattr(row, key, value)
    if enabling and not (row.auth_password_hash or "").strip():
        raise ValueError("Set a login password before enabling authentication")
    if row.library_path:
        Path(row.library_path).mkdir(parents=True, exist_ok=True)
    db.commit()
    db.refresh(row)
    return row


def library_root(db: Session) -> Path:
    row = ensure_settings(db)
    path = Path(row.library_path or default_library_path())
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def path_is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".musicarr_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def get_bitrate(db: Session) -> str:
    return ensure_settings(db).bitrate or "flac"
