from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.models import Album, Artist, Track
from app.services import lyrics


def _track(db, *, path, lyrics_checked_at=None, lyrics_plain=None, lyrics_synced=None):
    artist = Artist(provider="qobuz", provider_id="a1", name="Artist", monitored=True)
    db.add(artist)
    db.commit()
    db.refresh(artist)
    album = Album(provider="qobuz", provider_id="al1", artist_id=artist.id, title="Album")
    db.add(album)
    db.commit()
    db.refresh(album)
    track = Track(
        provider="qobuz", provider_id="t1", album_id=album.id, title="Song",
        path=path, duration=180,
        lyrics_checked_at=lyrics_checked_at,
        lyrics_plain=lyrics_plain,
        lyrics_synced=lyrics_synced,
    )
    db.add(track)
    db.commit()
    db.refresh(track)
    return track


def test_returns_cached_result_without_refetching(db, tmp_path):
    fpath = tmp_path / "song.mp3"
    fpath.write_bytes(b"")
    track = _track(
        db,
        path=str(fpath),
        lyrics_checked_at=datetime.now(timezone.utc),
        lyrics_plain="cached lyrics",
    )
    with patch("app.services.lyrics._fetch_external_lyrics") as fetch:
        result = lyrics.get_lyrics(db, track)
    fetch.assert_not_called()
    assert result == {"plain": "cached lyrics", "synced": None}


def test_sidecar_lrc_used_when_present(db, tmp_path):
    fpath = tmp_path / "song.mp3"
    fpath.write_bytes(b"")
    (tmp_path / "song.lrc").write_text("[00:01.00]Hello\n", encoding="utf-8")
    track = _track(db, path=str(fpath))
    with patch("app.services.lyrics._fetch_external_lyrics") as fetch:
        result = lyrics.get_lyrics(db, track)
    fetch.assert_not_called()
    assert result["synced"] == "[00:01.00]Hello"
    assert track.lyrics_checked_at is not None


def test_falls_back_to_external_when_nothing_local(db, tmp_path):
    fpath = tmp_path / "song.mp3"
    fpath.write_bytes(b"")
    track = _track(db, path=str(fpath))
    with patch(
        "app.services.lyrics._fetch_external_lyrics",
        return_value=("external plain", "external synced"),
    ) as fetch:
        result = lyrics.get_lyrics(db, track)
    fetch.assert_called_once()
    assert result == {"plain": "external plain", "synced": "external synced"}
    assert track.lyrics_plain == "external plain"


def test_caches_not_found_result(db, tmp_path):
    fpath = tmp_path / "song.mp3"
    fpath.write_bytes(b"")
    track = _track(db, path=str(fpath))
    with patch(
        "app.services.lyrics._fetch_external_lyrics", return_value=(None, None)
    ):
        result = lyrics.get_lyrics(db, track)
    assert result == {"plain": None, "synced": None}
    assert track.lyrics_checked_at is not None


def test_stale_cache_is_rechecked(db, tmp_path):
    fpath = tmp_path / "song.mp3"
    fpath.write_bytes(b"")
    old = datetime.now(timezone.utc) - timedelta(days=60)
    track = _track(db, path=str(fpath), lyrics_checked_at=old, lyrics_plain="stale")
    with patch(
        "app.services.lyrics._fetch_external_lyrics",
        return_value=("fresh", None),
    ) as fetch:
        result = lyrics.get_lyrics(db, track)
    fetch.assert_called_once()
    assert result["plain"] == "fresh"
