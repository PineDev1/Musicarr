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
    r"\bacapella\b",
    r"\ba\s+cappella\b",
    r"\bcommentary\b",
    r"\bin\s+the\s+style\s+of\b",
    r"\bsound[- ]?alike\b",
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
    """Return False if this release should not be imported as wanted.

    Kept for any external caller still using the bool shape; internally
    everything should go through classify_album_for_import instead so the
    skip reason is captured, not just discarded.
    """
    status, _reason, _code = classify_album_for_import(
        db, title=title, album_type=album_type, track_count=track_count
    )
    return status == "wanted"


def classify_album_for_import(
    db: Session,
    *,
    title: str,
    album_type: str,
    track_count: int = 0,
) -> tuple[str, str, str]:
    """Decide wanted vs. skipped for a release, with a reason.

    Returns (status, status_reason, skip_reason_code). status is "wanted" or
    "skipped". This is the single source of truth for the wanted/skip decision
    — every sync path (MusicBrainz-driven and provider-only fallback) must call
    this instead of re-implementing the same checks, so junk/live/type
    filtering never drifts out of sync between paths again.
    """
    settings = ensure_settings(db)
    mapping = {
        "album": settings.include_albums,
        "ep": settings.include_eps,
        "single": settings.include_singles,
        "compilation": settings.include_compilations,
    }
    if not mapping.get(album_type, False):
        return "skipped", f"{(album_type or 'release').title()}s are disabled", "type_disabled"
    if getattr(settings, "ignore_junk_titles", True) and is_junk_title(title):
        return "skipped", "Matched junk-title filter", "junk"
    if getattr(settings, "ignore_live_releases", False) and is_live_title(title):
        return "skipped", "Live release filter", "live"
    min_tracks = int(getattr(settings, "min_track_count", 0) or 0)
    if min_tracks > 0 and (track_count or 0) > 0 and track_count < min_tracks:
        # Only enforce when provider reported a count
        if album_type in {"album", "ep", "compilation"}:
            return "skipped", f"Below minimum track count ({min_tracks})", "min_tracks"
    return "wanted", "", ""
