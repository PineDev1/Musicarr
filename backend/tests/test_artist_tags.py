from __future__ import annotations

from app.api import artists as artists_api
from app.models.schemas import ArtistPatch
from app.services.artists import clean_tags, parse_tags
from tests.conftest import _artist


def test_clean_tags_trims_dedupes_case_insensitively_and_caps():
    assert clean_tags(["  Road  Trip ", "road trip", "", "Study"]) == ["Road Trip", "Study"]
    assert len(clean_tags([f"t{i}" for i in range(50)])) == 20
    assert len(clean_tags(["x" * 100])[0]) == 32


def test_parse_tags_tolerates_garbage():
    assert parse_tags(None) == [] and parse_tags("nope") == [] and parse_tags('{"a":1}') == []
    assert parse_tags('["a", 3, "b"]') == ["a", "b"]


def test_patch_sets_tags_on_linked_group_and_out_exposes_them(db):
    a = _artist(db, name="Twin", provider="deezer", provider_id="1", link_group_id="g")
    b = _artist(db, name="Twin", provider="qobuz", provider_id="2", link_group_id="g")
    out = artists_api.patch_artist(a.id, ArtistPatch(tags=["Chill", "chill", "Gym"]), db)
    db.refresh(b)
    assert out.tags == ["Chill", "Gym"]
    assert parse_tags(b.tags_json) == ["Chill", "Gym"]
    out2 = artists_api.patch_artist(a.id, ArtistPatch(tags=[]), db)
    assert out2.tags == []
