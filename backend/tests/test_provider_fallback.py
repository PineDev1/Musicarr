from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.models import Album, HistoryEvent
from app.services.artists import _legacy_id
from app.services.download_queue import DownloadQueue
from app.services.providers.base import ProviderError
from tests.conftest import _artist


def _album(db, artist, *, provider="qobuz", provider_id="alb1", title="Test Album"):
    album = Album(
        provider=provider,
        provider_id=provider_id,
        deezer_id=_legacy_id(provider, provider_id),
        artist_id=artist.id,
        title=title,
        album_type="album",
        track_count=10,
        monitored=True,
        status="wanted",
    )
    db.add(album)
    db.commit()
    db.refresh(album)
    return album


def _settings(*, active_provider="qobuz", fallback_providers_enabled=True):
    return SimpleNamespace(
        active_provider=active_provider,
        fallback_providers_enabled=fallback_providers_enabled,
    )


def test_resolve_download_target_uses_active_provider_first(db):
    artist = _artist(db, name="Artist", provider="qobuz", provider_id="a1")
    album = _album(db, artist)
    queue = DownloadQueue()
    fake_provider = object()

    with patch.object(queue, "_resolve_for_provider", return_value=(fake_provider, album)) as m:
        provider, resolved, name = queue._resolve_download_target(db, album, artist, _settings())

    assert name == "qobuz"
    assert provider is fake_provider
    assert resolved is album
    m.assert_called_once_with(db, album, artist, "qobuz")
    # No fallback happened, so nothing should be logged to history.
    assert db.query(HistoryEvent).count() == 0


def test_resolve_download_target_falls_back_when_active_fails(db):
    artist = _artist(db, name="Artist", provider="qobuz", provider_id="a2")
    album = _album(db, artist, provider="qobuz", provider_id="alb2")
    fallback_album = _album(db, artist, provider="deezer", provider_id="alb2-deezer")
    queue = DownloadQueue()
    fake_provider = object()

    def side_effect(db_, album_, artist_, name):
        if name == "qobuz":
            raise ProviderError("Qobuz doesn't have this album")
        if name == "deezer":
            return fake_provider, fallback_album
        raise ProviderError(f"{name} not authenticated")

    with patch.object(queue, "_resolve_for_provider", side_effect=side_effect):
        provider, resolved, name = queue._resolve_download_target(db, album, artist, _settings())

    assert name == "deezer"
    assert provider is fake_provider
    assert resolved is fallback_album
    events = db.query(HistoryEvent).all()
    assert len(events) == 1
    assert "deezer" in events[0].message
    assert "unavailable on qobuz" in events[0].message


def test_resolve_download_target_raises_last_error_when_all_fail(db):
    artist = _artist(db, name="Artist", provider="qobuz", provider_id="a3")
    album = _album(db, artist, provider="qobuz", provider_id="alb3")
    queue = DownloadQueue()

    def side_effect(db_, album_, artist_, name):
        raise ProviderError(f"{name} failed")

    # The error from the *last* candidate tried (deezer, tidal, qobuz in fixed
    # order with qobuz active) is what surfaces once every provider has failed.
    with patch.object(queue, "_resolve_for_provider", side_effect=side_effect):
        with pytest.raises(ProviderError, match="tidal failed"):
            queue._resolve_download_target(db, album, artist, _settings(active_provider="qobuz"))


def test_resolve_download_target_respects_fallback_disabled(db):
    artist = _artist(db, name="Artist", provider="qobuz", provider_id="a4")
    album = _album(db, artist, provider="qobuz", provider_id="alb4")
    queue = DownloadQueue()

    with patch.object(
        queue, "_resolve_for_provider", side_effect=ProviderError("qobuz not connected")
    ) as m:
        with pytest.raises(ProviderError):
            queue._resolve_download_target(
                db, album, artist, _settings(fallback_providers_enabled=False)
            )

    # Only the active provider should have been tried — no fallback candidates.
    m.assert_called_once_with(db, album, artist, "qobuz")
