from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Album, Artist


def upcoming_releases(db: Session, days_back: int = 30, days_forward: int = 90) -> list[dict]:
    """Monitored artists' albums with a release_date in [-days_back, +days_forward].

    release_date is stored as a free-text "YYYY-MM-DD"-ish string but every
    provider populates it in ISO order, so plain string range comparison sorts
    and filters correctly without parsing.
    """
    today = datetime.now(timezone.utc).date()
    lo = (today - timedelta(days=days_back)).isoformat()
    hi = (today + timedelta(days=days_forward)).isoformat()

    rows = db.scalars(
        select(Album)
        .join(Artist, Album.artist_id == Artist.id)
        .options(joinedload(Album.artist))
        .where(
            Artist.monitored.is_(True),
            Album.release_date.is_not(None),
            Album.release_date >= lo,
            Album.release_date <= hi,
        )
        .order_by(Album.release_date.asc())
    ).unique().all()

    return [
        {
            "album_id": a.id,
            "title": a.title,
            "artist_id": a.artist_id,
            "artist_name": a.artist.name if a.artist else "",
            "release_date": a.release_date,
            "status": a.status,
            "cover_url": a.cover_url,
        }
        for a in rows
    ]
