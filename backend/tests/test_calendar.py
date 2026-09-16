from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import Album
from app.services.calendar import upcoming_releases
from tests.conftest import _artist


def _album(db, artist, title, release_date):
    a = Album(
        provider=artist.provider,
        provider_id=f"al-{title}",
        artist_id=artist.id,
        title=title,
        release_date=release_date,
        status="wanted",
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def test_upcoming_releases_filters_window_and_monitored(db):
    today = datetime.now(timezone.utc).date()
    monitored = _artist(db, name="Monitored Artist", provider="qobuz", provider_id="m1")
    unmonitored = _artist(db, name="Unmonitored Artist", provider="qobuz", provider_id="m2")
    unmonitored.monitored = False
    db.commit()

    in_window = _album(db, monitored, "Soon", (today + timedelta(days=10)).isoformat())
    _album(db, monitored, "Too Far", (today + timedelta(days=400)).isoformat())
    _album(db, unmonitored, "Ignored", (today + timedelta(days=10)).isoformat())

    results = upcoming_releases(db)

    assert [r["album_id"] for r in results] == [in_window.id]
    assert results[0]["artist_name"] == "Monitored Artist"


def test_upcoming_releases_sorted_ascending(db):
    today = datetime.now(timezone.utc).date()
    artist = _artist(db, name="A", provider="qobuz", provider_id="a1")
    later = _album(db, artist, "Later", (today + timedelta(days=20)).isoformat())
    sooner = _album(db, artist, "Sooner", (today + timedelta(days=5)).isoformat())

    results = upcoming_releases(db)

    assert [r["album_id"] for r in results] == [sooner.id, later.id]
