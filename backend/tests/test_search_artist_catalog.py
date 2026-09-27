from __future__ import annotations

from unittest.mock import patch

from app.api import acquisition
from app.models import Album
from app.models.schemas import ReleaseGrabRequest
from app.services.artists import _legacy_id
from app.services.indexer_engine import search_artist_catalog
from app.services.indexers.base import ReleaseCandidate
from tests.conftest import _artist


def _album(db, artist, title, provider_id) -> Album:
    album = Album(
        provider=artist.provider, provider_id=provider_id, deezer_id=_legacy_id(artist.provider, provider_id),
        artist_id=artist.id, title=title, status="wanted",
    )
    db.add(album)
    db.commit()
    db.refresh(album)
    return album


def test_search_artist_catalog_annotates_matched_and_unmatched_releases(db):
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    known = _album(db, artist, "Fathers & Sons", "al1")
    db.refresh(artist)

    hits = [
        ReleaseCandidate(title="Fathers & Sons [FLAC]", protocol="usenet", download_url="https://x/1.nzb"),
        ReleaseCandidate(title="Some Random B-Side [FLAC]", protocol="usenet", download_url="https://x/2.nzb"),
    ]
    with patch("app.services.indexers.search.search_album", return_value=(hits, [])):
        annotated, errors = search_artist_catalog(db, artist)

    assert errors == []
    by_title = {c.title: album for c, album in annotated}
    assert by_title["Fathers & Sons [FLAC]"].id == known.id
    assert by_title["Some Random B-Side [FLAC]"] is None


def test_search_releases_for_artist_endpoint_returns_matches(db):
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    known = _album(db, artist, "Fathers & Sons", "al1")

    hits = [ReleaseCandidate(title="Fathers & Sons [FLAC]", protocol="usenet", download_url="https://x/1.nzb")]
    with patch("app.services.indexers.search.search_album", return_value=(hits, [])):
        out = acquisition.search_releases_for_artist(artist_id=artist.id, db=db)

    assert len(out.results) == 1
    assert out.results[0].matched_album_id == known.id
    assert out.results[0].matched_album_title == "Fathers & Sons"


def test_grab_release_with_artist_id_resolves_album_first(db):
    """An unmatched artist-level search result has no album_id yet — the
    grab endpoint must resolve/create one via artist_id before dispatching."""
    from app.models import DownloadClient

    artist = _artist(db, name="Some Indie Band", provider="local", provider_id="mb-1")
    db.add(DownloadClient(name="sab", protocol="usenet", implementation="sabnzbd", host="localhost", port=8080, enabled=True))
    db.commit()

    class FakeClient:
        def test(self):
            return True, "ok"

        def add_url(self, url, category=""):
            return "hash123"

        def close(self):
            pass

    with patch("app.services.acquisition_actions.get_client", return_value=FakeClient()), \
         patch("app.services.artists.ensure_musicbrainz_identity", return_value=None):
        result = acquisition.grab_release(
            ReleaseGrabRequest(artist_id=artist.id, grab_url="https://x/1.nzb", protocol="usenet", title="A Loose Single"),
            db=db,
        )

    assert result["ok"] is True
    album = db.query(Album).filter(Album.artist_id == artist.id).one()
    assert album.title == "A Loose Single"
    assert album.status == "wanted"


def test_grab_release_requires_album_id_or_artist_id(db):
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        acquisition.grab_release(
            ReleaseGrabRequest(grab_url="https://x/1.nzb", protocol="usenet"), db=db
        )
    assert exc.value.status_code == 400
