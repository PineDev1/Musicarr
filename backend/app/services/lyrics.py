from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from mutagen import File as MutagenFile
from mutagen.flac import FLAC
from mutagen.id3 import ID3, ID3NoHeaderError
from mutagen.mp4 import MP4

from app.models import Track

logger = logging.getLogger("musicarr.lyrics")

RECHECK_AFTER = timedelta(days=30)
LRCLIB_URL = "https://lrclib.net/api/get"


def _read_sidecar_lrc(path: Path) -> str | None:
    lrc_path = path.with_suffix(".lrc")
    if lrc_path.is_file():
        try:
            return lrc_path.read_text(encoding="utf-8", errors="ignore").strip() or None
        except OSError:
            return None
    return None


def _read_embedded_lyrics(path: Path) -> str | None:
    ext = path.suffix.lower()
    try:
        if ext == ".flac":
            audio = FLAC(str(path))
            for key in ("lyrics", "unsyncedlyrics"):
                val = audio.get(key)
                if val:
                    return str(val[0]).strip() or None
        elif ext in {".mp3", ".mpeg"}:
            try:
                tags = ID3(str(path))
            except ID3NoHeaderError:
                return None
            for frame in tags.getall("USLT"):
                text = getattr(frame, "text", "")
                if text:
                    return str(text).strip() or None
        elif ext in {".m4a", ".mp4", ".aac"}:
            audio = MP4(str(path))
            val = audio.get("\xa9lyr")
            if val:
                return str(val[0]).strip() or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed reading embedded lyrics from %s: %s", path, exc)
    return None


def read_genre(path: Path) -> str:
    try:
        audio = MutagenFile(path, easy=True)
        if not audio or not audio.tags:
            return ""
        val = audio.tags.get("genre")
        if isinstance(val, list) and val:
            return str(val[0]).strip()
        if val:
            return str(val).strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed reading genre from %s: %s", path, exc)
    return ""


def _fetch_external_lyrics(*, artist: str, title: str, album: str, duration: int) -> tuple[str | None, str | None]:
    params = {"artist_name": artist, "track_name": title}
    if album:
        params["album_name"] = album
    if duration:
        params["duration"] = duration
    try:
        resp = httpx.get(LRCLIB_URL, params=params, timeout=6.0)
        if resp.status_code != 200:
            return None, None
        data = resp.json()
        plain = (data.get("plainLyrics") or "").strip() or None
        synced = (data.get("syncedLyrics") or "").strip() or None
        return plain, synced
    except Exception as exc:  # noqa: BLE001
        logger.info("lrclib lookup failed for %s - %s: %s", artist, title, exc)
        return None, None


def get_lyrics(db, track: Track) -> dict:
    """Return {plain, synced} lyrics for a track, using a persisted cache.

    Order: cache -> sidecar .lrc -> embedded tags -> lrclib.net fallback.
    A "not found" result is cached too (lyrics_checked_at set, both fields
    left null) so we don't re-hit the external API on every replay.
    """
    checked_at = getattr(track, "lyrics_checked_at", None)
    if checked_at is not None:
        now = datetime.now(timezone.utc)
        checked = checked_at if checked_at.tzinfo else checked_at.replace(tzinfo=timezone.utc)
        if now - checked < RECHECK_AFTER:
            return {"plain": track.lyrics_plain, "synced": track.lyrics_synced}

    plain: str | None = None
    synced: str | None = None
    path = Path(track.path) if track.path else None

    if path and path.is_file():
        sidecar = _read_sidecar_lrc(path)
        if sidecar:
            synced = sidecar
        embedded = _read_embedded_lyrics(path)
        if embedded and not plain:
            plain = embedded

    if not plain and not synced:
        album = track.album
        artist = album.artist if album else None
        plain, synced = _fetch_external_lyrics(
            artist=artist.name if artist else "",
            title=track.title,
            album=album.title if album else "",
            duration=track.duration or 0,
        )

    track.lyrics_plain = plain
    track.lyrics_synced = synced
    track.lyrics_checked_at = datetime.now(timezone.utc)
    db.commit()
    return {"plain": plain, "synced": synced}


def ensure_genre(db, track: Track) -> str:
    if getattr(track, "genre", ""):
        return track.genre
    if not track.path:
        return ""
    genre = read_genre(Path(track.path))
    if genre:
        track.genre = genre
        db.commit()
    return genre
