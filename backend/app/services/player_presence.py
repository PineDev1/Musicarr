"""In-memory now-playing presence for player listeners."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

TTL_SECONDS = 45.0


@dataclass
class PresenceEntry:
    user_id: int
    username: str
    display_name: str = ""
    track_id: int | None = None
    title: str | None = None
    artist_name: str | None = None
    cover_url: str | None = None
    playing: bool = False
    position: float = 0.0
    updated_at: float = field(default_factory=time.time)
    stop_requested: bool = False


_lock = threading.Lock()
_entries: dict[int, PresenceEntry] = {}


def heartbeat(
    *,
    user_id: int,
    username: str,
    display_name: str,
    track_id: int | None,
    title: str | None,
    artist_name: str | None,
    cover_url: str | None,
    playing: bool,
    position: float,
) -> PresenceEntry:
    with _lock:
        existing = _entries.get(user_id)
        stop = existing.stop_requested if existing else False
        entry = PresenceEntry(
            user_id=user_id,
            username=username,
            display_name=display_name or username,
            track_id=track_id,
            title=title,
            artist_name=artist_name,
            cover_url=cover_url,
            playing=playing,
            position=position,
            updated_at=time.time(),
            stop_requested=stop,
        )
        _entries[user_id] = entry
        return entry


def list_active() -> list[PresenceEntry]:
    now = time.time()
    with _lock:
        dead = [uid for uid, e in _entries.items() if now - e.updated_at > TTL_SECONDS]
        for uid in dead:
            del _entries[uid]
        return sorted(_entries.values(), key=lambda e: e.updated_at, reverse=True)


def request_stop(user_id: int) -> bool:
    with _lock:
        entry = _entries.get(user_id)
        if not entry:
            # Create a stub so the client still picks up the command on next poll
            _entries[user_id] = PresenceEntry(
                user_id=user_id,
                username="",
                stop_requested=True,
                updated_at=time.time(),
            )
            return True
        entry.stop_requested = True
        entry.playing = False
        entry.updated_at = time.time()
        return True


def pop_stop(user_id: int) -> bool:
    with _lock:
        entry = _entries.get(user_id)
        if not entry or not entry.stop_requested:
            return False
        entry.stop_requested = False
        entry.playing = False
        entry.track_id = None
        entry.title = None
        entry.artist_name = None
        entry.cover_url = None
        entry.position = 0
        entry.updated_at = time.time()
        return True
