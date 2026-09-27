from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.models import Album, AppSettings
from app.services.artists import _legacy_id
from app.services.indexer_engine import resolve_or_create_album_for_release
from app.services.musicbrainz import ReleaseGroup
from tests.conftest import _artist


def _settings(db) -> AppSettings:
    row = AppSettings(
        id=1,
        library_path="/tmp/musicarr-test",
        active_provider="deezer",
        include_albums=True,
        include_eps=True,
        include_singles=True,
        include_compilations=False,
        official_releases_only=True,
        ignore_junk_titles=False,
        ignore_live_releases=False,
    )
    db.add(row)
    db.commit()
    return row


def test_resolves_to_existing_album_by_exact_title(db):
    _settings(db)
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    existing = Album(
        provider="qobuz", provider_id="al1", deezer_id=_legacy_id("qobuz", "al1"),
        artist_id=artist.id, title="Fathers & Sons", status="wanted",
    )
    db.add(existing)
    db.commit()
    db.refresh(artist)

    album = resolve_or_create_album_for_release(db, artist, "Fathers & Sons")
    assert album.id == existing.id


def test_resolves_to_existing_album_by_loose_title_match(db):
    _settings(db)
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    existing = Album(
        provider="qobuz", provider_id="al1", deezer_id=_legacy_id("qobuz", "al1"),
        artist_id=artist.id, title="Fathers & Sons", status="wanted",
    )
    db.add(existing)
    db.commit()
    db.refresh(artist)

    # A slightly noisy release title from an indexer result should still
    # loosely match the known album rather than creating a duplicate.
    album = resolve_or_create_album_for_release(db, artist, "Fathers & Sons.")
    assert album.id == existing.id


def test_resolves_to_existing_album_despite_indexer_quality_tags(db):
    """Regression: a real indexer release title always carries quality/source
    tags ("[FLAC]", "[WEB]") — matching logic borrowed from tag-based library
    import treats any bracket content as meaningful edition info and skips
    its loose-match tier entirely once brackets are present, which used to
    make every real release title miss the existing album and create a
    duplicate instead of reusing it."""
    _settings(db)
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    existing = Album(
        provider="qobuz", provider_id="al1", deezer_id=_legacy_id("qobuz", "al1"),
        artist_id=artist.id, title="Fathers & Sons", status="wanted",
    )
    db.add(existing)
    db.commit()
    db.refresh(artist)

    album = resolve_or_create_album_for_release(db, artist, "Fathers & Sons [FLAC][WEB]")
    assert album.id == existing.id


def test_resolves_to_existing_album_with_apostrophe_stripped_in_release_title(db):
    """Regression: indexer/torrent release names routinely drop apostrophes
    ("Don't" -> "Dont") — the old normalizer turned a stripped apostrophe
    into a token-splitting space ("don t"), so "don" (3 chars, kept) never
    matched the release's "dont" token, scoring well under the match floor
    and creating a duplicate album instead of reusing the existing one."""
    _settings(db)
    artist = _artist(db, name="Test Artist", provider="qobuz", provider_id="a1")
    existing = Album(
        provider="qobuz", provider_id="al1", deezer_id=_legacy_id("qobuz", "al1"),
        artist_id=artist.id, title="Don't Stop", status="wanted",
    )
    db.add(existing)
    db.commit()
    db.refresh(artist)

    album = resolve_or_create_album_for_release(db, artist, "Test Artist - Dont Stop [FLAC][WEB]")
    assert album.id == existing.id


def test_resolves_via_musicbrainz_when_no_existing_album_matches(db):
    """Regression: resolving via MusicBrainz (not this artist's own streaming
    provider) must land as status="wanted", not "missing" — "missing" means
    "the provider doesn't have this release," which doesn't apply here."""
    _settings(db)
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    rg = ReleaseGroup(mbid="rg-1", title="Gettin' Old", primary_type="album", year="2023")

    with patch("app.services.artists.ensure_musicbrainz_identity", return_value="mb-artist"), \
         patch("app.services.musicbrainz.search_release_group_for_artist", return_value=rg):
        album = resolve_or_create_album_for_release(db, artist, "Gettin' Old")

    assert album.title == "Gettin' Old"
    assert album.status == "wanted"
    assert not album.status_reason


def test_falls_back_to_a_bare_album_when_nothing_resolves(db):
    _settings(db)
    artist = _artist(db, name="Some Indie Band", provider="local", provider_id="mb-1")

    with patch("app.services.artists.ensure_musicbrainz_identity", return_value=None):
        album = resolve_or_create_album_for_release(db, artist, "A Totally Obscure Release")

    assert album.title == "A Totally Obscure Release"
    assert album.status == "wanted"
    assert album.artist_id == artist.id


def test_bare_fallback_is_idempotent_for_the_same_title(db):
    _settings(db)
    artist = _artist(db, name="Some Indie Band", provider="local", provider_id="mb-1")

    with patch("app.services.artists.ensure_musicbrainz_identity", return_value=None):
        first = resolve_or_create_album_for_release(db, artist, "A Totally Obscure Release")
        db.refresh(artist)
        second = resolve_or_create_album_for_release(db, artist, "A Totally Obscure Release")

    assert first.id == second.id
