"""Ease-of-use helpers for the admin UI: update check, setup checklist,
diagnostics bundle and a directory browser for picking folders."""

from __future__ import annotations

import os
import platform
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import APP_VERSION
from app.core.config import settings as app_config
from app.models import (
    Album,
    Artist,
    DownloadClient,
    HistoryEvent,
    Indexer,
    LibraryRoot,
    PushSubscription,
    RemotePathMapping,
    Track,
)
from app.services import system_info
from app.services.settings_service import ensure_settings, library_root, path_is_writable

GITHUB_REPO = "PineDev1/Musicarr"
RELEASE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_UPDATE_TTL = 6 * 3600
_UPDATE_FAIL_TTL = 30 * 60

_update_lock = threading.Lock()
_update_cache: dict[str, Any] = {"at": 0.0, "ttl": 0, "data": None}


def iso_utc(dt: datetime | None) -> str | None:
    """ISO string that always carries a timezone. SQLite hands back naive
    datetimes; without a suffix JavaScript parses them as LOCAL time and every
    'expires'/'deleted' timestamp in the UI is off by the viewer's UTC offset."""
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


# ---------------------------------------------------------------- update check


def parse_version(text: str | None) -> tuple[int, ...]:
    """'v1.22.2' -> (1, 22, 2). Unparseable -> ()."""
    nums = re.findall(r"\d+", (text or "").split("-")[0])
    return tuple(int(n) for n in nums[:4])


