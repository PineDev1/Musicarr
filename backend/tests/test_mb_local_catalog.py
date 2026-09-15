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


def test_resolve_artist_folds_diacritics(fixture_catalog):
    beyonce_mbid = "99999999-8888-7777-6666-555555555555"
    # Exact accented name still resolves.
    assert mb_local.resolve_artist("Beyoncé") == beyonce_mbid
    # ASCII query with no accent must still find the accented DB row.
    assert mb_local.resolve_artist("Beyonce") == beyonce_mbid


def test_search_release_group_distinguishes_editions(fixture_catalog):
    beyonce_mbid = "99999999-8888-7777-6666-555555555555"
    standard = mb_local.search_release_group_for_artist("Renaissance", beyonce_mbid)
    assert standard is not None
    assert standard.title == "Renaissance"

    deluxe = mb_local.search_release_group_for_artist(
        "Renaissance (Deluxe Edition)", beyonce_mbid
    )
    assert deluxe is not None
    assert deluxe.title == "Renaissance (Deluxe Edition)"


def test_search_release_group_finds_collab_despite_duplicate_artist_mbid(fixture_catalog):
    """Regression test: MusicBrainz can have two different MBIDs for the same
    real artist. If the artist Musicarr resolved to isn't the one linked via
    artist_rg to the real collab release-group, the wide-search fallback must
    still find it by matching the credited artist's *name* — and must never
    fall back to an unrelated same-titled release-group (here, a decoy also
    called "Life Goes On" credited to a different artist).
    """
    other_ed_sheeran_mbid = "dddddddd-1111-2222-3333-444444444444"
    hit = mb_local.search_release_group_for_artist(
        "Life Goes On (feat. Luke Combs)", other_ed_sheeran_mbid
    )
    assert hit is not None
    assert hit.mbid == "befae816-06e2-426d-aa51-6fcc6d93fca6"
    assert {c.name for c in hit.credits} == {"Ed Sheeran", "Luke Combs"}


def test_search_release_group_rejects_uncredited_same_title(fixture_catalog):
    """An artist genuinely unrelated to a same-titled release-group must not
    match it just because the bare title lines up."""
    other_ed_sheeran_mbid = "dddddddd-1111-2222-3333-444444444444"
    hit = mb_local.search_release_group_for_artist("Life Goes On", other_ed_sheeran_mbid)
    # Either no match, or a match that's genuinely credited to Ed Sheeran —
    # never the "Some Other Band" decoy release-group.
    if hit is not None:
        assert "Ed Sheeran" in {c.name for c in hit.credits}


def test_job_idle_shape():
    job = mb_catalog_import.get_job()
    assert job.state in {"idle", "running", "done", "error"}
    d = job.__dict__
    for key in ("phase", "progress_pct", "bytes_done", "bytes_total", "message", "error"):
        assert key in d
