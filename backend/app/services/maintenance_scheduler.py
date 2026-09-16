from __future__ import annotations

import logging
import shutil
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings as app_config
from app.core.database import SessionLocal
from app.services import dedupe
from app.services.backup_service import export_backup
from app.services.history import add_history
from app.services.notifications import send_notification
from app.services.providers import get_provider
from app.services.settings_service import ensure_settings, library_root

logger = logging.getLogger("musicarr.maintenance")


def backups_dir() -> Path:
    d = app_config.data_dir / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_backup_job() -> dict:
    """Write a fresh backup to disk and prune old ones past the retention count."""
    db = SessionLocal()
    try:
        settings = ensure_settings(db)
        data, filename = export_backup(db)
        out_dir = backups_dir()
        out_path = out_dir / filename
        out_path.write_bytes(data)

        retention = max(1, int(getattr(settings, "backup_retention_count", 7) or 7))
        existing = sorted(out_dir.glob("musicarr-backup-*.zip"), key=lambda p: p.name)
        removed = 0
        for stale in existing[:-retention]:
            stale.unlink(missing_ok=True)
            removed += 1

        add_history(db, "backup_scheduled", f"Scheduled backup saved ({out_path.name})")
        return {"ok": True, "file": out_path.name, "pruned": removed}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Scheduled backup failed")
        try:
            send_notification(db, "Scheduled backup failed", str(exc), kind="maintenance")
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "error": str(exc)}
    finally:
        db.close()


def run_dedupe_scan_job() -> dict:
    """Weekly read-only scan; never deletes anything — just reports if the
    user has cleanup to do via /maintenance."""
    db = SessionLocal()
    try:
        result = dedupe.scan(db)
        orphan_db = len(result["orphan_db_tracks"])
        orphan_files = len(result["orphan_files"])
        dupes = len(result["duplicate_groups"])
        total = orphan_db + orphan_files + dupes
        if total:
            send_notification(
                db,
                "Library maintenance found items to review",
                f"{orphan_db} missing file(s), {orphan_files} orphan file(s), "
                f"{dupes} duplicate group(s) — review under Duplicate Cleanup.",
                kind="maintenance",
            )
        return {"ok": True, "orphan_db_tracks": orphan_db, "orphan_files": orphan_files,
                 "duplicate_groups": dupes}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Scheduled dedupe scan failed")
        return {"ok": False, "error": str(exc)}
    finally:
        db.close()


# Tracks last-known state across ticks so we notify once on a *transition*,
# not on every single check while a problem persists.
_last_disk_ok = True
_last_provider_ok: dict[str, bool] = {}


def run_health_check_job() -> dict:
    global _last_disk_ok, _last_provider_ok
    db = SessionLocal()
    try:
        settings = ensure_settings(db)
        threshold_bytes = max(1, int(getattr(settings, "low_disk_threshold_gb", 10) or 10)) * (1024**3)
        try:
            free_bytes = shutil.disk_usage(library_root(db)).free
        except OSError:
            free_bytes = None

        if free_bytes is not None:
            disk_ok = free_bytes >= threshold_bytes
            if not disk_ok and _last_disk_ok:
                gb_free = free_bytes / (1024**3)
                send_notification(
                    db,
                    "Low disk space",
                    f"Only {gb_free:.1f}GB free on the library disk.",
                    kind="health",
                )
            _last_disk_ok = disk_ok

        for provider_name in ("deezer", "tidal", "qobuz"):
            try:
                provider = get_provider(db, provider_name)
                ok, err = provider.validate_session()
            except Exception:  # noqa: BLE001
                ok, err = False, "provider unavailable"
            was_ok = _last_provider_ok.get(provider_name, True)
            if not ok and was_ok:
                send_notification(
                    db,
                    f"{provider_name.title()} authentication needs attention",
                    err or "Session is no longer valid — reconnect in Settings.",
                    kind="health",
                )
            _last_provider_ok[provider_name] = ok

        return {"ok": True, "disk_free_bytes": free_bytes}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Scheduled health check failed")
        return {"ok": False, "error": str(exc)}
    finally:
        db.close()


class MaintenanceScheduler:
    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler()
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        db = SessionLocal()
        try:
            settings = ensure_settings(db)
            backup_on = bool(getattr(settings, "backup_schedule_enabled", True))
            dedupe_on = bool(getattr(settings, "dedupe_scan_schedule_enabled", True))
        finally:
            db.close()

        if backup_on:
            self.scheduler.add_job(
                run_backup_job,
                "cron",
                hour=3,
                minute=0,
                id="backup_nightly",
                replace_existing=True,
                max_instances=1,
            )
        if dedupe_on:
            self.scheduler.add_job(
                run_dedupe_scan_job,
                "cron",
                day_of_week="sun",
                hour=4,
                minute=0,
                id="dedupe_scan_weekly",
                replace_existing=True,
                max_instances=1,
            )
        self.scheduler.add_job(
            run_health_check_job,
            "interval",
            minutes=30,
            id="health_check",
            replace_existing=True,
            max_instances=1,
        )
        self.scheduler.start()
        self._started = True
        logger.info("Maintenance scheduler started")

    def stop(self) -> None:
        if self._started:
            self.scheduler.shutdown(wait=False)
            self._started = False


maintenance_scheduler = MaintenanceScheduler()
