from __future__ import annotations

import sqlite3

import pytest

from app.services import mb_local


@pytest.fixture()
def catalog(tmp_path):
    db_path = tmp_path / "catalog.sqlite"
    con = sqlite3.connect(str(db_path))
    con.executescript(
        """
        CREATE TABLE artist (id INTEGER PRIMARY KEY, gid TEXT NOT NULL, name TEXT NOT NULL);
        CREATE TABLE artist_credit (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE artist_credit_name (
          artist_credit INTEGER NOT NULL, position INTEGER NOT NULL,
          artist_id INTEGER NOT NULL, name TEXT NOT NULL, join_phrase TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE release_group (
          id INTEGER PRIMARY KEY, gid TEXT NOT NULL, name TEXT NOT NULL,
          artist_credit INTEGER NOT NULL, primary_type_id INTEGER
        );
        CREATE TABLE release_group_meta (id INTEGER PRIMARY KEY, first_release_year INTEGER);
        CREATE TABLE release_group_primary_type (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE release_group_secondary_type (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE release_group_secondary_type_join (
          release_group INTEGER NOT NULL, secondary_type INTEGER NOT NULL
        );
        CREATE TABLE artist_rg (artist_id INTEGER NOT NULL, release_group_id INTEGER NOT NULL);
        """
    )
    con.execute("INSERT INTO release_group_primary_type(id, name) VALUES (1, 'Album')")
    con.execute(
        "INSERT INTO artist(id, gid, name) VALUES (1, 'artist-mbid-1', 'Taylor Swift')"
    )
    con.execute("INSERT INTO artist_credit(id, name) VALUES (10, 'Taylor Swift')")
    con.execute(
        "INSERT INTO artist_credit_name(artist_credit, position, artist_id, name, join_phrase) "
        "VALUES (10, 0, 1, 'Taylor Swift', '')"
    )
    # Two different real release groups by the same artist: the studio album
    # the query is looking for, and an unrelated tour release that happens
    # to share a title prefix with it.
    con.execute(
        "INSERT INTO release_group(id, gid, name, artist_credit, primary_type_id) "
        "VALUES (200, 'rg-tour', 'Reputation Stadium Tour', 10, 1)"
    )
    con.execute("INSERT INTO release_group_meta(id, first_release_year) VALUES (200, 2018)")
    con.execute("INSERT INTO artist_rg(artist_id, release_group_id) VALUES (1, 200)")
    con.commit()
    con.close()
    mb_local.configure(db_path)
    yield db_path
    mb_local.configure(None)


def test_does_not_match_a_different_release_by_substring_containment(catalog):
    """Regression: searching for 'Reputation' must not match 'Reputation
    Stadium Tour' just because one title contains the other — same bug
    class as the library.py album matcher fix."""
    result = mb_local.search_release_group_for_artist("Reputation", "artist-mbid-1")
    assert result is None


def test_minor_punctuation_variance_still_matches(catalog):
    # A search string that's a substring of the stored title (missing one
    # trailing char) still has to pass the SQL LIKE pre-filter, so it must
    # itself literally appear inside the stored name.
    result = mb_local.search_release_group_for_artist(
        "Reputation Stadium Tou", "artist-mbid-1"
    )
    assert result is not None
    assert result.mbid == "rg-tour"


def test_exact_title_still_matches(catalog):
    result = mb_local.search_release_group_for_artist("Reputation Stadium Tour", "artist-mbid-1")
    assert result is not None
    assert result.mbid == "rg-tour"
