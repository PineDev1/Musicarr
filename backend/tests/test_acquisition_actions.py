from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models import Album, DownloadClient, DownloadJob
from app.services.acquisition_actions import GrabError, grab_release_for_album
from app.services.artists import _legacy_id
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


class FakeClient:
    def __init__(self, *, test_ok=True, test_message="ok", item_id="hash123"):
        self._test_ok = test_ok
        self._test_message = test_message
        self._item_id = item_id

    def test(self):
        return self._test_ok, self._test_message

    def add_url(self, url, category=""):
        return self._item_id

    def close(self):
        pass


def test_grab_release_for_album_creates_job(db):
    album = _album(db)
    db.add(DownloadClient(name="qbt", protocol="torrent", implementation="qbittorrent", host="localhost", port=8080, enabled=True))
    db.commit()

    with patch("app.services.acquisition_actions.get_client", return_value=FakeClient()):
        job = grab_release_for_album(db, album, grab_url="magnet:?xt=1", protocol="torrent", title="Fathers & Sons [FLAC]")

    assert job.source == "indexer"
    assert job.state == "grabbed"
    assert job.client_item_id == "hash123"


def test_grab_release_for_album_rejects_empty_url(db):
    album = _album(db)
    with pytest.raises(GrabError):
        grab_release_for_album(db, album, grab_url="", protocol="torrent")


def test_grab_release_for_album_rejects_when_no_client(db):
    album = _album(db)
    with pytest.raises(GrabError) as exc:
        grab_release_for_album(db, album, grab_url="magnet:?xt=1", protocol="torrent")
    assert exc.value.status_code == 400


def test_grab_release_for_album_surfaces_preflight_failure(db):
    album = _album(db)
    db.add(DownloadClient(name="qbt", protocol="torrent", implementation="qbittorrent", host="localhost", port=8080, enabled=True))
    db.commit()

    with patch("app.services.acquisition_actions.get_client", return_value=FakeClient(test_ok=False, test_message="auth failed")):
        with pytest.raises(GrabError) as exc:
            grab_release_for_album(db, album, grab_url="magnet:?xt=1", protocol="torrent")
    assert "auth failed" in str(exc.value)


def test_grab_release_for_album_rejects_duplicate_active_job(db):
    album = _album(db)
    db.add(DownloadClient(name="qbt", protocol="torrent", implementation="qbittorrent", host="localhost", port=8080, enabled=True))
    db.add(DownloadJob(target_type="album", target_id=album.id, album_id=album.id, state="downloading", source="indexer", client_id=1))
    db.commit()

    with patch("app.services.acquisition_actions.get_client", return_value=FakeClient()):
        with pytest.raises(GrabError) as exc:
            grab_release_for_album(db, album, grab_url="magnet:?xt=1", protocol="torrent")
    assert exc.value.status_code == 409
