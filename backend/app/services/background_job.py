from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("musicarr.background_job")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class JobState:
    """Minimal shared job fields. Subclasses add domain fields."""

    state: str = "idle"  # idle | running | done | error
    kind: str = ""
    phase: str = ""
    progress_pct: float = 0.0
    message: str = ""
    error: str = ""
    started_at: str = ""
    finished_at: str = ""


class BackgroundJobStore:
    """In-memory singleton job + lock + optional JSON persist + restart interrupt."""

    def __init__(
        self,
        *,
        job_factory: Callable[[], Any],
        persist_path: Path | None = None,
        thread_name: str = "background-job",
    ) -> None:
        self._job_factory = job_factory
        self._persist_path = persist_path
        self._thread_name = thread_name
        self._lock = threading.Lock()
        self._job = job_factory()
        self._worker: threading.Thread | None = None
        self._restore_if_needed()

    def get(self) -> Any:
        with self._lock:
            return self._job_factory(**asdict(self._job))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self._job)

    def update(self, **kwargs: Any) -> None:
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self._job, key):
                    setattr(self._job, key, value)
            snap = asdict(self._job)
        self._persist(snap)

    def is_running(self) -> bool:
        with self._lock:
            return self._job.state == "running"

    def start(
        self,
        *,
        target: Callable[[], None],
        initial: dict[str, Any] | None = None,
    ) -> Any:
        with self._lock:
            if self._job.state == "running":
                raise RuntimeError("Job already running")
            if self._worker and self._worker.is_alive():
                raise RuntimeError("Job already running")
            fields_map = {f.name for f in fields(self._job)}
            reset = self._job_factory()
            for key, value in asdict(reset).items():
                if key in fields_map:
                    setattr(self._job, key, value)
            if initial:
                for key, value in initial.items():
                    if hasattr(self._job, key):
                        setattr(self._job, key, value)
            self._job.state = "running"
            self._job.started_at = utc_now_iso()
            self._job.finished_at = ""
            self._job.error = ""
            self._job.progress_pct = float(initial.get("progress_pct", 0) if initial else 0)
            snap = asdict(self._job)
            worker = threading.Thread(target=target, name=self._thread_name, daemon=True)
            self._worker = worker
        self._persist(snap)
        worker.start()
        return self.get()

    def _persist(self, snap: dict[str, Any] | None = None) -> None:
        if not self._persist_path:
            return
        data = snap if snap is not None else self.snapshot()
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._persist_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            logger.debug("Could not persist job state", exc_info=True)

    def _restore_if_needed(self) -> None:
        if not self._persist_path or not self._persist_path.is_file():
            return
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        with self._lock:
            if self._job.state == "running":
                return
            known = {f.name for f in fields(self._job)}
            kwargs = {k: v for k, v in data.items() if k in known}
            restored = self._job_factory(**kwargs)
            if restored.state == "running":
                restored.state = "error"
                restored.phase = "error"
                restored.error = restored.error or "Interrupted by process restart"
                restored.finished_at = utc_now_iso()
                restored.message = restored.error
            self._job = restored
        self._persist()
