from __future__ import annotations

import io
import json
import logging
import os
import shutil
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from sqlalchemy import create_engine

from app.core.config import settings as app_config
from app.core.database import Base, migrate_schema
from app.models import AppSettings
from app.services.background_job import BackgroundJobStore, JobState, utc_now_iso
from app.services.settings_service import ensure_settings

logger = logging.getLogger("musicarr.backup")

BACKUP_SCHEMA_VERSION = 1

# Explicit allow-list of config that's safe to export. Every credential /
# session / secret field on AppSettings is deliberately left out — a restore
# never carries provider logins, so users re-authenticate providers
# afterward. Keep this list in sync by hand when AppSettings gains a new
# non-secret field; an allow-list means a forgotten new *secret* field fails
# safe (excluded) instead of leaking.
EXPORTABLE_SETTINGS_FIELDS = (
    "active_provider",
    "library_path",
    "bitrate",
    "folder_template",
    "track_template",
    "monitor_interval_minutes",
    "include_albums",
    "include_eps",
    "include_singles",
    "include_compilations",
    "min_track_count",
    "ignore_junk_titles",
    "ignore_live_releases",
    "official_releases_only",
    "mb_catalog_mode",
    "notify_webhook_url",
    "notify_channel",
    "notify_on_complete",
    "notify_on_failure",
    "upgrade_enabled",
    "fallback_providers_enabled",
    "media_refresh_url",
    "media_refresh_type",
    "auth_enabled",
    "auth_username",
    "ssl_enabled",
    "public_domain",
    "player_enabled",
    "player_sharing_enabled",
    "download_concurrency",
    "max_retries",
)

DB_ENTRY_NAME = "musicarr.db"
SETTINGS_ENTRY_NAME = "settings.json"
MANIFEST_ENTRY_NAME = "manifest.json"


def exportable_settings_dict(row: AppSettings) -> dict[str, Any]:
    return {field: getattr(row, field) for field in EXPORTABLE_SETTINGS_FIELDS}


SECRET_COLUMNS = (
    "arl",
    "tidal_access_token",
    "tidal_refresh_token",
    "tidal_expiry",
    "qobuz_email",
    "qobuz_user_id",
    "qobuz_user_auth_token",
    "qobuz_app_id",
    "qobuz_app_secret",
    "notify_token",
    "media_refresh_token",
    "auth_password_hash",
    "auth_secret",
)


def _snapshot_db_bytes(db_path: Path) -> bytes:
    """Consistent copy of the live (WAL-mode) SQLite file via the sqlite3
    backup API, which is safe to run while the app keeps writing to it —
    unlike copying the file directly, which can miss data still sitting in
    the -wal sidecar file. Blanks secret columns on the copy only.
    """
    import tempfile

    source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        dest = sqlite3.connect(str(tmp_path))
        try:
            source.backup(dest)
            assignments = ", ".join(f"{col} = ''" for col in SECRET_COLUMNS)
            dest.execute(f"UPDATE app_settings SET {assignments}")
            dest.commit()
        finally:
            dest.close()
        return tmp_path.read_bytes()
    finally:
        source.close()
        tmp_path.unlink(missing_ok=True)


def export_backup(db: Session) -> tuple[bytes, str]:
    """Build the backup zip in memory. Returns (bytes, suggested filename)."""
    row = ensure_settings(db)
    settings_json = json.dumps(exportable_settings_dict(row), indent=2, default=str)
    manifest = {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }

    db_path = app_config.data_dir / "musicarr.db"
    db_bytes = _snapshot_db_bytes(db_path)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MANIFEST_ENTRY_NAME, json.dumps(manifest, indent=2))
        zf.writestr(SETTINGS_ENTRY_NAME, settings_json)
        zf.writestr(DB_ENTRY_NAME, db_bytes)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"musicarr-backup-{stamp}.zip"
    return buf.getvalue(), filename


@dataclass
class RestoreJob(JobState):
    detail: str = ""


_store = BackgroundJobStore(
    job_factory=RestoreJob,
    persist_path=app_config.data_dir / "last_restore_job.json",
    thread_name="restore-job",
)


def get_restore_job() -> RestoreJob:
    return _store.get()


class RestoreError(Exception):
    pass


