from __future__ import annotations

from app.models import Album
from app.services.artists import _legacy_id
from app.services.library import TrackIndex, _read_tags, _upsert_track
from tests.conftest import _artist


def _album(db, artist, title="Album", provider_id="al1"):
    a = Album(
        provider="qobuz",
        provider_id=provider_id,
        deezer_id=_legacy_id("qobuz", provider_id),
        artist_id=artist.id,
        title=title,
        track_count=1,
        monitored=True,
        status="downloaded",
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def test_read_tags_includes_genre(tmp_path, monkeypatch):
    from app.services import library

    fake_tags = {"genre": ["Country"]}
    monkeypatch.setattr(
        library,
        "MutagenFile",
        lambda path, easy=True: type("F", (), {"tags": fake_tags})(),
    )
    meta = _read_tags(tmp_path / "song.flac")
    assert meta["genre"] == "Country"


def test_upsert_track_sets_genre_on_new_track(db):
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="luke")
    album = _album(db, artist)
    index = TrackIndex(db)

    track = _upsert_track(
        db,
        index,
        album,
        title="Fast Car",
        track_no=1,
        disc_no=1,
        isrc=None,
        path="/music/a/01 - Fast Car.flac",
        genre="Country",
    )

    assert track.genre == "Country"


def test_upsert_track_does_not_overwrite_existing_genre(db):
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="luke")
    album = _album(db, artist)
    index = TrackIndex(db)

    track = _upsert_track(
        db, index, album, title="Fast Car", track_no=1, disc_no=1, isrc=None,
        path="/music/a/01.flac", genre="Country",
    )
    db.commit()

    index2 = TrackIndex(db)
    same = _upsert_track(
        db, index2, album, title="Fast Car", track_no=1, disc_no=1, isrc=None,
        path="/music/a/01-renamed.flac", genre="Pop",
    )

    assert same.id == track.id
    assert same.genre == "Country"
