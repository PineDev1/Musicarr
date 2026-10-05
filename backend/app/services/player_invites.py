from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PlayerInvite, PlayerUser
from app.services import player_auth

DEFAULT_DAYS = 7
MAX_DAYS = 30
MIN_PASSWORD = 8


class InviteError(ValueError):
    pass


def _hash(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def create_invite(db: Session, *, note: str = "", days: int = DEFAULT_DAYS) -> tuple[str, PlayerInvite]:
    days = max(1, min(int(days or DEFAULT_DAYS), MAX_DAYS))
    raw = secrets.token_urlsafe(24)
    row = PlayerInvite(
        token_hash=_hash(raw),
        note=(note or "").strip()[:128],
        expires_at=datetime.now(timezone.utc) + timedelta(days=days),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return raw, row


def status_of(row: PlayerInvite) -> str:
    if row.used_at is not None:
        return "used"
    if _aware(row.expires_at) < datetime.now(timezone.utc):
        return "expired"
    return "pending"


def list_invites(db: Session) -> list[PlayerInvite]:
    return list(db.scalars(select(PlayerInvite).order_by(PlayerInvite.created_at.desc())).all())


def revoke(db: Session, invite_id: int) -> None:
    row = db.get(PlayerInvite, invite_id)
    if not row:
        raise InviteError("Invite not found")
    db.delete(row)
    db.commit()


def find_usable(db: Session, token: str) -> PlayerInvite:
    """The invite for this raw token, or InviteError. Unknown, used and expired
    tokens all produce the same message so a guesser learns nothing."""
    row = db.scalar(select(PlayerInvite).where(PlayerInvite.token_hash == _hash(token)))
    if not row or status_of(row) != "pending":
        raise InviteError("This invite link is invalid or has expired")
    return row


def accept(db: Session, token: str, *, username: str, password: str, display_name: str = "") -> PlayerUser:
    row = find_usable(db, token)
    if len(password or "") < MIN_PASSWORD:
        raise InviteError(f"Password must be at least {MIN_PASSWORD} characters")
    try:
        user = player_auth.create_user(db, username=username, password=password, display_name=display_name)
    except ValueError as exc:
        raise InviteError(str(exc)) from exc
    # Single use: burn the invite right after the account exists.
    row.used_at = datetime.now(timezone.utc)
    row.used_by_user_id = user.id
    db.commit()
    return user
