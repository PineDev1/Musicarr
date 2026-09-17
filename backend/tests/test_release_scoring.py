from __future__ import annotations

from app.services.release_scoring import REJECT_CEILING, score_release


def test_flac_release_scores_above_reject_ceiling():
    score = score_release(
        "Some Artist - Some Album (2021) [FLAC]",
        size_bytes=400 * 1024 * 1024,
        seeders=20,
        protocol="torrent",
        artist="Some Artist",
        album="Some Album",
        year="2021",
    )
    assert score > REJECT_CEILING


def test_wrong_artist_or_album_is_rejected():
    score = score_release(
        "Totally Different Band - Unrelated Album [FLAC]",
        size_bytes=400 * 1024 * 1024,
        seeders=20,
        protocol="torrent",
        artist="Some Artist",
        album="Some Album",
    )
    assert score < REJECT_CEILING


def test_karaoke_and_tribute_releases_are_heavily_penalized():
    good = score_release(
        "Some Artist - Some Album [FLAC]",
        size_bytes=400 * 1024 * 1024,
        seeders=20,
        protocol="torrent",
        artist="Some Artist",
        album="Some Album",
    )
    karaoke = score_release(
        "Some Artist - Some Album (Karaoke Version) [MP3]",
        size_bytes=400 * 1024 * 1024,
        seeders=20,
        protocol="torrent",
        artist="Some Artist",
        album="Some Album",
    )
    assert karaoke < good
    assert karaoke < REJECT_CEILING


def test_lossy_release_still_scores_above_reject_ceiling_when_no_lossless_available():
    # Not every legit release is FLAC — a well-seeded, correctly named 320kbps
    # MP3 release must still be usable, just ranked below a lossless one.
    mp3 = score_release(
        "Some Artist - Some Album (2021) [320kbps]",
        size_bytes=120 * 1024 * 1024,
        seeders=15,
        protocol="torrent",
        artist="Some Artist",
        album="Some Album",
        year="2021",
    )
    flac = score_release(
        "Some Artist - Some Album (2021) [FLAC]",
        size_bytes=400 * 1024 * 1024,
        seeders=15,
        protocol="torrent",
        artist="Some Artist",
        album="Some Album",
        year="2021",
    )
    assert mp3 > REJECT_CEILING
    assert mp3 < flac


def test_zero_seeder_torrent_is_penalized_but_usenet_is_not():
    torrent_dead = score_release(
        "Some Artist - Some Album [FLAC]",
        size_bytes=400 * 1024 * 1024,
        seeders=0,
        protocol="torrent",
        artist="Some Artist",
        album="Some Album",
    )
    torrent_alive = score_release(
        "Some Artist - Some Album [FLAC]",
        size_bytes=400 * 1024 * 1024,
        seeders=10,
        protocol="torrent",
        artist="Some Artist",
        album="Some Album",
    )
    usenet = score_release(
        "Some Artist - Some Album [FLAC]",
        size_bytes=400 * 1024 * 1024,
        seeders=0,
        protocol="usenet",
        artist="Some Artist",
        album="Some Album",
    )
    assert torrent_dead < torrent_alive
    assert usenet > REJECT_CEILING


def test_suspiciously_tiny_file_is_penalized():
    tiny = score_release(
        "Some Artist - Some Album [FLAC]",
        size_bytes=2 * 1024 * 1024,
        seeders=20,
        protocol="torrent",
        artist="Some Artist",
        album="Some Album",
    )
    normal = score_release(
        "Some Artist - Some Album [FLAC]",
        size_bytes=400 * 1024 * 1024,
        seeders=20,
        protocol="torrent",
        artist="Some Artist",
        album="Some Album",
    )
    assert tiny < normal
