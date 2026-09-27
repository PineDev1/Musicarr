from __future__ import annotations

from unittest.mock import patch

from app.models import Album, AppSettings, PlayerFavorite, PlayerPlayEvent, PlayerUser, Track
from app.services.player_mixes import made_for_you_mixes
from tests.conftest import _artist


def _settings(db) -> AppSettings:
    row = AppSettings(id=1, lastfm_api_key="key", lastfm_api_secret="secret")
    db.add(row)
    db.commit()
    return row


def _user(db, username="listener") -> PlayerUser:
    user = PlayerUser(username=username, password_hash="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _downloaded_track(db, album, *, provider_id, title="Song") -> Track:
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


def test_mixes_seeded_from_top_played_artist_and_similar_artists(db):
    _settings(db)
    user = _user(db)
    seed = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    similar = _artist(db, name="Ed Sheeran", provider="qobuz", provider_id="a2")
    other = _artist(db, name="Unrelated Band", provider="qobuz", provider_id="a3")

    seed_album = Album(provider="qobuz", provider_id="al1", artist_id=seed.id, title="Album")
    similar_album = Album(provider="qobuz", provider_id="al2", artist_id=similar.id, title="Album2")
    other_album = Album(provider="qobuz", provider_id="al3", artist_id=other.id, title="Album3")
    db.add_all([seed_album, similar_album, other_album])
    db.commit()

    seed_track = _downloaded_track(db, seed_album, provider_id="t0")
    for i in range(3):
        _downloaded_track(db, similar_album, provider_id=f"s{i}")
    _downloaded_track(db, other_album, provider_id="o0")

    # Plenty of plays on the seed artist's track — makes it the top artist.
    for _ in range(5):
        db.add(PlayerPlayEvent(user_id=user.id, track_id=seed_track.id))
    db.commit()

    with patch(
        "app.services.lastfm.similar_artists",
        return_value=[{"name": "Ed Sheeran", "match": 0.9}],
    ):
        mixes = made_for_you_mixes(db, user.id)

    assert len(mixes) == 1
    artist, tracks = mixes[0]
    assert artist.id == seed.id
    artist_ids_in_mix = {t.album.artist_id for t in tracks}
    # Includes the seed artist's own track and the matched similar artist's
    # tracks, but never the unrelated artist's.
    assert seed.id in artist_ids_in_mix
    assert similar.id in artist_ids_in_mix
    assert other.id not in artist_ids_in_mix


def test_mixes_fall_back_to_favorited_artist_with_no_play_history(db):
    _settings(db)
    user = _user(db)
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    album = Album(provider="qobuz", provider_id="al1", artist_id=artist.id, title="Album")
    db.add(album)
    db.commit()
    track = _downloaded_track(db, album, provider_id="t0")
    db.add(PlayerFavorite(user_id=user.id, track_id=track.id))
    db.commit()

    with patch("app.services.lastfm.similar_artists", return_value=[]):
        mixes = made_for_you_mixes(db, user.id)

    assert len(mixes) == 1
    assert mixes[0][0].id == artist.id


def test_mixes_are_stable_across_calls_on_the_same_day(db):
    """A "daily mix" should feel stable while browsing, not reshuffle on
    every page load — only the per-day seed should change the order."""
    _settings(db)
    user = _user(db)
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    album = Album(provider="qobuz", provider_id="al1", artist_id=artist.id, title="Album")
    db.add(album)
    db.commit()
    seed_track = _downloaded_track(db, album, provider_id="t0")
    for i in range(1, 10):
        _downloaded_track(db, album, provider_id=f"t{i}")
    for _ in range(3):
        db.add(PlayerPlayEvent(user_id=user.id, track_id=seed_track.id))
    db.commit()

    with patch("app.services.lastfm.similar_artists", return_value=[]):
        first = made_for_you_mixes(db, user.id)
        second = made_for_you_mixes(db, user.id)

    assert [t.id for t in first[0][1]] == [t.id for t in second[0][1]]


def test_mixes_skip_a_seed_artist_with_nothing_downloaded(db):
    _settings(db)
    user = _user(db)
    artist = _artist(db, name="Ghost Artist", provider="qobuz", provider_id="a1")
    album = Album(provider="qobuz", provider_id="al1", artist_id=artist.id, title="Album")
    db.add(album)
    db.commit()
    # A track with no local file — nothing playable, shouldn't seed a mix.
    track = Track(provider="qobuz", provider_id="t0", album_id=album.id, title="Song", path=None)
    db.add(track)
    db.commit()
    db.add(PlayerPlayEvent(user_id=user.id, track_id=track.id))
    db.commit()

    with patch("app.services.lastfm.similar_artists", return_value=[]):
        mixes = made_for_you_mixes(db, user.id)

    assert mixes == []
