from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import Album, Artist, Track
from app.services.library import AUDIO_EXTS
from app.services.library_roots import all_library_roots


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


def _file_identity(path: Path) -> tuple[int, int] | None:
    """(device, inode) — identifies the physical file regardless of which
    symlink/library-root path was used to reach it.

    A Track.path stored via one symlink (e.g. an extra library root) and the
    same physical file walked today via a different symlink both resolve to
    the same target, but Path.resolve() can only follow symlinks that still
    exist and still point where they used to — if the original symlink was
    since changed or removed, resolve() (strict=False) stops at the missing
    component and the two sides can end up as different strings even though
    it's the same file, misreporting an already-tracked file as an orphan.
    st_dev/st_ino aren't affected by any of that.
    """
    try:
        st = path.stat()
        return (st.st_dev, st.st_ino)
    except OSError:
        return None


def find_orphan_files(db: Session) -> list[dict]:
    """Audio files on disk under any configured library root with no
    matching Track.path."""
    known_identities: set[tuple[int, int]] = set()
    known_paths: set[str] = set()
    for (p,) in db.execute(select(Track.path).where(Track.path.is_not(None))):
        if not p:
            continue
        identity = _file_identity(Path(p))
        if identity is not None:
            known_identities.add(identity)
        else:
            # File doesn't exist (handled separately by find_orphan_db_tracks)
            # — fall back to the resolved string so this loop still behaves
            # as before for that case rather than silently dropping it.
            known_paths.add(str(Path(p).resolve()))

    out: list[dict] = []
    seen_identities: set[tuple[int, int]] = set()
    seen_paths: set[str] = set()
    for root in all_library_roots(db):
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in AUDIO_EXTS:
                continue
            identity = _file_identity(path)
            resolved = str(path.resolve())
            if identity is not None:
                if identity in known_identities or identity in seen_identities:
                    continue
                seen_identities.add(identity)
            else:
                if resolved in known_paths or resolved in seen_paths:
                    continue
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
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

    def _has_file(t: Track) -> bool:
        return bool(t.path) and Path(t.path).exists()

    def _ordered(rows: list[Track]) -> list[Track]:
        # A row with a real file on disk must sort first: callers (the
        # MaintenancePage UI) default the "keep" choice to the first entry in
        # a group, so an orphaned/pathless row sorting first would pre-select
        # deleting the only real file and keeping the orphan.
        return sorted(rows, key=lambda t: 0 if _has_file(t) else 1)

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
        rows = _ordered(rows)
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
        rows = _ordered(rows)
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
