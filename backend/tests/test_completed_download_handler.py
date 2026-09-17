from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from mutagen.easyid3 import EasyID3

from app.models import Album, DownloadClient, DownloadJob, RemotePathMapping, Track
from app.services.artists import _legacy_id
from app.services.completed_download_handler import (
    CompletedDownloadHandler,
    artist_tags_match_expected,
)
from app.services.download_clients.base import ClientStatus
from tests.conftest import _artist


def _mp3_frame(size: int = 417) -> bytes:
    # One valid MPEG1 Layer III 128kbps/44100Hz frame (silence), repeated to
    # build a file mutagen genuinely recognizes and can report a real bitrate
    # for — this exercises the real tag-read/quality-detect code path instead
    # of mocking mutagen away.
    header = bytes([0xFF, 0xFB, 0x90, 0x00])
    return header + bytes(size - len(header))


def make_mp3(path: Path, *, title: str, artist: str, track: str, isrc: str | None = None, genre: str | None = None) -> None:
    with open(path, "wb") as fh:
        for _ in range(80):
            fh.write(_mp3_frame())
    tags = EasyID3()
    tags["title"] = [title]
    tags["artist"] = [artist]
    tags["tracknumber"] = [track]
    if isrc:
        tags["isrc"] = [isrc]
    if genre:
        tags["genre"] = [genre]
    tags.save(path)


def _album_with_tracks(db, *, track_count=3, tracks=True):
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    album = Album(
        provider="qobuz",
        provider_id="al1",
        deezer_id=_legacy_id("qobuz", "al1"),
        artist_id=artist.id,
        title="Fathers & Sons",
        track_count=track_count,
        monitored=True,
        status="wanted",
    )
    db.add(album)
    db.commit()
    db.refresh(album)
    if tracks:
        rows = [
            Track(
                provider="qobuz",
                provider_id=f"t{i}",
                album_id=album.id,
                title=f"Song {i}",
                track_no=i,
                disc_no=1,
                isrc=f"ISRC{i}",
            )
            for i in range(1, track_count + 1)
        ]
        db.add_all(rows)
        db.commit()
    db.refresh(album)
    return artist, album


