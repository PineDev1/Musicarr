from __future__ import annotations

from unittest.mock import patch

from app.services import discovery
from tests.conftest import _artist


def test_discover_similar_dedupes_and_ranks_across_monitored_artists(db):
    discovery.clear_cache()
    a = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    b = _artist(db, name="Chris Stapleton", provider="qobuz", provider_id="a2")

    def fake_similar(_db, name, *, limit=10):
        if name == "Luke Combs":
            return [{"name": "Cody Johnson", "match": 0.4}, {"name": "Chris Stapleton", "match": 0.9}]
        if name == "Chris Stapleton":
            return [{"name": "Cody Johnson", "match": 0.7}, {"name": "Jason Isbell", "match": 0.6}]
        return []

    with patch("app.services.discovery.lastfm.similar_artists", side_effect=fake_similar):
        results = discovery.discover_similar(db)

    names = [r["name"] for r in results]
    # "Chris Stapleton" is already a monitored artist — must not suggest
    # adding someone already in the library as if they were new.
    assert "Chris Stapleton" not in names
    assert "Cody Johnson" in names
    assert "Jason Isbell" in names
    # First seen wins the dedupe (Cody Johnson from Luke Combs' list, match 0.4),
    # but ranking is still by match score descending.
    assert results[0]["name"] == "Jason Isbell"


def test_discover_similar_flags_already_in_library(db):
    discovery.clear_cache()
    seed = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    already = _artist(db, name="Cody Johnson", provider="qobuz", provider_id="a2")
    already.status = "inactive"  # not itself monitored/active, still findable by name
    db.commit()

    with patch(
        "app.services.discovery.lastfm.similar_artists",
        return_value=[{"name": "Cody Johnson", "match": 0.5}],
    ):
        results = discovery.discover_similar(db)

    assert results[0]["already_in_library"] == already.id


def test_discover_similar_caches_between_calls(db):
    discovery.clear_cache()
    _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    calls = {"n": 0}

    def fake_similar(_db, name, *, limit=10):
        calls["n"] += 1
        return [{"name": "Cody Johnson", "match": 0.5}]

    with patch("app.services.discovery.lastfm.similar_artists", side_effect=fake_similar):
        discovery.discover_similar(db)
        discovery.discover_similar(db)

    assert calls["n"] == 1


def test_discover_similar_skips_indexers_that_error(db):
    discovery.clear_cache()
    _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    from app.services.lastfm import LastfmError

    with patch("app.services.discovery.lastfm.similar_artists", side_effect=LastfmError("boom")):
        assert discovery.discover_similar(db) == []
