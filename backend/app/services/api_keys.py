from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ApiKey
from app.models.schemas import ApiKeyOut

KEY_PREFIX = "mcr_"


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def api_key_out(row: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(
        id=row.id,
        name=row.name,
        key_prefix=row.key_prefix,
        enabled=bool(row.enabled),
        created_at=row.created_at,
        last_used_at=row.last_used_at,
    )


def list_keys(db: Session) -> list[ApiKey]:
    return list(db.scalars(select(ApiKey).order_by(ApiKey.created_at.desc())).all())


def create_key(db: Session, *, name: str) -> tuple[str, ApiKey]:
    name = (name or "").strip()
    if not name:
        raise ValueError("Name required")
    raw = f"{KEY_PREFIX}{secrets.token_urlsafe(32)}"
    row = ApiKey(
        name=name,
        key_hash=_hash(raw),
        key_prefix=raw[: len(KEY_PREFIX) + 6],
        enabled=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return raw, row


def revoke_key(db: Session, key_id: int) -> None:
    row = db.get(ApiKey, key_id)
    if not row:
        raise ValueError("Key not found")
    db.delete(row)
    db.commit()


def verify_key(db: Session, raw: str | None) -> ApiKey | None:
    """Look up an enabled key by its raw value, touching last_used_at.

    Comparison is by hash lookup (indexed, effectively constant-time against
    guessing since it requires knowing the exact key already), not a
    linear scan with `==` on the raw value.
    """
    if not raw or not raw.startswith(KEY_PREFIX):
        return None
    row = db.scalar(select(ApiKey).where(ApiKey.key_hash == _hash(raw)))
    if not row or not row.enabled:
        return None
    row.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return row