def _validate_and_stage(archive_bytes: bytes, staged_db_path: Path) -> dict[str, Any]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise RestoreError("That file isn't a valid backup archive") from exc

    names = set(zf.namelist())
    missing = {MANIFEST_ENTRY_NAME, SETTINGS_ENTRY_NAME, DB_ENTRY_NAME} - names
    if missing:
        raise RestoreError(f"Backup archive is missing: {', '.join(sorted(missing))}")

    try:
        manifest = json.loads(zf.read(MANIFEST_ENTRY_NAME))
    except json.JSONDecodeError as exc:
        raise RestoreError("Backup manifest is corrupt") from exc
    if int(manifest.get("schema_version") or 0) > BACKUP_SCHEMA_VERSION:
        raise RestoreError(
            "This backup was made by a newer version of Musicarr and can't be restored here."
        )

    try:
        settings_data = json.loads(zf.read(SETTINGS_ENTRY_NAME))
    except json.JSONDecodeError as exc:
        raise RestoreError("Backup settings.json is corrupt") from exc

    staged_db_path.parent.mkdir(parents=True, exist_ok=True)
    staged_db_path.write_bytes(zf.read(DB_ENTRY_NAME))

    # Confirm it actually opens and can be brought up to the current schema
    # (new tables/columns added since the backup was made), before we go
    # anywhere near replacing the live database.
    try:
        staged_engine = create_engine(
            f"sqlite:///{staged_db_path}", connect_args={"check_same_thread": False}
        )
        try:
            Base.metadata.create_all(bind=staged_engine)
            migrate_schema(engine_=staged_engine)
        finally:
            staged_engine.dispose()
        con = sqlite3.connect(str(staged_db_path))
        try:
            tables = {
                r[0]
                for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        finally:
            con.close()
    except sqlite3.DatabaseError as exc:
        raise RestoreError(f"Backup database is corrupt: {exc}") from exc

    required = {"app_settings", "artists", "albums", "tracks"}
    if not required.issubset(tables):
        raise RestoreError("Backup database is missing expected tables")

    return settings_data


def _apply_settings(staged_db_path: Path, settings_data: dict[str, Any]) -> None:
    con = sqlite3.connect(str(staged_db_path))
    try:
        cols = {row[1] for row in con.execute("PRAGMA table_info(app_settings)").fetchall()}
        fields = [f for f in EXPORTABLE_SETTINGS_FIELDS if f in settings_data and f in cols]
        if not fields:
            return
        assignments = ", ".join(f"{f} = ?" for f in fields)
        values = [settings_data[f] for f in fields]
        con.execute(f"UPDATE app_settings SET {assignments} WHERE id = 1", values)
        con.commit()
    finally:
        con.close()


def _run_restore(archive_bytes: bytes) -> None:
    live_db_path = app_config.data_dir / "musicarr.db"
    staged_db_path = app_config.data_dir / "musicarr.db.restoring"
    try:
        _store.update(phase="validating", message="Checking backup archive…", progress_pct=10)
        settings_data = _validate_and_stage(archive_bytes, staged_db_path)

        _store.update(phase="applying", message="Applying settings…", progress_pct=60)
        _apply_settings(staged_db_path, settings_data)

        _store.update(phase="swapping", message="Replacing library database…", progress_pct=85)
        backup_of_live = app_config.data_dir / "musicarr.db.before-restore"
        if live_db_path.exists():
            shutil.copy2(live_db_path, backup_of_live)
        os.replace(staged_db_path, live_db_path)
        for sidecar in ("-wal", "-shm"):
            stale = Path(str(live_db_path) + sidecar)
            stale.unlink(missing_ok=True)

        _store.update(
            state="done",
            phase="done",
            progress_pct=100,
            message="Restore complete. Restart Musicarr to load the restored library.",
            detail=f"Your previous database was kept as {backup_of_live.name} in case you need it.",
            finished_at=utc_now_iso(),
            error="",
        )
    except RestoreError as exc:
        logger.warning("Restore validation failed: %s", exc)
        _store.update(
            state="error",
            phase="error",
            error=str(exc),
            message=str(exc),
            finished_at=utc_now_iso(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Restore failed")
        _store.update(
            state="error",
            phase="error",
            error=str(exc),
            message="Restore failed unexpectedly",
            finished_at=utc_now_iso(),
        )
    finally:
        staged_db_path.unlink(missing_ok=True)


def start_restore(archive_bytes: bytes) -> RestoreJob:
    return _store.start(
        target=lambda: _run_restore(archive_bytes),
        initial={"phase": "starting", "message": "Starting restore…", "progress_pct": 1},
    )
