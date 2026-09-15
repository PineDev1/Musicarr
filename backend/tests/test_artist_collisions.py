from __future__ import annotations

from app.services.artists import collision_groups, merge_artists
from tests.conftest import _artist


def test_collision_groups_flags_same_name_different_artists(db):
    _artist(db, name="Luke Combs", provider="deezer", provider_id="d1")
    _artist(db, name="Luke Combs", provider="qobuz", provider_id="q1")

    groups = collision_groups(db)
    assert len(groups) == 1
    assert len(groups[0]) == 2


def test_collision_groups_excludes_already_merged_pair(db):
    """A merged pair must not keep showing up as an unresolved duplicate."""
    a = _artist(db, name="Luke Combs", provider="deezer", provider_id="d2")
    b = _artist(db, name="Luke Combs", provider="qobuz", provider_id="q2")

    assert len(collision_groups(db)) == 1

    merge_artists(db, [a.id, b.id])

    assert collision_groups(db) == []


def test_collision_groups_still_flags_unmerged_third_artist(db):
    a = _artist(db, name="Luke Combs", provider="deezer", provider_id="d3")
    b = _artist(db, name="Luke Combs", provider="qobuz", provider_id="q3")
    _artist(db, name="Luke Combs", provider="tidal", provider_id="t3")

    merge_artists(db, [a.id, b.id])

    groups = collision_groups(db)
    assert len(groups) == 1
    assert len(groups[0]) == 3
