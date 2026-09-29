from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.api import player
from app.models import Album, PlayerPlayEvent, PlayerUser, Track
from tests.conftest import _artist


@pytest.fixture()
def seeded(db, monkeypatch):
    user = PlayerUser(username="listener", password_hash="x")
    db.add(user)
    artist = _artist(db, name="Luke Combs", provider="deezer", provider_id="a1")
    album = Album(artist_id=artist.id, provider="deezer", provider_id="al1", title="Gettin' Old", status="downloaded")
    db.add(album)
    db.commit()
    t1 = Track(provider="deezer", provider_id="t1", album_id=album.id, title="One", duration=200, path="/a.flac", genre="Country")
    t2 = Track(provider="deezer", provider_id="t2", album_id=album.id, title="Two", duration=100, path="/b.flac", genre="country")
    db.add_all([t1, t2])
    db.commit()
    monkeypatch.setattr(player, "_current_player_user", lambda r, d: user)
    return user, t1, t2


def _play(db, user, track, when):
    db.add(PlayerPlayEvent(user_id=user.id, track_id=track.id, played_at=when))
    db.commit()


def test_genres_albums_hours_and_totals(db, seeded):
    user, t1, t2 = seeded
    now = datetime.now(timezone.utc)
    base = now.replace(hour=21, minute=0, second=0, microsecond=0)
    _play(db, user, t1, base)
    _play(db, user, t1, base)
    _play(db, user, t2, base.replace(hour=8))

    out = player.listen_stats(None, db, range_days=30)
    assert out["play_events"] == 3 and out["total_seconds"] == 500
    assert out["top_genres"] == [{"genre": "Country", "plays": 3, "seconds": 500}]  # case-insensitive merge
    assert out["top_albums"][0]["plays"] == 3 and out["top_albums"][0]["title"] == "Gettin' Old"
    assert out["plays_by_hour"][21] == 2 and out["plays_by_hour"][8] == 1
    assert sum(out["plays_by_weekday"]) == 3
    assert out["active_days"] == 1 and out["year"] is None


def test_streaks_consecutive_days_and_broken_run(db, seeded):
    user, t1, _ = seeded
    today = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    for offset in (0, 1, 2, 5, 6, 7, 8):  # current run of 3, older run of 4
        _play(db, user, t1, today - timedelta(days=offset))
    out = player.listen_stats(None, db, range_days=30)
    assert out["current_streak_days"] == 3
    assert out["longest_streak_days"] == 4
    assert out["active_days"] == 7


def test_current_streak_survives_no_plays_yet_today(db, seeded):
    user, t1, _ = seeded
    y = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=1)
    _play(db, user, t1, y)
    _play(db, user, t1, y - timedelta(days=1))
    assert player.listen_stats(None, db, range_days=30)["current_streak_days"] == 2


def test_year_mode_only_counts_that_calendar_year(db, seeded):
    user, t1, t2 = seeded
    _play(db, user, t1, datetime(2024, 12, 31, 23, 0, tzinfo=timezone.utc))
    _play(db, user, t2, datetime(2025, 1, 1, 0, 30, tzinfo=timezone.utc))
    _play(db, user, t2, datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc))
    out = player.listen_stats(None, db, year=2025)
    assert out["year"] == 2025 and out["range_days"] == 365
    assert out["play_events"] == 2 and out["top_tracks"][0]["title"] == "Two"
    assert player.listen_stats(None, db, year=2024)["play_events"] == 1
