from __future__ import annotations

from unittest.mock import patch

from app.models import Album, AppSettings, DownloadClient, DownloadJob
from app.services.artists import _legacy_id
from app.services.download_queue import DownloadQueue, resolve_download_method
from tests.conftest import _artist


def _album(db, *, provider_id="al1") -> Album:
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    album = Album(
        provider="qobuz",
        provider_id=provider_id,
        deezer_id=_legacy_id("qobuz", provider_id),
        artist_id=artist.id,
        title="Fathers & Sons",
        track_count=1,
        monitored=True,
        status="wanted",
    )
    db.add(album)
    db.commit()
    db.refresh(album)
    return album


def test_resolve_download_method_defaults_and_validates():
    settings = AppSettings(preferred_download_method="bogus", streaming_enabled=True)
    assert resolve_download_method(settings) == "streaming"
    settings.preferred_download_method = "streaming_then_indexer"
    assert resolve_download_method(settings) == "streaming_then_indexer"
    assert resolve_download_method(settings, method="indexer") == "indexer"


def test_resolve_download_method_forces_indexer_when_streaming_disabled():
    settings = AppSettings(preferred_download_method="streaming", streaming_enabled=False)
    assert resolve_download_method(settings) == "indexer"
    settings.preferred_download_method = "streaming_then_indexer"
    assert resolve_download_method(settings) == "indexer"
    # Already indexer-only stays indexer regardless.
    settings.preferred_download_method = "indexer"
    assert resolve_download_method(settings) == "indexer"


def test_enqueue_album_never_auto_queues_pure_indexer_method(db):
    db.add(AppSettings(id=1, preferred_download_method="indexer"))
    db.commit()
    album = _album(db)
    queue = DownloadQueue()
    job = queue.enqueue_album(db, album.id)
    assert job is None
    assert db.query(DownloadJob).count() == 0


def test_enqueue_album_refuses_when_streaming_disabled(db):
    db.add(AppSettings(id=1, preferred_download_method="streaming", streaming_enabled=False))
    db.commit()
    album = _album(db)
    queue = DownloadQueue()
    job = queue.enqueue_album(db, album.id)
    assert job is None
    assert db.query(DownloadJob).count() == 0


def test_enqueue_album_queues_normally_for_streaming_then_indexer(db):
    db.add(AppSettings(id=1, preferred_download_method="streaming_then_indexer"))
    db.commit()
    album = _album(db)
    queue = DownloadQueue()
    job = queue.enqueue_album(db, album.id)
    assert job is not None
    assert job.source == "streaming"
    assert job.state == "queued"


def test_enqueue_album_blocked_while_indexer_grab_active(db):
    db.add(AppSettings(id=1, preferred_download_method="streaming_then_indexer"))
    db.commit()
    album = _album(db)
    db.add(
        DownloadJob(
            target_type="album", target_id=album.id, album_id=album.id,
            state="downloading", source="indexer", client_id=1,
        )
    )
    db.commit()
    queue = DownloadQueue()
    job = queue.enqueue_album(db, album.id)
    # Existing active indexer job wins — no second (streaming) job created.
    assert job is not None
    assert job.source == "indexer"
    assert db.query(DownloadJob).count() == 1


def test_retry_refuses_indexer_jobs(db):
    album = _album(db)
    job = DownloadJob(
        target_type="album", target_id=album.id, album_id=album.id,
        state="failed", source="indexer", client_id=1, client_item_id="hash1",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    queue = DownloadQueue()
    result = queue.retry(db, job.id)
    assert result is None
    db.refresh(job)
    assert job.state == "failed"


def test_cancel_aborts_download_client_item_for_indexer_job(db):
    album = _album(db)
    client_row = DownloadClient(name="qbt", protocol="torrent", implementation="qbittorrent", host="localhost", port=8080)
    db.add(client_row)
    db.commit()
    db.refresh(client_row)

    job = DownloadJob(
        target_type="album", target_id=album.id, album_id=album.id,
        state="downloading", source="indexer", client_id=client_row.id, client_item_id="hash1",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    removed = {}

    class FakeClient:
        def remove(self, item_id, *, delete_data=False):
            removed["item_id"] = item_id
            removed["delete_data"] = delete_data

        def close(self):
            pass

    queue = DownloadQueue()
    with patch("app.services.download_clients.get_client", return_value=FakeClient()):
        result = queue.cancel(db, job.id)

    assert result.state == "cancelled"
    assert removed == {"item_id": "hash1", "delete_data": True}


def test_cancel_streaming_job_does_not_touch_download_clients(db):
    album = _album(db)
    job = DownloadJob(
        target_type="album", target_id=album.id, album_id=album.id,
        state="running", source="streaming",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    queue = DownloadQueue()
    with patch("app.services.download_clients.get_client") as get_client:
        result = queue.cancel(db, job.id)
    get_client.assert_not_called()
    assert result.state == "cancelled"
