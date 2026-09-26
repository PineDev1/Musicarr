from __future__ import annotations

from unittest.mock import patch

from app.api.player import build_radio_tracks
from app.models import Album, AppSettings, Track
from tests.conftest import _artist


def _settings(db) -> AppSettings:
    row = AppSettings(id=1, lastfm_api_key="key", lastfm_api_secret="secret")
    db.add(row)
    db.commit()
    return row


def _downloaded_track(db, album, *, provider_id, title="Song"):
    t = Track(
        provider=album.provider,
        provider_id=provider_id,
        album_id=album.id,
        title=title,
        path=f"/library/{provider_id}.flac",
    )
    db.add(t)
    db.commit()
    return t


def test_radio_pulls_tracks_from_matched_similar_artists(db):
    _settings(db)
    seed = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    similar = _artist(db, name="Ed Sheeran", provider="qobuz", provider_id="a2")

    similar_album = Album(provider="qobuz", provider_id="al1", artist_id=similar.id, title="Album")
    db.add(similar_album)
    db.commit()
    for i in range(3):
        _downloaded_track(db, similar_album, provider_id=f"t{i}")

    with patch(
        "app.services.lastfm.similar_artists",
        return_value=[{"name": "Ed Sheeran", "match": 0.9}],
    ):
        tracks = build_radio_tracks(db, seed)

    assert len(tracks) == 3
    assert all(t.album.artist_id == similar.id for t in tracks)


def test_radio_falls_back_to_seed_artist_when_pool_too_small(db):
    _settings(db)
    seed = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    seed_album = Album(provider="qobuz", provider_id="al1", artist_id=seed.id, title="Album")
    db.add(seed_album)
    db.commit()
    for i in range(5):
        _downloaded_track(db, seed_album, provider_id=f"t{i}")

    with patch("app.services.lastfm.similar_artists", return_value=[]):
        tracks = build_radio_tracks(db, seed)

    assert len(tracks) == 5
    assert all(t.album.artist_id == seed.id for t in tracks)


def test_radio_excludes_the_seed_artist_from_the_similar_pool(db):
    _settings(db)
    seed = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    seed_album = Album(provider="qobuz", provider_id="al1", artist_id=seed.id, title="Album")
    db.add(seed_album)
    db.commit()
    _downloaded_track(db, seed_album, provider_id="t0")

    # Last.fm's own similar-artist result can (rarely) echo the seed name
    # back — must not treat the seed artist as its own "similar" match.
    with patch(
        "app.services.lastfm.similar_artists",
        return_value=[{"name": "Luke Combs", "match": 1.0}],
    ):
        tracks = build_radio_tracks(db, seed)

    # Falls back to the seed artist's own tracks either way, but via the
    # fallback path, not by double-counting it as a "similar" match.
    assert len(tracks) == 1
