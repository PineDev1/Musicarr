from __future__ import annotations

import pytest

from app.models import Album, PlayerPlayEvent, PlayerUser, Track
from app.services import player_activity, player_presence
from tests.conftest import _artist


@pytest.fixture(autouse=True)
def _clear_presence():
    """player_presence is a module-level in-memory registry, not scoped to
    the per-test DB — without clearing it, a leftover entry from an earlier
    test can collide with a reused autoincrement user_id in a later test."""
    player_presence._entries.clear()
    yield
    player_presence._entries.clear()


def _user(db, username, *, share=False) -> PlayerUser:
    user = PlayerUser(username=username, password_hash="x", share_listening_activity=share)
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


def test_now_playing_friends_excludes_non_opted_in_and_self(db):
    me = _user(db, "me")
    shared = _user(db, "friend", share=True)
    quiet = _user(db, "quiet", share=False)

    player_presence.heartbeat(
        user_id=shared.id, username=shared.username, display_name="", track_id=1,
        title="Song A", artist_name="Artist", cover_url=None, playing=True, position=0,
    )
    player_presence.heartbeat(
        user_id=quiet.id, username=quiet.username, display_name="", track_id=2,
        title="Song B", artist_name="Artist", cover_url=None, playing=True, position=0,
    )
    player_presence.heartbeat(
        user_id=me.id, username=me.username, display_name="", track_id=3,
        title="Song C", artist_name="Artist", cover_url=None, playing=True, position=0,
    )

    out = player_activity.now_playing_friends(db, me.id)

    assert len(out) == 1
    assert out[0]["user_id"] == shared.id
    assert out[0]["title"] == "Song A"


def test_now_playing_friends_excludes_paused_entries(db):
    me = _user(db, "me")
    shared = _user(db, "friend", share=True)
    player_presence.heartbeat(
        user_id=shared.id, username=shared.username, display_name="", track_id=1,
        title="Song A", artist_name="Artist", cover_url=None, playing=False, position=0,
    )

    assert player_activity.now_playing_friends(db, me.id) == []


def test_recent_friend_activity_only_includes_opted_in_users_with_playable_tracks(db):
    me = _user(db, "me")
    shared = _user(db, "friend", share=True)
    quiet = _user(db, "quiet", share=False)

    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    album = Album(provider="qobuz", provider_id="al1", artist_id=artist.id, title="Album")
    db.add(album)
    db.commit()
    track = _downloaded_track(db, album, provider_id="t0")

    db.add(PlayerPlayEvent(user_id=shared.id, track_id=track.id))
    db.add(PlayerPlayEvent(user_id=quiet.id, track_id=track.id))
    db.commit()

    out = player_activity.recent_friend_activity(db, me.id)

    assert len(out) == 1
    assert out[0]["user_id"] == shared.id
    assert out[0]["title"] == track.title


def test_recent_friend_activity_empty_when_nobody_opted_in(db):
    me = _user(db, "me")
    assert player_activity.recent_friend_activity(db, me.id) == []
    assert player_activity.now_playing_friends(db, me.id) == []
