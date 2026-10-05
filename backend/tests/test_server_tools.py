from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import main
from app.api import server_tools as tools_api
from app.models import DownloadClient, Indexer
from app.services import server_tools
from app.services.settings_service import ensure_settings


@pytest.fixture(autouse=True)
def _fresh_cache():
    server_tools.reset_update_cache()
    yield
    server_tools.reset_update_cache()


def test_healthz_is_public_and_reports_ok():
    r = TestClient(main.app).get("/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"


@pytest.mark.parametrize(
    "a,b,newer",
    [("1.22.3", "1.22.2", True), ("1.23", "1.22.9", True), ("1.22.2", "1.22.2", False), ("1.22.1", "1.22.2", False), ("", "1.0", False)],
)
def test_version_compare(a, b, newer):
    assert (bool(server_tools.parse_version(a)) and server_tools.parse_version(a) > server_tools.parse_version(b)) is newer


def test_update_status_reports_newer_release_and_caches(db, monkeypatch):
    calls = {"n": 0}

    def fake():
        calls["n"] += 1
        return {"tag": "v99.0.0", "url": "https://example.test/r", "name": "x"}

    monkeypatch.setattr(server_tools, "_fetch_latest_release", fake)
    first = server_tools.update_status(db)
    assert first["update_available"] and first["latest"] == "99.0.0"
    server_tools.update_status(db)
    assert calls["n"] == 1  # second call served from cache


def test_update_status_never_touches_network_when_disabled(db, monkeypatch):
    row = ensure_settings(db)
    row.update_check_enabled = False
    db.commit()
    monkeypatch.setattr(server_tools, "_fetch_latest_release", lambda: pytest.fail("network called"))
    out = server_tools.update_status(db)
    assert out["enabled"] is False and out["update_available"] is False


def test_update_status_survives_github_being_unreachable(db, monkeypatch):
    monkeypatch.setattr(server_tools, "_fetch_latest_release", lambda: None)
    out = server_tools.update_status(db)
    assert out["update_available"] is False and out["latest"] is None


def test_checklist_reflects_missing_then_configured_pieces(db, tmp_path):
    row = ensure_settings(db)
    row.library_path = str(tmp_path)
    row.streaming_enabled = False
    row.preferred_download_method = "indexer"
    db.commit()
    items = {i["key"]: i for i in server_tools.setup_checklist(db)["items"]}
    assert items["library"]["status"] == "ok"
    assert items["indexers"]["status"] == "todo" and items["client"]["status"] == "todo"
    db.add_all([Indexer(name="i", enabled=True), DownloadClient(name="c", enabled=True)])
    db.commit()
    out = server_tools.setup_checklist(db)
    items = {i["key"]: i for i in out["items"]}
    assert items["indexers"]["status"] == "ok" and items["client"]["status"] == "ok"
    assert items["notify"]["status"] == "optional"  # optional items never count as required
    assert out["required_left"] == sum(1 for i in out["items"] if i["status"] == "todo")


def test_diagnostics_masks_secrets_everywhere(db, tmp_path):
    row = ensure_settings(db)
    row.library_path = str(tmp_path)
    row.arl = "SECRET_ARL_VALUE"
    row.notify_webhook_url = "https://discord.test/api/webhooks/SECRET_HOOK"
    row.qobuz_app_secret = "SECRET_QOBUZ"
    db.add(Indexer(name="NZBGeek", protocol="usenet", enabled=True, api_key="SECRET_INDEXER_KEY", base_url="https://idx.test"))
    db.commit()
    import logging

    logging.getLogger("diag").warning("token=SECRET_LOG_TOKEN failed")
    blob = json.dumps(server_tools.diagnostics_bundle(db), default=str)
    for secret in ("SECRET_ARL_VALUE", "SECRET_HOOK", "SECRET_QOBUZ", "SECRET_INDEXER_KEY", "SECRET_LOG_TOKEN", "idx.test"):
        assert secret not in blob, secret
    assert "NZBGeek" in blob and tmp_path.name in blob


def test_browse_lists_only_folders_and_hides_dotfolders(db, tmp_path):
    (tmp_path / "Music").mkdir()
    (tmp_path / "b-folder").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "file.txt").write_text("x")
    out = server_tools.browse_directories(db, str(tmp_path))
    assert [e["name"] for e in out["entries"]] == ["b-folder", "Music"]
    assert out["parent"] == str(tmp_path.parent) and out["writable"] is True


@pytest.mark.parametrize("bad", ["relative/path", "/proc", "/proc/1", "/definitely/not/here"])
def test_browse_rejects_relative_blocked_and_missing(db, bad):
    with pytest.raises(HTTPException) as e:
        tools_api.browse_folders(bad, db)
    assert e.value.status_code == 400


def test_browse_never_lists_a_file(db, tmp_path):
    f = tmp_path / "song.flac"
    f.write_text("x")
    with pytest.raises(ValueError):
        server_tools.browse_directories(db, str(f))


def test_iso_utc_always_includes_a_timezone():
    from datetime import datetime, timezone

    assert server_tools.iso_utc(datetime(2026, 1, 1, 12, 0)).endswith("+00:00")
    assert server_tools.iso_utc(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)).endswith("+00:00")
    assert server_tools.iso_utc(None) is None
