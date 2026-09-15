from __future__ import annotations

from app.models import AppSettings
from app.services.filters import classify_album_for_import


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


def test_classify_type_disabled(db):
    _settings(db, include_singles=False)
    status, reason, code = classify_album_for_import(
        db, title="Some Song", album_type="single", track_count=1
    )
    assert status == "skipped"
    assert code == "type_disabled"
    assert reason


def test_classify_junk(db):
    _settings(db, include_albums=True, ignore_junk_titles=True)
    status, reason, code = classify_album_for_import(
        db, title="My Song (Karaoke Version)", album_type="album", track_count=10
    )
    assert status == "skipped"
    assert code == "junk"


def test_classify_live(db):
    _settings(db, include_albums=True, ignore_junk_titles=False, ignore_live_releases=True)
    status, reason, code = classify_album_for_import(
        db, title="Concert (Live)", album_type="album", track_count=10
    )
    assert status == "skipped"
    assert code == "live"


def test_classify_min_tracks(db):
    _settings(db, include_albums=True, ignore_junk_titles=False, min_track_count=5)
    status, reason, code = classify_album_for_import(
        db, title="Short Album", album_type="album", track_count=2
    )
    assert status == "skipped"
    assert code == "min_tracks"


def test_classify_wanted_when_nothing_matches(db):
    _settings(
        db,
        include_albums=True,
        ignore_junk_titles=True,
        ignore_live_releases=False,
        min_track_count=0,
    )
    status, reason, code = classify_album_for_import(
        db, title="Normal Album", album_type="album", track_count=10
    )
    assert status == "wanted"
    assert code == ""
    assert reason == ""
