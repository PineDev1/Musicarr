from __future__ import annotations

from app.models import Album
from app.services.artists import _legacy_id
from app.services.library import _find_or_create_album
from tests.conftest import _artist


def _existing_album(db, artist, title) -> Album:
    row = Album(
        provider="qobuz",
        provider_id=f"al-{title}",
        deezer_id=_legacy_id("qobuz", f"al-{title}"),
        artist_id=artist.id,
        title=title,
        track_count=10,
        monitored=True,
        status="downloaded",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_substring_match_does_not_merge_different_releases(db):
    """Regression: 'Reputation' must not loose-match 'Reputation Stadium
    Tour' — that's a different release, not tag-formatting variance."""
    artist = _artist(db, name="Taylor Swift", provider="qobuz", provider_id="a1")
    tour = _existing_album(db, artist, "Reputation Stadium Tour")
    artist.albums = [tour]

    result = _find_or_create_album(db, artist, "Reputation", year="2017", track_count=15)

    assert result.id != tour.id
    assert result.title == "Reputation"


def test_minor_punctuation_variance_still_merges(db):
    """A few stray characters (typo/punctuation) should still be treated as
    the same album — only whole extra words must be rejected."""
    artist = _artist(db, name="Some Artist", provider="qobuz", provider_id="a2")
    existing = _existing_album(db, artist, "Greatest Hits!")
    artist.albums = [existing]

    result = _find_or_create_album(db, artist, "Greatest Hits", year=None, track_count=10)

    assert result.id == existing.id
