from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Album, Artist, DownloadJob, HistoryEvent, Track
from app.services.settings_service import ensure_settings


def _disk_usage_bytes(library_path: str) -> int:
    root = Path(library_path)
    if not root.is_dir():
        return 0
    total = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                continue
    return total


def compute_stats(db: Session) -> dict:
    settings = ensure_settings(db)

    artists_total = db.scalar(select(func.count()).select_from(Artist)) or 0
    tracks_total = db.scalar(select(func.count()).select_from(Track)) or 0

    albums_by_status: dict[str, int] = {}
    for status, count in db.execute(
        select(Album.status, func.count()).group_by(Album.status)
    ).all():
        albums_by_status[status] = count

    since = datetime.now(timezone.utc) - timedelta(days=30)
    job_counts: dict[str, int] = {}
    for state, count in db.execute(
        select(DownloadJob.state, func.count())
        .where(DownloadJob.created_at >= since)
        .group_by(DownloadJob.state)
    ).all():
        job_counts[state] = count
    completed = job_counts.get("completed", 0)
    failed = job_counts.get("failed", 0)
    denom = completed + failed
    success_rate_30d = (completed / denom) if denom else None

    recent_events = db.scalars(
        select(HistoryEvent).order_by(HistoryEvent.created_at.desc()).limit(10)
    ).all()

    return {
        "artists": artists_total,
        "albums_by_status": albums_by_status,
        "tracks": tracks_total,
        "disk_usage_bytes": _disk_usage_bytes(settings.library_path),
        "success_rate_30d": success_rate_30d,
        "recent_events": [
            {"event_type": e.event_type, "message": e.message, "created_at": e.created_at}
            for e in recent_events
        ],
    }
