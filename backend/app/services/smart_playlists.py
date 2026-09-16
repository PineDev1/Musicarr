from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import Album, PlayerFavorite, PlayerPlayEvent, PlayerPlaylist, Track


def parse_criteria(playlist: PlayerPlaylist) -> dict | None:
    raw = getattr(playlist, "criteria_json", None)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _format_from_path(path: str | None) -> str:
    if not path:
        return ""
    return path.rsplit(".", 1)[-1].lower() if "." in path else ""


def evaluate_smart_playlist(db: Session, playlist: PlayerPlaylist) -> list[Track]:
    """Compute a smart playlist's track list live from its criteria_json.

    Never touches PlayerPlaylistTrack — smart playlists with criteria are
    fully dynamic, so there's nothing to resync when filters or the library
    change.
    """
    criteria = parse_criteria(playlist)
    if not criteria:
        return []

    rules = criteria.get("rules") or []
    match_mode = (criteria.get("match") or "all").lower()
    sort = (criteria.get("sort") or "random").lower()
    limit = int(criteria.get("limit") or 50)
    user_id = playlist.user_id

    play_counts: dict[int, int] | None = None
    last_played: dict[int, datetime] | None = None
    favorite_ids: set[int] | None = None

    def _play_counts() -> dict[int, int]:
        nonlocal play_counts
        if play_counts is None:
            rows = db.execute(
                select(PlayerPlayEvent.track_id, func.count())
                .where(PlayerPlayEvent.user_id == user_id)
                .group_by(PlayerPlayEvent.track_id)
            ).all()
            play_counts = {tid: count for tid, count in rows}
        return play_counts

    def _last_played() -> dict[int, datetime]:
        nonlocal last_played
        if last_played is None:
            rows = db.execute(
                select(PlayerPlayEvent.track_id, func.max(PlayerPlayEvent.played_at))
                .where(PlayerPlayEvent.user_id == user_id)
                .group_by(PlayerPlayEvent.track_id)
            ).all()
            last_played = {tid: played_at for tid, played_at in rows}
        return last_played

    def _favorites() -> set[int]:
        nonlocal favorite_ids
        if favorite_ids is None:
            favorite_ids = set(
                db.scalars(
                    select(PlayerFavorite.track_id).where(
                        PlayerFavorite.user_id == user_id
                    )
                ).all()
            )
        return favorite_ids

    tracks = db.scalars(
        select(Track)
        .options(joinedload(Track.album).joinedload(Album.artist))
        .where(Track.path.is_not(None), Track.path != "")
    ).unique().all()

    def rule_match(track: Track, rule: dict) -> bool:
        field = rule.get("field")
        op = (rule.get("op") or "eq").lower()
        value = rule.get("value")

        if field == "favorited":
            actual: object = track.id in _favorites()
        elif field == "genre":
            actual = (track.genre or "").strip().lower()
            value = str(value or "").strip().lower()
        elif field == "format":
            actual = _format_from_path(track.path)
            value = str(value or "").strip().lower()
        elif field == "artist_id":
            actual = track.album.artist_id if track.album else None
        elif field == "album_id":
            actual = track.album_id
        elif field == "play_count":
            actual = _play_counts().get(track.id, 0)
        elif field == "last_played_days":
            played = _last_played().get(track.id)
            if played is None:
                actual = None
            else:
                if played.tzinfo is None:
                    played = played.replace(tzinfo=timezone.utc)
                actual = (datetime.now(timezone.utc) - played).days
        else:
            return False

        if op == "eq":
            return actual == value
        if op == "ne":
            return actual != value
        if op == "in":
            return actual in (value or [])
        if op == "not_in":
            return actual not in (value or [])
        if op == "gte":
            return actual is not None and value is not None and actual >= value
        if op == "lte":
            return actual is not None and value is not None and actual <= value
        if op == "gt":
            return actual is not None and value is not None and actual > value
        if op == "lt":
            return actual is not None and value is not None and actual < value
        return False

    matched: list[Track] = []
    for track in tracks:
        if not rules:
            matched.append(track)
            continue
        results = [rule_match(track, r) for r in rules]
        ok = all(results) if match_mode == "all" else any(results)
        if ok:
            matched.append(track)

    if sort == "random":
        random.shuffle(matched)
    elif sort == "recently_added":
        matched.sort(key=lambda t: t.id, reverse=True)
    elif sort == "most_played":
        counts = _play_counts()
        matched.sort(key=lambda t: counts.get(t.id, 0), reverse=True)
    elif sort == "title":
        matched.sort(key=lambda t: (t.title or "").lower())
    elif sort == "artist":
        matched.sort(key=lambda t: ((t.album.artist.name if t.album and t.album.artist else "").lower()))

    return matched[:limit]
