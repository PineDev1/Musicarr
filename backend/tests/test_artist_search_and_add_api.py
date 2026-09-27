from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.api import artists as artists_api
from app.models.schemas import ArtistCreate, BulkArtistSearchRequest
from app.services.providers.base import ProviderError


def test_search_artists_falls_back_to_musicbrainz_without_a_provider(db):
    """Regression: with no working streaming-provider session (e.g. a
    torrent/Usenet-only setup with no Deezer/Tidal/Qobuz login), artist
    search used to hard-fail with a 400 instead of falling back to
    MusicBrainz, which needs no provider at all."""
    mb_hits = [{"mbid": "mbid-1", "name": "Some Indie Band", "rg_count": 3}]

    with patch("app.api.artists.get_active_provider", side_effect=ProviderError("not logged in")), \
         patch("app.services.musicbrainz.search_artists", return_value=mb_hits):
        results = artists_api.search_artists(q="Some Indie Band", db=db)

    assert len(results) == 1
    assert results[0].provider == "local"
    assert results[0].provider_id == "mbid-1"
    assert results[0].name == "Some Indie Band"
    assert results[0].image_url is None
    assert results[0].nb_album == 3


def test_search_artists_uses_provider_when_available(db):
    mock_provider = MagicMock()
    mock_provider.name = "deezer"
    hit = MagicMock(provider_id="42", name="Some Artist", image_url="http://x/img.jpg", nb_album=5)
    hit.name = "Some Artist"
    mock_provider.search_artists.return_value = [hit]

    with patch("app.api.artists.get_active_provider", return_value=mock_provider), \
         patch("app.services.musicbrainz.resolve_artist", return_value=None):
        results = artists_api.search_artists(q="Some Artist", db=db)

    assert len(results) == 1
    assert results[0].provider == "deezer"


def test_bulk_search_artists_falls_back_to_musicbrainz_without_a_provider(db):
    mb_hits = [{"mbid": "mbid-1", "name": "Some Indie Band", "rg_count": 2}]

    with patch("app.api.artists.get_active_provider", side_effect=ProviderError("not logged in")), \
         patch("app.services.musicbrainz.search_artists", return_value=mb_hits):
        out = artists_api.bulk_search_artists(
            BulkArtistSearchRequest(names="Some Indie Band"), db=db
        )

    assert len(out) == 1
    assert out[0].query == "Some Indie Band"
    assert out[0].results[0].provider == "local"
    assert out[0].results[0].provider_id == "mbid-1"


def test_create_artist_with_local_provider_adds_via_musicbrainz(db):
    mock_catalog = MagicMock()
    mock_catalog.error = None
    mock_catalog.release_groups = []
    mock_catalog.collaborators = []

    with patch("app.services.musicbrainz.fetch_catalog", return_value=mock_catalog):
        out = artists_api.create_artist(
            ArtistCreate(provider="local", provider_id="mbid-abc", name="Some Indie Band"),
            db=db,
        )

    assert out.provider == "local"
    assert out.name == "Some Indie Band"
