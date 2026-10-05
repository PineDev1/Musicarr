"""Undo for destructive file actions.

Deleting an album's files, an orphan file or a duplicate track used to be
permanent. Instead the file/folder is moved to <data_dir>/trash with a TrashItem
row remembering where it came from; it can be restored until it expires.
trash_retention_days = 0 turns this off (permanent delete, the old behaviour).
"""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings as app_config
from app.models import TrashItem
from app.services.settings_service import ensure_settings

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 30


class TrashError(Exception):
    pass


def trash_root() -> Path:
    d = app_config.data_dir / "trash"
    d.mkdir(parents=True, exist_ok=True)
    return d


def retention_days(db: Session) -> int:
    value = getattr(ensure_settings(db), "trash_retention_days", None)
    return DEFAULT_RETENTION_DAYS if value is None else max(0, int(value))


def _size(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
        total = 0
        for root, _dirs, files in os.walk(path):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass
        return total
    except OSError:
        return 0


def delete_or_trash(db: Session, path: str | Path, *, reason: str, label: str | None = None) -> str:
    """Remove `path`: park it in the trash when enabled, else delete for good.
    Returns 'trashed', 'deleted' or 'missing'. Never raises for a vanished path."""
    p = Path(path)
    if not p.exists():
        return "missing"
    if retention_days(db) <= 0:
        shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
        return "deleted"
    size = _size(p)
    dest_dir = trash_root() / f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
    dest_dir.mkdir(parents=True)
    dest = dest_dir / (p.name or "item")
    try:
        shutil.move(str(p), str(dest))  # shutil.move so a cross-filesystem move (library on another mount) works
    except OSError as exc:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise TrashError(f"Could not move {p.name} to the trash: {exc}") from exc
    db.add(
        TrashItem(
            original_path=str(p),
            trash_path=str(dest),
            label=(label or p.name)[:512],
            reason=reason[:64],
            is_dir=dest.is_dir(),
            size_bytes=size,
        )
    )
    db.commit()
    return "trashed"


def list_items(db: Session) -> list[TrashItem]:
    return list(db.scalars(select(TrashItem).order_by(TrashItem.deleted_at.desc(), TrashItem.id.desc())).all())


def _remove_payload(item: TrashItem) -> None:
    payload = Path(item.trash_path)
    # The whole timestamped wrapper folder goes, but only if it really is inside the trash.
    wrapper = payload.parent
    try:
        wrapper.resolve().relative_to(trash_root().resolve())
    except ValueError:
        logger.warning("Refusing to purge %s: not inside the trash folder", wrapper)
        return
    if wrapper != trash_root():
        shutil.rmtree(wrapper, ignore_errors=True)


def restore(db: Session, item_id: int) -> TrashItem:
    item = db.get(TrashItem, item_id)
    if not item:
        raise TrashError("Trash item not found")
    src = Path(item.trash_path)
    dest = Path(item.original_path)
    if not src.exists():
        db.delete(item)
        db.commit()
        raise TrashError("The trashed files are gone from disk")
    if dest.exists():
        raise TrashError(f"Something already exists at {dest}; move it first")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
    except OSError as exc:
        raise TrashError(f"Could not restore: {exc}") from exc
    _remove_payload(item)
    db.delete(item)
    db.commit()
    return item


def purge(db: Session, item_id: int) -> None:
    item = db.get(TrashItem, item_id)
    if not item:
        raise TrashError("Trash item not found")
    _remove_payload(item)
    db.delete(item)
    db.commit()


def empty(db: Session) -> int:
    items = list_items(db)
    for item in items:
        _remove_payload(item)
        db.delete(item)
    db.commit()
    return len(items)


def purge_expired(db: Session) -> int:
    """Delete trash older than the retention window."""
    days = retention_days(db)
    if days <= 0:
        return 0  # trash switched off: leave anything already there for a manual restore/empty
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    old = db.scalars(select(TrashItem).where(TrashItem.deleted_at < cutoff)).all()
    for item in old:
        _remove_payload(item)
        db.delete(item)
    db.commit()
    return len(old)
