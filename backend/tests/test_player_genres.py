from __future__ import annotations

from app.models import Album, Track
from app.services.player_genres import genre_counts, mood_counts, tracks_for_genre, tracks_for_mood
from tests.conftest import _artist


def _track(db, album, *, provider_id, genre, downloaded=True) -> Track:
    t = Track(
        provider=album.provider,
        provider_id=provider_id,
        album_id=album.id,
        title=f"Song {provider_id}",
        genre=genre,
        path=f"/library/{provider_id}.flac" if downloaded else None,
    )
    db.add(t)
    db.commit()
    return t


def _seed(db):
    artist = _artist(db, name="Luke Combs", provider="qobuz", provider_id="a1")
    album = Album(provider="qobuz", provider_id="al1", artist_id=artist.id, title="Album")
    db.add(album)
    db.commit()
    return album


def test_genre_counts_only_includes_downloaded_tracks_with_a_genre(db):
    album = _seed(db)
    _track(db, album, provider_id="t0", genre="Country")
    _track(db, album, provider_id="t1", genre="Country")
    _track(db, album, provider_id="t2", genre="")
    _track(db, album, provider_id="t3", genre="Rock", downloaded=False)

    counts = genre_counts(db)

    assert counts == [{"genre": "Country", "track_count": 2}]


def test_tracks_for_genre_is_case_insensitive(db):
    album = _seed(db)
    t0 = _track(db, album, provider_id="t0", genre="Country")

    tracks = tracks_for_genre(db, "country")

    assert [t.id for t in tracks] == [t0.id]


def test_mood_counts_group_genres_by_keyword(db):
    album = _seed(db)
    _track(db, album, provider_id="t0", genre="Ambient")
    _track(db, album, provider_id="t1", genre="Heavy Metal")

    moods = {m["mood"]: m["track_count"] for m in mood_counts(db)}

    assert moods.get("Chill") == 1
    assert moods.get("Focus") == 1
    assert moods.get("Workout") == 1


def test_tracks_for_mood_matches_partial_genre_keyword(db):
    album = _seed(db)
    t0 = _track(db, album, provider_id="t0", genre="Heavy Metal")
    _track(db, album, provider_id="t1", genre="Country")

    tracks = tracks_for_mood(db, "Workout")

    assert [t.id for t in tracks] == [t0.id]


def test_tracks_for_mood_returns_empty_for_unknown_mood(db):
    _seed(db)
    assert tracks_for_mood(db, "Not A Real Mood") == []
