from __future__ import annotations

import threading
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api import acquisition
from app.models import Album, DownloadClient, DownloadJob, Indexer, RemotePathMapping
from app.models.schemas import (
    DownloadClientCreate,
    DownloadClientUpdate,
    IndexerCreate,
    IndexerUpdate,
    ReleaseGrabRequest,
    RemotePathMappingCreate,
)
from app.services.artists import _legacy_id
from app.services.download_clients import DownloadClientError
from tests.conftest import _artist


def _album(db) -> Album:
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    album = Album(
        provider="qobuz",
        provider_id="al1",
        deezer_id=_legacy_id("qobuz", "al1"),
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


def test_indexer_crud_round_trip(db):
    created = acquisition.create_indexer(
        IndexerCreate(name="Example", protocol="torrent", implementation="torznab", base_url="https://x.tld/", api_key="k", categories=[3040]),
        db=db,
    )
    assert created.api_key_set is True
    assert created.categories == [3040]

    fetched = acquisition.get_indexer(created.id, db=db)
    assert fetched.name == "Example"

    updated = acquisition.update_indexer(created.id, IndexerUpdate(priority=5), db=db)
    assert updated.priority == 5

    rows = acquisition.list_indexers(db=db)
    assert len(rows) == 1

    acquisition.delete_indexer(created.id, db=db)
    with pytest.raises(HTTPException):
        acquisition.get_indexer(created.id, db=db)


def test_download_client_crud_masks_secrets(db):
    created = acquisition.create_download_client(
        DownloadClientCreate(name="qbt", implementation="qbittorrent", host="localhost", port=8080, password="secret"),
        db=db,
    )
    assert created.password_set is True
    assert "password" not in created.model_dump()  # never echoed back

    # Updating without a new password keeps the old one (not cleared).
    row = db.get(DownloadClient, created.id)
    old_hash = row.password
    acquisition.update_download_client(created.id, DownloadClientUpdate(priority=2), db=db)
    db.refresh(row)
    assert row.password == old_hash


def test_path_mapping_crud(db):
    created = acquisition.create_path_mapping(
        RemotePathMappingCreate(remote_path="/data/completed", local_path="/downloads"), db=db
    )
    assert created.local_path == "/downloads"
    acquisition.update_path_mapping(created.id, acquisition.RemotePathMappingUpdate(local_path="/mnt/downloads"), db=db)
    row = db.get(RemotePathMapping, created.id)
    assert row.local_path == "/mnt/downloads"
    acquisition.delete_path_mapping(created.id, db=db)
    assert db.get(RemotePathMapping, created.id) is None


def test_search_releases_returns_ranked_candidates(db):
    album = _album(db)
    db.add(Indexer(name="idx", protocol="torrent", base_url="https://x.tld", api_key="k", enabled=True))
    db.commit()

    from app.services.indexers.base import ReleaseCandidate

    hits = [
        ReleaseCandidate(title="Luke Combs - Fathers & Sons [FLAC]", size=1, seeders=10, protocol="torrent", magnet_url="magnet:?xt=1"),
    ]
    with patch("app.services.indexers.search.search_newznab", return_value=hits):
        out = acquisition.search_releases(album_id=album.id, db=db)
    assert len(out.results) == 1
    assert out.results[0].grab_url == "magnet:?xt=1"
    assert out.errors == []


def test_search_releases_404_for_missing_album(db):
    with pytest.raises(HTTPException):
        acquisition.search_releases(album_id=999, db=db)


def test_search_releases_surfaces_indexer_errors(db):
    """A bad API key (or any indexer failure) must reach the caller, not
    just the server log — an empty `results` list is otherwise
    indistinguishable from "nothing matched"."""
    album = _album(db)
    db.add(Indexer(name="NZBGeek", protocol="usenet", base_url="https://api.nzbgeek.info", api_key="bad", enabled=True))
    db.commit()

    from app.services.indexers.base import IndexerError

    with patch(
        "app.services.indexers.search.search_newznab",
        side_effect=IndexerError("Indexer error 100: Invalid API Key"),
    ):
        out = acquisition.search_releases(album_id=album.id, db=db)

    assert out.results == []
    assert len(out.errors) == 1
    assert out.errors[0].indexer_name == "NZBGeek"
    assert "Invalid API Key" in out.errors[0].message


def test_grab_release_creates_job_and_sends_to_client(db):
    album = _album(db)
    client_row = DownloadClient(name="qbt", protocol="torrent", implementation="qbittorrent", host="localhost", port=8080, enabled=True)
    db.add(client_row)
    db.commit()
    db.refresh(client_row)

    class FakeClient:
        def test(self):
            return True, "ok"

        def add_url(self, url, category=""):
            return "hash123"

        def close(self):
            pass

    with patch("app.services.acquisition_actions.get_client", return_value=FakeClient()), \
         patch("app.services.download_queue.download_queue.wake"):
        result = acquisition.grab_release(
            ReleaseGrabRequest(album_id=album.id, grab_url="magnet:?xt=1", protocol="torrent", title="Fathers & Sons [FLAC]"),
            db=db,
        )

    assert result["ok"] is True
    job = db.get(DownloadJob, result["job_id"])
    assert job.source == "indexer"
    assert job.state == "grabbed"
    assert job.client_item_id == "hash123"


def test_grab_release_holds_a_lock_across_the_client_dispatch():
    """Regression: two near-simultaneous "Grab" clicks on the same album used
    to both pass the active-job check and both reach the download client
    before either committed its DownloadJob row, sending the release twice.
    grab_release now holds _grab_lock across the whole check-dispatch-commit
    sequence, so a second grab attempted while the first is still talking to
    the client must find the lock held.

    Uses its own StaticPool-backed engine (rather than the shared `db`
    fixture) so the background thread's session sees the same in-memory
    database instead of a fresh, empty one — the default SQLite pool hands
    each thread its own :memory: connection."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.core.database import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    album = _album(db)
    client_row = DownloadClient(name="qbt", protocol="torrent", implementation="qbittorrent", host="localhost", port=8080, enabled=True)
    db.add(client_row)
    db.commit()

    entered_add_url = threading.Event()
    release_add_url = threading.Event()

    class SlowClient:
        def test(self):
            return True, "ok"

        def add_url(self, url, category=""):
            entered_add_url.set()
            release_add_url.wait(timeout=5)
            return "hash123"

        def close(self):
            pass

    with patch("app.services.acquisition_actions.get_client", return_value=SlowClient()):
        t = threading.Thread(
            target=acquisition.grab_release,
            args=(ReleaseGrabRequest(album_id=album.id, grab_url="magnet:?xt=1", protocol="torrent"),),
            kwargs={"db": db},
        )
        t.start()
        try:
            assert entered_add_url.wait(timeout=5), "first grab never reached the client"
            from app.services import acquisition_actions

            assert acquisition_actions._grab_lock.locked(), "lock must be held while dispatching to the client"
        finally:
            release_add_url.set()
            t.join(timeout=5)
    assert not t.is_alive()
    db.close()
    engine.dispose()


def test_grab_release_rejects_duplicate_active_job(db):
    album = _album(db)
    client_row = DownloadClient(name="qbt", protocol="torrent", implementation="qbittorrent", host="localhost", port=8080, enabled=True)
    db.add(client_row)
    db.add(
        DownloadJob(
            target_type="album", target_id=album.id, album_id=album.id,
            state="downloading", source="indexer", client_id=1,
        )
    )
    db.commit()
    db.refresh(client_row)

    class FakeClient:
        def test(self):
            return True, "ok"

        def close(self):
            pass

    with patch("app.services.acquisition_actions.get_client", return_value=FakeClient()):
        with pytest.raises(HTTPException) as exc_info:
            acquisition.grab_release(
                ReleaseGrabRequest(album_id=album.id, grab_url="magnet:?xt=1", protocol="torrent"), db=db
            )
    assert exc_info.value.status_code == 409


def test_grab_release_fails_when_no_client_configured(db):
    album = _album(db)
    with pytest.raises(HTTPException) as exc_info:
        acquisition.grab_release(
            ReleaseGrabRequest(album_id=album.id, grab_url="magnet:?xt=1", protocol="torrent"), db=db
        )
    assert exc_info.value.status_code == 400


def test_grab_release_surfaces_client_preflight_failure(db):
    album = _album(db)
    client_row = DownloadClient(name="qbt", protocol="torrent", implementation="qbittorrent", host="localhost", port=8080, enabled=True)
    db.add(client_row)
    db.commit()

    class FakeClient:
        def test(self):
            return False, "auth failed"

        def close(self):
            pass

    with patch("app.services.acquisition_actions.get_client", return_value=FakeClient()):
        with pytest.raises(HTTPException) as exc_info:
            acquisition.grab_release(
                ReleaseGrabRequest(album_id=album.id, grab_url="magnet:?xt=1", protocol="torrent"), db=db
            )
    assert exc_info.value.status_code == 400
    assert "auth failed" in exc_info.value.detail


def test_acquisition_status_flags_indexer_that_fails_connectivity(db):
    """A saved-but-broken indexer (bad key, unreachable host) used to look
    identical to a healthy one here — only the count was checked, not
    whether it actually responds."""
    db.add(Indexer(name="NZBGeek", protocol="usenet", base_url="https://api.nzbgeek.info", api_key="bad", enabled=True))
    db.commit()

    with patch(
        "app.api.acquisition.verify_indexer_key",
        return_value=(False, "Indexer error 100: Invalid API Key"),
    ):
        status = acquisition.acquisition_status(db=db)

    assert any("NZBGeek" in m and "Invalid API Key" in m for m in status.messages)


def test_acquisition_status_silent_when_indexer_connects(db):
    db.add(Indexer(name="NZBGeek", protocol="usenet", base_url="https://api.nzbgeek.info", api_key="good", enabled=True))
    db.commit()

    with patch(
        "app.api.acquisition.verify_indexer_key",
        return_value=(True, "Connected to api.nzbgeek.info"),
    ):
        status = acquisition.acquisition_status(db=db)

    assert not any("NZBGeek" in m for m in status.messages)


def test_acquisition_status_flags_download_client_that_fails_connectivity(db):
    client_row = DownloadClient(name="qbt", protocol="torrent", implementation="qbittorrent", host="localhost", port=8080, enabled=True)
    db.add(client_row)
    db.commit()

    class FakeClient:
        def test(self):
            return False, "Connection refused"

        def close(self):
            pass

    with patch("app.api.acquisition.get_client", return_value=FakeClient()):
        status = acquisition.acquisition_status(db=db)

    assert any("qbt" in m and "Connection refused" in m for m in status.messages)
