from __future__ import annotations

import re
from pathlib import Path

from app.services.deezer_client import sanitize_filename


def _year_from_date(release_date: str | None) -> str:
    if not release_date:
        return "0000"
    m = re.match(r"(\d{4})", release_date)
    return m.group(1) if m else "0000"


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
    parts = [sanitize_filename(p) for p in Path(relative).parts if p not in ("", ".")]
    folder = library_root.joinpath(*parts)
    # Safety: never escape library root
    resolved = folder.resolve()
    if not str(resolved).startswith(str(library_root.resolve())):
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
