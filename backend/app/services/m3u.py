from __future__ import annotations

import os
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Album, PlayerPlaylistTrack, Track


def export_m3u(tracks: list[Track]) -> str:
    lines = ["#EXTM3U"]
    for t in tracks:
        album = t.album
        artist = album.artist if album else None
        artist_name = artist.name if artist else ""
        duration = t.duration or -1
        lines.append(f"#EXTINF:{duration},{artist_name} - {t.title}")
        lines.append(t.path or "")
    return "\n".join(lines) + "\n"


def _candidate_paths_and_titles(db: Session) -> list[Track]:
    return db.scalars(
        select(Track)
        .options(joinedload(Track.album).joinedload(Album.artist))
        .where(Track.path.is_not(None), Track.path != "")
    ).unique().all()


def _match_track(entry_path: str, entry_title: str, tracks: list[Track]) -> Track | None:
    if entry_path:
        for t in tracks:
            if t.path and os.path.normpath(t.path) == os.path.normpath(entry_path):
                return t
        entry_base = os.path.basename(entry_path).lower()
        for t in tracks:
            if t.path and os.path.basename(t.path).lower() == entry_base:
                return t
    if entry_title:
        needle = entry_title.strip().lower()
        for t in tracks:
            album = t.album
            artist = album.artist if album else None
            artist_name = (artist.name if artist else "").lower()
            candidate = f"{artist_name} - {t.title}".lower().strip()
            if candidate == needle or t.title.lower().strip() == needle:
                return t
    return None


def parse_and_match_m3u(db: Session, content: str) -> list[Track]:
    """Parse M3U/EXTM3U text and resolve each entry to a library Track.

    Match order: exact path -> basename -> "Artist - Title" / bare title.
    Entries that can't be resolved are silently skipped (same precedent as
    the manual add-tracks endpoint, which skips tracks with no local path).
    """
    tracks = _candidate_paths_and_titles(db)
    matched: list[Track] = []
    pending_title = ""
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            _, _, rest = line.partition(",")
            pending_title = rest.strip()
            continue
        if line.startswith("#"):
            continue
        found = _match_track(line, pending_title, tracks)
        pending_title = ""
        if found and found.id not in {t.id for t in matched}:
            matched.append(found)
    return matched
