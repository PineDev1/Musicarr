"""Genre and mood browsing for the Player — a first-class "Explore" surface
instead of only artist/album/search, built entirely from the genre tag
already read off each downloaded file (library.py's tag reader)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Track

# Coarse, heuristic genre -> mood buckets. A genre can match more than one
# mood; a track counts toward every mood whose keyword appears in its genre
# string. Approximate by nature (there's no mood metadata to draw from), so
# moods are presented as a rough starting point, not a precise taxonomy.
MOODS: dict[str, tuple[str, ...]] = {
    "Chill": ("chill", "acoustic", "ambient", "lo-fi", "lofi", "folk", "soul", "jazz"),
    "Workout": ("edm", "dance", "electronic", "metal", "punk", "hip hop", "hip-hop", "rap", "rock"),
    "Focus": ("classical", "instrumental", "ambient", "piano", "soundtrack"),
    "Party": ("pop", "dance", "edm", "hip hop", "hip-hop", "disco", "funk"),
}


def _downloaded_tracks(db: Session) -> select:
    return select(Track).where(Track.path.is_not(None), Track.path != "")


def genre_counts(db: Session) -> list[dict]:
    rows = db.execute(
        select(Track.genre, func.count())
        .where(Track.genre.is_not(None), Track.genre != "", Track.path.is_not(None), Track.path != "")
        .group_by(Track.genre)
        .order_by(func.count().desc())
    ).all()
    return [{"genre": genre, "track_count": count} for genre, count in rows]


def mood_counts(db: Session) -> list[dict]:
    genres = genre_counts(db)
    out = []
    for mood, keywords in MOODS.items():
        count = sum(
            g["track_count"] for g in genres if any(k in (g["genre"] or "").lower() for k in keywords)
        )
        if count:
            out.append({"mood": mood, "track_count": count})
    return out


def tracks_for_genre(db: Session, genre: str) -> list[Track]:
    return list(
        db.scalars(_downloaded_tracks(db).where(func.lower(Track.genre) == genre.lower()))
        .unique()
        .all()
    )


def tracks_for_mood(db: Session, mood: str) -> list[Track]:
    keywords = MOODS.get(mood)
    if not keywords:
        return []
    rows = list(db.scalars(_downloaded_tracks(db)).unique().all())
    return [t for t in rows if t.genre and any(k in t.genre.lower() for k in keywords)]
