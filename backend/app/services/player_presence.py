"""In-memory now-playing presence for player listeners."""

from __future__ import annotations

import asyncio
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
    # Which track_id (if any) has already been scrobbled to Last.fm this play —
    # reset whenever the presence entry's track_id changes.
    scrobbled_track_id: int | None = None


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
        scrobbled = (
            existing.scrobbled_track_id
            if existing and existing.track_id == track_id
            else None
        )
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
            scrobbled_track_id=scrobbled,
        )
        _entries[user_id] = entry
        return entry


def get_entry(user_id: int) -> PresenceEntry | None:
    with _lock:
        return _entries.get(user_id)


def mark_scrobbled(user_id: int, track_id: int) -> None:
    with _lock:
        entry = _entries.get(user_id)
        if entry:
            entry.scrobbled_track_id = track_id


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


# ----- WebSocket fan-out (single-process; matches this app's single-worker
# deployment, so a plain in-memory registry is sufficient - no broker needed) -----

_ws_lock = threading.Lock()
_sockets: dict[int, set] = {}
_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Called once at app startup so sync request handlers (which run in a
    threadpool, off the event-loop thread) can schedule a broadcast safely."""
    global _main_loop
    _main_loop = loop


def register_socket(user_id: int, ws) -> None:
    with _ws_lock:
        _sockets.setdefault(user_id, set()).add(ws)


def unregister_socket(user_id: int, ws) -> None:
    with _ws_lock:
        sockets = _sockets.get(user_id)
        if sockets:
            sockets.discard(ws)
            if not sockets:
                del _sockets[user_id]


def _sockets_for(user_id: int, *, exclude=None) -> list:
    with _ws_lock:
        return [ws for ws in _sockets.get(user_id, set()) if ws is not exclude]


async def broadcast_presence(user_id: int, payload: dict, *, exclude=None) -> None:
    for ws in _sockets_for(user_id, exclude=exclude):
        try:
            await ws.send_json({"type": "presence", "data": payload})
        except Exception:  # noqa: BLE001
            unregister_socket(user_id, ws)


async def broadcast_stop(user_id: int) -> None:
    for ws in _sockets_for(user_id):
        try:
            await ws.send_json({"type": "stop"})
        except Exception:  # noqa: BLE001
            unregister_socket(user_id, ws)


def broadcast_presence_sync(user_id: int, payload: dict, *, exclude=None) -> None:
    """Fire-and-forget broadcast from a sync (threadpool) request handler."""
    if _main_loop is None or not _sockets.get(user_id):
        return
    asyncio.run_coroutine_threadsafe(
        broadcast_presence(user_id, payload, exclude=exclude), _main_loop
    )


def broadcast_stop_sync(user_id: int) -> None:
    if _main_loop is None or not _sockets.get(user_id):
        return
    asyncio.run_coroutine_threadsafe(broadcast_stop(user_id), _main_loop)
