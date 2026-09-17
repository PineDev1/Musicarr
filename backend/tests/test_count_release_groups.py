from __future__ import annotations

from unittest.mock import patch

from app.services import musicbrainz


def test_count_release_groups_falls_back_to_live_when_local_misses():
    """Regression: local_with_live_fallback mode must still hit live MB when
    the artist isn't in the local dump yet, same as every sibling function."""
    with patch.object(musicbrainz, "_prefer_local", return_value=True), \
         patch.object(musicbrainz, "_allow_live", return_value=True), \
         patch("app.services.mb_local.count_release_groups", return_value=None), \
         patch.object(musicbrainz, "fetch_catalog") as fetch_catalog:
        fetch_catalog.return_value = musicbrainz.CatalogResult(release_groups=[1, 2, 3])
        result = musicbrainz.count_release_groups("mbid-123")
    assert result == 3
    fetch_catalog.assert_called_once()


def test_count_release_groups_uses_local_when_available():
    with patch.object(musicbrainz, "_prefer_local", return_value=True), \
         patch.object(musicbrainz, "_allow_live", return_value=True), \
         patch("app.services.mb_local.count_release_groups", return_value=7), \
         patch.object(musicbrainz, "fetch_catalog") as fetch_catalog:
        result = musicbrainz.count_release_groups("mbid-123")
    assert result == 7
    fetch_catalog.assert_not_called()


def test_count_release_groups_local_only_mode_returns_none_without_live():
    with patch.object(musicbrainz, "_prefer_local", return_value=True), \
         patch.object(musicbrainz, "_allow_live", return_value=False), \
         patch("app.services.mb_local.count_release_groups", return_value=None), \
         patch.object(musicbrainz, "fetch_catalog") as fetch_catalog:
        result = musicbrainz.count_release_groups("mbid-123")
    assert result is None
    fetch_catalog.assert_not_called()
