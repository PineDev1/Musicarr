from __future__ import annotations

from unittest.mock import patch

from app.api.artists import get_similar_artists
from app.models import AppSettings
from tests.conftest import _artist


def _settings(db) -> AppSettings:
    row = AppSettings(id=1, lastfm_api_key="key", lastfm_api_secret="secret")
    db.add(row)
    db.commit()
    return row


def test_similar_artists_marks_ones_already_in_library(db):
    _settings(db)
    primary = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    existing = _artist(db, name="Ed Sheeran", provider="qobuz", provider_id="a2")

    with patch(
        "app.services.lastfm.similar_artists",
        return_value=[
            {"name": "Ed Sheeran", "match": 0.9},
            {"name": "Some New Artist", "match": 0.4},
        ],
    ):
        result = get_similar_artists(primary.id, db=db)

    assert result[0].name == "Ed Sheeran"
    assert result[0].already_in_library == existing.id
    assert result[1].name == "Some New Artist"
    assert result[1].already_in_library is None


def test_similar_artists_404_for_missing_artist(db):
    from fastapi import HTTPException

    try:
        get_similar_artists(999, db=db)
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 404
