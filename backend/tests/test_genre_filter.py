from __future__ import annotations

from app.api.artists import get_artists
from app.models import Album, AppSettings, Track
from app.services.artists import _legacy_id
from tests.conftest import _artist


def _settings(db) -> AppSettings:
    row = AppSettings(id=1, active_provider="qobuz")
    db.add(row)
    db.commit()
    return row


def _album_with_track(db, artist, *, genre: str, provider_id: str):
    album = Album(
        provider="qobuz",
        provider_id=provider_id,
        deezer_id=_legacy_id("qobuz", provider_id),
        artist_id=artist.id,
        title=f"Album {provider_id}",
        track_count=1,
        monitored=True,
        status="downloaded",
    )
    db.add(album)
    db.commit()
    db.refresh(album)
    db.add(
        Track(
            provider="qobuz",
            provider_id=f"{provider_id}-t1",
            album_id=album.id,
            title="Song",
            genre=genre,
        )
    )
    db.commit()
    return album


def test_get_artists_filters_by_genre(db):
    _settings(db)
    country_artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    pop_artist = _artist(db, name="Some Pop Act", provider="qobuz", provider_id="a2")
    _album_with_track(db, country_artist, genre="Country", provider_id="al1")
    _album_with_track(db, pop_artist, genre="Pop", provider_id="al2")

    result = get_artists(db=db, genre="Country")

    assert [a.name for a in result] == ["Luke Combs"]


def test_get_artists_no_genre_returns_all(db):
    _settings(db)
    _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    _artist(db, name="Some Pop Act", provider="qobuz", provider_id="a2")

    result = get_artists(db=db, genre=None)

    assert {a.name for a in result} == {"Luke Combs", "Some Pop Act"}
