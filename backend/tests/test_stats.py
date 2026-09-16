from __future__ import annotations

from datetime import datetime, timezone

from app.models import Album, DownloadJob, HistoryEvent, Track
from app.services.stats import compute_stats
from tests.conftest import _artist


def test_compute_stats_counts_and_grouping(db, tmp_path):
    artist = _artist(db, name="A", provider="qobuz", provider_id="a1")
    album = Album(
        provider="qobuz", provider_id="al1", artist_id=artist.id, title="X", status="downloaded"
    )
    db.add(album)
    db.commit()
    db.refresh(album)
    db.add(Track(provider="qobuz", provider_id="t1", album_id=album.id, title="T1"))
    db.commit()

    from app.services.settings_service import ensure_settings

    settings = ensure_settings(db)
    settings.library_path = str(tmp_path)
    db.commit()

    (tmp_path / "song.flac").write_bytes(b"x" * 100)

    result = compute_stats(db)
    assert result["artists"] == 1
    assert result["tracks"] == 1
    assert result["albums_by_status"] == {"downloaded": 1}
    assert result["disk_usage_bytes"] == 100


def test_compute_stats_success_rate(db):
    now = datetime.now(timezone.utc)
    db.add(DownloadJob(target_type="album", state="completed", created_at=now))
    db.add(DownloadJob(target_type="album", state="completed", created_at=now))
    db.add(DownloadJob(target_type="album", state="failed", created_at=now))
    db.commit()

    result = compute_stats(db)
    assert result["success_rate_30d"] == 2 / 3


def test_compute_stats_no_jobs_gives_none_success_rate(db):
    result = compute_stats(db)
    assert result["success_rate_30d"] is None


def test_compute_stats_recent_events(db):
    db.add(HistoryEvent(event_type="library_scan", message="Scan complete"))
    db.commit()
    result = compute_stats(db)
    assert len(result["recent_events"]) == 1
    assert result["recent_events"][0]["event_type"] == "library_scan"
