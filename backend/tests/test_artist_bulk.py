from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api import artists as artists_api
from app.models import Artist, HistoryEvent
from app.models.schemas import BulkArtistActionRequest
from app.services.artists import parse_tags
from tests.conftest import _artist


def _run(db, ids, action, value=None):
    return artists_api.bulk_artist_action(BulkArtistActionRequest(artist_ids=ids, action=action, value=value), db)


def test_unmonitor_and_monitor_hit_every_linked_row_once(db):
    a = _artist(db, name="Twin", provider="deezer", provider_id="1", link_group_id="g")
    b = _artist(db, name="Twin", provider="qobuz", provider_id="2", link_group_id="g")
    c = _artist(db, name="Solo", provider="deezer", provider_id="3")
    out = _run(db, [a.id, b.id, c.id], "unmonitor")
    assert out == {"affected": 2, "requested": 3}  # twin rows count as one logical artist
    for row in db.query(Artist).all():
        assert row.monitored is False and row.monitor_mode == "none"
    _run(db, [a.id], "monitor")
    db.refresh(a)
    db.refresh(b)
    assert a.monitored and b.monitored and a.monitor_mode == "all"


def test_quality_autograb_and_inherit_reset(db):
    a = _artist(db, name="A", provider="deezer", provider_id="1")
    _run(db, [a.id], "set_quality", "flac")
    _run(db, [a.id], "set_auto_grab", "on")
    db.refresh(a)
    assert a.quality_pref == "flac" and a.auto_grab_override == "on"
    _run(db, [a.id], "set_quality", "")
    _run(db, [a.id], "set_auto_grab", None)
    db.refresh(a)
    assert a.quality_pref is None and a.auto_grab_override is None


def test_tags_add_dedupe_case_insensitively_and_remove(db):
    a = _artist(db, name="A", provider="deezer", provider_id="1")
    b = _artist(db, name="B", provider="deezer", provider_id="2")
    _run(db, [a.id, b.id], "add_tag", "Road Trip")
    _run(db, [a.id], "add_tag", "road  trip")
    db.refresh(a)
    db.refresh(b)
    assert parse_tags(a.tags_json) == ["Road Trip"] and parse_tags(b.tags_json) == ["Road Trip"]
    _run(db, [a.id, b.id], "remove_tag", "ROAD TRIP")
    db.refresh(a)
    assert parse_tags(a.tags_json) == []


@pytest.mark.parametrize(
    "action,value",
    [("nonsense", None), ("set_quality", "wav"), ("set_auto_grab", "maybe"), ("add_tag", "  ")],
)
def test_invalid_requests_are_400s_and_change_nothing(db, action, value):
    a = _artist(db, name="A", provider="deezer", provider_id="1")
    with pytest.raises(HTTPException) as e:
        _run(db, [a.id], action, value)
    assert e.value.status_code == 400
    db.refresh(a)
    assert a.quality_pref is None and parse_tags(a.tags_json) == []


def test_empty_selection_is_rejected(db):
    with pytest.raises(HTTPException) as e:
        _run(db, [], "unmonitor")
    assert e.value.status_code == 400


def test_delete_removes_group_and_is_audited(db):
    a = _artist(db, name="Gone", provider="deezer", provider_id="1", link_group_id="g")
    b = _artist(db, name="Gone", provider="qobuz", provider_id="2", link_group_id="g")
    keep = _artist(db, name="Keep", provider="deezer", provider_id="3")
    _run(db, [a.id], "delete")
    assert [r.name for r in db.query(Artist).all()] == ["Keep"]
    assert any("Gone" in e.message for e in db.query(HistoryEvent).filter_by(event_type="audit"))
    assert keep.id
