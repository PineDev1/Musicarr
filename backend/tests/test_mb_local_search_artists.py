from __future__ import annotations

import pytest

from app.services import mb_local
from app.services.mb_catalog_import import build_fixture_catalog


@pytest.fixture()
def fixture_catalog(tmp_path):
    db_path = tmp_path / "catalog.sqlite"
    build_fixture_catalog(db_path)
    mb_local.configure(db_path)
    yield db_path
    mb_local.configure(None)


def test_search_artists_ranks_exact_match_with_real_releases_first(fixture_catalog):
    """The fixture has two "Ed Sheeran" rows: a real one credited on a
    release group, and a same-named stub with none. Both are exact
    name matches, so the tiebreak must be release-group count."""
    results = mb_local.search_artists("Ed Sheeran")
    names = [r["name"] for r in results]
    assert names.count("Ed Sheeran") == 2
    assert results[0]["mbid"] == "b8a7c51f-362c-4dcb-a259-bc6e0095f0a6"
    assert results[0]["rg_count"] >= 1


def test_search_artists_matches_via_alias(fixture_catalog):
    results = mb_local.search_artists("Edward Sheeran")
    assert any(r["mbid"] == "b8a7c51f-362c-4dcb-a259-bc6e0095f0a6" for r in results)


def test_search_artists_partial_query(fixture_catalog):
    results = mb_local.search_artists("Luke")
    assert any(r["name"] == "Luke Combs" for r in results)


def test_search_artists_returns_empty_for_unknown_name(fixture_catalog):
    assert mb_local.search_artists("Totally Unknown Artist Name Xyz") == []


def test_search_artists_empty_query_returns_empty(fixture_catalog):
    assert mb_local.search_artists("") == []


def test_search_artists_respects_limit(fixture_catalog):
    results = mb_local.search_artists("e", limit=1)
    assert len(results) == 1
