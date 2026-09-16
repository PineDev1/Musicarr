from __future__ import annotations

import logging
import re
from pathlib import Path

from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, TIT2, TPE1, TPE2, TALB, TRCK, TPOS, TDRC, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover

logger = logging.getLogger("musicarr.tags")


def write_track_tags(
    path: Path,
    *,
    title: str,
    artist: str,
    album_artist: str,
    album: str,
    track_no: int = 0,
    disc_no: int = 1,
    year: str = "",
    cover_path: Path | None = None,
) -> None:
    """Rewrite tags so collabs never become 'Artist feat. Artist' and details are complete."""
    if not path.exists():
        return
    ext = path.suffix.lower()
    cover_bytes = None
    cover_mime = "image/jpeg"
    if cover_path and cover_path.exists():
        try:
            cover_bytes = cover_path.read_bytes()
            if cover_path.suffix.lower() in {".png"}:
                cover_mime = "image/png"
        except OSError:
            cover_bytes = None
    try:
        if ext == ".flac":
            audio = FLAC(str(path))
            audio["title"] = [title]
            audio["artist"] = [artist]
            audio["albumartist"] = [album_artist]
            audio["album"] = [album]
            if track_no:
                audio["tracknumber"] = [str(track_no)]
            if disc_no:
                audio["discnumber"] = [str(disc_no)]
            if year:
                audio["date"] = [year]
            if cover_bytes:
                pic = Picture()
                pic.type = 3
                pic.mime = cover_mime
                pic.desc = "Cover"
                pic.data = cover_bytes
                audio.clear_pictures()
                audio.add_picture(pic)
            audio.save()
            return
        if ext in {".mp3", ".mpeg"}:
            try:
                tags = ID3(str(path))
            except ID3NoHeaderError:
                tags = ID3()
            tags.delall("TIT2")
            tags.delall("TPE1")
            tags.delall("TPE2")
            tags.delall("TALB")
            tags.delall("TRCK")
            tags.delall("TPOS")
            tags.delall("TDRC")
            tags.add(TIT2(encoding=3, text=title))
            tags.add(TPE1(encoding=3, text=artist))
            tags.add(TPE2(encoding=3, text=album_artist))
            tags.add(TALB(encoding=3, text=album))
            if track_no:
                tags.add(TRCK(encoding=3, text=str(track_no)))
            if disc_no:
                tags.add(TPOS(encoding=3, text=str(disc_no)))
            if year:
                tags.add(TDRC(encoding=3, text=year))
            if cover_bytes:
                tags.delall("APIC")
                tags.add(
                    APIC(
                        encoding=3,
                        mime=cover_mime,
                        type=3,
                        desc="Cover",
                        data=cover_bytes,
                    )
                )
            tags.save(str(path), v2_version=3)
            return
        if ext in {".m4a", ".mp4", ".aac"}:
            audio = MP4(str(path))
            audio["\xa9nam"] = [title]
            audio["\xa9ART"] = [artist]
            audio["aART"] = [album_artist]
            audio["\xa9alb"] = [album]
            if track_no:
                audio["trkn"] = [(track_no, 0)]
            if disc_no:
                audio["disk"] = [(disc_no, 0)]
            if year:
                audio["\xa9day"] = [year]
            if cover_bytes:
                fmt = MP4Cover.FORMAT_PNG if "png" in cover_mime else MP4Cover.FORMAT_JPEG
                audio["covr"] = [MP4Cover(cover_bytes, imageformat=fmt)]
            audio.save()
            return
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed tagging %s: %s", path, exc)


def write_track_genre(path: Path, genre: str) -> None:
    """Rewrite just the genre tag. Uses mutagen's format-agnostic "easy" tag
    interface (same one _read_tags reads through) rather than duplicating the
    per-format branching in write_track_tags — genre is the one field every
    format's easy mapping already normalizes to a single "genre" key."""
    if not path.exists():
        return
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(path, easy=True)
        if audio is None:
            return
        audio["genre"] = [genre]
        audio.save()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed writing genre for %s: %s", path, exc)


def format_credit_artist(primary: str, collaborators: list[str]) -> str:
    """Build a clean artist credit string without duplicating the primary name."""
    primary_clean = (primary or "").strip()
    others: list[str] = []
    seen = {re.sub(r"\s+", " ", primary_clean.lower())}
    for name in collaborators:
        clean = (name or "").strip()
        key = re.sub(r"\s+", " ", clean.lower())
        if not clean or key in seen:
            continue
        seen.add(key)
        others.append(clean)
    if not others:
        return primary_clean
    if len(others) == 1:
        return f"{primary_clean} feat. {others[0]}"
    return f"{primary_clean} feat. {', '.join(others[:-1])} & {others[-1]}"
