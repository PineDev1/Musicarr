from __future__ import annotations

import random
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Album, Artist, PlayerFavorite, PlayerPlayEvent, Track

MIX_COUNT = 3
TRACKS_PER_MIX = 30
SIMILAR_ARTIST_LIMIT = 10


def _downloaded_tracks_for_artists(db: Session, artist_ids: list[int]) -> list[Track]:
    if not artist_ids:
        return []
    return list(
        db.scalars(
            select(Track)
            .join(Album, Track.album_id == Album.id)
            .where(
                Album.artist_id.in_(artist_ids),
                Track.path.is_not(None),
                Track.path != "",
            )
        )
        .unique()
        .all()
    )


def _top_played_artist_ids(db: Session, user_id: int, limit: int) -> list[int]:
    rows = db.execute(
        select(Album.artist_id, func.count(PlayerPlayEvent.id))
        .select_from(PlayerPlayEvent)
        .join(Track, Track.id == PlayerPlayEvent.track_id)
        .join(Album, Album.id == Track.album_id)
        .where(PlayerPlayEvent.user_id == user_id)
        .group_by(Album.artist_id)
        .order_by(func.count(PlayerPlayEvent.id).desc())
        .limit(limit)
    ).all()
    return [r[0] for r in rows]


def _favorited_artist_ids(db: Session, user_id: int, limit: int) -> list[int]:
    return list(
        db.scalars(
            select(Album.artist_id)
            .join(Track, Track.album_id == Album.id)
            .join(PlayerFavorite, PlayerFavorite.track_id == Track.id)
            .where(PlayerFavorite.user_id == user_id)
            .distinct()
            .limit(limit)
        ).all()
    )


def made_for_you_mixes(
    db: Session,
    user_id: int,
    *,
    mix_count: int = MIX_COUNT,
    tracks_per_mix: int = TRACKS_PER_MIX,
) -> list[tuple[Artist, list[Track]]]:
    """A few named mixes, each seeded from an artist the user actually
    listens to (or has favorited, with no listen history yet) and filled out
    with that artist's own downloaded tracks plus downloaded tracks from its
    Last.fm-similar artists — same "only ever plays what's already in the
    library" constraint as artist radio.

    Shuffled with a per-day/user/artist seed so a mix stays stable across
    repeated page loads within a day instead of reshuffling on every fetch,
    then changes again tomorrow — the "daily mix" feel, without a background
    job or any new storage.
    """
    from app.services import lastfm
    from app.services.artists import find_artist_by_normalized_name

    seed_artist_ids = _top_played_artist_ids(db, user_id, mix_count)
    if not seed_artist_ids:
        seed_artist_ids = _favorited_artist_ids(db, user_id, mix_count)

    today_key = date.today().isoformat()
    mixes: list[tuple[Artist, list[Track]]] = []
    for artist_id in seed_artist_ids:
        artist = db.get(Artist, artist_id)
        if not artist:
            continue
        pool_artist_ids = {artist_id}
        try:
            hits = lastfm.similar_artists(db, artist.name, limit=SIMILAR_ARTIST_LIMIT)
        except lastfm.LastfmError:
            hits = []
        for hit in hits:
            found = find_artist_by_normalized_name(db, hit["name"], artist.provider)
            if found:
                pool_artist_ids.add(found.id)

        tracks = _downloaded_tracks_for_artists(db, list(pool_artist_ids))
        if not tracks:
            continue
        rng = random.Random(f"{today_key}:{user_id}:{artist_id}")
        rng.shuffle(tracks)
        mixes.append((artist, tracks[:tracks_per_mix]))

    return mixes
