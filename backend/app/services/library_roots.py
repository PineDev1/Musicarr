from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LibraryRoot
from app.services.settings_service import library_root as primary_library_root


def list_extra_roots(db: Session) -> list[LibraryRoot]:
    return list(db.scalars(select(LibraryRoot).order_by(LibraryRoot.created_at.asc())).all())


def all_library_roots(db: Session) -> list[Path]:
    """Every folder scan/import/dedupe should look at — the primary library
    path first, then each configured extra root. Deduplicated by resolved
    path (an extra root that's a subdirectory of the primary, or an exact
    duplicate, would otherwise double-count every file under it)."""
    primary = primary_library_root(db)
    roots = [primary]
    seen = {primary}
    for row in list_extra_roots(db):
        try:
            path = Path(row.path).resolve()
        except OSError:
            continue
        if path in seen:
            continue
        if any(path == r or path in r.parents or r in path.parents for r in seen):
            continue
        if not path.is_dir():
            continue
        seen.add(path)
        roots.append(path)
    return roots


def add_root(db: Session, *, path: str, label: str = "") -> LibraryRoot:
    raw = (path or "").strip()
    if not raw:
        raise ValueError("Path required")
    resolved = Path(raw).expanduser()
    resolved.mkdir(parents=True, exist_ok=True)
    resolved = resolved.resolve()

    primary = primary_library_root(db)
    if resolved == primary:
        raise ValueError("This is already the primary library path")

    existing = db.scalar(select(LibraryRoot).where(LibraryRoot.path == str(resolved)))
    if existing:
        raise ValueError("This path is already added")

    row = LibraryRoot(path=str(resolved), label=(label or "").strip())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def remove_root(db: Session, root_id: int) -> None:
    row = db.get(LibraryRoot, root_id)
    if not row:
        raise ValueError("Library root not found")
    db.delete(row)
    db.commit()
