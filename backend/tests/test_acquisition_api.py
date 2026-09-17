from __future__ import annotations

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
        results = acquisition.search_releases(album_id=album.id, db=db)
    assert len(results) == 1
    assert results[0].grab_url == "magnet:?xt=1"


def test_search_releases_404_for_missing_album(db):
    with pytest.raises(HTTPException):
        acquisition.search_releases(album_id=999, db=db)


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

    with patch("app.api.acquisition.get_client", return_value=FakeClient()), \
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

    with patch("app.api.acquisition.get_client", return_value=FakeClient()):
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

    with patch("app.api.acquisition.get_client", return_value=FakeClient()):
        with pytest.raises(HTTPException) as exc_info:
            acquisition.grab_release(
                ReleaseGrabRequest(album_id=album.id, grab_url="magnet:?xt=1", protocol="torrent"), db=db
            )
    assert exc_info.value.status_code == 400
    assert "auth failed" in exc_info.value.detail
