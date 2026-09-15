from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.models import AppSettings
from app.services.artists import link_artists_by_mbid, list_artists_grouped, sync_artist_albums
from app.services.musicbrainz import (
    ReleaseGroup,
    is_official_match,
    match_provider_album,
    match_release,
    normalize_title,
)
from app.services.providers.base import ProviderAlbum
from tests.conftest import _artist


def test_normalize_title_strips_edition_noise():
    assert normalize_title("Random Access Memories (Deluxe Edition)") == "random access memories"
    assert normalize_title("Discovery [Remastered]") == "discovery"


def test_match_release_fuzzy_title_and_year():
    catalog = [
        ReleaseGroup(mbid="rg1", title="Discovery", primary_type="album", year="2001"),
        ReleaseGroup(mbid="rg2", title="Homework", primary_type="album", year="1997"),
    ]
    hit = match_release("Discovery (Remastered)", "2001", "album", catalog)
    assert hit is not None
    assert hit.mbid == "rg1"
    assert is_official_match("Unknown Bootleg Live", "2019", "album", catalog) is False


def test_match_release_rejects_unrelated_title():
    catalog = [ReleaseGroup(mbid="rg1", title="Blue Album", primary_type="album", year="1994")]
    assert match_release("Pinkerton", "1996", "album", catalog) is None
    assert match_release("Completely Different Bootleg", "1994", "album", catalog) is None


def test_match_provider_album_for_rg():
    rg = ReleaseGroup(mbid="rg1", title="Discovery", primary_type="album", year="2001")
    albums = [
        ProviderAlbum(provider_id="1", title="Homework", album_type="album", release_date="1997"),
        ProviderAlbum(provider_id="2", title="Discovery", album_type="album", release_date="2001-03-12"),
    ]
    hit = match_provider_album(rg, albums)
    assert hit is not None
    assert hit.provider_id == "2"


def test_link_artists_by_shared_mbid(db):
    mbid = "mbid-daft-punk"
    a = _artist(db, name="Daft Punk", provider="tidal", provider_id="t1", musicbrainz_id=mbid)
    b = _artist(db, name="Daft Punk", provider="qobuz", provider_id="q1", musicbrainz_id=mbid)
    _artist(db, name="Daft Punk", provider="deezer", provider_id="d1", musicbrainz_id="other-mbid")

    linked = link_artists_by_mbid(db, mbid)
    assert {x.id for x in linked} == {a.id, b.id}
    assert a.link_group_id == mbid
    assert b.link_group_id == mbid

    groups = list_artists_grouped(db)
    assert len(groups) == 2
    sizes = sorted(len(g) for g in groups)
    assert sizes == [1, 2]


def test_sync_mb_first_wanted_and_missing(db):
    settings = AppSettings(
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
    db.add(settings)
    db.commit()

    artist = _artist(db, name="Test Artist", provider="deezer", provider_id="100")
    catalog_rgs = [
        ReleaseGroup(mbid="rg-ok", title="Official Album", primary_type="album", year="2020"),
        ReleaseGroup(mbid="rg-miss", title="Only On Vinyl", primary_type="album", year="2019"),
    ]
    provider_albums = [
        ProviderAlbum(
            provider_id="a1",
            title="Official Album",
            album_type="album",
            release_date="2020-01-01",
            cover_url=None,
            track_count=10,
        ),
        ProviderAlbum(
            provider_id="a2",
            title="Random Fan Compilation",
            album_type="album",
            release_date="2021-01-01",
            cover_url=None,
            track_count=12,
        ),
    ]
    mock_provider = MagicMock()
    mock_provider.name = "deezer"
    mock_provider.list_albums.return_value = provider_albums
    mock_catalog = MagicMock()
    mock_catalog.error = None
    mock_catalog.release_groups = catalog_rgs
    mock_catalog.collaborators = []

    with (
        patch("app.services.artists.get_active_provider", return_value=mock_provider),
        patch("app.services.artists.ensure_musicbrainz_identity", return_value="mb-artist"),
        patch("app.services.musicbrainz.fetch_catalog", return_value=mock_catalog),
    ):
        albums = sync_artist_albums(db, artist, discover_featured=False)

    by_title = {a.title: a for a in albums}
    assert by_title["Official Album"].status == "wanted"
    assert by_title["Official Album"].monitored is True
    assert by_title["Only On Vinyl"].status == "missing"
    assert "doesn't have this release" in (by_title["Only On Vinyl"].status_reason or "")
    assert by_title["Random Fan Compilation"].status == "skipped"


def test_sync_unresolved_artist_fails_open(db):
    settings = AppSettings(
        id=1,
        library_path="/tmp/musicarr-test",
        active_provider="deezer",
        include_albums=True,
        include_eps=True,
        include_singles=False,
        include_compilations=False,
        official_releases_only=True,
        ignore_junk_titles=False,
    )
    db.add(settings)
    db.commit()

    artist = _artist(db, name="Nobody", provider="deezer", provider_id="200")
    mock_provider = MagicMock()
    mock_provider.name = "deezer"
    mock_provider.list_albums.return_value = [
        ProviderAlbum(
            provider_id="x1",
            title="Anything",
            album_type="album",
            release_date="2020-01-01",
            cover_url=None,
            track_count=8,
        ),
    ]

    with (
        patch("app.services.artists.get_active_provider", return_value=mock_provider),
        patch("app.services.artists.ensure_musicbrainz_identity", return_value=None),
    ):
        albums = sync_artist_albums(db, artist, discover_featured=False)

    assert len(albums) == 1
    assert albums[0].status == "wanted"
    assert albums[0].monitored is True
