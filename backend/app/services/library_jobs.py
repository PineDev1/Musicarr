from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.background_job import BackgroundJobStore, JobState, utc_now_iso
from app.services.library import import_existing_library, reorganize_library, scan_library

logger = logging.getLogger("musicarr.library_jobs")

ProgressCb = Callable[[dict[str, Any]], None]


@dataclass
class LibraryJob(JobState):
    """Adds library-import-specific counters to the shared job shape.

    `kind` distinguishes import | scan | reorganize.
    """

    files_seen: int = 0
    files_done: int = 0
    artists_created: int = 0
    albums_imported: int = 0
    tracks_linked: int = 0
    provider_linked: int = 0
    matched: int = 0
    unmatched: int = 0
    moved: int = 0
    skipped: int = 0
    result: dict[str, Any] = field(default_factory=dict)
    link_providers: bool = True


_store = BackgroundJobStore(
    job_factory=LibraryJob,
    persist_path=settings.data_dir / "last_library_job.json",
    thread_name="library-job",
)


def get_job() -> LibraryJob:
    return _store.get()


def job_dict() -> dict[str, Any]:
    return asdict(get_job())


def _apply_progress(updates: dict[str, Any]) -> None:
    counters = {
        "files_seen",
        "files_done",
        "artists_created",
        "albums_imported",
        "tracks_linked",
        "provider_linked",
        "matched",
        "unmatched",
        "moved",
        "skipped",
    }
    patch: dict[str, Any] = {}
    for key, value in updates.items():
        if key in {"phase", "message", "progress_pct"} or key in counters:
            patch[key] = value
    if patch:
        _store.update(**patch)


def _run_kind(kind: str, *, link_providers: bool = True) -> None:
    def on_progress(updates: dict[str, Any]) -> None:
        _apply_progress(updates)

    db = SessionLocal()
    try:
        if kind == "import":
            _store.update(phase="importing", message="Importing library…", progress_pct=5)
            result = import_existing_library(
                db, link_providers=link_providers, on_progress=on_progress
            )
        elif kind == "scan":
            _store.update(phase="scanning", message="Matching files…", progress_pct=5)
            result = scan_library(db, on_progress=on_progress)
        elif kind == "reorganize":
            _store.update(phase="moving", message="Reorganizing files…", progress_pct=5)
            result = reorganize_library(db, on_progress=on_progress)
        else:
            raise ValueError(f"Unknown library job kind: {kind}")

        _store.update(
            state="done",
            phase="done",
            progress_pct=100,
            message=str(result.get("message") or "Done"),
            finished_at=utc_now_iso(),
            files_seen=int(result.get("files_seen") or 0),
            artists_created=int(result.get("artists_created") or 0),
            albums_imported=int(result.get("albums_imported") or 0),
            tracks_linked=int(result.get("tracks_linked") or 0),
            provider_linked=int(result.get("provider_linked") or 0),
            matched=int(result.get("matched") or 0),
            unmatched=int(result.get("unmatched") or 0),
            moved=int(result.get("moved") or 0),
            skipped=int(result.get("skipped") or 0),
            result=dict(result),
            error="",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Library job %s failed", kind)
        _store.update(
            state="error",
            phase="error",
            error=str(exc),
            message=str(exc),
            finished_at=utc_now_iso(),
        )
    finally:
        db.close()


def start_library_job(kind: str, *, link_providers: bool = True) -> LibraryJob:
    kind = (kind or "").strip().lower()
    if kind not in {"import", "scan", "reorganize"}:
        raise ValueError("kind must be import, scan, or reorganize")
    if _store.is_running():
        raise RuntimeError("Library job already running")

    labels = {
        "import": "Importing existing library…",
        "scan": "Matching files to library…",
        "reorganize": "Reorganizing files…",
    }
    return _store.start(
        target=lambda: _run_kind(kind, link_providers=link_providers),
        initial={
            "kind": kind,
            "phase": "starting",
            "message": labels[kind],
            "progress_pct": 1,
            "link_providers": link_providers,
        },
    )
