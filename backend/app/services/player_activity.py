"""Opt-in "what are other listeners playing" feed for the Player.

Reuses the existing in-memory presence tracker (player_presence — already
built for the admin now-playing monitor) for "listening right now", and
PlayerPlayEvent for "recently played", filtered to only the player accounts
that have explicitly opted into share_listening_activity. Off by default per
account — this is a materially different privacy posture than the
admin-only monitor it's built on top of.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Album, PlayerPlayEvent, PlayerUser, Track
from app.services import player_presence

RECENT_HOURS = 24
RECENT_LIMIT = 20


def _opted_in_user_ids(db: Session, exclude_user_id: int) -> set[int]:
    return set(
        db.scalars(
            select(PlayerUser.id).where(
                PlayerUser.share_listening_activity.is_(True),
                PlayerUser.id != exclude_user_id,
            )
        ).all()
    )


def now_playing_friends(db: Session, current_user_id: int) -> list[dict]:
    opted_in = _opted_in_user_ids(db, current_user_id)
    if not opted_in:
        return []
    users = {u.id: u for u in db.scalars(select(PlayerUser).where(PlayerUser.id.in_(opted_in)))}
    out: list[dict] = []
    for entry in player_presence.list_active():
        if entry.user_id not in opted_in or not entry.playing or not entry.track_id:
            continue
        user = users.get(entry.user_id)
        out.append(
            {
                "user_id": entry.user_id,
                "username": user.display_name if user and user.display_name else entry.username,
                "user": user,
                "track_id": entry.track_id,
                "title": entry.title,
                "artist_name": entry.artist_name,
                "cover_url": entry.cover_url,
            }
        )
    return out


def recent_friend_activity(
    db: Session,
    current_user_id: int,
    *,
    hours: int = RECENT_HOURS,
    limit: int = RECENT_LIMIT,
) -> list[dict]:
    opted_in = _opted_in_user_ids(db, current_user_id)
    if not opted_in:
        return []
    users = {u.id: u for u in db.scalars(select(PlayerUser).where(PlayerUser.id.in_(opted_in)))}
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    events = db.scalars(
        select(PlayerPlayEvent)
        .options(joinedload(PlayerPlayEvent.track).joinedload(Track.album).joinedload(Album.artist))
        .where(PlayerPlayEvent.user_id.in_(opted_in), PlayerPlayEvent.played_at >= cutoff)
        .order_by(PlayerPlayEvent.played_at.desc())
        .limit(limit * 3)
    ).unique().all()

    out: list[dict] = []
    seen: set[tuple[int, int]] = set()
    for ev in events:
        if not ev.track or not ev.track.path:
            continue
        key = (ev.user_id, ev.track_id)
        if key in seen:
            continue
        seen.add(key)
        user = users.get(ev.user_id)
        album = ev.track.album
        artist = album.artist if album else None
        out.append(
            {
                "user_id": ev.user_id,
                "username": user.display_name if user and user.display_name else (user.username if user else ""),
                "user": user,
                "track_id": ev.track.id,
                "title": ev.track.title,
                "artist_name": artist.name if artist else "",
                "cover_url": album.cover_url if album else None,
                "played_at": ev.played_at,
            }
        )
        if len(out) >= limit:
            break
    return out
