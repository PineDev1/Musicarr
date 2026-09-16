from __future__ import annotations

from unittest.mock import patch

from app.api.albums import BulkGenreRequest, bulk_set_track_genre
from app.models import Album, Track
from app.services.artists import _legacy_id
from tests.conftest import _artist


def _album_with_tracks(db, tmp_path):
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    album = Album(
        provider="qobuz",
        provider_id="al1",
        deezer_id=_legacy_id("qobuz", "al1"),
        artist_id=artist.id,
        title="Album",
        track_count=2,
        monitored=True,
        status="downloaded",
    )
    db.add(album)
    db.commit()
    db.refresh(album)

    p1 = tmp_path / "01.flac"
    p1.write_bytes(b"data")
    t1 = Track(provider="qobuz", provider_id="t1", album_id=album.id, title="Song 1", path=str(p1))
    t2 = Track(provider="qobuz", provider_id="t2", album_id=album.id, title="Song 2", path=None)
    db.add_all([t1, t2])
    db.commit()
    db.refresh(t1)
    db.refresh(t2)
    return album, t1, t2


def test_bulk_set_track_genre_updates_db_and_writes_file(db, tmp_path):
    album, t1, t2 = _album_with_tracks(db, tmp_path)

    with patch("app.services.tagging.write_track_genre") as write_genre:
        result = bulk_set_track_genre(
            album.id, BulkGenreRequest(track_ids=[t1.id, t2.id], genre="Country"), db=db
        )

    assert result == {"ok": True, "updated": 2}
    db.refresh(t1)
    db.refresh(t2)
    assert t1.genre == "Country"
    assert t2.genre == "Country"
    # Only the track with a real file on disk gets a file-tag write.
    write_genre.assert_called_once()
    assert str(write_genre.call_args.args[0]) == t1.path


def test_bulk_set_track_genre_requires_nonempty_genre(db, tmp_path):
    from fastapi import HTTPException

    album, t1, _t2 = _album_with_tracks(db, tmp_path)
    try:
        bulk_set_track_genre(album.id, BulkGenreRequest(track_ids=[t1.id], genre="  "), db=db)
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 400
