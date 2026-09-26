"""Regression tests for the streaming download completion path in
DownloadQueue._process_job:

- Files must be matched to Track rows by the track number embedded in the
  provider's filename, not by positional index — a provider that silently
  skips a track shifts every subsequent index, which used to tag/rename the
  wrong file as the wrong track.
- album.quality must reflect the quality actually detected in the delivered
  files, not just the quality that was requested (providers can silently
  fall back to a lower bitrate/format for some tracks).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.core.config import settings as app_config
from app.models import Album, DownloadJob, Track
from app.services.artists import _legacy_id
from app.services.download_queue import DownloadQueue
from app.services.providers.base import DownloadResult
from tests.conftest import _artist


def _mp3_frame(size: int = 417) -> bytes:
    header = bytes([0xFF, 0xFB, 0x90, 0x00])
    return header + bytes(size - len(header))


def make_mp3(path: Path) -> None:
    with open(path, "wb") as fh:
        for _ in range(80):
            fh.write(_mp3_frame())


def _album_with_tracks(db, *, track_count=3) -> tuple[Album, list[Track]]:
    artist = _artist(db, name="Luke Combs", provider="deezer", provider_id="a1")
    album = Album(
        provider="deezer",
        provider_id="al1",
        deezer_id=_legacy_id("deezer", "al1"),
        artist_id=artist.id,
        title="Fathers & Sons",
        track_count=track_count,
        monitored=True,
        status="wanted",
    )
    db.add(album)
    db.commit()
    db.refresh(album)
    tracks = [
        Track(
            provider="deezer",
            provider_id=f"t{i}",
            album_id=album.id,
            title=f"Song {i}",
            track_no=i,
            disc_no=1,
        )
        for i in range(1, track_count + 1)
    ]
    db.add_all(tracks)
    db.commit()
    db.refresh(album)
    return album, sorted(album.tracks, key=lambda t: t.track_no)


class FakeProvider:
    def __init__(self, files: list[Path]):
        self._files = files

    def download_album(self, provider_album_id, staging, bitrate, on_progress=None, is_cancelled=None):
        return DownloadResult(files=list(self._files), cover=None)


def _run_job(db, album, files: list[Path], monkeypatch) -> DownloadJob:
    job = DownloadJob(
        target_type="album",
        target_id=album.id,
        album_id=album.id,
        artist_name="Luke Combs",
        album_title=album.title,
        state="queued",
        source="streaming",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    import app.services.download_queue as dq_module

    monkeypatch.setattr(dq_module, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    queue = DownloadQueue()
    provider = FakeProvider(files)
    with patch.object(
        DownloadQueue, "_resolve_download_target", return_value=(provider, album, "deezer")
    ), patch("app.services.artists.sync_album_tracks", lambda db_, alb: None):
        queue._process_job(job.id)
    db.refresh(job)
    return job


def test_track_matched_by_filename_number_survives_a_skipped_track(db, tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "data_dir", tmp_path)
    album, tracks = _album_with_tracks(db, track_count=3)

    # Track 2 was skipped by the provider — only files "1 - ..." and
    # "3 - ..." exist. A positional zip would wrongly tag "3 - ..." as track 2.
    staging = tmp_path / "src"
    staging.mkdir()
    f1 = staging / "1 - Song 1.mp3"
    f3 = staging / "3 - Song 3.mp3"
    make_mp3(f1)
    make_mp3(f3)

    job = _run_job(db, album, [f1, f3], monkeypatch)

    assert job.state == "completed"
    db.refresh(album)
    by_no = {t.track_no: t for t in album.tracks}
    assert by_no[1].path and Path(by_no[1].path).name.startswith("Song 1") or "1" in Path(by_no[1].path).name
    assert by_no[3].path is not None
    # The critical assertion: track 2 (skipped) got no file, and track 3's
    # file is genuinely track 3's content, not the second downloaded file
    # mislabeled as track 2.
    assert by_no[2].path is None
    assert Path(by_no[3].path).exists()


def test_album_quality_reflects_actual_detected_quality_not_requested(db, tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "data_dir", tmp_path)
    album, tracks = _album_with_tracks(db, track_count=1)

    staging = tmp_path / "src"
    staging.mkdir()
    f1 = staging / "1 - Song 1.mp3"
    make_mp3(f1)  # our synthetic mp3 frame is a low bitrate file, not flac

    with patch(
        "app.services.artists.effective_quality", return_value="flac"
    ):
        job = _run_job(db, album, [f1], monkeypatch)

    assert job.state == "completed"
    db.refresh(album)
    # Requested "flac", but the actual file is an mp3 — quality must reflect
    # what was really delivered, not the request.
    assert album.quality != "flac"
