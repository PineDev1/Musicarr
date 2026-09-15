from __future__ import annotations

from app.models import Album, Track
from app.services.artists import _legacy_id
from app.services.library import _upsert_track
from sqlalchemy import select
from tests.conftest import _artist


def test_upsert_track_sees_unflushed_siblings(db):
    """Import used to insert duplicate (provider, provider_id) before commit."""
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="luke")
    album = Album(
        provider="qobuz",
        provider_id="heyk2usghkh1b",
        deezer_id=_legacy_id("qobuz", "heyk2usghkh1b"),
        artist_id=artist.id,
        title="Life Goes On (feat. Luke Combs)",
        album_type="single",
        track_count=1,
        monitored=True,
        status="downloaded",
    )
    db.add(album)
    db.commit()
    db.refresh(album)

    first = _upsert_track(
        db,
        album,
        title="Life Goes On (feat. Luke Combs)",
        track_no=1,
        disc_no=1,
        isrc=None,
        path="/music/a/01 - Life Goes On.flac",
    )
    second = _upsert_track(
        db,
        album,
        title="Life Goes On (feat. Luke Combs)",
        track_no=1,
        disc_no=1,
        isrc=None,
        path="/music/a/01 - Life Goes On (copy).flac",
    )
    assert first is second
    db.commit()
    rows = db.scalars(select(Track).where(Track.album_id == album.id)).all()
    assert len(rows) == 1
    assert rows[0].path.endswith("(copy).flac")


def test_upsert_track_unique_pid_across_albums(db):
    artist = _artist(db, name="Artist", provider="qobuz", provider_id="art1")
    other = Album(
        provider="qobuz",
        provider_id="other",
        deezer_id=_legacy_id("qobuz", "other"),
        artist_id=artist.id,
        title="Other",
        album_type="album",
        track_count=1,
        monitored=True,
        status="downloaded",
    )
    album = Album(
        provider="qobuz",
        provider_id="alb1",
        deezer_id=_legacy_id("qobuz", "alb1"),
        artist_id=artist.id,
        title="Singles",
        album_type="album",
        track_count=1,
        monitored=True,
        status="downloaded",
    )
    db.add_all([other, album])
    db.commit()
    db.refresh(other)
    db.refresh(album)
    clash = "alb1-t1-1-hello"
    db.add(
        Track(
            provider="qobuz",
            provider_id=clash,
            deezer_id=_legacy_id("qobuz", clash),
            album_id=other.id,
            title="Hello",
            track_no=1,
            disc_no=1,
            duration=1,
            path="/music/other/hello.flac",
        )
    )
    db.commit()

    created = _upsert_track(
        db,
        album,
        title="Hello",
        track_no=1,
        disc_no=1,
        isrc=None,
        path="/music/singles/hello.flac",
    )
    db.commit()
    assert created.provider_id != clash
    assert created.album_id == album.id
