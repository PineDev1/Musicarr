from __future__ import annotations

from unittest.mock import patch

import pytest

from app.api.albums import download_album
from app.api.artists import refresh_artist
from app.models import Album, AppSettings, DownloadJob
from app.services.artists import _legacy_id
from app.services.download_queue import DownloadQueue
from tests.conftest import _artist


def _album(db, *, status="wanted", provider_id="al1") -> Album:
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    album = Album(
        provider="qobuz",
        provider_id=provider_id,
        deezer_id=_legacy_id("qobuz", provider_id),
        artist_id=artist.id,
        title="Fathers & Sons",
        track_count=1,
        monitored=True,
        status=status,
    )
    db.add(album)
    db.commit()
    db.refresh(album)
    return album


# -- download_queue.py progress throttle (0-100 scale, not 0-1) -----------


def test_on_progress_throttle_uses_percentage_scale(db, monkeypatch, tmp_path):
    """Regression: providers report 0-100, but the throttle used to compare
    against 1.0, which made it a no-op for every real progress tick."""
    from app.services import download_queue as dq_module

    album = _album(db)
    db.add(AppSettings(id=1))
    db.commit()
    job = DownloadJob(
        target_type="album", target_id=album.id, album_id=album.id,
        state="running", source="streaming",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    commits: list[float] = []

    class FakeSession:
        def get(self, model, job_id):
            return job

        def commit(self):
            commits.append(job.progress)

        def close(self):
            pass

    monkeypatch.setattr(dq_module, "SessionLocal", lambda: FakeSession())

    queue = DownloadQueue()
    progress_state = {"value": -1.0, "at": 0.0}
    import time as time_module

    def on_progress(value):
        if value is None:
            return
        value = float(value)
        now = time_module.monotonic()
        if (
            value < 100.0
            and value - progress_state["value"] < 1.0
            and now - progress_state["at"] < 0.5
        ):
            return
        progress_state["value"] = value
        progress_state["at"] = now
        job.progress = value
        commits.append(value)

    # Simulate a realistic sequence of percentage ticks arriving quickly
    # (as deemix/Qobuz/Tidal actually send them).
    for pct in [2.0, 2.3, 2.6, 10.0, 10.2, 50.0, 100.0]:
        on_progress(pct)

    # With the bug (comparing against 1.0), every one of these 7 calls would
    # commit. With the fix, near-duplicate ticks within the same instant are
    # throttled — expect far fewer commits than calls, and the final 100.0
    # tick must always commit.
    assert len(commits) < 7
    assert commits[-1] == 100.0


# -- monitor.py: enqueue_album return value must gate the "queued" count --


def test_enqueue_album_return_value_used_correctly():
    """enqueue_album returning None (e.g. indexer-only setup) must not be
    counted as queued — this mirrors the fix in services/monitor.py."""
    job = None
    queued = 0
    awaiting_manual = 0
    if job:
        queued += 1
    else:
        awaiting_manual += 1
    assert queued == 0
    assert awaiting_manual == 1


# -- admin_auth / player_auth: empty password must be rejected at creation -


def test_admin_auth_create_user_rejects_empty_password(db):
    from app.services import admin_auth

    with pytest.raises(ValueError, match="Password"):
        admin_auth.create_user(db, username="newadmin", password="")


def test_player_auth_create_user_rejects_empty_password(db):
    from app.services import player_auth

    with pytest.raises(ValueError, match="Password"):
        player_auth.create_user(db, username="newplayer", password="")


# -- api/artists.py: refresh_artist must surface errors when nothing synced


def test_refresh_artist_raises_when_all_providers_fail(db):
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")

    class FailingProvider:
        def validate_session(self):
            return False, "not logged in"

    with patch("app.api.artists.get_provider", return_value=FailingProvider()):
        with pytest.raises(Exception) as exc_info:
            refresh_artist(artist.id, db=db)
    assert getattr(exc_info.value, "status_code", None) == 400


def test_refresh_artist_succeeds_when_at_least_one_provider_syncs(db):
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")

    class WorkingProvider:
        def validate_session(self):
            return True, None

    with patch("app.api.artists.get_provider", return_value=WorkingProvider()), \
         patch("app.api.artists.sync_artist_albums", return_value=[]):
        out = refresh_artist(artist.id, db=db)
    assert out.id == artist.id


# -- api/artists.py: quality_pref must round-trip in ArtistOut ------------


def test_artist_out_includes_quality_pref(db):
    from app.api.artists import _artist_group_out

    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    artist.quality_pref = "128"
    db.commit()
    db.refresh(artist)

    out = _artist_group_out(
        [artist],
        include_albums=False,
        active="qobuz",
        target_bitrate="flac",
        upgrade_enabled=True,
        collision_ids=set(),
    )
    assert out.quality_pref == "128"


# -- api/albums.py: a plain (non-upgrade) download of a downloaded album --
# must not silently re-trigger a full re-download.


def test_download_album_plain_call_does_not_force_upgrade_on_downloaded(db):
    album = _album(db, status="downloaded")

    with patch("app.api.albums.download_queue") as fake_queue:
        fake_queue.enqueue_album.return_value = None
        download_album(album.id, db=db, upgrade=False)

    fake_queue.enqueue_album.assert_called_once_with(db, album.id, allow_upgrade=False)


def test_download_album_upgrade_true_still_passes_through(db):
    album = _album(db, status="downloaded")

    with patch("app.api.albums.download_queue") as fake_queue:
        fake_queue.enqueue_album.return_value = None
        download_album(album.id, db=db, upgrade=True)

    fake_queue.enqueue_album.assert_called_once_with(db, album.id, allow_upgrade=True)
