from __future__ import annotations

from app.models import RemotePathMapping
from app.services.path_mapping import map_remote_to_local, remote_basename


def test_map_remote_to_local_no_mappings_returns_original(db):
    result = map_remote_to_local(db, "/downloads/Some Album")
    assert str(result) == "/downloads/Some Album"


def test_map_remote_to_local_translates_prefix(db):
    db.add(RemotePathMapping(remote_path="/data/completed", local_path="/downloads"))
    db.commit()
    result = map_remote_to_local(db, "/data/completed/Some Album/01.flac")
    assert str(result) == "/downloads/Some Album/01.flac"


def test_map_remote_to_local_prefers_longest_matching_prefix(db):
    db.add(RemotePathMapping(remote_path="/data", local_path="/wrong"))
    db.add(RemotePathMapping(remote_path="/data/completed", local_path="/downloads"))
    db.commit()
    result = map_remote_to_local(db, "/data/completed/Album")
    assert str(result) == "/downloads/Album"


def test_map_remote_to_local_returns_none_for_empty_input(db):
    assert map_remote_to_local(db, "") is None


def test_remote_basename_posix_and_windows():
    assert remote_basename("/data/completed/Some Album") == "Some Album"
    assert remote_basename("C:\\downloads\\Some Album") == "Some Album"
    assert remote_basename("") == ""
