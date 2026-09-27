from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import Album, DownloadJob, HistoryEvent, Track
from app.services import stats_history
from tests.conftest import _artist


def _today_str() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def test_growth_series_counts_new_artists_and_downloads_today(db):
    _artist(db, name="A", provider="qobuz", provider_id="a1")
    db.add(HistoryEvent(event_type="downloaded", message="Imported X"))
    db.add(HistoryEvent(event_type="grabbed", message="Grabbed Y"))  # not counted
    db.commit()

    series = stats_history.growth_series(db, days=7)
    assert len(series) == 7
    today = next(p for p in series if p["date"] == _today_str())
    assert today["artists_added"] == 1
    assert today["albums_downloaded"] == 1


def test_growth_series_zero_fills_days_with_no_activity(db):
    series = stats_history.growth_series(db, days=5)
    assert len(series) == 5
    assert all(p["artists_added"] == 0 and p["albums_downloaded"] == 0 for p in series)


def test_download_trend_buckets_completed_and_failed_by_day(db):
    now = datetime.now(timezone.utc)
    db.add(DownloadJob(target_type="album", state="completed", finished_at=now))
    db.add(DownloadJob(target_type="album", state="completed", finished_at=now))
    db.add(DownloadJob(target_type="album", state="failed", finished_at=now))
    db.add(DownloadJob(target_type="album", state="queued", finished_at=None))  # ignored
    db.commit()

    trend = stats_history.download_trend(db, days=7)
    today = next(p for p in trend if p["date"] == _today_str())
    assert today["completed"] == 2
    assert today["failed"] == 1


def test_download_trend_excludes_jobs_outside_the_window(db):
    old = datetime.now(timezone.utc) - timedelta(days=60)
    db.add(DownloadJob(target_type="album", state="completed", finished_at=old))
    db.commit()

    trend = stats_history.download_trend(db, days=7)
    assert sum(p["completed"] for p in trend) == 0


def test_storage_breakdown_groups_by_quality(db, tmp_path):
    artist = _artist(db, name="A", provider="qobuz", provider_id="a1")
    flac_dir = tmp_path / "flac_album"
    flac_dir.mkdir()
    (flac_dir / "song.flac").write_bytes(b"x" * 100)
    mp3_dir = tmp_path / "mp3_album"
    mp3_dir.mkdir()
    (mp3_dir / "song.mp3").write_bytes(b"y" * 50)

    db.add(Album(provider="qobuz", provider_id="al1", artist_id=artist.id, title="A1", status="downloaded", quality="flac", path=str(flac_dir)))
    db.add(Album(provider="qobuz", provider_id="al2", artist_id=artist.id, title="A2", status="downloaded", quality="320", path=str(mp3_dir)))
    db.add(Album(provider="qobuz", provider_id="al3", artist_id=artist.id, title="A3", status="wanted", quality="", path=None))
    db.commit()

    breakdown = stats_history.storage_breakdown(db)
    by_quality = {row["quality"]: row["bytes"] for row in breakdown}
    assert by_quality["flac"] == 100
    assert by_quality["320"] == 50
    assert "wanted" not in by_quality


def test_top_genres_ranks_by_track_count(db):
    artist = _artist(db, name="A", provider="qobuz", provider_id="a1")
    album = Album(provider="qobuz", provider_id="al1", artist_id=artist.id, title="A1")
    db.add(album)
    db.commit()
    db.refresh(album)
    db.add(Track(provider="qobuz", provider_id="t1", album_id=album.id, title="T1", genre="Rock"))
    db.add(Track(provider="qobuz", provider_id="t2", album_id=album.id, title="T2", genre="Rock"))
    db.add(Track(provider="qobuz", provider_id="t3", album_id=album.id, title="T3", genre="Jazz"))
    db.add(Track(provider="qobuz", provider_id="t4", album_id=album.id, title="T4", genre=""))
    db.commit()

    genres = stats_history.top_genres(db)
    assert genres[0] == {"genre": "Rock", "track_count": 2}
    assert genres[1] == {"genre": "Jazz", "track_count": 1}
