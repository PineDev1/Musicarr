from __future__ import annotations

from unittest.mock import patch

from app.models import Album, AppSettings
from app.services.acquisition_actions import GrabError
from app.services.artists import _legacy_id
from app.services.indexers.base import ReleaseCandidate
from app.services.monitor import _try_auto_grab_from_indexer
from tests.conftest import _artist


def _album(db) -> Album:
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    album = Album(
        provider="qobuz",
        provider_id="al1",
        deezer_id=_legacy_id("qobuz", "al1"),
        artist_id=artist.id,
        title="Fathers & Sons",
        track_count=1,
        monitored=True,
        status="wanted",
    )
    db.add(album)
    db.commit()
    db.refresh(album)
    return artist, album


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


def test_auto_grab_picks_top_scored_candidate_above_threshold(db):
    artist, album = _album(db)
    settings = _settings(db, auto_grab_min_score=20.0)
    candidates = [
        ReleaseCandidate(title="Fathers & Sons [FLAC]", protocol="usenet", download_url="https://x/1.nzb", score=25.0, indexer_id=1),
    ]

    with patch("app.services.indexers.search.search_album", return_value=(candidates, [])), \
         patch("app.services.acquisition_actions.grab_release_for_album") as grab:
        result = _try_auto_grab_from_indexer(db, artist, album, settings)

    assert result is True
    grab.assert_called_once()
    _, kwargs = grab.call_args
    assert kwargs["grab_url"] == "https://x/1.nzb"


def test_auto_grab_refuses_when_nothing_meets_the_score_threshold(db):
    artist, album = _album(db)
    settings = _settings(db, auto_grab_min_score=20.0)
    candidates = [
        ReleaseCandidate(title="Fathers & Sons [FLAC]", protocol="usenet", download_url="https://x/1.nzb", score=5.0, indexer_id=1),
    ]

    with patch("app.services.indexers.search.search_album", return_value=(candidates, [])), \
         patch("app.services.acquisition_actions.grab_release_for_album") as grab:
        result = _try_auto_grab_from_indexer(db, artist, album, settings)

    assert result is False
    grab.assert_not_called()


def test_auto_grab_returns_false_on_grab_error_without_raising(db):
    artist, album = _album(db)
    settings = _settings(db, auto_grab_min_score=20.0)
    candidates = [
        ReleaseCandidate(title="Fathers & Sons [FLAC]", protocol="usenet", download_url="https://x/1.nzb", score=25.0, indexer_id=1),
    ]

    with patch("app.services.indexers.search.search_album", return_value=(candidates, [])), \
         patch("app.services.acquisition_actions.grab_release_for_album", side_effect=GrabError("no client")):
        result = _try_auto_grab_from_indexer(db, artist, album, settings)

    assert result is False
