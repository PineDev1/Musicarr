from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Album, PlayerPlayEvent, PlayerPlaylist, PlayerUser, Track
from app.services.smart_playlists import evaluate_smart_playlist
from tests.conftest import _artist


@pytest.fixture()
def lib(db):
    user = PlayerUser(username="u", password_hash="x")
    db.add(user)
    luke = _artist(db, name="Luke Combs", provider="deezer", provider_id="a1")
    post = _artist(db, name="Post Malone", provider="deezer", provider_id="a2")
    old = Album(artist_id=luke.id, provider="deezer", provider_id="al1", title="This One's for You",
                release_date="2017-06-02", status="downloaded")
    new = Album(artist_id=post.id, provider="deezer", provider_id="al2", title="Austin",
                release_date="2024-07-19", status="downloaded")
    db.add_all([old, new])
    db.commit()
    rows = {}
    for key, album, title, dur, genre in (
        ("hurricane", old, "Hurricane", 220, "Country"),
        ("beer", old, "Beer Never Broke My Heart", 190, "Country"),
        ("chemical", new, "Chemical", 184, "Pop"),
        ("ghost", new, "No File", 100, "Pop"),
    ):
        t = Track(provider="deezer", provider_id=key, album_id=album.id, title=title, duration=dur,
                  genre=genre, path=None if key == "ghost" else f"/m/{key}.flac")
        db.add(t)
        rows[key] = t
    db.commit()
    return user, rows


def _titles(db, user, **criteria):
    pl = PlayerPlaylist(user_id=user.id, name="s", is_smart=True,
                        criteria_json=json.dumps({"sort": "title", "limit": 50, **criteria}))
    db.add(pl)
    db.commit()
    return [t.title for t in evaluate_smart_playlist(db, pl)]


def test_year_decade_and_ranges(db, lib):
    user, _ = lib
    assert _titles(db, user, rules=[{"field": "year", "op": "gte", "value": 2020}]) == ["Chemical"]
    assert _titles(db, user, rules=[{"field": "decade", "op": "eq", "value": 2010}]) == [
        "Beer Never Broke My Heart", "Hurricane",
    ]


def test_text_contains_starts_with_and_not_contains(db, lib):
    user, _ = lib
    assert _titles(db, user, rules=[{"field": "title", "op": "contains", "value": "BEER"}]) == [
        "Beer Never Broke My Heart"
    ]
    assert _titles(db, user, rules=[{"field": "artist_name", "op": "starts_with", "value": "post"}]) == ["Chemical"]
    assert _titles(db, user, rules=[{"field": "album_title", "op": "contains", "value": "austin"}]) == ["Chemical"]
    assert _titles(db, user, rules=[{"field": "artist_name", "op": "not_contains", "value": "luke"}]) == ["Chemical"]


def test_empty_text_value_matches_nothing_rather_than_everything(db, lib):
    user, _ = lib
    assert _titles(db, user, rules=[{"field": "title", "op": "contains", "value": ""}]) == []


def test_duration_rule_and_files_only(db, lib):
    user, _ = lib
    assert _titles(db, user, rules=[{"field": "duration", "op": "lt", "value": 200}]) == [
        "Beer Never Broke My Heart", "Chemical",
    ]  # the 100s "No File" track has no file so never appears


def test_match_any_combines_new_and_old_rules(db, lib):
    user, _ = lib
    out = _titles(
        db, user, match="any",
        rules=[{"field": "year", "op": "gte", "value": 2024}, {"field": "title", "op": "contains", "value": "hurr"}],
    )
    assert out == ["Chemical", "Hurricane"]


def test_new_sorts(db, lib):
    user, rows = lib
    now = datetime.now(timezone.utc)
    db.add_all([
        PlayerPlayEvent(user_id=user.id, track_id=rows["chemical"].id, played_at=now - timedelta(days=1)),
        PlayerPlayEvent(user_id=user.id, track_id=rows["chemical"].id, played_at=now - timedelta(days=2)),
        PlayerPlayEvent(user_id=user.id, track_id=rows["hurricane"].id, played_at=now),
    ])
    db.commit()
    assert _titles(db, user, sort="longest")[0] == "Hurricane"
    assert _titles(db, user, sort="shortest")[0] == "Chemical"
    assert _titles(db, user, sort="newest_release")[0] == "Chemical"
    assert _titles(db, user, sort="oldest_release")[-1] == "Chemical"
    assert _titles(db, user, sort="last_played")[0] == "Hurricane"
    assert _titles(db, user, sort="least_played")[-1] == "Chemical"
