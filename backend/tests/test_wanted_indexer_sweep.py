from __future__ import annotations

from unittest.mock import patch

from app.models import Album, AppSettings, DownloadJob
from app.services.artists import _legacy_id
from app.services.indexer_engine import WantedIndexerSweep
from tests.conftest import _artist


def _settings(db, **overrides) -> AppSettings:
    row = AppSettings(id=1, auto_grab_indexers_enabled=True, auto_grab_min_score=20.0)
    for key, value in overrides.items():
        setattr(row, key, value)
    db.add(row)
    db.commit()
    return row


def _album(db, artist, title, provider_id, status="wanted") -> Album:
    album = Album(
        provider=artist.provider, provider_id=provider_id, deezer_id=_legacy_id(artist.provider, provider_id),
        artist_id=artist.id, title=title, status=status,
    )
    db.add(album)
    db.commit()
    db.refresh(album)
    return album


def test_run_once_grabs_across_multiple_wanted_albums_and_artists(db):
    _settings(db)
    a1 = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    a2 = _artist(db, name="Chris Stapleton", provider="qobuz", provider_id="a2")
    _album(db, a1, "Album One", "al1")
    _album(db, a2, "Album Two", "al2")

    with patch("app.services.indexer_engine.try_auto_grab_release", return_value=True) as grab:
        result = WantedIndexerSweep().run_once(force=True, db=db)

    assert result["checked"] == 2
    assert result["grabbed"] == 2
    assert grab.call_count == 2


def test_run_once_skips_artists_without_auto_grab_enabled(db):
    _settings(db, auto_grab_indexers_enabled=False)
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    _album(db, artist, "Album One", "al1")

    with patch("app.services.indexer_engine.try_auto_grab_release") as grab:
        result = WantedIndexerSweep().run_once(force=True, db=db)

    assert result["checked"] == 0
    grab.assert_not_called()


def test_run_once_skips_albums_with_an_active_job(db):
    _settings(db)
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    album = _album(db, artist, "Album One", "al1")
    db.add(DownloadJob(target_type="album", target_id=album.id, album_id=album.id, state="downloading", source="indexer"))
    db.commit()

    with patch("app.services.indexer_engine.try_auto_grab_release") as grab:
        result = WantedIndexerSweep().run_once(force=True, db=db)

    assert result["checked"] == 0
    grab.assert_not_called()


def test_run_once_ignores_non_wanted_albums(db):
    _settings(db)
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    _album(db, artist, "Downloaded Album", "al1", status="downloaded")

    with patch("app.services.indexer_engine.try_auto_grab_release") as grab:
        result = WantedIndexerSweep().run_once(force=True, db=db)

    assert result["checked"] == 0
    grab.assert_not_called()


def test_run_once_respects_indexer_sweep_enabled_when_not_forced(db):
    _settings(db, indexer_sweep_enabled=False)
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    _album(db, artist, "Album One", "al1")

    with patch("app.services.indexer_engine.try_auto_grab_release") as grab:
        result = WantedIndexerSweep().run_once(force=False, db=db)

    assert result.get("skipped") is True
    grab.assert_not_called()
