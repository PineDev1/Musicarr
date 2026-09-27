from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.models import AppSettings
from app.services.artists import add_local_artist_from_mbid
from app.services.musicbrainz import ReleaseGroup


def _settings(db) -> AppSettings:
    row = AppSettings(
        id=1,
        library_path="/tmp/musicarr-test",
        active_provider="deezer",
        include_albums=True,
        include_eps=True,
        include_singles=False,
        include_compilations=False,
        official_releases_only=True,
        ignore_junk_titles=False,
        ignore_live_releases=False,
    )
    db.add(row)
    db.commit()
    return row


def test_add_local_artist_from_mbid_creates_artist_with_no_provider(db):
    _settings(db)
    mock_catalog = MagicMock()
    mock_catalog.error = None
    mock_catalog.release_groups = []
    mock_catalog.collaborators = []

    with patch("app.services.musicbrainz.fetch_catalog", return_value=mock_catalog):
        artist = add_local_artist_from_mbid(db, "mbid-1234", "Some Indie Band")

    assert artist.provider == "local"
    assert artist.provider_id == "mbid-1234"
    assert artist.musicbrainz_id == "mbid-1234"
    assert artist.name == "Some Indie Band"


def test_add_local_artist_from_mbid_marks_albums_wanted_not_missing(db):
    """Regression: _upsert_mb_album's "no provider hit" branch unconditionally
    set status="missing" with a "<Provider> doesn't have this release"
    reason — written for a real streaming-provider artist whose catalog is
    just incomplete. A "local" (no-provider) artist has no provider catalog
    to be missing *from* in the first place; every MusicBrainz release group
    is simply wanted, or it would silently disappear from the Wanted page
    (which only lists status="wanted") even though "Search releases" could
    still grab it from an indexer."""
    _settings(db)
    mock_catalog = MagicMock()
    mock_catalog.error = None
    mock_catalog.release_groups = [
        ReleaseGroup(mbid="rg-1", title="Debut Album", primary_type="album", year="2020"),
    ]
    mock_catalog.collaborators = []

    with patch("app.services.musicbrainz.fetch_catalog", return_value=mock_catalog):
        artist = add_local_artist_from_mbid(db, "mbid-5678", "Some Indie Band")

    albums = list(artist.albums)
    assert len(albums) == 1
    assert albums[0].status == "wanted"
    assert albums[0].monitored is True
    assert not albums[0].status_reason


def test_add_local_artist_from_mbid_is_idempotent(db):
    _settings(db)
    mock_catalog = MagicMock()
    mock_catalog.error = None
    mock_catalog.release_groups = []
    mock_catalog.collaborators = []

    with patch("app.services.musicbrainz.fetch_catalog", return_value=mock_catalog):
        first = add_local_artist_from_mbid(db, "mbid-9999", "Some Band")
        second = add_local_artist_from_mbid(db, "mbid-9999", "Some Band")

    assert first.id == second.id
