from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import library_jobs


@pytest.fixture(autouse=True)
def _reset_library_job(tmp_path, monkeypatch):
    from app.core.database import migrate_schema

    migrate_schema()
    monkeypatch.setattr(
        library_jobs._store,
        "_persist_path",
        tmp_path / "last_library_job.json",
    )
    # Wait for any previous worker
    deadline = time.time() + 2
    while library_jobs.get_job().state == "running" and time.time() < deadline:
        time.sleep(0.05)
    library_jobs._store.update(
        state="idle",
        kind="",
        phase="",
        progress_pct=0,
        message="",
        error="",
        started_at="",
        finished_at="",
        files_seen=0,
        files_done=0,
        artists_created=0,
        albums_imported=0,
        tracks_linked=0,
        provider_linked=0,
        matched=0,
        unmatched=0,
        moved=0,
        skipped=0,
        result={},
        link_providers=True,
    )
    yield


def test_start_scan_job_returns_202_and_completes():
    client = TestClient(app)
    release = threading.Event()

    def fake_scan(db, *, on_progress=None):
        release.wait(timeout=2)
        if on_progress:
            on_progress({"phase": "matching", "progress_pct": 50, "message": "halfway"})
        return {"files_seen": 2, "matched": 2, "unmatched": 0, "message": "Scan complete: ok"}

    with patch("app.services.library_jobs.scan_library", side_effect=fake_scan):
        res = client.post("/api/library/scan")
        assert res.status_code == 202
        body = res.json()
        assert body["kind"] == "scan"
        assert body["state"] == "running"

        conflict = client.post("/api/library/scan")
        assert conflict.status_code == 409

        release.set()

        deadline = time.time() + 5
        job = body
        while time.time() < deadline:
            job = client.get("/api/library/job").json()
            if job["state"] in {"done", "error"}:
                break
            time.sleep(0.05)

        assert job["state"] == "done"
        assert job["progress_pct"] == 100
        assert "Scan complete" in job["message"]
        assert job["matched"] == 2


def test_import_job_progress_and_result():
    client = TestClient(app)

    def fake_import(db, *, link_providers=True, on_progress=None):
        if on_progress:
            on_progress(
                {
                    "phase": "importing",
                    "progress_pct": 40,
                    "files_seen": 3,
                    "artists_created": 1,
                    "message": "Importing…",
                }
            )
        return {
            "files_seen": 3,
            "artists_created": 1,
            "albums_imported": 1,
            "tracks_linked": 3,
            "provider_linked": 0,
            "matched": 0,
            "unmatched": 0,
            "message": "Import complete",
        }

    with patch("app.services.library_jobs.import_existing_library", side_effect=fake_import):
        res = client.post("/api/library/import")
        assert res.status_code == 202
        deadline = time.time() + 5
        job = res.json()
        while time.time() < deadline:
            job = client.get("/api/library/job").json()
            if job["state"] in {"done", "error"}:
                break
            time.sleep(0.05)
        assert job["state"] == "done"
        assert job["artists_created"] == 1
        assert job["result"]["message"] == "Import complete"


def test_get_library_job_idle():
    client = TestClient(app)
    res = client.get("/api/library/job")
    assert res.status_code == 200
    assert res.json()["state"] == "idle"
