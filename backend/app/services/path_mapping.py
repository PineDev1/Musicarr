from __future__ import annotations

import json
import logging
from pathlib import Path, PurePosixPath, PureWindowsPath

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RemotePathMapping

logger = logging.getLogger("musicarr.path_mapping")


def _normalize(path: str) -> str:
    """Unify separators and drop trailing slashes so prefixes compare cleanly."""
    text = (path or "").strip().replace("\\", "/")
    while len(text) > 1 and text.endswith("/"):
        text = text[:-1]
    return text


def map_remote_to_local(db: Session, remote_path: str, host: str | None = None) -> Path | None:
    """Translate a download client path into a path Musicarr can read.

    Uses the longest matching remote prefix so nested mappings win over their
    parents. When `host` is given, only mappings for that host (or with no
    host set, treated as a wildcard) are considered — otherwise two clients
    reporting paths under the same-looking remote prefix but needing
    different local mounts would silently resolve to whichever mapping row
    happens to have the longer prefix. Returns the original path when no
    mapping applies.
    """
    if not remote_path:
        return None
    normalized = _normalize(remote_path)
    rows = list(db.scalars(select(RemotePathMapping)).all())
    best: tuple[int, RemotePathMapping] | None = None
    for row in rows:
        row_host = (row.host or "").strip()
        if host is not None and row_host and row_host != host:
            continue
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


def seed_remote_path_mappings_from_env(db: Session, raw: str | None = None) -> int:
    """Apply MUSICARR_REMOTE_PATH_MAPPINGS on startup, same idea as Lidarr's
    Settings -> Download Clients -> Remote Path Mappings table, but settable
    from docker-compose for infra-as-code setups (a download client running
    in another container/host reports paths in its own filesystem, not
    Musicarr's — see README's "Remote path mappings" section).

    Expects a JSON array of {"host", "remote_path", "local_path"} objects.
    `host` may be omitted/empty for a wildcard mapping. Upserts by
    (host, remote_path): re-running with the same env value is a no-op, and
    changing local_path in the env and restarting updates the existing row —
    the env var is treated as the source of truth for rows it defines, same
    as any other MUSICARR_* setting. Invalid JSON/shape logs a warning and
    seeds nothing rather than blocking startup.
    """
    raw = raw if raw is not None else ""
    text = (raw or "").strip()
    if not text:
        return 0
    try:
        entries = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("MUSICARR_REMOTE_PATH_MAPPINGS is not valid JSON: %s", exc)
        return 0
    if not isinstance(entries, list):
        logger.warning("MUSICARR_REMOTE_PATH_MAPPINGS must be a JSON array")
        return 0

    applied = 0
    for entry in entries:
        if not isinstance(entry, dict):
            logger.warning("Skipping non-object MUSICARR_REMOTE_PATH_MAPPINGS entry: %r", entry)
            continue
        host = (entry.get("host") or "").strip()
        remote_path = (entry.get("remote_path") or "").strip()
        local_path = (entry.get("local_path") or "").strip()
        if not remote_path or not local_path:
            logger.warning(
                "Skipping MUSICARR_REMOTE_PATH_MAPPINGS entry missing remote_path/local_path: %r",
                entry,
            )
            continue
        row = db.scalar(
            select(RemotePathMapping).where(
                RemotePathMapping.host == host,
                RemotePathMapping.remote_path == remote_path,
            )
        )
        if row is None:
            db.add(RemotePathMapping(host=host, remote_path=remote_path, local_path=local_path))
        elif row.local_path != local_path:
            row.local_path = local_path
        applied += 1
    db.commit()
    return applied


def remote_basename(remote_path: str) -> str:
    """Last path component of a client-reported path, POSIX or Windows."""
    text = (remote_path or "").strip()
    if not text:
        return ""
    if "\\" in text and "/" not in text:
        return PureWindowsPath(text).name
    return PurePosixPath(text.replace("\\", "/")).name
