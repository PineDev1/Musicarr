from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from app.services import mb_catalog_import
from app.services.background_job import BackgroundJobStore


@pytest.fixture(autouse=True)
def _reset_catalog_job(tmp_path):
    # Give the job store its own scratch persist file per test and reset state.
    mb_catalog_import._store._persist_path = tmp_path / "last_job.json"
    deadline = time.time() + 2
    while mb_catalog_import.get_job().state == "running" and time.time() < deadline:
        time.sleep(0.05)
    mb_catalog_import._store.update(
        state="idle",
        phase="",
        progress_pct=0,
        bytes_done=0,
        bytes_total=0,
        message="",
        error="",
        dump_version="",
        started_at="",
        finished_at="",
    )
    yield


def test_catalog_job_uses_shared_background_job_store():
    """Catalog import should reuse the same job-tracking mechanism as library jobs
    instead of its own hand-rolled dataclass/lock/persist implementation."""
    assert isinstance(mb_catalog_import._store, BackgroundJobStore)


def test_start_catalog_update_runs_to_completion():
    release = None

    def fake_fetch_latest(*args, **kwargs):
        raise RuntimeError("stop after version fetch")

    with patch.object(mb_catalog_import, "fetch_latest_dump_version", fake_fetch_latest):
        job = mb_catalog_import.start_catalog_update()
        assert job.state == "running"

        deadline = time.time() + 2
        while mb_catalog_import.get_job().state == "running" and time.time() < deadline:
            time.sleep(0.02)

    final = mb_catalog_import.get_job()
    assert final.state == "error"
    assert "stop after version fetch" in final.error


def test_start_catalog_update_rejects_concurrent_start():
    release_event = __import__("threading").Event()

    def fake_fetch_latest(*args, **kwargs):
        release_event.wait(timeout=2)
        raise RuntimeError("done")

    with patch.object(mb_catalog_import, "fetch_latest_dump_version", fake_fetch_latest):
        first = mb_catalog_import.start_catalog_update()
        assert first.state == "running"

        # A second start while running must not clobber the first job or raise.
        second = mb_catalog_import.start_catalog_update()
        assert second.state == "running"

        release_event.set()
        deadline = time.time() + 2
        while mb_catalog_import.get_job().state == "running" and time.time() < deadline:
            time.sleep(0.02)
