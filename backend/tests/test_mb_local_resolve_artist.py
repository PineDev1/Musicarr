from __future__ import annotations

import sqlite3

import pytest

from app.services import mb_local
from app.services.mb_catalog_import import build_fixture_catalog


@pytest.fixture()
def fixture_catalog(tmp_path):
    db_path = tmp_path / "catalog.sqlite"
    build_fixture_catalog(db_path)
    mb_local.configure(db_path)
    yield db_path
    mb_local.configure(None)


def test_resolve_artist_prefers_the_duplicate_with_real_release_groups(fixture_catalog):
    """Regression: the fixture deliberately has two 'Ed Sheeran' artist rows
    (a real one credited on a release group, and a same-named stub with
    none) — resolve_artist must reliably pick the real one, not whichever
    row SQLite's UNION happened to return first."""
    for _ in range(20):  # SQLite's arbitrary ordering could vary run to run
        gid = mb_local.resolve_artist("Ed Sheeran")
        assert gid == "b8a7c51f-362c-4dcb-a259-bc6e0095f0a6"


def test_resolve_artist_exact_match_with_no_duplicates_still_works(fixture_catalog):
    assert mb_local.resolve_artist("Luke Combs") == "c20ee61f-071f-4e65-9c81-45ee931a54ce"


def test_resolve_artist_returns_none_for_unknown_name(fixture_catalog):
    assert mb_local.resolve_artist("Totally Unknown Artist Name Xyz") is None


def test_resolve_artist_picks_real_artist_even_when_stub_gid_sorts_first(tmp_path):
    """A bare `UNION ... LIMIT 1` dedups via an implicit sort over the
    selected columns (here, gid), so it effectively returns whichever GID is
    alphabetically first — nothing to do with which row is the "real"
    artist. Build a case where the near-empty stub's GID sorts before the
    real artist's GID, so a regression back to that query would provably
    return the wrong one."""
    db_path = tmp_path / "adversarial.sqlite"
    con = sqlite3.connect(str(db_path))
    con.executescript(
        """
        CREATE TABLE artist (id INTEGER PRIMARY KEY, gid TEXT NOT NULL, name TEXT NOT NULL);
        CREATE TABLE artist_alias (artist_id INTEGER NOT NULL, name TEXT NOT NULL);
        CREATE TABLE artist_rg (artist_id INTEGER NOT NULL, release_group_id INTEGER NOT NULL);
        """
    )
    # Stub's gid ("aaaa...") sorts alphabetically before the real artist's
    # gid ("zzzz...") — the old buggy query would return the stub.
    con.execute("INSERT INTO artist(id, gid, name) VALUES (1, 'aaaaaaaa-0000-0000-0000-000000000000', 'Some Band')")
    con.execute("INSERT INTO artist(id, gid, name) VALUES (2, 'zzzzzzzz-0000-0000-0000-000000000000', 'Some Band')")
    con.execute("INSERT INTO artist_rg(artist_id, release_group_id) VALUES (2, 100)")
    con.commit()
    con.close()

    mb_local.configure(db_path)
    try:
        gid = mb_local.resolve_artist("Some Band")
    finally:
        mb_local.configure(None)
    assert gid == "zzzzzzzz-0000-0000-0000-000000000000"
