from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Artist
from app.services import lastfm
from app.services.text_match import normalize_key

_CACHE_TTL_SECONDS = 300
_cache: dict[str, tuple[float, list[dict]]] = {}


def _monitored_active_artists(db: Session) -> list[Artist]:
    return list(
        db.scalars(
            select(Artist).where(Artist.monitored.is_(True), Artist.status == "active")
        ).all()
    )


def discover_similar(db: Session, *, limit_per_artist: int = 5, limit_total: int = 40) -> list[dict]:
    """Similar artists across every monitored artist, deduped and ranked.

    Fans out one Last.fm call per monitored artist, so the result is cached
    briefly — otherwise every Discover page load would refetch this for the
    whole library.
    """
    cached = _cache.get("similar")
    if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    from app.services.artists import find_artist_by_normalized_name

    seen: set[str] = set()
    results: list[dict] = []
    for artist in _monitored_active_artists(db):
        seen.add(normalize_key(artist.name))
    for artist in _monitored_active_artists(db):
        try:
            hits = lastfm.similar_artists(db, artist.name, limit=limit_per_artist)
        except lastfm.LastfmError:
            continue
        for hit in hits:
            key = normalize_key(hit.get("name") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            existing = find_artist_by_normalized_name(db, hit["name"], artist.provider)
            results.append(
                {
                    "name": hit["name"],
                    "match": hit.get("match") or 0.0,
                    "already_in_library": existing.id if existing else None,
                    "seed_artist_name": artist.name,
                }
            )

    results.sort(key=lambda r: r["match"], reverse=True)
    results = results[:limit_total]
    _cache["similar"] = (time.monotonic(), results)
    return results


def clear_cache() -> None:
    _cache.clear()
