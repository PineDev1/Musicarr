from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.services.deezer_client import sanitize_filename


def _year_from_date(release_date: str | None) -> str:
    if not release_date:
        return "0000"
    m = re.match(r"(\d{4})", release_date)
    return m.group(1) if m else "0000"


def _norm_artist_name(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def artist_folder_name(
    artist: Any | None,
    *,
    collide: bool | None = None,
    db: Any | None = None,
) -> str:
    """Display name, or disambiguated segment when another artist shares the name.

    Pass collide=True/False to skip a DB lookup (tests / callers that already know).
    """
    if artist is None:
        return "Unknown Artist"
    name = (getattr(artist, "name", None) or "").strip() or "Unknown Artist"
    needs_disambiguation = collide
    if needs_disambiguation is None and db is not None:
        key = _norm_artist_name(name)
        artist_id = getattr(artist, "id", None)
        from sqlalchemy import select
        from app.models import Artist

        others = db.scalars(select(Artist)).all()
        needs_disambiguation = any(
            _norm_artist_name(a.name) == key and a.id != artist_id for a in others
        )
    if not needs_disambiguation:
        return name
    provider = (getattr(artist, "provider", None) or "unknown").strip() or "unknown"
    provider_id = (getattr(artist, "provider_id", None) or "").strip() or "0"
    return f"{name} [{provider}-{provider_id}]"


def render_template(template: str, values: dict[str, str | int]) -> str:
    result = template
    # Support {track:02d} style
    for match in re.finditer(r"\{(\w+)(?::([^}]+))?\}", template):
        key, fmt = match.group(1), match.group(2)
        if key not in values:
            continue
        val = values[key]
        if fmt:
            try:
                rendered = format(val, fmt)
            except (ValueError, TypeError):
                rendered = str(val)
        else:
            rendered = str(val)
        result = result.replace(match.group(0), rendered)
    return result


def build_album_folder(
    library_root: Path,
    folder_template: str,
    *,
    artist: str,
    album: str,
    year: str | None,
    album_type: str = "album",
) -> Path:
    values = {
        "artist": sanitize_filename(artist),
        "album": sanitize_filename(album),
        "year": year or "0000",
        "type": album_type,
    }
    relative = render_template(folder_template, values)
    parts = [sanitize_filename(p) for p in Path(relative).parts if p not in ("", ".", "..")]
    folder = library_root.joinpath(*parts)
    # Safety: never escape library root. A bare string-prefix check would
    # wrongly accept a sibling directory that merely shares the root's name
    # as a prefix (e.g. root "/data/music" vs. "/data/music-private/...").
    root_resolved = library_root.resolve()
    resolved = folder.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValueError("Resolved path escapes library root")
    return resolved


def build_track_filename(
    track_template: str,
    *,
    title: str,
    track: int,
    disc: int = 1,
    artist: str = "",
    album: str = "",
    ext: str = ".flac",
) -> str:
    values = {
        "title": sanitize_filename(title),
        "track": track,
        "disc": disc,
        "artist": sanitize_filename(artist),
        "album": sanitize_filename(album),
    }
    name = render_template(track_template, values)
    name = sanitize_filename(name)
    if not name.lower().endswith(ext.lower()):
        name = f"{name}{ext}"
    return name


def year_from_release(release_date: str | None) -> str:
    return _year_from_date(release_date)
