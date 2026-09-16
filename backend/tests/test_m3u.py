from __future__ import annotations

from app.models import Album, Artist, Track
from app.services.m3u import export_m3u, parse_and_match_m3u


def _album_with_track(db, *, artist_name, title, path):
    artist = Artist(provider="qobuz", provider_id=artist_name, name=artist_name, monitored=True)
    db.add(artist)
    db.commit()
    db.refresh(artist)
    album = Album(provider="qobuz", provider_id=title, artist_id=artist.id, title=title)
    db.add(album)
    db.commit()
    db.refresh(album)
    track = Track(
        provider="qobuz", provider_id=f"{title}-1", album_id=album.id, title=title,
        path=path, duration=200,
    )
    db.add(track)
    db.commit()
    db.refresh(track)
    return track


def test_export_format(db):
    t = _album_with_track(db, artist_name="Artist A", title="Song A", path="/music/a/song.flac")
    content = export_m3u([t])
    lines = content.splitlines()
    assert lines[0] == "#EXTM3U"
    assert lines[1] == "#EXTINF:200,Artist A - Song A"
    assert lines[2] == "/music/a/song.flac"


def test_import_matches_exact_path(db):
    t = _album_with_track(db, artist_name="Artist A", title="Song A", path="/music/a/song.flac")
    content = "#EXTM3U\n#EXTINF:200,Artist A - Song A\n/music/a/song.flac\n"
    matched = parse_and_match_m3u(db, content)
    assert [m.id for m in matched] == [t.id]


def test_import_matches_by_basename_when_path_differs(db):
    t = _album_with_track(db, artist_name="Artist A", title="Song A", path="/music/a/song.flac")
    content = "#EXTM3U\n#EXTINF:200,Artist A - Song A\nC:\\Other\\Place\\song.flac\n"
    matched = parse_and_match_m3u(db, content)
    assert [m.id for m in matched] == [t.id]


def test_import_matches_by_title_when_path_unresolvable(db):
    t = _album_with_track(db, artist_name="Artist A", title="Song A", path="/music/a/song.flac")
    content = "#EXTM3U\n#EXTINF:200,Artist A - Song A\n/totally/unknown/file.mp3\n"
    matched = parse_and_match_m3u(db, content)
    assert [m.id for m in matched] == [t.id]


def test_import_skips_unmatched_entries(db):
    content = "#EXTM3U\n#EXTINF:200,Nobody - Nothing\n/nowhere/file.mp3\n"
    matched = parse_and_match_m3u(db, content)
    assert matched == []
