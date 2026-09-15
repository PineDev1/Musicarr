from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from app.services.artists import (
    delete_artist,
    find_linked_artists,
    list_artists_grouped,
)
from app.services.download_queue import pick_unique_artist_search_hit
from app.services.library import _find_artist_by_name
from app.services.naming import artist_folder_name, build_album_folder
from tests.conftest import _artist


def test_same_name_artists_are_separate_groups(db):
    a = _artist(db, name="John Smith", provider="deezer", provider_id="111")
    b = _artist(db, name="John Smith", provider="deezer", provider_id="222")
    groups = list_artists_grouped(db)
    assert len(groups) == 2
    ids = {g[0].id for g in groups}
    assert ids == {a.id, b.id}
    linked_a = find_linked_artists(db, a)
    assert len(linked_a) == 1
    assert linked_a[0].id == a.id


def test_link_group_merges_explicitly(db):
    a = _artist(db, name="Adele", provider="deezer", provider_id="1", link_group_id="g1")
    b = _artist(db, name="Adele", provider="tidal", provider_id="9", link_group_id="g1")
    _artist(db, name="Adele", provider="local", provider_id="other")
    groups = list_artists_grouped(db)
    assert len(groups) == 2
    linked = find_linked_artists(db, a)
    assert {x.id for x in linked} == {a.id, b.id}


def test_delete_one_same_name_leaves_other(db):
    a = _artist(db, name="Prince", provider="deezer", provider_id="1")
    b = _artist(db, name="Prince", provider="deezer", provider_id="2")
    assert delete_artist(db, a.id) is True
    remaining = list_artists_grouped(db)
    assert len(remaining) == 1
    assert remaining[0][0].id == b.id


def test_folder_disambiguates_on_collision(db, tmp_path):
    a = _artist(db, name="Nova", provider="deezer", provider_id="10")
    _artist(db, name="Nova", provider="tidal", provider_id="20")
    plain = artist_folder_name(a, collide=False)
    assert plain == "Nova"
    disambig = artist_folder_name(a, collide=True)
    assert disambig == "Nova [deezer-10]"
    auto = artist_folder_name(a, db=db)
    assert auto == "Nova [deezer-10]"
    folder = build_album_folder(
        tmp_path,
        "{artist}/{album} ({year})",
        artist=auto,
        album="Debut",
        year="2020",
    )
    assert "Nova [deezer-10]" in str(folder)


def test_find_artist_by_name_ambiguous(db):
    _artist(db, name="Sam", provider="deezer", provider_id="1")
    _artist(db, name="Sam", provider="deezer", provider_id="2")
    assert _find_artist_by_name(db, "Sam") is None
    only = _artist(db, name="Unique Name", provider="deezer", provider_id="3")
    assert _find_artist_by_name(db, "Unique Name").id == only.id


def test_pick_unique_artist_search_hit():
    hits = [
        SimpleNamespace(name="John Smith", provider_id="1"),
        SimpleNamespace(name="John Smith", provider_id="2"),
        SimpleNamespace(name="John Smith Band", provider_id="3"),
    ]
    assert pick_unique_artist_search_hit("John Smith", hits) is None
    assert pick_unique_artist_search_hit("John Smith Band", hits).provider_id == "3"
    assert pick_unique_artist_search_hit("Nobody", hits) is None


def test_find_artist_by_name_folds_diacritics_and_article(db):
    beyonce = _artist(db, name="Beyoncé", provider="deezer", provider_id="1")
    assert _find_artist_by_name(db, "Beyonce").id == beyonce.id

    beatles = _artist(db, name="Beatles", provider="deezer", provider_id="2")
    assert _find_artist_by_name(db, "The Beatles").id == beatles.id


def test_pick_unique_artist_search_hit_folds_diacritics_and_article():
    hits = [SimpleNamespace(name="Beyoncé", provider_id="1")]
    assert pick_unique_artist_search_hit("Beyonce", hits).provider_id == "1"

    hits2 = [SimpleNamespace(name="Beatles", provider_id="2")]
    assert pick_unique_artist_search_hit("The Beatles", hits2).provider_id == "2"
