from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RemotePathMapping


def _normalize(path: str) -> str:
    """Unify separators and drop trailing slashes so prefixes compare cleanly."""
    text = (path or "").strip().replace("\\", "/")
    while len(text) > 1 and text.endswith("/"):
        text = text[:-1]
    return text


def map_remote_to_local(db: Session, remote_path: str) -> Path | None:
    """Translate a download client path into a path Musicarr can read.

    Uses the longest matching remote prefix so nested mappings win over their
    parents. Returns the original path when no mapping applies.
    """
    if not remote_path:
        return None
    normalized = _normalize(remote_path)
    rows = list(db.scalars(select(RemotePathMapping)).all())
    best: tuple[int, RemotePathMapping] | None = None
    for row in rows:
        remote = _normalize(row.remote_path or "")
        if not remote:
            continue
        if normalized == remote or normalized.startswith(f"{remote}/"):
            if best is None or len(remote) > best[0]:
                best = (len(remote), row)
    if best is None:
        return Path(remote_path)

    remote = _normalize(best[1].remote_path or "")
    local = _normalize(best[1].local_path or "")
    if not local:
        return Path(remote_path)
    remainder = normalized[len(remote) :].lstrip("/")
    return Path(local) / remainder if remainder else Path(local)


def remote_basename(remote_path: str) -> str:
    """Last path component of a client-reported path, POSIX or Windows."""
    text = (remote_path or "").strip()
    if not text:
        return ""
    if "\\" in text and "/" not in text:
        return PureWindowsPath(text).name
    return PurePosixPath(text.replace("\\", "/")).name
