from __future__ import annotations

from app.api.search import search
from app.models import Album
from tests.conftest import _artist


def test_search_matches_artist_name(db):
    a = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    _artist(db, name="Someone Else", provider="qobuz", provider_id="a2")

    res = search(q="luke", db=db)

    assert [hit.id for hit in res.artists] == [a.id]
    assert res.albums == []


def test_search_matches_album_title(db):
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    album = Album(provider="qobuz", provider_id="al1", artist_id=artist.id, title="Gettin' Old")
    db.add(album)
    db.commit()
    db.refresh(album)

    res = search(q="gettin", db=db)

    assert len(res.albums) == 1
    assert res.albums[0].id == album.id
    assert res.albums[0].artist_name == "Luke Combs"


def test_search_empty_query_returns_nothing(db):
    _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    res = search(q="", db=db)
    assert res.artists == []
    assert res.albums == []
