from __future__ import annotations

import pytest

from app.models import AppSettings
from app.services import spotify


def _settings(db) -> AppSettings:
    row = AppSettings(id=1, spotify_client_id="cid", spotify_client_secret="csecret")
    db.add(row)
    db.commit()
    return row


@pytest.mark.parametrize(
    "value,expected",
    [
        ("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc", "37i9dQZF1DXcBWIGoYBM5M"),
        ("spotify:playlist:37i9dQZF1DXcBWIGoYBM5M", "37i9dQZF1DXcBWIGoYBM5M"),
        ("37i9dQZF1DXcBWIGoYBM5M", "37i9dQZF1DXcBWIGoYBM5M"),
        ("not a playlist", None),
        ("", None),
    ],
)
def test_extract_playlist_id(value, expected):
    assert spotify.extract_playlist_id(value) == expected


def test_credentials_missing_raises(db):
    db.add(AppSettings(id=1))
    db.commit()
    with pytest.raises(spotify.SpotifyError):
        spotify._get_token(db)


def test_get_token_caches_across_calls(db, monkeypatch):
    _settings(db)
    calls = {"n": 0}

    class FakeResp:
        status_code = 200

        def json(self):
            calls["n"] += 1
            return {"access_token": f"tok-{calls['n']}", "expires_in": 3600}

    monkeypatch.setattr(spotify.requests, "post", lambda *a, **k: FakeResp())
    spotify._token_cache.clear()

    tok1 = spotify._get_token(db)
    tok2 = spotify._get_token(db)

    assert tok1 == tok2 == "tok-1"
    assert calls["n"] == 1


def test_playlist_artist_names_dedupes_and_paginates(db, monkeypatch):
    _settings(db)
    spotify._token_cache.clear()
    monkeypatch.setattr(
        spotify, "_get_token", lambda _db: "faketoken"
    )

    pages = [
        {
            "items": [
                {"track": {"artists": [{"name": "Luke Combs"}, {"name": "Ed Sheeran"}]}},
                {"track": {"artists": [{"name": "Luke Combs"}]}},
            ],
            "next": "https://api.spotify.com/v1/playlists/x/tracks?offset=100",
        },
        {
            "items": [{"track": {"artists": [{"name": "Morgan Wallen"}]}}],
            "next": None,
        },
    ]
    call_urls = []

    class FakeResp:
        status_code = 200

        def __init__(self, data):
            self._data = data

        def json(self):
            return self._data

    def fake_get(url, headers=None, params=None, timeout=None):
        call_urls.append(url)
        return FakeResp(pages[len(call_urls) - 1])

    monkeypatch.setattr(spotify.requests, "get", fake_get)

    names = spotify.playlist_artist_names(db, "x")

    assert names == ["Luke Combs", "Ed Sheeran", "Morgan Wallen"]
    assert len(call_urls) == 2
