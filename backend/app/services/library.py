from __future__ import annotations

from pathlib import Path

from mutagen import File as MutagenFile
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Album, Track
from app.services.history import add_history
from app.services.naming import (
    build_album_folder,
    build_track_filename,
    year_from_release,
)
from app.services.settings_service import ensure_settings, library_root


AUDIO_EXTS = {".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav"}


def _read_tags(path: Path) -> dict:
    meta = {"title": None, "artist": None, "album": None, "track": None, "isrc": None}
    try:
        audio = MutagenFile(path, easy=True)
        if not audio or not audio.tags:
            return meta
        tags = audio.tags

        def first(key: str):
            val = tags.get(key)
            if isinstance(val, list) and val:
                return str(val[0])
            if val:
                return str(val)
            return None

        meta["title"] = first("title")
        meta["artist"] = first("artist")
        meta["album"] = first("album")
        meta["isrc"] = first("isrc")
        track = first("tracknumber")
        if track:
            meta["track"] = track.split("/")[0]
    except Exception:  # noqa: BLE001
        pass
    return meta


def scan_library(db: Session) -> dict:
    root = library_root(db)
    files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_EXTS]
    tracks = db.scalars(select(Track)).all()
    by_isrc = {t.isrc: t for t in tracks if t.isrc}
    by_path = {t.path: t for t in tracks if t.path}
    matched = 0
    unmatched = 0

    for path in files:
        sp = str(path)
        if sp in by_path:
            matched += 1
            continue
        tags = _read_tags(path)
        track = None
        if tags.get("isrc") and tags["isrc"] in by_isrc:
            track = by_isrc[tags["isrc"]]
        else:
            # Fuzzy: match album title + track number
            if tags.get("album") and tags.get("track"):
                try:
                    track_no = int(tags["track"])
                except ValueError:
                    track_no = None
                if track_no is not None:
                    album = db.scalar(
                        select(Album).where(Album.title == tags["album"])
                    )
                    if album:
                        track = next(
                            (t for t in album.tracks if t.track_no == track_no),
                            None,
                        )
        if track:
            track.path = sp
            if track.album and track.album.status != "downloaded":
                # Mark downloaded if any track linked
                linked = sum(1 for t in track.album.tracks if t.path)
                if linked + (0 if track.path else 1) >= max(1, track.album.track_count // 2):
                    track.album.status = "downloaded"
                    track.album.path = str(path.parent)
            matched += 1
        else:
            unmatched += 1

    # Update albums that have all tracks on disk
    for album in db.scalars(select(Album)).all():
        if not album.tracks:
            continue
        if all(t.path and Path(t.path).exists() for t in album.tracks):
            album.status = "downloaded"
            if not album.path:
                album.path = str(Path(album.tracks[0].path).parent)

    db.commit()
    msg = f"Scan complete: {len(files)} files, {matched} matched, {unmatched} unmatched"
    add_history(db, "library_scan", msg)
    return {
        "files_seen": len(files),
        "matched": matched,
        "unmatched": unmatched,
        "message": msg,
    }


def reorganize_library(db: Session) -> dict:
    settings = ensure_settings(db)
    root = library_root(db)
    moved = 0
    skipped = 0
    albums = db.scalars(
        select(Album).options(joinedload(Album.tracks), joinedload(Album.artist))
    ).unique().all()
    for album in albums:
        tracks = [t for t in album.tracks if t.path and Path(t.path).exists()]
        if not tracks:
            skipped += 1
            continue
        artist_name = album.artist.name if album.artist else "Unknown Artist"
        dest_folder = build_album_folder(
            root,
            settings.folder_template,
            artist=artist_name,
            album=album.title,
            year=year_from_release(album.release_date),
            album_type=album.album_type,
        )
        dest_folder.mkdir(parents=True, exist_ok=True)
        for track in tracks:
            src = Path(track.path)
            filename = build_track_filename(
                settings.track_template,
                title=track.title,
                track=track.track_no or 0,
                disc=track.disc_no or 1,
                artist=artist_name,
                album=album.title,
                ext=src.suffix.lower(),
            )
            dest = dest_folder / filename
            if src.resolve() == dest.resolve():
                continue
            if dest.exists() and src.resolve() != dest.resolve():
                skipped += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dest)
            track.path = str(dest)
            moved += 1
        album.path = str(dest_folder)
    db.commit()
    msg = f"Reorganized library: moved {moved}, skipped {skipped}"
    add_history(db, "reorganize", msg)
    return {"moved": moved, "skipped": skipped, "message": msg}
