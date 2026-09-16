from __future__ import annotations

from app.models import AppSettings
from app.services.artists import effective_quality
from tests.conftest import _artist


def _settings(db, bitrate="flac") -> AppSettings:
    row = db.get(AppSettings, 1)
    if row is None:
        row = AppSettings(id=1, bitrate=bitrate, active_provider="deezer")
        db.add(row)
    else:
        row.bitrate = bitrate
    db.commit()
    return row


def test_effective_quality_inherits_global_default(db):
    _settings(db, bitrate="320")
    artist = _artist(db, name="A", provider="qobuz", provider_id="a1")

    assert effective_quality(db, artist) == "320"


def test_effective_quality_artist_override_wins(db):
    _settings(db, bitrate="320")
    artist = _artist(db, name="A", provider="qobuz", provider_id="a1")
    artist.quality_pref = "flac"

    assert effective_quality(db, artist) == "flac"
