from __future__ import annotations

from pathlib import Path

import pytest

from app.services import mb_catalog_import, mb_local, musicbrainz


@pytest.fixture()
def fixture_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "musicbrainz_catalog.sqlite"
    mb_catalog_import.build_fixture_catalog(db_path)
    meta = {
        "dump_version": "test-fixture",
        "imported_at": "2026-01-01T00:00:00+00:00",
        "size_bytes": db_path.stat().st_size,
    }
    meta_path = tmp_path / "catalog_meta.json"
    meta_path.write_text(__import__("json").dumps(meta), encoding="utf-8")

    monkeypatch.setattr(mb_catalog_import, "catalog_db_path", lambda: db_path)
    monkeypatch.setattr(mb_catalog_import, "catalog_meta_path", lambda: meta_path)
    monkeypatch.setattr(mb_local, "catalog_db_path", lambda: db_path)
    from app.services import mb_catalog_paths

    monkeypatch.setattr(mb_catalog_paths, "catalog_db_path", lambda: db_path)
    monkeypatch.setattr(mb_catalog_paths, "catalog_meta_path", lambda: meta_path)

    mb_local.configure(db_path)
    musicbrainz.clear_cache()
    yield db_path
    mb_local.configure(None)
    musicbrainz.clear_cache()


def test_local_count_release_groups(fixture_catalog):
    n = mb_local.count_release_groups("c20ee61f-071f-4e65-9c81-45ee931a54ce")
    assert n == 2  # solo album + collab single


def test_local_resolve_and_catalog(fixture_catalog):
    assert mb_local.resolve_artist("Luke Combs") == "c20ee61f-071f-4e65-9c81-45ee931a54ce"
    assert mb_local.resolve_artist("Edward Sheeran") == "b8a7c51f-362c-4dcb-a259-bc6e0095f0a6"

    cat = mb_local.fetch_catalog("c20ee61f-071f-4e65-9c81-45ee931a54ce")
    assert not cat.error
    titles = {rg.title for rg in cat.release_groups}
    assert "This One's for You" in titles
    assert "Life Goes On" in titles

    collab = next(rg for rg in cat.release_groups if rg.title == "Life Goes On")
    assert len(collab.credits) == 2
    assert collab.credits[0].name == "Ed Sheeran"
    assert "feat." in (collab.credits[0].joinphrase or "")
    assert collab.credits[1].name == "Luke Combs"


def test_local_search_release_group(fixture_catalog):
    hit = mb_local.search_release_group_for_artist(
        "Life Goes On",
        "b8a7c51f-362c-4dcb-a259-bc6e0095f0a6",
    )
    assert hit is not None
    assert hit.mbid == "befae816-06e2-426d-aa51-6fcc6d93fca6"
    assert hit.credits


def test_facade_uses_local(fixture_catalog, monkeypatch):
    monkeypatch.setattr(musicbrainz, "_catalog_mode", lambda: "local")
    called = {"live": False}

    def boom(*_a, **_k):
        called["live"] = True
        raise AssertionError("live MusicBrainz should not be called")

    monkeypatch.setattr(musicbrainz, "_get", boom)
    mbid = musicbrainz.resolve_artist("Luke Combs")
    assert mbid == "c20ee61f-071f-4e65-9c81-45ee931a54ce"
    cat = musicbrainz.fetch_catalog(mbid)
    assert not cat.error
    assert any(rg.title == "This One's for You" for rg in cat.release_groups)
    assert called["live"] is False


def test_catalog_status_shape(fixture_catalog):
    status = mb_catalog_import.catalog_status(mode="local")
    assert status["ready"] is True
    assert status["status"] == "ready"
    assert status["dump_version"] == "test-fixture"
    assert status["size_bytes"] > 0
    job = status["job"]
    assert "state" in job
    assert "phase" in job
    assert "progress_pct" in job
    assert "message" in job


def test_job_idle_shape():
    job = mb_catalog_import.get_job()
    assert job.state in {"idle", "running", "done", "error"}
    d = job.__dict__
    for key in ("phase", "progress_pct", "bytes_done", "bytes_total", "message", "error"):
        assert key in d
