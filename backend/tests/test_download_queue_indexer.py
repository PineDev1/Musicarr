from __future__ import annotations

from unittest.mock import patch

import pytest

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


def test_enqueue_album_refuses_already_downloaded_without_upgrade(db):
    db.add(AppSettings(id=1, preferred_download_method="streaming"))
    db.commit()
    album = _album(db)
    album.status = "downloaded"
    db.commit()
    queue = DownloadQueue()
    assert queue.enqueue_album(db, album.id, allow_upgrade=False) is None
    assert db.query(DownloadJob).count() == 0


def test_enqueue_album_upgrade_requeues_downloaded(db):
    db.add(AppSettings(id=1, preferred_download_method="streaming"))
    db.commit()
    album = _album(db)
    album.status = "downloaded"
    db.commit()
    queue = DownloadQueue()
    job = queue.enqueue_album(db, album.id, allow_upgrade=True)
    assert job is not None
    db.refresh(album)
    assert album.status == "wanted"


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


def test_rematch_does_not_fuzzy_match_a_short_title_to_an_unrelated_album(db):
    """Regression: the fuzzy fallback in _rematch_album_to_provider matched
    whenever one normalized title was a substring of the other, with no
    length floor. For a short title like "Red", that's satisfied by almost
    anything containing those letters — e.g. "Alfred" normalizes to
    "alfred", which contains "red" — so a provider-fallback rematch could
    silently grab a completely unrelated album. Below the length floor it
    must refuse to guess rather than pick the wrong release."""
    from types import SimpleNamespace

    artist = _artist(db, name="Prince", provider="qobuz", provider_id="p1")
    album = Album(
        provider="qobuz",
        provider_id="al-red",
        deezer_id=_legacy_id("qobuz", "al-red"),
        artist_id=artist.id,
        title="Red",
        track_count=1,
        monitored=True,
        status="wanted",
    )
    db.add(album)

    tidal_artist = _artist(db, name="Prince", provider="tidal", provider_id="tidal-1")
    unrelated = Album(
        provider="tidal",
        provider_id="tidal-al-1",
        deezer_id=_legacy_id("tidal", "tidal-al-1"),
        artist_id=tidal_artist.id,
        title="Alfred",
        album_type="album",
        track_count=5,
    )
    db.add(unrelated)
    db.commit()
    db.refresh(album)
    db.refresh(tidal_artist)

    hit = SimpleNamespace(name="Prince", provider_id="tidal-1")

    class FakeProvider:
        def validate_session(self):
            return True, None

        def search_artists(self, name, limit=8):
            return [hit]

        def list_tracks(self, provider_id):
            return []

    queue = DownloadQueue()
    with patch("app.services.providers.get_provider", return_value=FakeProvider()), \
         patch("app.services.artists.sync_artist_albums"):
        result = queue._rematch_album_to_provider(db, album, artist, "tidal")

    assert result is None


def test_cancel_does_not_leak_a_still_queued_jobs_id(db):
    """Regression: cancelling a job still in "queued" (never claimed by
    _process_job) used to unconditionally add its id to _cancel_ids, which is
    only ever discarded in _process_job's finally block — a block that never
    runs for a job that was never claimed. The id would leak in that set for
    the life of the process."""
    album = _album(db)
    job = DownloadJob(
        target_type="album", target_id=album.id, album_id=album.id,
        state="queued", source="streaming",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    queue = DownloadQueue()
    result = queue.cancel(db, job.id)

    assert result.state == "cancelled"
    assert job.id not in queue._cancel_ids


def test_cancel_refuses_a_job_that_is_already_importing(db):
    """A job in "importing" is being actively copied by the completed-download
    handler's background thread right now. Aborting the client item here
    would delete the payload out from under that in-progress copy, and
    either side's final commit could race the other's job.state write."""
    album = _album(db)
    client_row = DownloadClient(
        name="qbt", protocol="torrent", implementation="qbittorrent", host="localhost", port=8080
    )
    db.add(client_row)
    db.commit()
    db.refresh(client_row)

    job = DownloadJob(
        target_type="album", target_id=album.id, album_id=album.id,
        state="importing", source="indexer", client_id=client_row.id, client_item_id="hash1",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    queue = DownloadQueue()
    with patch("app.services.download_clients.get_client") as get_client:
        with pytest.raises(ValueError):
            queue.cancel(db, job.id)
    get_client.assert_not_called()
    db.refresh(job)
    assert job.state == "importing"
