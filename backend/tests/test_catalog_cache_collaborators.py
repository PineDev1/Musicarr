from __future__ import annotations

from unittest.mock import patch

from app.services import musicbrainz


def test_cached_catalog_result_preserves_collaborators(monkeypatch):
    """Regression: a cache hit used to silently return collaborators=[] even
    though the original fetch found real ones."""
    musicbrainz._rg_cache.clear()
    monkeypatch.setattr(musicbrainz, "_prefer_local", lambda: False)
    monkeypatch.setattr(musicbrainz, "_allow_live", lambda: True)

    credit = musicbrainz.CreditArtist(mbid="collab-1", name="Featured Artist")
    rg = musicbrainz.ReleaseGroup(
        mbid="rg-1", title="Album", primary_type="album", year="2024",
        secondary_types=(), credits=(credit,),
    )

    with patch.object(musicbrainz, "_get") as fake_get:
        fake_get.side_effect = [
            {
                "release-groups": [
                    {
                        "id": "rg-1",
                        "title": "Album",
                        "primary-type": "Album",
                        "secondary-types": [],
                        "first-release-date": "2024-01-01",
                        "artist-credit": [
                            {"artist": {"id": "artist-self"}},
                            {"artist": {"id": "collab-1", "name": "Featured Artist"}},
                        ],
                    }
                ],
                "release-group-count": 1,
            },
        ]
        first = musicbrainz.fetch_catalog("artist-self")

    assert len(first.collaborators) == 1

    second = musicbrainz.fetch_catalog("artist-self")
    assert len(second.release_groups) == 1
    assert len(second.collaborators) == 1
    assert second.collaborators[0].mbid == "collab-1"

    musicbrainz._rg_cache.clear()
