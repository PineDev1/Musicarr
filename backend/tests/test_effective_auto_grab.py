from __future__ import annotations

from app.models import AppSettings
from app.services.artists import effective_auto_grab
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


def test_effective_auto_grab_inherits_global_default(db):
    _settings(db, auto_grab_indexers_enabled=False)
    artist = _artist(db, name="A", provider="qobuz", provider_id="a1")
    assert effective_auto_grab(db, artist) is False

    _settings(db, auto_grab_indexers_enabled=True)
    assert effective_auto_grab(db, artist) is True


def test_effective_auto_grab_artist_override_wins(db):
    _settings(db, auto_grab_indexers_enabled=True)
    artist = _artist(db, name="A", provider="qobuz", provider_id="a1")
    artist.auto_grab_override = "off"
    db.commit()
    assert effective_auto_grab(db, artist) is False

    _settings(db, auto_grab_indexers_enabled=False)
    artist.auto_grab_override = "on"
    db.commit()
    assert effective_auto_grab(db, artist) is True
