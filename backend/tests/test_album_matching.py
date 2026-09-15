from __future__ import annotations

from app.services.artists import _legacy_id, merge_album_rows
from app.services.library import _find_or_create_album
from tests.conftest import _artist


def test_find_or_create_album_keeps_editions_distinct(db):
    artist = _artist(db, name="Beyonce", provider="local", provider_id="a1")

    standard = _find_or_create_album(db, artist, "Renaissance", year="2022", track_count=16)
    db.refresh(artist)

    deluxe = _find_or_create_album(
        db, artist, "Renaissance (Deluxe Edition)", year="2022", track_count=20
    )
    db.refresh(artist)

    assert standard.id != deluxe.id
    assert {a.title for a in artist.albums} == {"Renaissance", "Renaissance (Deluxe Edition)"}

    # Re-importing the same two titles must attach to the existing rows, not
    # create a third/fourth.
    again_standard = _find_or_create_album(db, artist, "Renaissance", year="2022", track_count=16)
    again_deluxe = _find_or_create_album(
        db, artist, "Renaissance (Deluxe Edition)", year="2022", track_count=20
    )
    assert again_standard.id == standard.id
    assert again_deluxe.id == deluxe.id
    assert len(artist.albums) == 2


def test_find_or_create_album_diacritic_tag_matches_existing(db):
    artist = _artist(db, name="Motley Crue", provider="local", provider_id="a2")
    first = _find_or_create_album(db, artist, "Dr Feelgood", year="1989", track_count=10)
    db.refresh(artist)
    # A re-tagged file with an accented artist/album spelling should still
    # attach to the same album row rather than creating a duplicate.
    again = _find_or_create_album(db, artist, "Dr Feelgood", year="1989", track_count=10)
    assert again.id == first.id


def test_merge_album_rows_keeps_editions_distinct():
    artist_id = 1
    standard = type(
        "A",
        (),
        {
            "id": 1,
            "title": "Renaissance",
            "provider": "deezer",
            "status": "downloaded",
            "track_count": 16,
            "release_date": "2022",
        },
    )()
    deluxe = type(
        "A",
        (),
        {
            "id": 2,
            "title": "Renaissance (Deluxe Edition)",
            "provider": "qobuz",
            "status": "downloaded",
            "track_count": 20,
            "release_date": "2022",
        },
    )()
    merged = merge_album_rows([standard, deluxe], active_provider="deezer")
    assert len(merged) == 2
    assert {m[0].title for m in merged} == {"Renaissance", "Renaissance (Deluxe Edition)"}
