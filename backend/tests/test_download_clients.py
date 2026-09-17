from __future__ import annotations

import httpx
import pytest

from app.services.download_clients.base import DownloadClientError, base_url
from app.services.download_clients.qbittorrent import QBittorrentClient, hash_from_magnet
from app.services.download_clients.sabnzbd import SabnzbdClient


def test_base_url_variants():
    assert base_url("localhost", 8080, False) == "http://localhost:8080"
    assert base_url("qbittorrent", 8080, False) == "http://qbittorrent:8080"
    assert base_url("https://host.tld:9443", 8080, True) == "https://host.tld:9443"
    assert base_url("host.tld/qb", 8080, False) == "http://host.tld:8080/qb"
    # Default scheme ports must not be echoed back explicitly.
    assert base_url("https://host.tld", 443, True) == "https://host.tld"


def test_hash_from_magnet_hex_and_base32():
    magnet_hex = "magnet:?xt=urn:btih:" + "a" * 40 + "&dn=test"
    assert hash_from_magnet(magnet_hex) == "a" * 40
    assert hash_from_magnet("https://not-a-magnet") == ""


MAGNET = "magnet:?xt=urn:btih:" + "b" * 40 + "&dn=album"


def _client(monkeypatch, responses: dict[str, httpx.Response]) -> QBittorrentClient:
    client = QBittorrentClient("localhost", 8080, username="admin", password="pw")

    def fake_request(self, method, path, **kwargs):
        key = f"{method} {path}"
        if key not in responses:
            raise AssertionError(f"unexpected request {key}")
        return responses[key]

    monkeypatch.setattr(httpx.Client, "request", fake_request, raising=True)
    monkeypatch.setattr(httpx.Client, "post", lambda self, path, **kw: fake_request(self, "POST", path, **kw), raising=True)
    return client


def test_qbittorrent_add_url_uses_magnet_hash_without_polling(monkeypatch):
    responses = {
        "POST /api/v2/auth/login": httpx.Response(200, text="Ok."),
        "POST /api/v2/torrents/add": httpx.Response(200, text="Ok."),
    }
    client = _client(monkeypatch, responses)
    item_id = client.add_url(MAGNET, "musicarr")
    assert item_id == "b" * 40


def test_qbittorrent_get_status_maps_states(monkeypatch):
    responses = {
        "POST /api/v2/auth/login": httpx.Response(200, text="Ok."),
        "GET /api/v2/torrents/info": httpx.Response(
            200,
            json=[
                {
                    "hash": "b" * 40,
                    "state": "uploading",
                    "progress": 1.0,
                    "content_path": "/downloads/Some Album",
                    "name": "Some Album",
                }
            ],
        ),
    }
    client = _client(monkeypatch, responses)
    status = client.get_status("b" * 40)
    assert status.state == "completed"
    assert status.output_path == "/downloads/Some Album"


def test_qbittorrent_login_rejected_raises_clear_error(monkeypatch):
    responses = {"POST /api/v2/auth/login": httpx.Response(200, text="Fails.")}
    client = _client(monkeypatch, responses)
    with pytest.raises(DownloadClientError, match="rejected"):
        client.add_url(MAGNET, "musicarr")


def _sab_client(monkeypatch, payload_by_mode: dict[str, dict]) -> SabnzbdClient:
    client = SabnzbdClient("localhost", 8080, api_key="key123")

    def fake_get(self, path, params=None, **kwargs):
        mode = (params or {}).get("mode")
        if mode not in payload_by_mode:
            raise AssertionError(f"unexpected mode {mode}")
        resp = httpx.Response(200, json=payload_by_mode[mode])
        resp._request = httpx.Request("GET", "http://localhost:8080/api")
        return resp

    monkeypatch.setattr(httpx.Client, "get", fake_get, raising=True)
    return client


def test_sabnzbd_add_url_returns_nzo_id(monkeypatch):
    client = _sab_client(monkeypatch, {"addurl": {"status": True, "nzo_ids": ["SABnzbd_nzo_123"]}})
    item_id = client.add_url("https://indexer.example/x.nzb", "musicarr")
    assert item_id == "SABnzbd_nzo_123"


def test_sabnzbd_get_status_completed_from_history(monkeypatch):
    client = _sab_client(
        monkeypatch,
        {
            "queue": {"queue": {"slots": []}},
            "history": {
                "history": {
                    "slots": [
                        {
                            "nzo_id": "id1",
                            "status": "Completed",
                            "storage": "/downloads/Some Album",
                            "name": "Some Album",
                        }
                    ]
                }
            },
        },
    )
    status = client.get_status("id1")
    assert status.state == "completed"
    assert status.output_path == "/downloads/Some Album"


def test_sabnzbd_missing_api_key_raises():
    client = SabnzbdClient("localhost", 8080, api_key="")
    with pytest.raises(DownloadClientError):
        client.add_url("https://indexer.example/x.nzb", "musicarr")
