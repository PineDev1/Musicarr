from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import Album, Artist, Track
from app.services.library import AUDIO_EXTS
from app.services.settings_service import library_root


def find_orphan_db_tracks(db: Session) -> list[dict]:
    """Track rows whose path is set but the file no longer exists on disk."""
    rows = db.scalars(
        select(Track)
        .options(joinedload(Track.album).joinedload(Album.artist))
        .where(Track.path.is_not(None), Track.path != "")
    ).unique().all()
    out = []
    for t in rows:
        if not t.path or Path(t.path).exists():
            continue
        album = t.album
        out.append(
            {
                "track_id": t.id,
                "path": t.path,
                "title": t.title,
                "album_title": album.title if album else "",
                "artist_name": album.artist.name if album and album.artist else "",
            }
        )
    return out


def find_orphan_files(db: Session) -> list[dict]:
    """Audio files on disk under the library root with no matching Track.path."""
    root = library_root(db)
    known_paths = {
        str(Path(p).resolve())
        for (p,) in db.execute(select(Track.path).where(Track.path.is_not(None)))
        if p
    }
    out: list[dict] = []
    if not root.is_dir():
        return out
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTS:
            continue
        resolved = str(path.resolve())
        if resolved in known_paths:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        out.append({"path": resolved, "size_bytes": size})
    return out


def find_duplicate_groups(db: Session) -> list[dict]:
    """Concrete, safe duplicate signals only: matching ISRC, or matching
    (album, disc, track number) slot — not fuzzy cross-library title matching,
    which is prone to false positives for a destructive-cleanup tool."""
    groups: list[dict] = []
    seen_track_ids: set[int] = set()

    def _track_dict(t: Track) -> dict:
        album = t.album
        return {
            "track_id": t.id,
            "title": t.title,
            "path": t.path,
            "album_title": album.title if album else "",
            "artist_name": album.artist.name if album and album.artist else "",
        }

    isrc_dupes = db.execute(
        select(Track.isrc, func.count())
        .where(Track.isrc.is_not(None), Track.isrc != "")
        .group_by(Track.isrc)
        .having(func.count() > 1)
    ).all()
    for isrc, _count in isrc_dupes:
        rows = db.scalars(
            select(Track)
            .options(joinedload(Track.album).joinedload(Album.artist))
            .where(Track.isrc == isrc)
        ).unique().all()
        if len(rows) < 2:
            continue
        seen_track_ids.update(r.id for r in rows)
        groups.append({"reason": "isrc", "key": isrc, "tracks": [_track_dict(r) for r in rows]})

    slot_dupes = db.execute(
        select(Track.album_id, Track.disc_no, Track.track_no, func.count())
        .group_by(Track.album_id, Track.disc_no, Track.track_no)
        .having(func.count() > 1)
    ).all()
    for album_id, disc_no, track_no, _count in slot_dupes:
        rows = db.scalars(
            select(Track)
            .options(joinedload(Track.album).joinedload(Album.artist))
            .where(
                Track.album_id == album_id,
                Track.disc_no == disc_no,
                Track.track_no == track_no,
            )
        ).unique().all()
        rows = [r for r in rows if r.id not in seen_track_ids]
        if len(rows) < 2:
            continue
        groups.append(
            {
                "reason": "album_slot",
                "key": f"{album_id}:{disc_no}:{track_no}",
                "tracks": [_track_dict(r) for r in rows],
            }
        )
    return groups


def scan(db: Session) -> dict:
    return {
        "orphan_db_tracks": find_orphan_db_tracks(db),
        "orphan_files": find_orphan_files(db),
        "duplicate_groups": find_duplicate_groups(db),
    }
