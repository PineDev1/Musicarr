from __future__ import annotations

from app.models import Album, Track
from app.services import library_health
from tests.conftest import _artist


def _album(db, artist, title, *, status="downloaded", track_count=0, cover="https://c/x"):
    a = Album(
        artist_id=artist.id, provider="deezer", provider_id=f"al-{title}", title=title,
        status=status, track_count=track_count, cover_url=cover,
    )
    db.add(a)
    db.commit()
    return a


def _track(db, album, n, *, path="set", genre="Country"):
    t = Track(
        provider="deezer", provider_id=f"{album.id}-{n}", album_id=album.id, title=f"T{n}",
        track_no=n, path=(f"/m/{album.id}/{n}.flac" if path == "set" else path), genre=genre,
    )
    db.add(t)
    db.commit()
    return t


def _section(report, key):
    return next(s for s in report["sections"] if s["key"] == key)


def test_healthy_library_reports_nothing(db):
    artist = _artist(db, name="Fine", provider="deezer", provider_id="1", musicbrainz_id="mb-1")
    al = _album(db, artist, "Good", track_count=3)
    for n in (1, 2, 3):
        _track(db, al, n)
    report = library_health.scan(db)
    assert report["total_issues"] == 0


def test_ghost_incomplete_cover_genre_and_unlinked_are_found(db):
    artist = _artist(db, name="Messy", provider="deezer", provider_id="1")  # no MBID
    ghost = _album(db, artist, "Ghost", track_count=4)
    _track(db, ghost, 1, path=None)
    partial = _album(db, artist, "Partial", track_count=5, cover="")
    _track(db, partial, 1)
    _track(db, partial, 2, genre="")

    report = library_health.scan(db)
    assert [i["title"] for i in _section(report, "ghost_albums")["items"]] == ["Ghost"]
    inc = _section(report, "incomplete_albums")["items"]
    assert [i["title"] for i in inc] == ["Partial"] and inc[0]["detail"] == "2 of 5 tracks on disk"
    assert [i["title"] for i in _section(report, "no_cover")["items"]] == ["Partial"]
    genre = _section(report, "no_genre")["items"]
    assert genre[0]["title"] == "Partial" and "1 track" in genre[0]["detail"]
    assert [i["artist_name"] for i in _section(report, "no_mbid")["items"]] == ["Messy"]
    assert report["total_issues"] == 1 + 1 + 1 + 1 + 1


def test_short_albums_and_wanted_albums_are_not_flagged(db):
    artist = _artist(db, name="A", provider="deezer", provider_id="1", musicbrainz_id="mb")
    single = _album(db, artist, "Single", track_count=2)
    _track(db, single, 1)  # 1 of 2 — below the >=3 threshold, not "incomplete"
    _album(db, artist, "Wanted", status="wanted", track_count=10)  # never downloaded: not a problem
    report = library_health.scan(db)
    assert _section(report, "incomplete_albums")["count"] == 0
    assert _section(report, "ghost_albums")["count"] == 0


def test_examples_are_capped_but_count_is_exact(db):
    artist = _artist(db, name="Many", provider="deezer", provider_id="1", musicbrainz_id="mb")
    for i in range(library_health.EXAMPLE_LIMIT + 7):
        al = _album(db, artist, f"G{i:03d}", track_count=3)
        _track(db, al, 1, path=None)
    ghost = _section(library_health.scan(db), "ghost_albums")
    assert ghost["count"] == library_health.EXAMPLE_LIMIT + 7
    assert len(ghost["items"]) == library_health.EXAMPLE_LIMIT
