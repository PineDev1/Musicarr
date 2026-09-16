from __future__ import annotations

from app.api.ops import BulkJobIds, bulk_cancel_jobs, bulk_retry_jobs
from app.models import Album, DownloadJob
from tests.conftest import _artist


def _album(db, artist):
    album = Album(provider="qobuz", provider_id="al1", artist_id=artist.id, title="X")
    db.add(album)
    db.commit()
    db.refresh(album)
    return album


def test_bulk_cancel_jobs(db):
    artist = _artist(db, name="A", provider="qobuz", provider_id="a1")
    album = _album(db, artist)
    j1 = DownloadJob(target_type="album", album_id=album.id, state="queued")
    j2 = DownloadJob(target_type="album", album_id=album.id, state="running")
    db.add_all([j1, j2])
    db.commit()
    db.refresh(j1)
    db.refresh(j2)

    result = bulk_cancel_jobs(BulkJobIds(job_ids=[j1.id, j2.id, 9999]), db)

    assert result == {"cancelled": 2}
    db.refresh(j1)
    db.refresh(j2)
    assert j1.state == "cancelled"
    assert j2.state == "cancelled"


def test_bulk_retry_jobs(db):
    artist = _artist(db, name="A", provider="qobuz", provider_id="a1")
    album = _album(db, artist)
    j1 = DownloadJob(target_type="album", album_id=album.id, state="failed", retries=1)
    db.add(j1)
    db.commit()
    db.refresh(j1)

    result = bulk_retry_jobs(BulkJobIds(job_ids=[j1.id]), db)

    assert result == {"retried": 1}
    db.refresh(j1)
    assert j1.state == "queued"
    assert j1.retries == 2


def test_bulk_retry_skips_jobs_without_album(db):
    j1 = DownloadJob(target_type="album", album_id=None, state="failed")
    db.add(j1)
    db.commit()
    db.refresh(j1)

    result = bulk_retry_jobs(BulkJobIds(job_ids=[j1.id]), db)
    assert result == {"retried": 0}
