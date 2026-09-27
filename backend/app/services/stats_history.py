from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Album, Artist, DownloadJob, HistoryEvent, Track


def _date_range(days: int) -> list[str]:
    today = datetime.now(timezone.utc).date()
    return [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]


def growth_series(db: Session, *, days: int = 90) -> list[dict]:
    """Daily new-artist and new-download counts, zero-filled for gaps."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    artists_by_day: dict[str, int] = {}
    for day, count in db.execute(
        select(func.date(Artist.added_at), func.count())
        .where(Artist.added_at >= since)
        .group_by(func.date(Artist.added_at))
    ).all():
        if day:
            artists_by_day[str(day)] = count

    # HistoryEvent already records a "downloaded" entry per completed import
    # (see download_queue.py / completed_download_handler.py) — a de facto
    # activity time series with no extra timestamp column needed.
    albums_by_day: dict[str, int] = {}
    for day, count in db.execute(
        select(func.date(HistoryEvent.created_at), func.count())
        .where(HistoryEvent.event_type == "downloaded", HistoryEvent.created_at >= since)
        .group_by(func.date(HistoryEvent.created_at))
    ).all():
        if day:
            albums_by_day[str(day)] = count

    return [
        {
            "date": day,
            "artists_added": artists_by_day.get(day, 0),
            "albums_downloaded": albums_by_day.get(day, 0),
        }
        for day in _date_range(days)
    ]


def download_trend(db: Session, *, days: int = 30) -> list[dict]:
    """Daily completed/failed download counts, zero-filled for gaps."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    completed_by_day: dict[str, int] = {}
    failed_by_day: dict[str, int] = {}
    for day, state, count in db.execute(
        select(func.date(DownloadJob.finished_at), DownloadJob.state, func.count())
        .where(
            DownloadJob.finished_at.is_not(None),
            DownloadJob.finished_at >= since,
            DownloadJob.state.in_(["completed", "failed"]),
        )
        .group_by(func.date(DownloadJob.finished_at), DownloadJob.state)
    ).all():
        if not day:
            continue
        if state == "completed":
            completed_by_day[str(day)] = count
        elif state == "failed":
            failed_by_day[str(day)] = count

    return [
        {
            "date": day,
            "completed": completed_by_day.get(day, 0),
            "failed": failed_by_day.get(day, 0),
        }
        for day in _date_range(days)
    ]


def _folder_size_bytes(path: str) -> int:
    root = Path(path)
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


def storage_breakdown(db: Session) -> list[dict]:
    """Bytes used by downloaded albums, grouped by quality.

    Walks each album's own folder rather than the whole library tree —
    cheaper than a full-library walk once there are more than a handful of
    albums, and gives per-quality attribution the whole-tree total can't.
    """
    rows = db.execute(
        select(Album.quality, Album.path).where(
            Album.status == "downloaded", Album.path.is_not(None), Album.path != ""
        )
    ).all()
    totals: dict[str, int] = {}
    for quality, path in rows:
        key = quality or "unknown"
        totals[key] = totals.get(key, 0) + _folder_size_bytes(path)
    return [
        {"quality": quality, "bytes": total_bytes}
        for quality, total_bytes in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    ]


def top_genres(db: Session, *, limit: int = 10) -> list[dict]:
    rows = db.execute(
        select(Track.genre, func.count())
        .where(Track.genre.is_not(None), Track.genre != "")
        .group_by(Track.genre)
        .order_by(func.count().desc())
        .limit(limit)
    ).all()
    return [{"genre": genre, "track_count": count} for genre, count in rows]
