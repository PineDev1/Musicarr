from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api import acquisition
from app.models import BlocklistEntry, DownloadJob
from app.models.schemas import BlocklistAdd
from app.services import blocklist
from app.services.completed_download_handler import CompletedDownloadHandler
from app.services.indexer_engine import try_auto_grab_release
from app.services.indexers.base import ReleaseCandidate
from tests.test_monitor_auto_grab import _album, _settings


def _cand(title, score=25.0):
    return ReleaseCandidate(
        title=title, protocol="usenet", download_url=f"https://x/{title}.nzb", score=score, indexer_id=1
    )


def test_auto_grab_skips_blocklisted_release_and_takes_next_best(db):
    artist, album = _album(db)
    settings = _settings(db, auto_grab_min_score=20.0)
    blocklist.add_release(db, "Fathers.and.Sons-FLAC-GRP", reason="bad")
    candidates = [_cand("Fathers.and.Sons-FLAC-GRP", 40.0), _cand("Fathers & Sons [FLAC] Other", 30.0)]

    with patch("app.services.indexers.search.search_album", return_value=(candidates, [])), patch(
        "app.services.acquisition_actions.grab_release_for_album"
    ) as grab:
        assert try_auto_grab_release(db, artist, album, settings) is True

    assert grab.call_args.kwargs["title"] == "Fathers & Sons [FLAC] Other"


def test_auto_grab_refuses_when_only_candidate_is_blocklisted(db):
    artist, album = _album(db)
    settings = _settings(db, auto_grab_min_score=20.0)
    blocklist.add_release(db, "Fathers & Sons [FLAC]")

    with patch(
        "app.services.indexers.search.search_album", return_value=([_cand("Fathers & Sons [FLAC]")], [])
    ), patch("app.services.acquisition_actions.grab_release_for_album") as grab:
        assert try_auto_grab_release(db, artist, album, settings) is False
    grab.assert_not_called()


def test_title_match_ignores_punctuation_and_case(db):
    blocklist.add_release(db, "Some.Album-2024-[FLAC]")
    assert blocklist.is_blocklisted(db, "some album 2024 flac")
    assert not blocklist.is_blocklisted(db, "some other album")
    blocklist.add_release(db, "Some.Album-2024-[FLAC]")  # idempotent
    assert db.query(BlocklistEntry).count() == 1


def test_failed_indexer_job_is_auto_blocklisted_but_streaming_is_not(db):
    idx = DownloadJob(
        target_type="album", state="grabbed", source="indexer", release_title="Bad Release [MP3]"
    )
    streaming = DownloadJob(target_type="album", state="running", source="streaming", release_title="")
    db.add_all([idx, streaming])
    db.commit()
    handler = CompletedDownloadHandler.__new__(CompletedDownloadHandler)
    with patch("app.services.notifications.send_notification"):
        handler._fail_job(db, idx, "corrupt", blocklist=True)
        handler._fail_job(db, streaming, "boom", blocklist=True)
    entries = db.query(BlocklistEntry).all()
    assert [e.release_title for e in entries] == ["Bad Release [MP3]"]
    assert "corrupt" in entries[0].reason


def test_local_failures_do_not_blocklist_a_good_release(db):
    """A missing path mapping / crash / disk error says nothing about the release."""
    job = DownloadJob(target_type="album", state="grabbed", source="indexer", release_title="Good Release [FLAC]")
    db.add(job)
    db.commit()
    handler = CompletedDownloadHandler.__new__(CompletedDownloadHandler)
    with patch("app.services.notifications.send_notification"):
        handler._fail_job(db, job, "Completed download not found at '/downloads/x'")
    assert db.query(BlocklistEntry).count() == 0
    assert job.state == "failed"


def test_blocklist_endpoints_add_from_job_list_remove(db):
    job = DownloadJob(target_type="album", state="failed", source="indexer", release_title="X Release")
    stream = DownloadJob(target_type="album", state="failed", source="streaming")
    db.add_all([job, stream])
    db.commit()
    entry = acquisition.add_to_blocklist(BlocklistAdd(job_id=job.id), db)
    assert entry.release_title == "X Release"
    with pytest.raises(HTTPException) as e:
        acquisition.add_to_blocklist(BlocklistAdd(job_id=stream.id), db)
    assert e.value.status_code == 400
    assert len(acquisition.list_blocklist(db)) == 1
    acquisition.remove_from_blocklist(entry.id, db)
    assert acquisition.list_blocklist(db) == []
