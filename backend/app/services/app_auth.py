from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Any

from fastapi import Response
from sqlalchemy.orm import Session

from app.services.settings_service import ensure_settings

COOKIE_NAME = "musicarr_session"
SESSION_DAYS = 14
PBKDF2_ROUNDS = 200_000


def hash_password(password: str, salt_hex: str | None = None) -> str:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not password:
        return False
    try:
        algo, salt_hex, digest = stored.split("$", 2)
    except ValueError:
        return False
    if algo != "pbkdf2":
        return False
    candidate = hash_password(password, salt_hex)
    return hmac.compare_digest(candidate, stored)


def ensure_auth_secret(db: Session) -> str:
    settings = ensure_settings(db)
    secret = (getattr(settings, "auth_secret", None) or "").strip()
    if not secret:
        secret = secrets.token_urlsafe(32)
        settings.auth_secret = secret
        db.commit()
        db.refresh(settings)
    return secret


def _sign(secret: str, payload: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def create_session_token(db: Session, username: str) -> str:
    secret = ensure_auth_secret(db)
    exp = int(time.time()) + SESSION_DAYS * 24 * 3600
    nonce = secrets.token_hex(8)
    payload = f"{username}|{exp}|{nonce}"
    return f"{payload}|{_sign(secret, payload)}"


def parse_session_token(db: Session, token: str | None) -> str | None:
    if not token or "|" not in token:
        return None
    parts = token.split("|")
    if len(parts) != 4:
        return None
    username, exp_s, nonce, sig = parts
    try:
        exp = int(exp_s)
    except ValueError:
        return None
    if exp < int(time.time()):
        return None
    secret = ensure_auth_secret(db)
    payload = f"{username}|{exp_s}|{nonce}"
    expected = _sign(secret, payload)
    if not hmac.compare_digest(sig, expected):
        return None
    settings = ensure_settings(db)
    expected_user = (getattr(settings, "auth_username", None) or "admin").strip() or "admin"
    if not hmac.compare_digest(username, expected_user):
        return None
    return username


def auth_enabled(db: Session) -> bool:
    settings = ensure_settings(db)
    return bool(getattr(settings, "auth_enabled", False))


def password_is_set(db: Session) -> bool:
    settings = ensure_settings(db)
    return bool((getattr(settings, "auth_password_hash", None) or "").strip())


def set_session_cookie(response: Response, token: str, db: Session) -> None:
    from app.services.proxy import cookie_domain_for_settings, ssl_enabled

    secure = ssl_enabled(db)
    domain = cookie_domain_for_settings(db)
    kwargs: dict = {
        "key": COOKIE_NAME,
        "value": token,
        "httponly": True,
        "samesite": "lax",
        "secure": secure,
        "max_age": SESSION_DAYS * 24 * 3600,
        "path": "/",
    }
    if domain:
        kwargs["domain"] = domain
    response.set_cookie(**kwargs)


def clear_session_cookie(response: Response, db: Session | None = None) -> None:
    kwargs: dict = {"key": COOKIE_NAME, "path": "/"}
    if db is not None:
        from app.services.proxy import cookie_domain_for_settings

        domain = cookie_domain_for_settings(db)
        if domain:
            kwargs["domain"] = domain
    response.delete_cookie(**kwargs)


def auth_status(db: Session, token: str | None) -> dict[str, Any]:
    enabled = auth_enabled(db)
    user = parse_session_token(db, token) if enabled else None
    settings = ensure_settings(db)
    return {
        "enabled": enabled,
        "authenticated": (not enabled) or bool(user),
        "username": user if user else ((getattr(settings, "auth_username", None) or "admin") if enabled else None),
        "password_set": password_is_set(db),
    }
