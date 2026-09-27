from __future__ import annotations

from sqlalchemy import select

from app.models import RemotePathMapping
from app.services.path_mapping import (
    map_remote_to_local,
    remote_basename,
    seed_remote_path_mappings_from_env,
)


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


def test_seed_remote_path_mappings_from_env_creates_rows(db):
    raw = '[{"host": "qbittorrent", "remote_path": "/downloads", "local_path": "/config/downloads"}]'
    applied = seed_remote_path_mappings_from_env(db, raw)
    assert applied == 1
    row = db.scalar(select(RemotePathMapping))
    assert row.host == "qbittorrent"
    assert row.remote_path == "/downloads"
    assert row.local_path == "/config/downloads"


def test_seed_remote_path_mappings_from_env_is_idempotent(db):
    raw = '[{"host": "qbittorrent", "remote_path": "/downloads", "local_path": "/config/downloads"}]'
    seed_remote_path_mappings_from_env(db, raw)
    seed_remote_path_mappings_from_env(db, raw)
    rows = db.scalars(select(RemotePathMapping)).all()
    assert len(rows) == 1


def test_seed_remote_path_mappings_from_env_updates_existing_row(db):
    seed_remote_path_mappings_from_env(
        db, '[{"host": "qbt", "remote_path": "/downloads", "local_path": "/old"}]'
    )
    seed_remote_path_mappings_from_env(
        db, '[{"host": "qbt", "remote_path": "/downloads", "local_path": "/new"}]'
    )
    rows = db.scalars(select(RemotePathMapping)).all()
    assert len(rows) == 1
    assert rows[0].local_path == "/new"


def test_seed_remote_path_mappings_from_env_allows_wildcard_host(db):
    applied = seed_remote_path_mappings_from_env(
        db, '[{"remote_path": "/downloads", "local_path": "/config/downloads"}]'
    )
    assert applied == 1
    row = db.scalar(select(RemotePathMapping))
    assert row.host == ""


def test_seed_remote_path_mappings_from_env_handles_empty_and_blank(db):
    assert seed_remote_path_mappings_from_env(db, "") == 0
    assert seed_remote_path_mappings_from_env(db, None) == 0
    assert seed_remote_path_mappings_from_env(db, "   ") == 0


def test_seed_remote_path_mappings_from_env_ignores_invalid_json(db):
    assert seed_remote_path_mappings_from_env(db, "not json") == 0
    assert db.scalar(select(RemotePathMapping)) is None


def test_seed_remote_path_mappings_from_env_ignores_non_array(db):
    assert seed_remote_path_mappings_from_env(db, '{"host": "x"}') == 0


def test_seed_remote_path_mappings_from_env_skips_incomplete_entries(db):
    raw = '[{"host": "qbt"}, {"remote_path": "/only-remote"}, "not-an-object"]'
    assert seed_remote_path_mappings_from_env(db, raw) == 0
    assert db.scalar(select(RemotePathMapping)) is None
