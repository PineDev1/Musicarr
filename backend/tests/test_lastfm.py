from __future__ import annotations

import pytest

from app.models import AppSettings, PlayerUser
from app.services import lastfm


def _settings_with_lastfm(db) -> AppSettings:
    row = AppSettings(id=1, lastfm_api_key="key123", lastfm_api_secret="secret456")
    db.add(row)
    db.commit()
    return row


def _player_user(db, **kwargs) -> PlayerUser:
    kwargs.setdefault("username", "listener")
    row = PlayerUser(**kwargs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_credentials_missing_raises(db):
    db.add(AppSettings(id=1))
    db.commit()
    user = _player_user(db)
    with pytest.raises(lastfm.LastfmError):
        lastfm.auth_url(db, user)


def test_auth_url_uses_returned_token(db, monkeypatch):
    _settings_with_lastfm(db)
    user = _player_user(db)

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"token": "tok-abc"}

    monkeypatch.setattr(lastfm.requests, "get", lambda *a, **k: FakeResp())

    url = lastfm.auth_url(db, user)

    assert "tok-abc" in url
    assert "key123" in url
    assert user.lastfm_pending_token == "tok-abc"


def test_complete_auth_stores_session_key(db, monkeypatch):
    _settings_with_lastfm(db)
    user = _player_user(db, lastfm_pending_token="tok-abc")

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"session": {"key": "sess-key", "name": "lastfm_user"}}

    monkeypatch.setattr(lastfm.requests, "get", lambda *a, **k: FakeResp())

    lastfm.complete_auth(db, user, "tok-abc")

    assert user.lastfm_session_key == "sess-key"
    assert user.lastfm_username == "lastfm_user"
    assert user.lastfm_pending_token is None


def test_complete_auth_rejects_token_not_issued_for_this_user(db, monkeypatch):
    """CSRF/account-linking regression: an attacker could authorize their own
    Last.fm account via their own /lastfm/start, then send the resulting
    callback link to a victim. Without binding the token to whoever's flow
    issued it, the victim's session would silently link to the attacker's
    Last.fm account."""
    _settings_with_lastfm(db)
    victim = _player_user(db, username="victim", lastfm_pending_token="victims-own-token")

    called = {"n": 0}

    def _fake_get(*a, **k):
        called["n"] += 1
        raise AssertionError("should never call Last.fm with an unbound token")

    monkeypatch.setattr(lastfm.requests, "get", _fake_get)

    with pytest.raises(lastfm.LastfmError):
        lastfm.complete_auth(db, victim, "attackers-own-token")

    assert called["n"] == 0
    assert victim.lastfm_session_key is None


def test_complete_auth_rejects_when_no_flow_was_started(db, monkeypatch):
    _settings_with_lastfm(db)
    user = _player_user(db)

    def _fake_get(*a, **k):
        raise AssertionError("should never call Last.fm with no pending flow")

    monkeypatch.setattr(lastfm.requests, "get", _fake_get)

    with pytest.raises(lastfm.LastfmError):
        lastfm.complete_auth(db, user, "some-token")


def test_scrobble_noop_without_session_key(db, monkeypatch):
    _settings_with_lastfm(db)
    user = _player_user(db)
    called = {"post": False}

    def boom(*a, **k):
        called["post"] = True
        raise AssertionError("should not call Last.fm without a session key")

    monkeypatch.setattr(lastfm.requests, "post", boom)

    lastfm.scrobble(db, user, "Artist", "Track")

    assert called["post"] is False


def test_scrobble_calls_api_with_session_key(db, monkeypatch):
    _settings_with_lastfm(db)
    user = _player_user(db, lastfm_session_key="sess-key")
    captured = {}

    class FakeResp:
        status_code = 200
        text = "{}"

    def fake_post(url, data, timeout):
        captured["data"] = data
        return FakeResp()

    monkeypatch.setattr(lastfm.requests, "post", fake_post)

    lastfm.scrobble(db, user, "Artist", "Track", started_at=1000)

    assert captured["data"]["method"] == "track.scrobble"
    assert captured["data"]["sk"] == "sess-key"
    assert captured["data"]["timestamp"] == "1000"
    assert "api_sig" in captured["data"]


def test_similar_artists_parses_results(db, monkeypatch):
    _settings_with_lastfm(db)

    class FakeResp:
        status_code = 200

        def json(self):
            return {
                "similarartists": {
                    "artist": [
                        {"name": "Ed Sheeran", "match": "0.95"},
                        {"name": "Shenandoah", "match": "0.5"},
                    ]
                }
            }

    monkeypatch.setattr(lastfm.requests, "get", lambda *a, **k: FakeResp())

    results = lastfm.similar_artists(db, "Luke Combs")

    assert results == [
        {"name": "Ed Sheeran", "match": 0.95},
        {"name": "Shenandoah", "match": 0.5},
    ]


def test_similar_artists_empty_name_short_circuits(db):
    assert lastfm.similar_artists(db, "") == []


def test_similar_artists_raises_on_http_error(db, monkeypatch):
    _settings_with_lastfm(db)

    class FakeResp:
        status_code = 500
        text = "boom"

    monkeypatch.setattr(lastfm.requests, "get", lambda *a, **k: FakeResp())

    with pytest.raises(lastfm.LastfmError):
        lastfm.similar_artists(db, "Luke Combs")