def _fetch_latest_release() -> dict[str, Any] | None:
    try:
        resp = httpx.get(
            RELEASE_URL,
            timeout=5.0,
            headers={"Accept": "application/vnd.github+json", "User-Agent": f"Musicarr/{APP_VERSION}"},
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return {"tag": data.get("tag_name") or "", "url": data.get("html_url") or "", "name": data.get("name") or ""}
    except (httpx.HTTPError, ValueError):
        return None


def update_status(db: Session, *, force: bool = False) -> dict[str, Any]:
    """Compare the running version with the latest GitHub release. Does nothing
    network-wise when the user turned the check off; results are cached for 6h
    (30 min after a failure) so opening the UI never hammers GitHub."""
    enabled = bool(getattr(ensure_settings(db), "update_check_enabled", True))
    base = {"enabled": enabled, "current": APP_VERSION, "latest": None, "update_available": False, "url": None}
    if not enabled:
        return base
    now = time.time()
    with _update_lock:
        cached = _update_cache["data"]
        fresh = cached is not None or _update_cache["at"]
        if not force and fresh and now - _update_cache["at"] < _update_cache["ttl"]:
            release = cached
        else:
            release = _fetch_latest_release()
            _update_cache.update(at=now, data=release, ttl=_UPDATE_TTL if release else _UPDATE_FAIL_TTL)
    if not release:
        return base
    latest = release["tag"].lstrip("v")
    newer = parse_version(latest) > parse_version(APP_VERSION) and bool(parse_version(latest))
    return {**base, "latest": latest, "update_available": newer, "url": release["url"] or None}


def reset_update_cache() -> None:
    with _update_lock:
        _update_cache.update(at=0.0, ttl=0, data=None)


# ------------------------------------------------------------------- checklist


def setup_checklist(db: Session) -> dict[str, Any]:
    """Setup progress computed from stored settings/rows only — no network calls
    (provider/indexer connectivity has its own 'Test' buttons)."""
    row = ensure_settings(db)
    streaming = bool(getattr(row, "streaming_enabled", True))
    method = (getattr(row, "preferred_download_method", "streaming") or "streaming").lower()
    items: list[dict[str, Any]] = []

    def add(key: str, label: str, ok: bool, detail: str, link: str, *, required: bool = True) -> None:
        items.append(
            {
                "key": key,
                "label": label,
                "status": "ok" if ok else ("todo" if required else "optional"),
                "detail": detail,
                "link": link,
            }
        )

    lib = Path(row.library_path or "")
    lib_ok = bool(row.library_path) and lib.is_dir() and os.access(lib, os.W_OK)
    add(
        "library",
        "Library folder is writable",
        lib_ok,
        str(lib) if lib_ok else "Pick a folder Musicarr can write to (check the Docker volume mapping).",
        "/settings?tab=library",
    )

    provider_connected = bool(row.arl) or bool(row.tidal_access_token) or bool(row.qobuz_user_auth_token)
    indexers = db.scalar(select(func.count()).select_from(Indexer).where(Indexer.enabled.is_(True))) or 0
    clients = db.scalar(select(func.count()).select_from(DownloadClient).where(DownloadClient.enabled.is_(True))) or 0
    if streaming and method != "indexer":
        add(
            "source",
            "A streaming account is connected",
            provider_connected or indexers > 0,
            "Connected" if provider_connected else "Log in to Deezer, Tidal or Qobuz (or use indexers).",
            "/settings?tab=sources",
        )
    if method != "streaming" or not streaming:
        add("indexers", "At least one indexer is enabled", indexers > 0, f"{indexers} enabled", "/settings?tab=indexers")
        add(
            "client",
            "A download client is enabled",
            clients > 0,
            f"{clients} enabled" if clients else "Add qBittorrent or SABnzbd, then press Test.",
            "/settings?tab=indexers",
        )
        if clients:
            maps = db.scalar(select(func.count()).select_from(RemotePathMapping)) or 0
            add(
                "path_mapping",
                "Remote path mapping (only needed if the client runs elsewhere)",
                maps > 0,
                f"{maps} mapping(s)" if maps else "Skip this if the client sees the same folders as Musicarr.",
                "/settings?tab=indexers",
                required=False,
            )

    artists = db.scalar(select(func.count()).select_from(Artist).where(Artist.status != "pending")) or 0
    add("artists", "Your library has artists", artists > 0, f"{artists} artist(s)", "/add")

    notify = bool((row.notify_webhook_url or "").strip()) or bool(
        db.scalar(select(func.count()).select_from(PushSubscription))
    )
    add("notify", "Notifications are set up", notify, "Webhook or browser push" if notify else "Get told when downloads finish or fail.", "/settings?tab=notifications", required=False)

    has_backup = _has_saved_backup()
    add(
        "backup",
        "Backups are running",
        bool(getattr(row, "backup_schedule_enabled", True)) and has_backup,
        "Nightly backup on" if has_backup else "No saved backup yet — press Back up now.",
        "/settings?tab=backup",
        required=False,
    )
    add("auth", "Sign-in is required", bool(getattr(row, "auth_enabled", False)), "Protect the admin UI with a password." , "/settings?tab=security", required=False)

    done = sum(1 for i in items if i["status"] == "ok")
    required_left = sum(1 for i in items if i["status"] == "todo")
    return {"items": items, "done": done, "total": len(items), "required_left": required_left}


def _has_saved_backup() -> bool:
    from app.services import backup_service

    try:
        return bool(backup_service.list_backup_files())
    except OSError:
        return False


# ------------------------------------------------------------------ diagnostics

_SENSITIVE_KEY = re.compile(r"token|secret|key|password|hash|arl|webhook|url|email|username", re.I)


def _mask_settings(row) -> dict[str, Any]:
    from app.services.backup_service import EXPORTABLE_SETTINGS_FIELDS

    out: dict[str, Any] = {}
    for field in EXPORTABLE_SETTINGS_FIELDS:
        value = getattr(row, field, None)
        if _SENSITIVE_KEY.search(field):
            out[field] = "(set)" if value else "(empty)"
        else:
            out[field] = value
    return out


def diagnostics_bundle(db: Session, *, log_lines: int = 300) -> dict[str, Any]:
    """Everything useful for a bug report, with secrets masked. Settings are
    masked by field NAME (anything token/secret/key/password/url-like), logs go
    through system_info.redact via the ring buffer."""
    row = ensure_settings(db)
    status = system_info.system_status(str(library_root(db)))
    status.pop("argv", None)
    counts = {
        "artists": db.scalar(select(func.count()).select_from(Artist)) or 0,
        "albums": db.scalar(select(func.count()).select_from(Album)) or 0,
        "albums_wanted": db.scalar(select(func.count()).select_from(Album).where(Album.status == "wanted")) or 0,
        "tracks": db.scalar(select(func.count()).select_from(Track)) or 0,
        "library_roots": db.scalar(select(func.count()).select_from(LibraryRoot)) or 0,
        "path_mappings": db.scalar(select(func.count()).select_from(RemotePathMapping)) or 0,
    }
    indexers = [
        {"name": i.name, "protocol": i.protocol, "enabled": bool(i.enabled)}
        for i in db.scalars(select(Indexer)).all()
    ]
    clients = [
        {"name": c.name, "protocol": c.protocol, "enabled": bool(c.enabled)}
        for c in db.scalars(select(DownloadClient)).all()
    ]
    recent_problems = [
        {"time": e.created_at.isoformat() if e.created_at else None, "type": e.event_type, "message": system_info.redact(e.message)[:300]}
        for e in db.scalars(
            select(HistoryEvent)
            .where(HistoryEvent.event_type.in_(("download_failed", "error", "health_warning", "import_failed")))
            .order_by(HistoryEvent.created_at.desc())
            .limit(25)
        ).all()
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": APP_VERSION,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "in_docker": Path("/.dockerenv").exists(),
        "data_dir": str(app_config.data_dir),
        "status": status,
        "counts": counts,
        "settings": _mask_settings(row),
        "indexers": indexers,
        "download_clients": clients,
        "recent_problems": recent_problems,
        "logs": system_info.log_buffer.snapshot(limit=max(1, min(log_lines, 1000))),
        "note": "Secrets are masked. Review before sharing publicly.",
    }


# ------------------------------------------------------------- directory browse

_BLOCKED_PREFIXES = ("/proc", "/sys", "/dev")
MAX_DIR_ENTRIES = 500


def browse_directories(db: Session, path: str | None) -> dict[str, Any]:
    """List sub-FOLDERS only (never files) of an absolute path so the UI can offer
    a folder picker instead of typing container paths. Admin-only by route."""
    target = Path(path).expanduser() if path else library_root(db)
    if not target.is_absolute():
        raise ValueError("Path must be absolute")
    try:
        target = target.resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError("Path cannot be resolved") from exc
    if str(target).startswith(_BLOCKED_PREFIXES):
        raise ValueError("That location can't be browsed")
    if not target.is_dir():
        raise ValueError("Not a folder")

    entries: list[dict[str, str]] = []
    truncated = False
    error = None
    try:
        with os.scandir(target) as it:
            for entry in it:
                if entry.name.startswith("."):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=True):
                        entries.append({"name": entry.name, "path": str(Path(entry.path))})
                except OSError:
                    continue
                if len(entries) >= MAX_DIR_ENTRIES:
                    truncated = True
                    break
    except PermissionError:
        error = "Permission denied"
    except OSError as exc:
        error = str(exc)
    entries.sort(key=lambda e: e["name"].lower())

    shortcuts = [{"name": "Library", "path": str(library_root(db))}]
    for cand in (app_config.music_dir, Path("/music"), Path("/mnt"), Path("/media"), Path("/data"), Path.home()):
        try:
            resolved = Path(cand).resolve()
        except OSError:
            continue
        if resolved.is_dir() and all(s["path"] != str(resolved) for s in shortcuts):
            shortcuts.append({"name": resolved.name or str(resolved), "path": str(resolved)})
    parent = str(target.parent) if target.parent != target else None
    return {
        "path": str(target),
        "parent": parent,
        "writable": os.access(target, os.W_OK),
        "entries": entries,
        "truncated": truncated,
        "error": error,
        "shortcuts": shortcuts,
    }
