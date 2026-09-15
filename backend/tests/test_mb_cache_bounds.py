from __future__ import annotations

from unittest.mock import patch

from app.services import musicbrainz as mb
from app.services.musicbrainz import CatalogResult, CreditArtist, ReleaseGroup, _TtlLruCache


def test_ttl_lru_evicts_oldest():
    cache: _TtlLruCache[int] = _TtlLruCache(maxsize=2, ttl_s=3600)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3
    assert len(cache) == 2


def test_ttl_lru_expires():
    cache: _TtlLruCache[str] = _TtlLruCache(maxsize=8, ttl_s=0.01)
    cache.set("k", "v")
    assert cache.get("k") == "v"
    import time

    time.sleep(0.02)
    assert cache.get("k") is None


def test_live_fetch_catalog_populates_bounded_cache():
    mb.clear_cache()
    rg = ReleaseGroup(mbid="rg1", title="Discovery", primary_type="album", year="2001")

    def fake_get(path, params=None):
        if path == "/release-group":
            return {
                "release-groups": [
                    {
                        "id": "rg1",
                        "title": "Discovery",
                        "primary-type": "Album",
                        "secondary-types": [],
                        "first-release-date": "2001-03-12",
                        "artist-credit": [],
                    }
                ],
                "release-group-count": 1,
            }
        return {"_error": "unexpected"}

    with (
        patch.object(mb, "_prefer_local", return_value=False),
        patch.object(mb, "_allow_live", return_value=True),
        patch.object(mb, "_get", side_effect=fake_get),
    ):
        first = mb.fetch_catalog("artist-mbid")
        assert len(first.release_groups) == 1
        assert len(mb._rg_cache) == 1
        # Second call should hit cache (no _get)
        with patch.object(mb, "_get", side_effect=AssertionError("should use cache")):
            second = mb.fetch_catalog("artist-mbid")
        assert second.release_groups[0].mbid == rg.mbid
    mb.clear_cache()
    assert len(mb._rg_cache) == 0


def test_local_fetch_catalog_does_not_grow_cache():
    mb.clear_cache()
    local = CatalogResult(
        release_groups=[
            ReleaseGroup(mbid="rg1", title="Homework", primary_type="album", year="1997")
        ],
        collaborators=[],
    )
    with (
        patch.object(mb, "_prefer_local", return_value=True),
        patch("app.services.mb_local.fetch_catalog", return_value=local),
    ):
        out = mb.fetch_catalog("artist-mbid")
        assert len(out.release_groups) == 1
        assert len(mb._rg_cache) == 0


def test_local_credit_enrich_skips_cache():
    mb.clear_cache()
    rg = ReleaseGroup(mbid="rg-local", title="X", primary_type="album")

    def enrich_local(target: ReleaseGroup) -> ReleaseGroup:
        target.credits = (CreditArtist(mbid="a", name="A"),)
        return target

    with (
        patch.object(mb, "_prefer_local", return_value=True),
        patch("app.services.mb_local.enrich_release_group_credits", side_effect=enrich_local),
    ):
        mb.enrich_release_group_credits(rg)
        assert rg.credits
        assert len(mb._credit_cache) == 0


def test_live_credit_enrich_writes_cache():
    mb.clear_cache()
    rg = ReleaseGroup(mbid="rg-live", title="Y", primary_type="album")
    payload = {
        "id": "rg-live",
        "artist-credit": [
            {"name": "Artist", "joinphrase": "", "artist": {"id": "mb1", "name": "Artist"}}
        ],
    }
    with (
        patch.object(mb, "_prefer_local", return_value=False),
        patch.object(mb, "_allow_live", return_value=True),
        patch.object(mb, "_get", return_value=payload),
    ):
        mb.enrich_release_group_credits(rg)
        assert len(rg.credits) == 1
        assert len(mb._credit_cache) == 1
    mb.clear_cache()
