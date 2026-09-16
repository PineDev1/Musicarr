from __future__ import annotations

import json

from app.models import (
    Album,
    Artist,
    PlayerFavorite,
    PlayerPlayEvent,
    PlayerPlaylist,
    PlayerUser,
    Track,
)
from app.services.smart_playlists import evaluate_smart_playlist


def _user(db, username="u1"):
    user = PlayerUser(username=username, password_hash="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _album_with_track(db, *, artist_name, title, genre="", fmt="flac"):
    artist = Artist(
        provider="qobuz", provider_id=artist_name, name=artist_name, monitored=True
    )
    db.add(artist)
    db.commit()
    db.refresh(artist)
    album = Album(provider="qobuz", provider_id=title, artist_id=artist.id, title=title)
    db.add(album)
    db.commit()
    db.refresh(album)
    track = Track(
        provider="qobuz",
        provider_id=f"{title}-1",
        album_id=album.id,
        title=title,
        path=f"/music/{title}.{fmt}",
        genre=genre,
    )
    db.add(track)
    db.commit()
    db.refresh(track)
    return artist, album, track


def _smart_playlist(db, user, criteria: dict):
    pl = PlayerPlaylist(
        user_id=user.id, name="Smart", is_smart=True, criteria_json=json.dumps(criteria)
    )
    db.add(pl)
    db.commit()
    db.refresh(pl)
    return pl


def test_genre_rule_filters(db):
    user = _user(db)
    _, _, rock = _album_with_track(db, artist_name="A", title="Rock Song", genre="Rock")
    _, _, jazz = _album_with_track(db, artist_name="B", title="Jazz Song", genre="Jazz")

    pl = _smart_playlist(
        db, user, {"match": "all", "rules": [{"field": "genre", "op": "eq", "value": "Rock"}]}
    )
    result = evaluate_smart_playlist(db, pl)
    assert [t.id for t in result] == [rock.id]


def test_favorited_rule(db):
    user = _user(db)
    _, _, liked = _album_with_track(db, artist_name="A", title="Liked")
    _, _, unliked = _album_with_track(db, artist_name="B", title="Unliked")
    db.add(PlayerFavorite(user_id=user.id, track_id=liked.id))
    db.commit()

    pl = _smart_playlist(
        db, user, {"rules": [{"field": "favorited", "op": "eq", "value": True}]}
    )
    result = evaluate_smart_playlist(db, pl)
    assert [t.id for t in result] == [liked.id]


def test_play_count_and_match_any(db):
    user = _user(db)
    _, _, often = _album_with_track(db, artist_name="A", title="Often", genre="Pop")
    _, _, rarely = _album_with_track(db, artist_name="B", title="Rarely", genre="Blues")
    for _ in range(5):
        db.add(PlayerPlayEvent(user_id=user.id, track_id=often.id))
    db.commit()

    pl = _smart_playlist(
        db,
        user,
        {
            "match": "any",
            "rules": [
                {"field": "play_count", "op": "gte", "value": 3},
                {"field": "genre", "op": "eq", "value": "Blues"},
            ],
        },
    )
    result = {t.id for t in evaluate_smart_playlist(db, pl)}
    assert result == {often.id, rarely.id}


def test_format_rule_and_limit(db):
    user = _user(db)
    tracks = []
    for i in range(3):
        _, _, t = _album_with_track(db, artist_name=f"A{i}", title=f"T{i}", fmt="flac")
        tracks.append(t)
    _, _, mp3_track = _album_with_track(db, artist_name="B", title="Mp3", fmt="mp3")

    pl = _smart_playlist(
        db,
        user,
        {"rules": [{"field": "format", "op": "eq", "value": "flac"}], "sort": "title", "limit": 2},
    )
    result = evaluate_smart_playlist(db, pl)
    assert len(result) == 2
    assert mp3_track.id not in [t.id for t in result]


def test_no_criteria_returns_empty(db):
    user = _user(db)
    pl = PlayerPlaylist(user_id=user.id, name="Not smart", is_smart=False)
    db.add(pl)
    db.commit()
    db.refresh(pl)
    assert evaluate_smart_playlist(db, pl) == []
