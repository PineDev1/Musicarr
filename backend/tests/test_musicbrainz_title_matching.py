"""Regression tests: match_release/match_provider_album must not treat a
short album title as a match for a longer, differently-scoped release
(e.g. "Reputation" vs "Reputation Stadium Tour") just because one contains
the other. mb_local.py's search_release_group_for_artist already had this
guard (see test_mb_local_search_release_group.py); match_release and
match_provider_album (used in live/local catalog matching) did not.
"""
from types import SimpleNamespace

from app.services.musicbrainz import ReleaseGroup, match_provider_album, match_release


def test_match_release_does_not_confuse_short_and_long_titles():
    catalog = [
        ReleaseGroup(
            mbid="tour", title="Reputation Stadium Tour", primary_type="album", year="2018"
        ),
    ]
    assert match_release("Reputation", "2017", "album", catalog) is None


def test_match_release_still_matches_minor_punctuation_variance():
    catalog = [
        ReleaseGroup(
            mbid="tour", title="Reputation Stadium Tour", primary_type="album", year="2018"
        ),
    ]
    # Missing trailing char — small delta, should still resolve via containment.
    best = match_release("Reputation Stadium Tou", "2018", "album", catalog)
    assert best is not None
    assert best.mbid == "tour"


def test_match_provider_album_does_not_confuse_short_and_long_titles():
    rg = ReleaseGroup(mbid="short", title="Reputation", primary_type="album", year="2017")
    albums = [
        SimpleNamespace(title="Reputation Stadium Tour", release_date="2018"),
    ]
    assert match_provider_album(rg, albums) is None
