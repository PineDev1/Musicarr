from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Album, Artist, Track

EXAMPLE_LIMIT = 50
# A short album can legitimately have one bad/missing track; below this expected
# count we don't call it "incomplete" (mirrors the importer's own >=3 rule).
MIN_EXPECTED_FOR_INCOMPLETE = 3


def _has_file():
    return (Track.path.is_not(None)) & (Track.path != "")


def scan(db: Session) -> dict:
    """Read-only report of library problems worth a human look. Every finding
    carries the ids the UI needs to link straight to the artist/album."""
    files_per_album = dict(
        db.execute(select(Track.album_id, func.count(Track.id)).where(_has_file()).group_by(Track.album_id)).all()
    )
    tracks_per_album = dict(
        db.execute(select(Track.album_id, func.count(Track.id)).group_by(Track.album_id)).all()
    )
    downloaded = db.execute(
        select(Album.id, Album.title, Album.artist_id, Album.track_count, Album.cover_url, Artist.name)
        .join(Artist, Artist.id == Album.artist_id)
        .where(Album.status == "downloaded")
        .order_by(func.lower(Artist.name), Album.title)
    ).all()

    incomplete, ghost, no_cover = [], [], []
    for album_id, title, artist_id, track_count, cover, artist_name in downloaded:
        have = files_per_album.get(album_id, 0)
        expected = max(int(track_count or 0), tracks_per_album.get(album_id, 0))
        base = {
            "album_id": album_id,
            "artist_id": artist_id,
            "title": title,
            "artist_name": artist_name,
        }
        if have == 0:
            ghost.append({**base, "detail": "Marked downloaded but no track has a file"})
        elif expected >= MIN_EXPECTED_FOR_INCOMPLETE and have < expected:
            incomplete.append({**base, "detail": f"{have} of {expected} tracks on disk"})
        if have > 0 and not (cover or "").strip():
            no_cover.append({**base, "detail": "No cover art"})

    no_genre_rows = db.execute(
        select(Album.id, Album.title, Album.artist_id, Artist.name, func.count(Track.id))
        .join(Track, Track.album_id == Album.id)
        .join(Artist, Artist.id == Album.artist_id)
        .where(_has_file(), (Track.genre.is_(None)) | (Track.genre == ""))
        .group_by(Album.id)
        .order_by(func.lower(Artist.name), Album.title)
    ).all()
    no_genre = [
        {
            "album_id": aid,
            "artist_id": art_id,
            "title": title,
            "artist_name": artist_name,
            "detail": f"{n} track(s) without a genre",
        }
        for aid, title, art_id, artist_name, n in no_genre_rows
    ]

    unlinked_rows = db.execute(
        select(Artist.id, Artist.name)
        .where(
            Artist.status == "active",
            (Artist.musicbrainz_id.is_(None)) | (Artist.musicbrainz_id == ""),
        )
        .order_by(func.lower(Artist.name))
    ).all()
    no_mbid = [
        {"artist_id": aid, "artist_name": name, "detail": "Not linked to MusicBrainz"}
        for aid, name in unlinked_rows
    ]

    def section(key: str, label: str, hint: str, items: list[dict]) -> dict:
        return {
            "key": key,
            "label": label,
            "hint": hint,
            "count": len(items),
            "items": items[:EXAMPLE_LIMIT],
        }

    sections = [
        section(
            "ghost_albums",
            "Downloaded albums with no files",
            "These show as downloaded but nothing is on disk. Re-download them or reset their status.",
            ghost,
        ),
        section(
            "incomplete_albums",
            "Incomplete albums",
            "Fewer tracks on disk than the album should have.",
            incomplete,
        ),
        section("no_cover", "Albums without cover art", "Players will show a blank cover.", no_cover),
        section(
            "no_genre",
            "Albums with untagged tracks",
            "Tracks without a genre don't appear in genre browsing or genre-based smart playlists.",
            no_genre,
        ),
        section(
            "no_mbid",
            "Artists not linked to MusicBrainz",
            "Without a MusicBrainz link, release tracking and collab credits are limited.",
            no_mbid,
        ),
    ]
    return {"total_issues": sum(s["count"] for s in sections), "sections": sections}
