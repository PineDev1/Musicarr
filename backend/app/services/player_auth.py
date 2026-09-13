from __future__ import annotations

import hmac
import secrets
import time
from typing import Any

from fastapi import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PlayerUser
from app.models.schemas import PlayerUserOut
from app.services.app_auth import hash_password, verify_password
from app.services.proxy import cookie_domain_for_settings, ssl_enabled
from app.services.settings_service import ensure_settings

COOKIE_NAME = "musicarr_player_session"
SESSION_DAYS = 30


def player_enabled(db: Session) -> bool:
    return bool(getattr(ensure_settings(db), "player_enabled", False))


def avatar_url_for_user(user: PlayerUser | None) -> str | None:
    if not user:
        return None
    path = getattr(user, "avatar_path", None)
    if path:
        return f"/api/player/avatars/{user.id}"
    return None


def player_user_out(user: PlayerUser) -> PlayerUserOut:
    return PlayerUserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name or "",
        is_active=bool(user.is_active),
        created_at=user.created_at,
        avatar_url=avatar_url_for_user(user),
    )


def ensure_player_secret(db: Session) -> str:
    # Reuse admin auth_secret store for HMAC signing (same app instance)
    settings = ensure_settings(db)
    secret = (getattr(settings, "auth_secret", None) or "").strip()
    if not secret:
        secret = secrets.token_urlsafe(32)
        settings.auth_secret = secret
        db.commit()
        db.refresh(settings)
    return secret + ":player"


def _sign(secret: str, payload: str) -> str:
    import hashlib

    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def create_session_token(db: Session, user: PlayerUser) -> str:
    secret = ensure_player_secret(db)
    exp = int(time.time()) + SESSION_DAYS * 24 * 3600
    nonce = secrets.token_hex(8)
    payload = f"{user.id}|{user.username}|{exp}|{nonce}"
    return f"{payload}|{_sign(secret, payload)}"


def parse_session_token(db: Session, token: str | None) -> PlayerUser | None:
    if not token or token.count("|") != 4:
        return None
    user_id_s, username, exp_s, nonce, sig = token.split("|")
    try:
        exp = int(exp_s)
        user_id = int(user_id_s)
    except ValueError:
        return None
    if exp < int(time.time()):
        return None
    secret = ensure_player_secret(db)
    payload = f"{user_id_s}|{username}|{exp_s}|{nonce}"
    if not hmac.compare_digest(sig, _sign(secret, payload)):
        return None
    user = db.get(PlayerUser, user_id)
    if not user or not user.is_active:
        return None
    if not hmac.compare_digest(user.username, username):
        return None
    return user


def set_session_cookie(response: Response, token: str, db: Session) -> None:
    kwargs: dict[str, Any] = {
        "key": COOKIE_NAME,
        "value": token,
        "httponly": True,
        "samesite": "lax",
        "secure": ssl_enabled(db),
        "max_age": SESSION_DAYS * 24 * 3600,
        "path": "/",
    }
    domain = cookie_domain_for_settings(db)
    if domain:
        kwargs["domain"] = domain
    response.set_cookie(**kwargs)


def clear_session_cookie(response: Response, db: Session | None = None) -> None:
    kwargs: dict[str, Any] = {"key": COOKIE_NAME, "path": "/"}
    if db is not None:
        domain = cookie_domain_for_settings(db)
        if domain:
            kwargs["domain"] = domain
    response.delete_cookie(**kwargs)


def auth_status(db: Session, token: str | None) -> dict[str, Any]:
    enabled = player_enabled(db)
    user = parse_session_token(db, token) if enabled else None
    return {
        "enabled": enabled,
        "authenticated": bool(user) if enabled else False,
        "username": user.username if user else None,
        "user_id": user.id if user else None,
        "display_name": (user.display_name or user.username) if user else None,
        "avatar_url": avatar_url_for_user(user),
    }


def list_users(db: Session) -> list[PlayerUser]:
    return list(db.scalars(select(PlayerUser).order_by(PlayerUser.username)).all())


def create_user(
    db: Session,
    *,
    username: str,
    password: str,
    display_name: str = "",
) -> PlayerUser:
    name = username.strip()
    if not name:
        raise ValueError("Username required")
    existing = db.scalar(select(PlayerUser).where(PlayerUser.username == name))
    if existing:
        raise ValueError("Username already exists")
    user = PlayerUser(
        username=name,
        password_hash=hash_password(password),
        display_name=(display_name or name).strip(),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(
    db: Session,
    user_id: int,
    *,
    password: str | None = None,
    display_name: str | None = None,
    is_active: bool | None = None,
) -> PlayerUser:
    user = db.get(PlayerUser, user_id)
    if not user:
        raise ValueError("User not found")
    if password is not None and password.strip():
        user.password_hash = hash_password(password.strip())
    if display_name is not None:
        user.display_name = display_name.strip()
    if is_active is not None:
        user.is_active = is_active
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user_id: int) -> None:
    user = db.get(PlayerUser, user_id)
    if not user:
        raise ValueError("User not found")
    db.delete(user)
    db.commit()


def authenticate(db: Session, username: str, password: str) -> PlayerUser | None:
    user = db.scalar(select(PlayerUser).where(PlayerUser.username == username.strip()))
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
