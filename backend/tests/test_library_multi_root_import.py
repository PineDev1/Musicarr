"""Regression: import_existing_library/scan_library must scan every
configured library root, not just the primary AppSettings.library_path —
otherwise files under an added extra root are silently invisible to
import/scan/dedupe."""
from __future__ import annotations

from pathlib import Path

from mutagen.easyid3 import EasyID3

from app.models import AppSettings
from app.services import library, library_roots


def _mp3_frame(size: int = 417) -> bytes:
    header = bytes([0xFF, 0xFB, 0x90, 0x00])
    return header + bytes(size - len(header))


def make_mp3(path: Path, *, title: str, artist: str, album: str, track: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        for _ in range(40):
            fh.write(_mp3_frame())
    tags = EasyID3()
    tags["title"] = [title]
    tags["artist"] = [artist]
    tags["album"] = [album]
    tags["tracknumber"] = [track]
    tags.save(path)


def _settings(db, primary: Path) -> AppSettings:
    row = AppSettings(id=1, library_path=str(primary), active_provider="deezer")
    db.add(row)
    db.commit()
    return row


def test_import_existing_library_scans_extra_roots_too(db, tmp_path):
    primary = tmp_path / "primary"
    extra = tmp_path / "old_drive"
    _settings(db, primary)
    library_roots.add_root(db, path=str(extra), label="Old drive")

    make_mp3(
        primary / "Primary Artist" / "Primary Album" / "1 - Song.mp3",
        title="Song",
        artist="Primary Artist",
        album="Primary Album",
        track="1",
    )
    make_mp3(
        extra / "Old Artist" / "Old Album" / "1 - Old Song.mp3",
        title="Old Song",
        artist="Old Artist",
        album="Old Album",
        track="1",
    )

    result = library.import_existing_library(db, link_providers=False)

    assert result["files_seen"] == 2
    from app.models import Artist

    names = {a.name for a in db.query(Artist).all()}
    assert "Primary Artist" in names
    assert "Old Artist" in names


def test_scan_library_matches_tracks_in_extra_roots(db, tmp_path):
    primary = tmp_path / "primary"
    extra = tmp_path / "old_drive"
    _settings(db, primary)
    library_roots.add_root(db, path=str(extra))

    make_mp3(
        extra / "Old Artist" / "Old Album" / "1 - Old Song.mp3",
        title="Old Song",
        artist="Old Artist",
        album="Old Album",
        track="1",
    )

    result = library.import_existing_library(db, link_providers=False)
    assert result["files_seen"] == 1

    # scan_library must also see this file on a re-scan (matching, not just
    # first import) — regression target is the same _collect_files(root)
    # call site.
    scan_result = library.scan_library(db)
    assert scan_result["matched"] >= 1 or scan_result.get("files_seen", 0) >= 1
