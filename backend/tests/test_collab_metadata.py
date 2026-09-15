from __future__ import annotations

from app.models import Album
from app.services.artists import _legacy_id, _upsert_mb_album
from app.services.musicbrainz import ReleaseGroup
from app.services.providers.base import ProviderAlbum
from tests.conftest import _artist


def _album(db, artist, *, provider_id, status, musicbrainz_id=None, title="Placeholder"):
    album = Album(
        provider="qobuz",
        provider_id=provider_id,
        deezer_id=_legacy_id("qobuz", provider_id),
        artist_id=artist.id,
        title=title,
        album_type="album",
        track_count=1,
        monitored=True,
        status=status,
        musicbrainz_id=musicbrainz_id,
    )
    db.add(album)
    db.commit()
    db.refresh(album)
    return album


def test_downloaded_row_gets_collab_metadata_without_touching_provider_id(db):
    """Enriching an already-downloaded row's collab credit must not require
    reassigning its provider_id (the common case: the row already sits on
    the right provider id, only the metadata was ever missing)."""
    artist = _artist(db, name="Ed Sheeran", provider="qobuz", provider_id="es1")
    album = _album(db, artist, provider_id="heyk2usghkh1b", status="downloaded")

    rg = ReleaseGroup(mbid="rg-life-goes-on", title="Life Goes On", primary_type="single")
    provider_hit = ProviderAlbum(provider_id="heyk2usghkh1b", title="Life Goes On (feat. Luke Combs)")
    existing_by_mbid: dict = {}
    existing_by_pid = {album.provider_id: album}

    result = _upsert_mb_album(
        db,
        artist=artist,
        rg=rg,
        provider_hit=provider_hit,
        provider_name="qobuz",
        existing_by_mbid=existing_by_mbid,
        existing_by_pid=existing_by_pid,
        collaborator_names=["Luke Combs"],
        artist_credit="Ed Sheeran feat. Luke Combs",
    )
    db.commit()

    assert result.id == album.id
    assert result.artist_credit == "Ed Sheeran feat. Luke Combs"
    assert result.musicbrainz_id == "rg-life-goes-on"
    import json

    assert json.loads(result.collaborators_json) == ["Luke Combs"]


def test_downloaded_row_reassign_avoids_duplicate_provider_id(db):
    """Regression: a downloaded row with a placeholder 'mb:' provider_id must
    be safely reassigned to the real provider id even when a *different*
    row for the same artist already sits on that exact id (a stale
    duplicate) — it must not raise a UNIQUE constraint error."""
    artist = _artist(db, name="Ed Sheeran", provider="qobuz", provider_id="es2")
    stale_duplicate = _album(db, artist, provider_id="heyk2usghkh1b", status="skipped")
    target = _album(db, artist, provider_id="mb:rg-life-goes-on", status="downloaded")

    rg = ReleaseGroup(mbid="rg-life-goes-on", title="Life Goes On", primary_type="single")
    provider_hit = ProviderAlbum(provider_id="heyk2usghkh1b", title="Life Goes On (feat. Luke Combs)")
    existing_by_mbid = {rg.mbid: target}
    existing_by_pid = {
        stale_duplicate.provider_id: stale_duplicate,
        target.provider_id: target,
    }

    result = _upsert_mb_album(
        db,
        artist=artist,
        rg=rg,
        provider_hit=provider_hit,
        provider_name="qobuz",
        existing_by_mbid=existing_by_mbid,
        existing_by_pid=existing_by_pid,
        collaborator_names=["Luke Combs"],
        artist_credit="Ed Sheeran feat. Luke Combs",
    )
    db.commit()

    assert result.id == target.id
    # Got some safe, unique provider_id — not the exact raw pid the stale
    # duplicate still holds.
    assert result.provider_id != "heyk2usghkh1b" or stale_duplicate.provider_id != "heyk2usghkh1b"


def test_non_downloaded_duplicate_is_cleaned_up_on_reassign(db):
    """Same collision, but the conflicting row isn't downloaded — it should
    be deleted (not left to collide) when the real row claims its provider id,
    without a UNIQUE constraint error from delete/update ordering."""
    artist = _artist(db, name="Ed Sheeran", provider="qobuz", provider_id="es3")
    stale_duplicate = _album(db, artist, provider_id="rawpid123", status="skipped")
    target = _album(db, artist, provider_id="mb:rg-x", status="wanted")

    rg = ReleaseGroup(mbid="rg-x", title="Some Song", primary_type="single")
    provider_hit = ProviderAlbum(provider_id="rawpid123", title="Some Song (feat. Other Artist)")
    existing_by_mbid = {rg.mbid: target}
    existing_by_pid = {
        stale_duplicate.provider_id: stale_duplicate,
        target.provider_id: target,
    }

    result = _upsert_mb_album(
        db,
        artist=artist,
        rg=rg,
        provider_hit=provider_hit,
        provider_name="qobuz",
        existing_by_mbid=existing_by_mbid,
        existing_by_pid=existing_by_pid,
        collaborator_names=["Other Artist"],
        artist_credit="Ed Sheeran feat. Other Artist",
    )
    db.commit()

    assert result.provider_id == "rawpid123"
    remaining = db.get(Album, stale_duplicate.id)
    assert remaining is None
