from __future__ import annotations

import pytest

from app.api import player
from app.models import Album, PlayerFavorite, PlayerPlayEvent, PlayerUser, Track
from tests.conftest import _artist


@pytest.fixture()
def lib(db, monkeypatch):
    me = PlayerUser(username="me", password_hash="x")
    db.add(me)
    a1 = _artist(db, name="Alpha Band", provider="deezer", provider_id="a1")
    a2 = _artist(db, name="Beta 100% Crew", provider="deezer", provider_id="a2")
    al1 = Album(artist_id=a1.id, provider="deezer", provider_id="al1", title="First Light", status="downloaded")
    al2 = Album(artist_id=a2.id, provider="deezer", provider_id="al2", title="Second_Wind", status="downloaded")
    db.add_all([al1, al2])
    db.commit()
    tracks = []
    for n, (al, title, path) in enumerate(
        [(al1, "Zebra", "/m/1.flac"), (al1, "Apple", "/m/2.flac"), (al2, "Mango", "/m/3.flac"),
         (al2, "Cherry", "/m/4.flac"), (al1, "Ghost", None)], start=1):
        t = Track(provider="deezer", provider_id=f"t{n}", album_id=al.id, title=title, track_no=n,
                  path=path, duration=100)
        db.add(t)
        tracks.append(t)
    db.commit()
    monkeypatch.setattr(player, "_current_player_user", lambda r, d: me)
    return me, a1, a2, tracks


def _songs(db, **kw):
    return player.library_songs(None, db=db, **kw)


def test_songs_page_is_sorted_paginated_and_skips_fileless_tracks(db, lib):
    page = _songs(db, limit=2, offset=0)
    assert page.total == 4  # the fileless "Ghost" track is not playable
    assert [t.title for t in page.items] == ["Apple", "Cherry"]
    assert [t.title for t in _songs(db, limit=2, offset=2).items] == ["Mango", "Zebra"]


def test_songs_search_spans_title_album_and_artist(db, lib):
    assert [t.title for t in _songs(db, q="alpha band").items] == ["Apple", "Zebra"]
    assert [t.title for t in _songs(db, q="second").items] == ["Cherry", "Mango"]
    assert [t.title for t in _songs(db, q="mango second").items] == ["Mango"]  # across title+album


def test_songs_search_treats_like_wildcards_literally(db, lib):
    assert [t.title for t in _songs(db, q="100%").items] == ["Cherry", "Mango"]
    assert _songs(db, q="%").total == 2  # only the artist literally containing '%'
    assert [t.title for t in _songs(db, q="second_wind").items] == ["Cherry", "Mango"]
    assert _songs(db, q="second.wind").total == 0  # '.' / '_' must not act as wildcards


def test_recommended_prefers_seed_artists_and_excludes_recent(db, lib):
    me, a1, a2, tracks = lib
    zebra, apple, mango, cherry, _ghost = tracks
    db.add(PlayerPlayEvent(user_id=me.id, track_id=mango.id))  # seeds artist 2, excludes Mango
    db.add(PlayerFavorite(user_id=me.id, track_id=zebra.id))   # seeds artist 1
    db.commit()
    titles = [t.title for t in player.library_recommended(None, db=db)]
    assert "Mango" not in titles
    assert set(titles) == {"Zebra", "Apple", "Cherry"}
    assert titles == sorted(titles, key=lambda x: {"Zebra": 1, "Apple": 2, "Cherry": 4}[x])  # by id within boost


def test_clear_history_removes_only_my_events(db, lib):
    me, _a1, _a2, tracks = lib
    other = PlayerUser(username="other", password_hash="x")
    db.add(other)
    db.commit()
    db.add_all([PlayerPlayEvent(user_id=me.id, track_id=tracks[0].id),
                PlayerPlayEvent(user_id=other.id, track_id=tracks[0].id)])
    db.commit()
    player.clear_listen_history(None, db=db)
    left = db.query(PlayerPlayEvent).all()
    assert [e.user_id for e in left] == [other.id]
