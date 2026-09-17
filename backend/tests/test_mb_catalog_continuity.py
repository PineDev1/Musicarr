from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services import mb_catalog_import, mb_local
from app.services.mb_catalog_import import build_fixture_catalog


@pytest.fixture()
def fixture_catalog(tmp_path):
    db_path = tmp_path / "catalog.sqlite"
    build_fixture_catalog(db_path)
    mb_local.configure(db_path)
    yield db_path
    mb_local.configure(None)


def test_reload_does_not_break_an_in_flight_connection_reference(fixture_catalog, tmp_path):
    """Regression: reload() (called right after a catalog swap) used to call
    .close() on the shared connection. Any caller that had already fetched a
    reference via _connect() and was mid-query would then hit
    'Cannot operate on a closed database' — meaning an old-catalog lookup
    in flight during an update could crash instead of finishing cleanly."""
    old_con = mb_local._connect()

    # Simulate a catalog rebuild finishing and swapping in a new file, while
    # `old_con` is a reference a caller obtained just before the swap
    # (mirrors fetch_catalog/count_release_groups holding `con` across
    # several queries in one call).
    new_db = tmp_path / "catalog_new.sqlite"
    build_fixture_catalog(new_db)
    mb_local.reload()

    # The old reference must still work — this must not raise.
    row = old_con.execute("SELECT name FROM artist WHERE gid = ?", (
        "c20ee61f-071f-4e65-9c81-45ee931a54ce",
    )).fetchone()
    assert row["name"] == "Luke Combs"


def test_connect_after_reload_uses_the_new_path(fixture_catalog, tmp_path):
    mb_local._connect()  # warm the cache against the old path

    new_db = tmp_path / "catalog_new.sqlite"
    build_fixture_catalog(new_db)
    mb_local.configure(new_db)

    fresh = mb_local._connect()
    assert fresh is not None
    row = fresh.execute("SELECT COUNT(*) AS n FROM artist").fetchone()
    assert row["n"] > 0


def test_old_catalog_stays_available_throughout_a_simulated_rebuild(fixture_catalog, tmp_path):
    """is_available()/fetch_catalog() must keep working against the old file
    the entire time a rebuild is in progress (i.e. before the atomic swap),
    with no window where the app thinks the catalog is missing."""
    assert mb_local.is_available() is True
    result = mb_local.fetch_catalog("c20ee61f-071f-4e65-9c81-45ee931a54ce")
    assert not result.error

    # "Rebuild in progress": build into a separate tmp path, exactly like
    # _run_import_job does — the configured (live) path is untouched.
    tmp_new = tmp_path / "work" / "musicbrainz_catalog.sqlite.tmp"
    build_fixture_catalog(tmp_new)

    assert mb_local.is_available() is True
    result2 = mb_local.fetch_catalog("c20ee61f-071f-4e65-9c81-45ee931a54ce")
    assert not result2.error
    assert result2.release_groups


def test_disk_space_preflight_fails_fast_without_touching_existing_catalog(tmp_path, monkeypatch):
    monkeypatch.setattr(mb_catalog_import, "catalog_dir", lambda: tmp_path)
    monkeypatch.setattr(mb_catalog_import, "catalog_work_dir", lambda: tmp_path / "work")

    class TinyDisk:
        free = 1024  # far below the threshold

    monkeypatch.setattr(mb_catalog_import.shutil, "disk_usage", lambda _p: TinyDisk())

    existing = tmp_path / "musicbrainz_catalog.sqlite"
    existing.write_bytes(b"not touched")
    monkeypatch.setattr(mb_catalog_import, "catalog_db_path", lambda: existing)

    mb_catalog_import._run_import_job()

    job = mb_catalog_import.get_job()
    assert job.state == "error"
    assert "free" in job.error.lower() or "gib" in job.error.lower()
    # The existing catalog must be completely untouched by the failed preflight.
    assert existing.read_bytes() == b"not touched"
