from __future__ import annotations

import pytest

from app.api import player_queue
from app.models import Album, PlayerQueueState, PlayerUser, Track
from app.services import player_auth
from tests.conftest import _artist


@pytest.fixture()
def world(db, monkeypatch):
    me = PlayerUser(username="me", password_hash="x")
    other = PlayerUser(username="other", password_hash="x")
    db.add_all([me, other])
    artist = _artist(db, name="A", provider="deezer", provider_id="a1")
    album = Album(artist_id=artist.id, provider="deezer", provider_id="al1", title="Al", status="downloaded")
    db.add(album)
    db.commit()
    tracks = []
    for n in range(1, 5):
        t = Track(provider="deezer", provider_id=f"t{n}", album_id=album.id, title=f"S{n}", track_no=n,
                  path=f"/m/{n}.flac")
        db.add(t)
        tracks.append(t)
    db.commit()
    current = {"user": me}
    monkeypatch.setattr(player_queue, "_current_player_user", lambda r, d: current["user"])
    return me, other, tracks, current


def _save(db, ids, index=0, position=0.0, device="dev-a", **kw):
    return player_queue.save_queue(
        player_queue.QueueSave(track_ids=ids, index=index, position=position, device_id=device,
                               device_name="Chrome on Mac", **kw),
        None, db,
    )


def test_round_trip_keeps_order_position_and_device(db, world):
    me, _, tracks, _ = world
    ids = [t.id for t in tracks]
    _save(db, ids, index=2, position=41.5, shuffle=True, repeat="all", source_label="Album")
    out = player_queue.get_queue(None, db)
    assert out.exists and [t.title for t in out.tracks] == ["S1", "S2", "S3", "S4"]
    assert out.index == 2 and out.position == 41.5 and out.shuffle and out.repeat == "all"
    assert out.device_id == "dev-a" and out.device_name == "Chrome on Mac" and out.source_label == "Album"


def test_saving_again_updates_the_single_row(db, world):
    _, _, tracks, _ = world
    _save(db, [tracks[0].id], device="phone")
    _save(db, [tracks[1].id, tracks[2].id], index=1, device="laptop")
    assert db.query(PlayerQueueState).count() == 1
    out = player_queue.get_queue(None, db)
    assert out.device_id == "laptop" and out.index == 1


def test_missing_and_fileless_tracks_drop_out_and_index_follows_the_same_song(db, world):
    _, _, tracks, _ = world
    tracks[0].path = None  # file removed after the queue was saved
    db.commit()
    _save(db, [t.id for t in tracks], index=2, position=10.0)  # pointing at S3
    out = player_queue.get_queue(None, db)
    assert [t.title for t in out.tracks] == ["S2", "S3", "S4"]
    assert out.tracks[out.index].title == "S3" and out.position == 10.0


def test_when_the_current_song_is_gone_position_resets(db, world):
    _, _, tracks, _ = world
    _save(db, [t.id for t in tracks], index=1, position=99.0)
    tracks[1].path = None
    db.commit()
    out = player_queue.get_queue(None, db)
    assert out.exists and out.position == 0.0 and 0 <= out.index < len(out.tracks)


def test_empty_save_clears_and_all_gone_reads_as_no_queue(db, world):
    _, _, tracks, _ = world
    _save(db, [tracks[0].id])
    _save(db, [])
    assert db.query(PlayerQueueState).count() == 0
    assert player_queue.get_queue(None, db).exists is False
    _save(db, [tracks[0].id])
    tracks[0].path = None
    db.commit()
    assert player_queue.get_queue(None, db).exists is False


def test_users_have_separate_queues_and_bad_repeat_is_normalised(db, world):
    me, other, tracks, current = world
    _save(db, [tracks[0].id], repeat="bogus")
    current["user"] = other
    assert player_queue.get_queue(None, db).exists is False
    current["user"] = me
    assert player_queue.get_queue(None, db).repeat == "off"


def test_deleting_the_user_removes_their_saved_queue(db, world):
    me, _, tracks, _ = world
    _save(db, [tracks[0].id])
    player_auth.delete_user(db, me.id)
    assert db.query(PlayerQueueState).count() == 0


def test_get_queue_keeps_slot_when_song_is_queued_twice(db, world):
    _, _, tracks, _ = world
    a, b = tracks[0].id, tracks[1].id
    _save(db, [a, b, a], index=2, position=5.0)
    out = player_queue.get_queue(None, db)
    assert out.index == 2 and out.position == 5.0
