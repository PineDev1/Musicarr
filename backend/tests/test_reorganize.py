from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.models import Album, Track
from app.services import library
from app.services.settings_service import ensure_settings
from tests.conftest import _artist


@pytest.fixture()
def lib(db, tmp_path):
    root = tmp_path / "music"
    root.mkdir()
    messy = tmp_path / "messy"
    messy.mkdir()
    row = ensure_settings(db)
    row.library_path = str(root)
    db.commit()
    artist = _artist(db, name="Luke Combs", provider="deezer", provider_id="a1")
    albums = []
    for n, title in enumerate(("Gettin Old", "The Prequel"), start=1):
        al = Album(artist_id=artist.id, provider="deezer", provider_id=f"al{n}", title=title,
                   release_date="2023-03-24", album_type="album", status="downloaded")
        db.add(al)
        db.commit()
        f = messy / f"{title}-song.flac"
        f.write_bytes(b"x")
        t = Track(provider="deezer", provider_id=f"t{n}", album_id=al.id, title=f"Song {n}",
                  track_no=1, path=str(f))
        db.add(t)
        db.commit()
        albums.append((al, t, f))
    return root, albums


def test_preview_lists_moves_and_touches_nothing(db, lib):
    root, albums = lib
    out = library.preview_reorganize(db)
    assert out["total_moves"] == 2 and out["total_conflicts"] == 0
    assert all(m["to"].startswith(str(root)) for m in out["moves"])
    assert {m["album"] for m in out["moves"]} == {"Gettin Old", "The Prequel"}
    for _al, t, f in albums:
        assert f.exists()  # nothing moved
        db.refresh(t)
        assert t.path == str(f)
    assert not any(root.iterdir())  # no empty folders created either


def test_reorganize_moves_files_and_records_new_paths(db, lib):
    root, albums = lib
    out = library.reorganize_library(db)
    assert out["moved"] == 2 and out["failed"] == 0
    for _al, t, f in albums:
        db.refresh(t)
        assert not f.exists() and Path(t.path).exists() and Path(t.path).is_relative_to(root)
    assert library.preview_reorganize(db)["total_moves"] == 0  # idempotent


def test_existing_destination_is_a_conflict_not_an_overwrite(db, lib):
    root, albums = lib
    preview = library.preview_reorganize(db)
    dest = Path(preview["moves"][0]["to"])
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"precious")
    again = library.preview_reorganize(db)
    assert again["total_conflicts"] == 1 and again["total_moves"] == 1
    out = library.reorganize_library(db)
    assert out["moved"] == 1 and out["skipped"] >= 1
    assert dest.read_bytes() == b"precious"


def test_a_failed_move_does_not_lose_track_of_files_already_moved(db, lib, monkeypatch):
    root, albums = lib
    real_move = shutil.move
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:  # the second album's file fails to move
            raise OSError("permission denied")
        return real_move(src, dst)

    monkeypatch.setattr(shutil, "move", flaky)
    out = library.reorganize_library(db)
    assert out["moved"] == 1 and out["failed"] == 1
    moved = failed = 0
    for al, t, f in albums:
        db.refresh(t)
        db.refresh(al)
        if f.exists():
            failed += 1
            assert t.path == str(f)  # untouched file keeps its old, valid path
            assert al.path != str(Path(t.path).parent)  # album isn't repointed at a folder lacking its file
        else:
            moved += 1
            assert Path(t.path).exists()  # moved file's new path was recorded
    assert (moved, failed) == (1, 1)
