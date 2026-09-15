from __future__ import annotations

from app.models import Album, AppSettings, DownloadJob
from app.services.artists import (
    approve_pending_artist,
    effective_download_mode,
    list_pending_artists,
    reject_pending_artist,
)
from tests.conftest import _artist


def _settings(db, **overrides) -> AppSettings:
    row = db.get(AppSettings, 1)
    if row is None:
        row = AppSettings(id=1)
        db.add(row)
    for key, value in overrides.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def test_effective_download_mode_inherits_global_default(db):
    _settings(db, default_download_mode="manual")
    artist = _artist(db, name="A", provider="qobuz", provider_id="a1")
    assert effective_download_mode(db, artist) == "manual"

    _settings(db, default_download_mode="auto")
    assert effective_download_mode(db, artist) == "auto"


def test_effective_download_mode_artist_override_wins(db):
    _settings(db, default_download_mode="manual")
    artist = _artist(db, name="A", provider="qobuz", provider_id="a1")
    artist.download_mode = "auto"
    db.commit()
    assert effective_download_mode(db, artist) == "auto"


def test_list_pending_artists_only_returns_pending(db):
    active = _artist(db, name="Active", provider="qobuz", provider_id="a1")
    pending = _artist(db, name="Pending", provider="qobuz", provider_id="p1")
    pending.status = "pending"
    pending.pending_reason = "import_list"
    db.commit()

    rows = list_pending_artists(db)
    assert [r.id for r in rows] == [pending.id]
    assert active.status == "active"


def test_approve_pending_artist_flips_status_and_clears_reason(db):
    artist = _artist(db, name="Pending", provider="qobuz", provider_id="p1")
    artist.status = "pending"
    artist.pending_reason = "featured"
    artist.monitored = False  # avoid triggering a real download-queue sweep
    db.commit()

    approved = approve_pending_artist(db, artist.id)
    assert approved.status == "active"
    assert approved.pending_reason == ""


def test_reject_pending_artist_deletes_artist_and_cleans_up_jobs(db):
    artist = _artist(db, name="Pending", provider="qobuz", provider_id="p1")
    artist.status = "pending"
    db.commit()

    album = Album(
        provider="qobuz",
        provider_id="alb1",
        artist_id=artist.id,
        title="Some Album",
        status="wanted",
        monitored=True,
    )
    db.add(album)
    db.commit()
    db.refresh(album)

    job = DownloadJob(
        target_type="album",
        target_provider_id="alb1",
        album_id=album.id,
        artist_name=artist.name,
        album_title=album.title,
        state="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = job.id
    album_id = album.id
    artist_id = artist.id

    reject_pending_artist(db, artist_id)

    assert db.get(Album, album_id) is None
    assert db.get(DownloadJob, job_id) is None
    from app.models import Artist

    assert db.get(Artist, artist_id) is None


def test_reject_only_targets_pending_artists(db):
    artist = _artist(db, name="Active", provider="qobuz", provider_id="a1")
    import pytest

    with pytest.raises(ValueError):
        reject_pending_artist(db, artist.id)
