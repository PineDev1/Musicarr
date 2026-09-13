from __future__ import annotations

import re

LOSSLESS_TOKENS = ("flac", "lossless", "alac", "ape", "wavpack", "dsd")
HI_RES_TOKENS = ("24bit", "24 bit", "hi res", "hires", "96khz", "192khz")
LOSSY_TOKENS = ("mp3", "aac", "m4a", "ogg", "opus", "vorbis")
LOSSY_BITRATE = re.compile(r"\b(\d{2,3})\s?kbps\b")

# Different recordings of the album — never what the user asked for.
WRONG_RECORDING_TOKENS = (
    "karaoke",
    "tribute",
    "instrumental",
    "cover version",
    "covers of",
    "acapella",
    "a cappella",
    "sample pack",
    "dj mix",
    "mixtape",
    "in the style of",
)
# Right recording, awkward packaging — demote but still usable.
PACKAGING_TOKENS = (
    "discography",
    "anthology",
    "box set",
    "boxset",
    "vinyl rip",
    "vinylrip",
    "web rip",
    "complete collection",
)

# Below this, pick_best() refuses to grab. Gated releases stay in 0-9 so a
# human browsing the manual search still sees them ranked.
REJECT_CEILING = 9.0
ARTIST_MIN_RATIO = 0.7
ALBUM_MIN_RATIO = 0.4


def _norm(text: str | None) -> str:
    value = (text or "").lower()
    value = re.sub(r"[\._\-\[\]\(\)\{\}/\\,:;!?'\"+]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _tokens(text: str) -> set[str]:
    return {t for t in _norm(text).split(" ") if len(t) > 2}


def _match_ratio(query: str, name: str) -> float:
    """How much of `query` shows up in the normalised release name."""
    normalized = _norm(query)
    if not normalized:
        return 1.0
    if normalized in name:
        return 1.0
    wanted = _tokens(query)
    if not wanted:
        # Short or symbol-only names (e.g. "10", "+") cannot be token matched.
        return 1.0
    return len(wanted & set(name.split(" "))) / len(wanted)


def score_release(
    title: str,
    size_bytes: int,
    seeders: int,
    protocol: str,
    artist: str,
    album: str,
    year: str | None = None,
) -> float:
    """Rank a release by how well it matches the album and how good it looks.

    Higher is better. Anything under 10 is considered unusable for automatic
    grabs, so releases that fail the artist/album match are capped below that.
    """
    name = _norm(title)
    if not name:
        return 0.0

    artist_ratio = _match_ratio(artist, name)
    album_ratio = _match_ratio(album, name)
    if artist_ratio < ARTIST_MIN_RATIO or album_ratio < ALBUM_MIN_RATIO:
        # Wrong release: keep the relative ordering but stay under the floor.
        return round(REJECT_CEILING * (artist_ratio + album_ratio) / 2, 2)

    score = 10.0 + 25.0 * artist_ratio + 30.0 * album_ratio

    year_digits = ""
    if year:
        m = re.match(r"(\d{4})", str(year))
        year_digits = m.group(1) if m else ""
    if year_digits:
        if year_digits in name:
            score += 8.0
        elif re.search(r"\b(19|20)\d{2}\b", name):
            # A different year in the title is a yellow flag for same-name artists
            score -= 6.0

    if any(token in name for token in LOSSLESS_TOKENS):
        score += 25.0
        if any(token in name for token in HI_RES_TOKENS):
            score += 5.0
    else:
        bitrate = LOSSY_BITRATE.search(name)
        if bitrate:
            kbps = int(bitrate.group(1))
            if kbps >= 320:
                score += 10.0
            elif kbps >= 256:
                score += 6.0
            elif kbps >= 192:
                score += 3.0
        elif any(token in name for token in LOSSY_TOKENS):
            score += 5.0

    if (protocol or "").lower() == "torrent":
        seeds = max(0, int(seeders or 0))
        if seeds <= 0:
            score -= 20.0
        else:
            # Diminishing returns: one seeder beats none, ~25 is plenty.
            score += min(20.0, 4.0 * (seeds ** 0.5))
    else:
        # Usenet has no seeders, so availability is neutral.
        score += 8.0

    size_mb = max(0, int(size_bytes or 0)) / (1024 * 1024)
    if size_mb == 0:
        score -= 2.0
    elif size_mb < 15:
        score -= 12.0
    elif size_mb > 4096:
        score -= 8.0

    album_n = _norm(album)
    for token in WRONG_RECORDING_TOKENS:
        if token in name and token not in album_n:
            score -= 70.0
            break
    for token in PACKAGING_TOKENS:
        if token in name and token not in album_n:
            score -= 25.0
            break

    return round(max(0.0, score), 2)
