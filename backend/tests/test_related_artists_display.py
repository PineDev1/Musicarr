from __future__ import annotations

from unittest.mock import patch

from app.services.artists import _related_artists_display
from tests.conftest import _artist


def test_related_artists_display_links_existing_artist(db):
    primary = _artist(db, name="Luke Combs", provider="qobuz", provider_id="p1")
    collab = _artist(db, name="Ed Sheeran", provider="qobuz", provider_id="p2")

    related = _related_artists_display(db, primary=primary, featured_names=["Ed Sheeran"])

    assert related == [
        {
            "id": collab.id,
            "name": "Ed Sheeran",
            "musicbrainz_id": collab.musicbrainz_id,
            "provider": "qobuz",
        }
    ]


def test_related_artists_display_does_not_create_or_search(db):
    """A collaborator with no existing Artist row must show up as a name-only
    suggestion (id=None) — never trigger a provider search or create a row.
    Artist rows for collaborators are only ever created on actual download
    completion (mirror_downloaded_album_to_collaborators)."""
    primary = _artist(db, name="Luke Combs", provider="qobuz", provider_id="p1")

    with patch("app.services.providers.get_provider") as get_provider:
        related = _related_artists_display(
            db, primary=primary, featured_names=["Some New Collaborator"]
        )
        get_provider.assert_not_called()

    assert related == [
        {"id": None, "name": "Some New Collaborator", "musicbrainz_id": None, "provider": None}
    ]

    from app.models import Artist
    from sqlalchemy import select

    assert db.scalar(select(Artist).where(Artist.name == "Some New Collaborator")) is None


def test_related_artists_display_excludes_self(db):
    primary = _artist(db, name="Luke Combs", provider="qobuz", provider_id="p1")

    related = _related_artists_display(
        db, primary=primary, featured_names=["Luke Combs", "Ed Sheeran"]
    )

    assert [r["name"] for r in related] == ["Ed Sheeran"]
