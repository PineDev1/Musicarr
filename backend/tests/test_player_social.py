from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api import player, player_social
from app.models import Album, PlayerFollow, PlayerPlaylist, PlayerUser, Track
from app.models.schemas import PlayerPlaylistAddTracks
from tests.conftest import _artist


def _user(db, name, *, share=False) -> PlayerUser:
    u = PlayerUser(username=name, password_hash="x", share_listening_activity=share)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def as_user(monkeypatch):
    def _set(user):
        monkeypatch.setattr(player_social, "_current_player_user", lambda r, d: user)
        monkeypatch.setattr(player, "_current_player_user", lambda r, d: user)

    return _set


def _track(db, pid="t1") -> Track:
    artist = _artist(db, name="A", provider="deezer", provider_id="a1")
    album = Album(
        artist_id=artist.id, provider="deezer", provider_id="al1", title="Al", status="downloaded"
    )
    db.add(album)
    db.commit()
    t = Track(provider="deezer", provider_id=pid, album_id=album.id, title="S", path=f"/x/{pid}.flac")
    db.add(t)
    db.commit()
    return t


def test_follow_unfollow_and_self_follow_rejected(db, as_user):
    a, b = _user(db, "a"), _user(db, "b")
    as_user(a)
    player_social.follow(b.id, None, db)
    player_social.follow(b.id, None, db)  # idempotent
    assert db.query(PlayerFollow).count() == 1
    people = player_social.list_people(None, db)
    assert [p.username for p in people] == ["b"] and people[0].is_following
    with pytest.raises(HTTPException) as e:
        player_social.follow(a.id, None, db)
    assert e.value.status_code == 400
    player_social.unfollow(b.id, None, db)
    assert db.query(PlayerFollow).count() == 0


def test_profile_hides_activity_unless_shared(db, as_user):
    a, quiet = _user(db, "a"), _user(db, "quiet", share=False)
    as_user(a)
    prof = player_social.profile(quiet.id, None, db)
    assert not prof.activity_shared and prof.recent == [] and prof.plays_30d == 0
    assert player_social.profile(a.id, None, db).is_self


def test_collaborator_can_add_tracks_but_not_rename_or_share(db, as_user):
    owner, friend, stranger = _user(db, "owner"), _user(db, "friend"), _user(db, "stranger")
    t = _track(db)
    pl = PlayerPlaylist(user_id=owner.id, name="Mix")
    db.add(pl)
    db.commit()

    as_user(stranger)
    with pytest.raises(HTTPException):
        player.get_playlist(pl.id, None, db)

    as_user(owner)
    collabs = player_social.add_collaborator(
        pl.id, player_social.AddCollaborator(username="FRIEND"), None, db
    )
    assert [c.username for c in collabs] == ["friend"]

    as_user(friend)
    assert [p.name for p in player.list_playlists(None, db)] == ["Mix"]
    out = player.add_tracks(pl.id, PlayerPlaylistAddTracks(track_ids=[t.id]), None, db)
    assert out.track_count == 1 and not out.is_owner
    assert out.tracks[0].added_by_name == "friend"
    with pytest.raises(HTTPException):
        player_social.add_collaborator(
            pl.id, player_social.AddCollaborator(username="stranger"), None, db
        )
    with pytest.raises(HTTPException) as e:
        player_social.remove_collaborator(pl.id, owner.id, None, db)
    assert e.value.status_code == 403
    player_social.remove_collaborator(pl.id, friend.id, None, db)  # leave
    with pytest.raises(HTTPException):
        player.get_playlist(pl.id, None, db)


def test_deleting_playlist_or_user_leaves_no_social_rows_behind(db, as_user):
    from app.models import PlayerPlaylistMember
    from app.services import player_auth

    owner, friend = _user(db, "owner"), _user(db, "friend")
    pl = PlayerPlaylist(user_id=owner.id, name="Mix")
    db.add(pl)
    db.commit()
    as_user(owner)
    player_social.add_collaborator(pl.id, player_social.AddCollaborator(username="friend"), None, db)
    player_social.follow(friend.id, None, db)

    db.delete(pl)  # what DELETE /playlists/{id} does
    db.commit()
    assert db.query(PlayerPlaylistMember).count() == 0  # no orphan to inherit on id reuse

    player_auth.delete_user(db, friend.id)
    assert db.query(PlayerFollow).count() == 0
