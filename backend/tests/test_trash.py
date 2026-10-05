from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.api import albums as albums_api
from app.api import maintenance as maint_api
from app.api import trash as trash_api
from app.models import Album, TrashItem, Track
from app.services import trash
from app.services.settings_service import ensure_settings
from tests.conftest import _artist


@pytest.fixture()
def tr(db, tmp_path, monkeypatch):
    monkeypatch.setattr(trash.app_config, "data_dir", tmp_path / "data")
    (tmp_path / "data").mkdir()
    lib = tmp_path / "lib"
    lib.mkdir()
    row = ensure_settings(db)
    row.library_path = str(lib)
    db.commit()
    return lib


def test_trashed_file_can_be_restored_to_its_original_path(db, tr):
    f = tr / "a" / "song.flac"
    f.parent.mkdir()
    f.write_bytes(b"audio")
    assert trash.delete_or_trash(db, f, reason="orphan_file") == "trashed"
    assert not f.exists()
    [item] = trash.list_items(db)
    assert item.size_bytes == 5 and item.original_path == str(f)
    trash.restore(db, item.id)
    assert f.read_bytes() == b"audio" and trash.list_items(db) == []


def test_restore_refuses_to_overwrite_something_new(db, tr):
    f = tr / "song.flac"
    f.write_bytes(b"old")
    trash.delete_or_trash(db, f, reason="x")
    f.write_bytes(b"new")
    with pytest.raises(trash.TrashError):
        trash.restore(db, trash.list_items(db)[0].id)
    assert f.read_bytes() == b"new"


def test_retention_zero_deletes_permanently_like_before(db, tr):
    row = ensure_settings(db)
    row.trash_retention_days = 0
    db.commit()
    f = tr / "gone.flac"
    f.write_bytes(b"x")
    assert trash.delete_or_trash(db, f, reason="x") == "deleted"
    assert not f.exists() and trash.list_items(db) == []


def test_purge_expired_removes_only_old_items_and_their_files(db, tr):
    old, new = tr / "old.flac", tr / "new.flac"
    old.write_bytes(b"1")
    new.write_bytes(b"2")
    trash.delete_or_trash(db, old, reason="x")
    trash.delete_or_trash(db, new, reason="x")
    item_old = next(i for i in trash.list_items(db) if i.label == "old.flac")
    item_old.deleted_at = datetime.now(timezone.utc) - timedelta(days=45)
    db.commit()
    payload = item_old.trash_path
    assert trash.purge_expired(db) == 1
    assert [i.label for i in trash.list_items(db)] == ["new.flac"]
    import os

    assert not os.path.exists(payload)


def test_purge_is_a_noop_when_retention_is_zero(db, tr):
    f = tr / "keep.flac"
    f.write_bytes(b"x")
    trash.delete_or_trash(db, f, reason="x")
    row = ensure_settings(db)
    row.trash_retention_days = 0
    db.commit()
    assert trash.purge_expired(db) == 0 and len(trash.list_items(db)) == 1


def test_delete_album_with_files_goes_to_trash_then_restores(db, tr):
    artist = _artist(db, name="A", provider="deezer", provider_id="a1")
    folder = tr / "A" / "Album"
    folder.mkdir(parents=True)
    song = folder / "01.flac"
    song.write_bytes(b"song")
    album = Album(artist_id=artist.id, provider="deezer", provider_id="al1", title="Album", status="downloaded", path=str(folder))
    db.add(album)
    db.commit()
    db.add(Track(provider="deezer", provider_id="t1", album_id=album.id, title="One", path=str(song)))
    db.commit()
    albums_api.delete_album(album.id, db=db, delete_files=True)
    assert not folder.exists() and db.get(Album, album.id) is None
    [item] = trash.list_items(db)
    assert item.is_dir and item.reason == "album_deleted"
    trash_api.restore_item(item.id, db)
    assert (folder / "01.flac").read_bytes() == b"song"


def test_trash_api_empty_and_unknown_ids(db, tr):
    f = tr / "x.flac"
    f.write_bytes(b"x")
    trash.delete_or_trash(db, f, reason="x")
    assert trash_api.list_trash(db)["items"][0]["label"] == "x.flac"
    assert trash_api.empty_trash(db)["removed"] == 1
    with pytest.raises(HTTPException) as e:
        trash_api.delete_item(999, db)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        trash_api.restore_item(999, db)
    assert e.value.status_code == 409
