"""patch_album must not accept an arbitrary AlbumStatus value: "downloaded"
and "missing" are set only by the download/import and MusicBrainz-resolution
flows themselves — accepting them from a raw PATCH would desync album.status
from the real filesystem state, or (for "missing") permanently block
re-queuing since that value is treated elsewhere as a magic
provider-has-no-match marker.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.albums import patch_album
from app.models import Album
from app.models.schemas import AlbumPatch
from tests.conftest import _artist


def _album(db, **kwargs):
    artist = _artist(db, name="Artist", provider="qobuz", provider_id="a1")
    kwargs.setdefault("status", "wanted")
    album = Album(
        provider="qobuz",
        provider_id="al1",
        artist_id=artist.id,
        title="Album",
        **kwargs,
    )
    db.add(album)
    db.commit()
    db.refresh(album)
    return album


def test_patch_album_rejects_downloaded_status(db):
    album = _album(db)
    with pytest.raises(HTTPException) as exc:
        patch_album(album.id, AlbumPatch(status="downloaded"), db)
    assert exc.value.status_code == 400


def test_patch_album_rejects_missing_status(db):
    album = _album(db)
    with pytest.raises(HTTPException) as exc:
        patch_album(album.id, AlbumPatch(status="missing"), db)
    assert exc.value.status_code == 400


def test_patch_album_allows_skipped_and_sets_reason(db):
    album = _album(db)
    patch_album(album.id, AlbumPatch(status="skipped"), db)
    db.refresh(album)
    assert album.status == "skipped"
    assert album.skip_reason_code == "manual"
    assert album.status_reason


def test_patch_album_allows_wanted_and_clears_reason(db):
    album = _album(db, status="skipped", skip_reason_code="manual", status_reason="Skipped manually")
    patch_album(album.id, AlbumPatch(status="wanted"), db)
    db.refresh(album)
    assert album.status == "wanted"
    assert album.skip_reason_code == ""
    assert album.status_reason == ""