def _job(db, album, *, client_id=1) -> DownloadJob:
    job = DownloadJob(
        target_type="album",
        target_id=album.id,
        album_id=album.id,
        artist_name="Luke Combs",
        album_title=album.title,
        state="downloading",
        source="indexer",
        indexer_id=1,
        client_id=client_id,
        release_title="Luke Combs - Fathers & Sons [FLAC]",
        client_item_id="item-1",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _client_row(db) -> DownloadClient:
    row = DownloadClient(name="qbt", protocol="torrent", implementation="qbittorrent", host="localhost", port=8080)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_artist_tags_match_expected_true_false_and_none(tmp_path):
    good = tmp_path / "good.mp3"
    make_mp3(good, title="Fast Car", artist="Luke Combs", track="1")
    assert artist_tags_match_expected([good], "Luke Combs") is True

    wrong = tmp_path / "wrong.mp3"
    make_mp3(wrong, title="Some Song", artist="A Completely Different Band", track="1")
    assert artist_tags_match_expected([wrong], "Luke Combs") is False

    untagged = tmp_path / "untagged.wav"
    untagged.write_bytes(b"not real audio")
    assert artist_tags_match_expected([untagged], "Luke Combs") is None


def test_import_job_matches_by_isrc_and_sets_quality(db, tmp_path):
    artist, album = _album_with_tracks(db, track_count=3)
    src_dir = tmp_path / "download"
    src_dir.mkdir()
    # Deliberately out of natural order to prove ISRC (not position) drives matching.
    make_mp3(src_dir / "b.mp3", title="Track Three", artist="Luke Combs", track="3", isrc="ISRC3")
    make_mp3(src_dir / "a.mp3", title="Track One", artist="Luke Combs", track="1", isrc="ISRC1")
    make_mp3(src_dir / "c.mp3", title="Track Two", artist="Luke Combs", track="2", isrc="ISRC2")

    job = _job(db, album)
    client_row = _client_row(db)
    library_root = tmp_path / "library"
    library_root.mkdir()

    handler = CompletedDownloadHandler()
    with patch("app.services.completed_download_handler.library_root", return_value=library_root), \
         patch("app.services.completed_download_handler.map_remote_to_local", return_value=src_dir):
        result = handler._import_job(
            db, job, client_row, ClientStatus(state="completed", output_path=str(src_dir))
        )

    assert result == "imported"
    db.refresh(job)
    db.refresh(album)
    assert job.state == "completed"
    assert album.status == "downloaded"
    assert album.quality == "128"

    tracks_by_isrc = {t.isrc: t for t in album.tracks}
    assert tracks_by_isrc["ISRC1"].path and Path(tracks_by_isrc["ISRC1"].path).exists()
    assert tracks_by_isrc["ISRC2"].path and Path(tracks_by_isrc["ISRC2"].path).exists()
    assert tracks_by_isrc["ISRC3"].path and Path(tracks_by_isrc["ISRC3"].path).exists()


def test_import_job_rejects_wrong_artist(db, tmp_path):
    artist, album = _album_with_tracks(db, track_count=2)
    src_dir = tmp_path / "download"
    src_dir.mkdir()
    for i in (1, 2):
        make_mp3(src_dir / f"{i}.mp3", title=f"Song {i}", artist="Totally Different Artist", track=str(i))

    job = _job(db, album)
    client_row = _client_row(db)

    handler = CompletedDownloadHandler()
    with patch("app.services.completed_download_handler.library_root", return_value=tmp_path / "library"), \
         patch("app.services.completed_download_handler.map_remote_to_local", return_value=src_dir):
        result = handler._import_job(
            db, job, client_row, ClientStatus(state="completed", output_path=str(src_dir))
        )

    assert result == "failed"
    db.refresh(job)
    assert job.state == "failed"
    assert "different artist" in (job.error or "")
    # Nothing should have been filed into the library.
    db.refresh(album)
    assert album.status != "downloaded"


def test_import_job_rejects_incomplete_release(db, tmp_path):
    """A release missing most of its tracks must not be silently marked downloaded."""
    artist, album = _album_with_tracks(db, track_count=10)
    src_dir = tmp_path / "download"
    src_dir.mkdir()
    # Only 2 of 10 expected tracks present.
    make_mp3(src_dir / "1.mp3", title="Song 1", artist="Luke Combs", track="1", isrc="ISRC1")
    make_mp3(src_dir / "2.mp3", title="Song 2", artist="Luke Combs", track="2", isrc="ISRC2")

    job = _job(db, album)
    client_row = _client_row(db)

    handler = CompletedDownloadHandler()
    with patch("app.services.completed_download_handler.library_root", return_value=tmp_path / "library"), \
         patch("app.services.completed_download_handler.map_remote_to_local", return_value=src_dir):
        result = handler._import_job(
            db, job, client_row, ClientStatus(state="completed", output_path=str(src_dir))
        )

    assert result == "failed"
    db.refresh(job)
    assert job.state == "failed"
    assert "incomplete" in (job.error or "").lower()
    db.refresh(album)
    assert album.status != "downloaded"
    # No files should have been transferred out of the source directory.
    assert not (tmp_path / "library").exists() or not any((tmp_path / "library").rglob("*.mp3"))


def test_import_job_allows_near_complete_release(db, tmp_path):
    """8 of 10 tracks (>= 70%) is a legitimate partial-but-real release, not junk."""
    artist, album = _album_with_tracks(db, track_count=10)
    src_dir = tmp_path / "download"
    src_dir.mkdir()
    for i in range(1, 9):
        make_mp3(src_dir / f"{i}.mp3", title=f"Song {i}", artist="Luke Combs", track=str(i), isrc=f"ISRC{i}")

    job = _job(db, album)
    client_row = _client_row(db)

    handler = CompletedDownloadHandler()
    with patch("app.services.completed_download_handler.library_root", return_value=tmp_path / "library"), \
         patch("app.services.completed_download_handler.map_remote_to_local", return_value=src_dir):
        result = handler._import_job(
            db, job, client_row, ClientStatus(state="completed", output_path=str(src_dir))
        )

    assert result == "imported"
    db.refresh(album)
    assert album.status == "downloaded"


def test_import_job_fails_when_mapped_path_missing(db, tmp_path):
    artist, album = _album_with_tracks(db, track_count=1)
    job = _job(db, album)
    client_row = _client_row(db)

    handler = CompletedDownloadHandler()
    with patch(
        "app.services.completed_download_handler.map_remote_to_local",
        return_value=tmp_path / "does-not-exist",
    ):
        result = handler._import_job(
            db, job, client_row, ClientStatus(state="completed", output_path="/remote/path")
        )

    assert result == "failed"
    db.refresh(job)
    assert "not found" in (job.error or "").lower()


def test_poll_job_marks_downloading_progress(db, tmp_path):
    artist, album = _album_with_tracks(db, track_count=1)
    job = _job(db, album)
    client_row = _client_row(db)

    handler = CompletedDownloadHandler()

    class FakeClient:
        def get_status(self, item_id):
            return ClientStatus(state="downloading", progress=0.42, title="Fathers & Sons")

        def close(self):
            pass

    with patch("app.services.completed_download_handler.get_client", return_value=FakeClient()):
        result = handler._poll_job(db, job)

    assert result == "pending"
    db.refresh(job)
    assert job.state == "downloading"
    assert 40 <= job.progress <= 45


def test_poll_job_fails_when_client_reports_failed(db, tmp_path):
    artist, album = _album_with_tracks(db, track_count=1)
    job = _job(db, album)
    client_row = _client_row(db)

    handler = CompletedDownloadHandler()

    class FakeClient:
        def get_status(self, item_id):
            return ClientStatus(state="failed")

        def close(self):
            pass

    with patch("app.services.completed_download_handler.get_client", return_value=FakeClient()):
        result = handler._poll_job(db, job)

    assert result == "failed"
    db.refresh(job)
    assert job.state == "failed"


def test_run_once_ignores_streaming_jobs(db, monkeypatch):
    """The completed-download handler must only ever touch source='indexer' jobs."""
    import app.services.completed_download_handler as handler_module

    artist, album = _album_with_tracks(db, track_count=1)
    streaming_job = DownloadJob(
        target_type="album",
        target_id=album.id,
        album_id=album.id,
        artist_name="Luke Combs",
        album_title=album.title,
        state="running",
        source="streaming",
    )
    db.add(streaming_job)
    db.commit()

    # run_once() opens/closes its own session; keep it pinned to the test's
    # in-memory db and stop it from closing that session out from under us.
    monkeypatch.setattr(handler_module, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    handler = handler_module.CompletedDownloadHandler()
    stats = handler.run_once()
    assert stats["polled"] == 0
