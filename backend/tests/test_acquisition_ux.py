from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.acquisition import acquisition_status, grab_release
from app.models import Album, DownloadClient, Indexer, RemotePathMapping
from app.models.schemas import ReleaseGrabRequest
from app.services.download_clients.base import base_url
from app.services.download_clients.qbittorrent import QBittorrentClient
from app.services.download_queue import download_queue
from app.services.settings_service import ensure_settings
from tests.conftest import _artist


@pytest.mark.parametrize(
    "host,port,ssl,expected",
    [
        ("localhost", 8080, False, "http://localhost:8080"),
        ("qbittorrent", 8080, False, "http://qbittorrent:8080"),
        ("host.docker.internal:8080", 9999, False, "http://host.docker.internal:8080"),
        ("http://qb:8080/qbittorrent", 8080, False, "http://qb:8080/qbittorrent"),
            ("https://dl.example.com/sab", 8080, True, "https://dl.example.com:8080/sab"),
            ("https://dl.example.com:443/sab", 8080, True, "https://dl.example.com/sab"),
        ("192.168.1.10:8080/path", 1, False, "http://192.168.1.10:8080/path"),
    ],
)
def test_base_url_cases(host, port, ssl, expected):
    assert base_url(host, port, ssl) == expected


def test_qbittorrent_defaults_username_when_password_set():
    client = QBittorrentClient("localhost", 8080, username="", password="secret")
    assert client.username == "admin"
    bare = QBittorrentClient("localhost", 8080, username="", password="")
    assert bare.username == ""


def test_enqueue_indexer_preferred_does_not_create_job(db):
    artist = _artist(db, name="Test", provider="deezer", provider_id="1")
    album = Album(
        artist_id=artist.id,
        provider="deezer",
        provider_id="10",
        title="Album",
        status="wanted",
        monitored=True,
    )
    db.add(album)
    db.commit()
    db.refresh(album)

    settings = ensure_settings(db)
    settings.preferred_download_method = "indexer"
    db.commit()

    assert download_queue.enqueue_album(db, album.id) is None
    assert download_queue.enqueue_album(db, album.id, method="indexer") is None
    job = download_queue.enqueue_album(db, album.id, method="streaming")
    assert job is not None
    assert job.source == "streaming"


def test_acquisition_status_messages(db):
    out = acquisition_status(db)
    assert out.indexers_enabled == 0
    assert out.torrent_client is False
    assert out.usenet_client is False
    assert out.path_mappings == 0
    assert any("indexer" in m.lower() for m in out.messages)

    db.add(
        Indexer(
            name="Prowlarr",
            protocol="torrent",
            implementation="torznab",
            base_url="http://prowlarr:9696/1/api",
            api_key="x",
            enabled=True,
            priority=25,
            categories="[3000]",
        )
    )
    db.add(
        DownloadClient(
            name="qB",
            protocol="torrent",
            implementation="qbittorrent",
            host="qbittorrent",
            port=8080,
            enabled=True,
        )
    )
    db.commit()
    out2 = acquisition_status(db)
    assert out2.indexers_enabled == 1
    assert out2.torrent_client is True
    assert any("path" in m.lower() for m in out2.messages)

    db.add(
        RemotePathMapping(
            host="",
            remote_path="/downloads",
            local_path="/data/downloads",
        )
    )
    db.commit()
    out3 = acquisition_status(db)
    assert out3.path_mappings == 1
    assert not any("path" in m.lower() for m in out3.messages)


def test_grab_preflight_requires_client(db):
    artist = _artist(db, name="Test", provider="deezer", provider_id="2")
    album = Album(
        artist_id=artist.id,
        provider="deezer",
        provider_id="20",
        title="Grab Me",
        status="wanted",
        monitored=True,
    )
    db.add(album)
    db.commit()
    db.refresh(album)

    with pytest.raises(HTTPException) as exc:
        grab_release(
            ReleaseGrabRequest(
                album_id=album.id,
                title="Some Release",
                grab_url="magnet:?xt=urn:btih:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                protocol="torrent",
            ),
            db,
        )
    assert exc.value.status_code == 400
    assert "download client" in str(exc.value.detail).lower()
