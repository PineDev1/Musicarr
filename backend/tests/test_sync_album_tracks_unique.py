from __future__ import annotations

from unittest.mock import MagicMock

from app.models import Album, Track
from app.services.artists import _legacy_id, sync_album_tracks
from app.services.providers.base import ProviderTrack
from tests.conftest import _artist


def test_sync_album_tracks_namespaces_when_raw_id_taken(db, monkeypatch):
    owner = _artist(db, name="Owner", provider="qobuz", provider_id="o1")
    other = Album(
        provider="qobuz",
        provider_id="raw-album",
        deezer_id=_legacy_id("qobuz", "raw-album"),
        artist_id=owner.id,
        title="Original",
        status="wanted",
    )
    db.add(other)
    db.commit()
    db.refresh(other)
    db.add(
        Track(
            provider="qobuz",
            provider_id="track-raw",
            deezer_id=_legacy_id("qobuz", "track-raw"),
            album_id=other.id,
            title="Song",
            track_no=1,
            disc_no=1,
            duration=10,
        )
    )
    db.commit()

    collab_artist = _artist(db, name="Collab", provider="qobuz", provider_id="c1")
    collab_album = Album(
        provider="qobuz",
        provider_id=f"collab:{collab_artist.id}:raw-album",
        deezer_id=_legacy_id("qobuz", f"collab:{collab_artist.id}:raw-album"),
        artist_id=collab_artist.id,
        title="Original",
        status="wanted",
    )
    db.add(collab_album)
    db.commit()
    db.refresh(collab_album)

    fake = MagicMock()
    fake.list_tracks.return_value = [
        ProviderTrack(
            provider_id="track-raw",
            title="Song",
            track_no=1,
            disc_no=1,
            duration=10,
            isrc=None,
        )
    ]
    monkeypatch.setattr("app.services.providers.get_provider", lambda *_a, **_k: fake)

    tracks = sync_album_tracks(db, collab_album)
    assert len(tracks) == 1
    assert tracks[0].provider_id != "track-raw"
    assert tracks[0].provider_id.startswith(f"{collab_album.id}:")
