from __future__ import annotations

import hashlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import subsonic
from app.core.database import Base, get_db
from app.models import Album, PlayerFavorite, PlayerPlayEvent, PlayerUser, Track
from tests.conftest import _artist


@pytest.fixture()
def db():
    # StaticPool: TestClient runs handlers on another thread, and a plain
    # :memory: engine gives each thread its own empty database.
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db, tmp_path, monkeypatch):
    monkeypatch.setattr(subsonic.player_auth, "player_enabled", lambda _db: True)
    app = FastAPI()
    app.include_router(subsonic.router)
    app.dependency_overrides[get_db] = lambda: db

    user = PlayerUser(username="Riley", password_hash="x", subsonic_secret="s3cret")
    db.add(user)
    artist = _artist(db, name="Luke Combs", provider="deezer", provider_id="a1")
    album = Album(artist_id=artist.id, provider="deezer", provider_id="al1", title="The Way I Am",
                  release_date="2020-05-01", cover_url="https://c/x/front-250", status="downloaded")
    db.add(album)
    db.commit()
    f = tmp_path / "15 Minutes.flac"
    f.write_bytes(b"x" * 100)
    t = Track(provider="deezer", provider_id="t1", album_id=album.id, title="15 Minutes",
              track_no=1, duration=215, path=str(f), genre="Country")
    ghost = Track(provider="deezer", provider_id="t2", album_id=album.id, title="No File", path=None)
    db.add_all([t, ghost])
    db.commit()
    c = TestClient(app)
    c.ids = {"artist": artist.id, "album": album.id, "track": t.id, "user": user.id}
    return c


def _auth(salt="abc", secret="s3cret"):
    return {"u": "riley", "s": salt, "t": hashlib.md5((secret + salt).encode()).hexdigest(), "f": "json", "v": "1.16.1", "c": "test"}


def _ok(r):
    body = r.json()["subsonic-response"]
    assert body["status"] == "ok", body
    return body


def test_rejects_bad_token_and_missing_secret(client, db):
    assert client.get("/rest/ping", params=_auth(secret="wrong")).json()["subsonic-response"]["error"]["code"] == 40
    db.query(PlayerUser).update({"subsonic_secret": None})
    db.commit()
    assert client.get("/rest/ping", params=_auth()).json()["subsonic-response"]["status"] == "failed"


def test_token_and_plain_and_enc_password_auth(client):
    _ok(client.get("/rest/ping.view", params=_auth()))
    _ok(client.get("/rest/ping", params={"u": "riley", "p": "s3cret", "f": "json"}))
    _ok(client.get("/rest/ping", params={"u": "riley", "p": "enc:" + b"s3cret".hex(), "f": "json"}))


def test_xml_is_default_format(client):
    q = _auth()
    q.pop("f")
    r = client.get("/rest/ping", params=q)
    assert r.headers["content-type"].startswith("text/xml")
    assert 'status="ok"' in r.text and "subsonic-response" in r.text


def test_browse_artists_album_song_only_downloaded(client):
    ids = client.ids
    arts = _ok(client.get("/rest/getArtists", params=_auth()))["artists"]["index"]
    assert arts[0]["artist"][0]["id"] == f"ar-{ids['artist']}" and arts[0]["name"] == "L"
    alb = _ok(client.get("/rest/getAlbum", params={**_auth(), "id": f"al-{ids['album']}"}))["album"]
    assert alb["songCount"] == 1 and [s["title"] for s in alb["song"]] == ["15 Minutes"]
    assert alb["song"][0]["suffix"] == "flac" and alb["year"] == 2020
    song = _ok(client.get("/rest/getSong", params={**_auth(), "id": f"tr-{ids['track']}"}))["song"]
    assert song["duration"] == 215 and song["size"] == 100
    art = _ok(client.get("/rest/getArtist", params={**_auth(), "id": f"ar-{ids['artist']}"}))["artist"]
    assert art["albumCount"] == 1


def test_search_album_list_and_genres(client):
    s = _ok(client.get("/rest/search3", params={**_auth(), "query": "minutes"}))["searchResult3"]
    assert [x["title"] for x in s["song"]] == ["15 Minutes"] and s["artist"] == []
    by_artist = _ok(client.get("/rest/search3", params={**_auth(), "query": "luke"}))["searchResult3"]
    assert len(by_artist["artist"]) == 1 and len(by_artist["album"]) == 1
    lst = _ok(client.get("/rest/getAlbumList2", params={**_auth(), "type": "newest"}))["albumList2"]["album"]
    assert len(lst) == 1
    g = _ok(client.get("/rest/getGenres", params=_auth()))["genres"]["genre"]
    assert g == [{"value": "Country", "songCount": 1, "albumCount": 1}]


def test_stream_returns_audio_and_missing_is_subsonic_error(client):
    r = client.get("/rest/stream", params={**_auth(), "id": f"tr-{client.ids['track']}"})
    assert r.status_code == 200 and len(r.content) == 100
    bad = client.get("/rest/getSong", params={**_auth(), "id": "tr-99999"})
    assert bad.json()["subsonic-response"]["error"]["code"] == 70


def test_cover_art_redirects_and_scales(client):
    r = client.get("/rest/getCoverArt", params={**_auth(), "id": f"al-{client.ids['album']}", "size": 600},
                   follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"].endswith("front-500")


def test_star_scrobble_and_playlist_lifecycle(client, db):
    tid = f"tr-{client.ids['track']}"
    _ok(client.get("/rest/star", params={**_auth(), "id": tid}))
    assert db.query(PlayerFavorite).count() == 1
    st = _ok(client.get("/rest/getStarred2", params=_auth()))["starred2"]["song"]
    assert st[0]["starred"]
    _ok(client.get("/rest/unstar", params={**_auth(), "id": tid}))
    assert db.query(PlayerFavorite).count() == 0

    _ok(client.get("/rest/scrobble", params={**_auth(), "id": tid, "submission": "false"}))
    assert db.query(PlayerPlayEvent).count() == 0
    _ok(client.get("/rest/scrobble", params={**_auth(), "id": tid}))
    assert db.query(PlayerPlayEvent).count() == 1

    created = _ok(client.get("/rest/createPlaylist", params={**_auth(), "name": "Road", "songId": tid}))["playlist"]
    assert created["songCount"] == 1 and created["entry"][0]["title"] == "15 Minutes"
    pid = created["id"]
    _ok(client.get("/rest/updatePlaylist", params={**_auth(), "playlistId": pid, "name": "Road2", "songIndexToRemove": "0"}))
    pl = _ok(client.get("/rest/getPlaylist", params={**_auth(), "id": pid}))["playlist"]
    assert pl["name"] == "Road2" and pl["songCount"] == 0
    assert len(_ok(client.get("/rest/getPlaylists", params=_auth()))["playlists"]["playlist"]) == 1
    _ok(client.get("/rest/deletePlaylist", params={**_auth(), "id": pid}))
    assert _ok(client.get("/rest/getPlaylists", params=_auth()))["playlists"]["playlist"] == []


def test_unexpected_handler_error_is_a_subsonic_error_not_an_html_500(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setitem(subsonic.HANDLERS, "ping", boom)
    r = client.get("/rest/ping", params=_auth())
    assert r.status_code == 200
    err = r.json()["subsonic-response"]["error"]
    assert err["code"] == 0 and "kaboom" not in err["message"]


def test_unknown_method(client):
    err = client.get("/rest/nonsense", params=_auth()).json()["subsonic-response"]["error"]
    assert err["code"] == 70
