from __future__ import annotations

import logging
import platform
import re
import shutil
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone

from app.core.config import APP_VERSION, settings as app_config

STARTED_AT = time.time()
LOG_CAPACITY = 1000

_SECRET_RE = re.compile(
    r"(?i)((?:api[_-]?key|apikey|arl|token|password|passwd|secret|authorization|cookie|session)"
    r"[\"']?\s*[=:]\s*[\"']?)([^\s&\"',;]+)"
)
_BEARER_RE = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")


_PATH_TOKEN_RE = re.compile(r"(/(?:cast|share)/)[A-Za-z0-9_-]{16,}")
# Subsonic clients put their credentials in short query params (t=token, s=salt,
# p=password); a logged token+salt pair can be replayed indefinitely.
_SUBSONIC_QS_RE = re.compile(r"([?&](?:t|s|p)=)[^&\s\"']+")


def redact(text: str) -> str:
    text = _PATH_TOKEN_RE.sub(lambda m: f"{m.group(1)}***", text)
    text = _SUBSONIC_QS_RE.sub(lambda m: f"{m.group(1)}***", text)
    text = _BEARER_RE.sub(lambda m: f"{m.group(1)} ***", text)
    return _SECRET_RE.sub(lambda m: f"{m.group(1)}***", text)


class RingBufferHandler(logging.Handler):
    def __init__(self, capacity: int = LOG_CAPACITY) -> None:
        super().__init__(level=logging.INFO)
        self._lock_buf = threading.Lock()
        self.records: deque[dict] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = redact(record.getMessage())
            if record.exc_info:
                msg += "\n" + redact(logging.Formatter().formatException(record.exc_info))
        except Exception:  # noqa: BLE001
            return
        with self._lock_buf:
            self.records.append(
                {
                    "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": msg,
                }
            )

    def snapshot(self, *, level: str | None = None, search: str | None = None, limit: int = 300):
        min_level = logging.getLevelName((level or "INFO").upper())
        if not isinstance(min_level, int):
            min_level = logging.INFO
        needle = (search or "").lower()
        with self._lock_buf:
            rows = list(self.records)
        out = [
            r
            for r in rows
            if logging.getLevelName(r["level"]) >= min_level
            and (not needle or needle in r["message"].lower() or needle in r["logger"].lower())
        ]
        return out[-limit:][::-1]


log_buffer = RingBufferHandler()


def install_log_buffer() -> None:
    root = logging.getLogger()
    if log_buffer not in root.handlers:
        root.addHandler(log_buffer)
    if root.level == logging.NOTSET or root.level > logging.INFO:
        root.setLevel(logging.INFO)


def _running_schedulers() -> list:
    from app.services.completed_download_handler import completed_download_handler
    from app.services.import_lists import import_list_runner
    from app.services.indexer_engine import wanted_indexer_sweep
    from app.services.maintenance_scheduler import maintenance_scheduler
    from app.services.monitor import release_monitor

    out = []
    for owner in (
        release_monitor,
        maintenance_scheduler,
        completed_download_handler,
        wanted_indexer_sweep,
        import_list_runner,
    ):
        sched = getattr(owner, "scheduler", None)
        if sched is not None and getattr(sched, "running", False):
            out.append(sched)
    return out


def run_task_now(task_id: str) -> bool:
    """Ask the owning scheduler to fire a job immediately (its own enable
    flags are still honoured inside the job). Returns False for unknown ids."""
    for sched in _running_schedulers():
        job = sched.get_job(task_id)
        if job is not None:
            job.modify(next_run_time=datetime.now(timezone.utc))
            return True
    return False


def _scheduled_tasks() -> list[dict]:
    labels = {
        "backup_nightly": "Nightly backup",
        "dedupe_scan_weekly": "Weekly duplicate scan",
        "health_check": "Health check (disk, provider session)",
    }
    tasks: list[dict] = []
    for sched in _running_schedulers():
        for job in sched.get_jobs():
            nxt = getattr(job, "next_run_time", None)
            tasks.append(
                {
                    "id": job.id,
                    "name": labels.get(job.id, job.id.replace("_", " ").capitalize()),
                    "trigger": str(job.trigger),
                    "next_run": nxt.isoformat() if nxt else None,
                }
            )
    return sorted(tasks, key=lambda t: t["next_run"] or "9")


def system_status(library_path: str | None) -> dict:
    db_file = app_config.data_dir / "musicarr.db"
    disk = None
    if library_path:
        try:
            u = shutil.disk_usage(library_path)
            disk = {"path": library_path, "free": u.free, "total": u.total}
        except OSError:
            disk = None
    return {
        "version": APP_VERSION,
        "python": platform.python_version(),
        "platform": f"{platform.system()} {platform.release()}",
        "uptime_seconds": int(time.time() - STARTED_AT),
        "data_dir": str(app_config.data_dir),
        "db_bytes": db_file.stat().st_size if db_file.exists() else 0,
        "disk": disk,
        "tasks": _scheduled_tasks(),
        "argv": sys.argv[0] if sys.argv else "",
    }
