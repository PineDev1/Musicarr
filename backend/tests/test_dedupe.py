from __future__ import annotations

import os
from pathlib import Path

from app.models import Album, AppSettings, Track
from app.services import dedupe
from tests.conftest import _artist


def _settings(db, library_path: Path) -> AppSettings:
    row = db.get(AppSettings, 1)
    if row is None:
        row = AppSettings(id=1, library_path=str(library_path), active_provider="deezer")
        db.add(row)
    else:
        row.library_path = str(library_path)
    db.commit()
    return row


def _album(db, artist, title="Album"):
    a = Album(provider=artist.provider, provider_id=f"al-{title}", artist_id=artist.id, title=title)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def test_find_orphan_db_tracks_flags_missing_file(db, tmp_path):
    _settings(db, tmp_path)
    artist = _artist(db, name="Artist", provider="qobuz", provider_id="a1")
    album = _album(db, artist)
    t = Track(provider="qobuz", provider_id="t1", album_id=album.id, title="Song", path=str(tmp_path / "missing.flac"))
    db.add(t)
    db.commit()

    orphans = dedupe.find_orphan_db_tracks(db)

    assert len(orphans) == 1
    assert orphans[0]["track_id"] == t.id


def test_find_orphan_db_tracks_ignores_existing_file(db, tmp_path):
    _settings(db, tmp_path)
    artist = _artist(db, name="Artist", provider="qobuz", provider_id="a1")
    album = _album(db, artist)
    real = tmp_path / "real.flac"
    real.write_bytes(b"data")
    t = Track(provider="qobuz", provider_id="t1", album_id=album.id, title="Song", path=str(real))
    db.add(t)
    db.commit()

    assert dedupe.find_orphan_db_tracks(db) == []


def test_find_orphan_files_finds_untracked_audio(db, tmp_path):
    _settings(db, tmp_path)
    (tmp_path / "Artist").mkdir()
    untracked = tmp_path / "Artist" / "song.mp3"
    untracked.write_bytes(b"data")
    (tmp_path / "Artist" / "notes.txt").write_text("not audio")

    orphans = dedupe.find_orphan_files(db)

    assert len(orphans) == 1
    assert orphans[0]["path"] == str(untracked.resolve())


def test_find_orphan_files_uses_file_identity_not_just_resolved_path(db, tmp_path):
    """Regression: comparing resolved path *strings* used to falsely flag an
    already-tracked physical file as an orphan whenever the DB path and the
    on-disk-walked path reach the same file through different names/links —
    e.g. two configured library roots that both reach the same underlying
    file. A hardlink reproduces this deterministically: two directory
    entries, one physical file. Track.path recording one name must count
    the other as already-tracked too, since it's the identical file."""
    _settings(db, tmp_path)
    artist_dir = tmp_path / "Artist"
    artist_dir.mkdir()
    real = artist_dir / "song.mp3"
    real.write_bytes(b"data")
    hardlink = artist_dir / "song-alt-name.mp3"
    os.link(real, hardlink)

    artist = _artist(db, name="Artist", provider="qobuz", provider_id="a1")
    album = _album(db, artist)
    track = Track(provider="qobuz", provider_id="t1", album_id=album.id, title="Song", path=str(hardlink))
    db.add(track)
    db.commit()

    assert dedupe.find_orphan_files(db) == []


def test_find_duplicate_groups_by_isrc(db, tmp_path):
    _settings(db, tmp_path)
    artist = _artist(db, name="Artist", provider="qobuz", provider_id="a1")
    album = _album(db, artist)
    db.add_all(
        [
            Track(provider="qobuz", provider_id="t1", album_id=album.id, title="Song", isrc="ISRC1"),
            Track(provider="deezer", provider_id="t2", album_id=album.id, title="Song (dup)", isrc="ISRC1"),
        ]
    )
    db.commit()

    groups = dedupe.find_duplicate_groups(db)

    assert len(groups) == 1
    assert groups[0]["reason"] == "isrc"
    assert len(groups[0]["tracks"]) == 2


def test_find_duplicate_groups_by_album_slot(db, tmp_path):
    _settings(db, tmp_path)
    artist = _artist(db, name="Artist", provider="qobuz", provider_id="a1")
    album = _album(db, artist)
    db.add_all(
        [
            Track(provider="qobuz", provider_id="t1", album_id=album.id, title="A", track_no=1, disc_no=1),
            Track(provider="qobuz", provider_id="t2", album_id=album.id, title="A copy", track_no=1, disc_no=1),
        ]
    )
    db.commit()

    groups = dedupe.find_duplicate_groups(db)

    assert len(groups) == 1
    assert groups[0]["reason"] == "album_slot"


def test_duplicate_group_orders_row_with_real_file_first(db, tmp_path):
    """The MaintenancePage UI defaults its "keep" radio to tracks[0] — a row
    whose file no longer exists on disk must never sort before a row whose
    file is real, or the UI pre-selects deleting the only real file."""
    _settings(db, tmp_path)
    artist = _artist(db, name="Artist", provider="qobuz", provider_id="a1")
    album = _album(db, artist)
    real_file = tmp_path / "song.flac"
    real_file.write_bytes(b"fake audio bytes")

    db.add_all(
        [
            # Orphaned row (no file on disk) inserted first, by id order —
            # the buggy code had no ordering, so it would sort first.
            Track(
                provider="qobuz",
                provider_id="t1",
                album_id=album.id,
                title="Song",
                isrc="ISRC1",
                path=str(tmp_path / "missing.flac"),
            ),
            Track(
                provider="deezer",
                provider_id="t2",
                album_id=album.id,
                title="Song (dup)",
                isrc="ISRC1",
                path=str(real_file),
            ),
        ]
    )
    db.commit()

    groups = dedupe.find_duplicate_groups(db)

    assert len(groups) == 1
    assert groups[0]["tracks"][0]["path"] == str(real_file)
