from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.services.settings_service import ensure_settings

_JUNK_PATTERNS = [
    r"\bkaraoke\b",
    r"\binstrumental\b",
    r"\bpiano\s+cover\b",
    r"\bpiano\s+instrumental\b",
    r"\boriginally\s+performed\b",
    r"\btribute\b",
    r"\bcover\s+version\b",
    r"\bmade\s+famous\b",
    r"\bbacking\s+track\b",
    r"\bminus\s+one\b",
    r"\bplayback\b",
]


def is_junk_title(title: str) -> bool:
    t = (title or "").lower()
    return any(re.search(p, t) for p in _JUNK_PATTERNS)


def is_live_title(title: str) -> bool:
    t = (title or "").lower()
    return bool(re.search(r"\blive\b|\(live\)|\[live\]", t))


def album_passes_import_filters(
    db: Session,
    *,
    title: str,
    album_type: str,
    track_count: int = 0,
) -> bool:
    """Return False if this release should not be imported as wanted."""
    settings = ensure_settings(db)
    mapping = {
        "album": settings.include_albums,
        "ep": settings.include_eps,
        "single": settings.include_singles,
        "compilation": settings.include_compilations,
    }
    if not mapping.get(album_type, False):
        return False
    if getattr(settings, "ignore_junk_titles", True) and is_junk_title(title):
        return False
    if getattr(settings, "ignore_live_releases", False) and is_live_title(title):
        return False
    min_tracks = int(getattr(settings, "min_track_count", 0) or 0)
    if min_tracks > 0 and (track_count or 0) > 0 and track_count < min_tracks:
        # Only enforce when provider reported a count
        if album_type in {"album", "ep", "compilation"}:
            return False
    return True
