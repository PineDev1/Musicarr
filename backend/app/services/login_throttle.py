"""In-memory brute-force throttle for the login endpoints.

Failures are counted per client IP and per username inside a sliding window;
once either bucket is full the caller gets a 429 until old failures age out.
The state is per-process and resets on restart, which is fine for the goal
(making online password / TOTP guessing impractical), not durable auditing.
"""

from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import HTTPException, Request

WINDOW_SECONDS = 600
MAX_PER_USERNAME = 8
MAX_PER_IP = 25
MAX_TRACKED_KEYS = 10_000

_lock = threading.Lock()
_failures: dict[str, deque[float]] = {}


def client_ip(request: Request | None) -> str:
    """Left-most X-Forwarded-For when behind a reverse proxy, else the socket
    peer. XFF is spoofable, but spoofing it only evades the per-IP bucket —
    the per-username bucket still applies."""
    if request is None:
        return "unknown"
    xff = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if xff:
        return xff[:64]
    return request.client.host if request.client else "unknown"


def _keys(scope: str, ip: str, username: str) -> list[tuple[str, int]]:
    keys = [(f"{scope}:ip:{ip}", MAX_PER_IP)]
    name = (username or "").strip().lower()[:64]
    if name:
        keys.append((f"{scope}:user:{name}", MAX_PER_USERNAME))
    return keys


def _prune(q: deque[float], now: float) -> None:
    while q and now - q[0] > WINDOW_SECONDS:
        q.popleft()


def retry_after(scope: str, ip: str, username: str) -> int:
    """Seconds until another attempt is allowed (0 when not throttled)."""
    now = time.time()
    wait = 0
    with _lock:
        for key, limit in _keys(scope, ip, username):
            q = _failures.get(key)
            if not q:
                continue
            _prune(q, now)
            if len(q) >= limit:
                wait = max(wait, int(WINDOW_SECONDS - (now - q[0])) + 1)
    return wait


def record_failure(scope: str, ip: str, username: str) -> None:
    now = time.time()
    with _lock:
        if len(_failures) > MAX_TRACKED_KEYS:
            for key in [k for k, q in _failures.items() if not q or now - q[-1] > WINDOW_SECONDS]:
                _failures.pop(key, None)
            if len(_failures) > MAX_TRACKED_KEYS:
                _failures.clear()  # under a flood, fail open on memory rather than grow
        for key, _limit in _keys(scope, ip, username):
            q = _failures.setdefault(key, deque())
            _prune(q, now)
            q.append(now)


def record_success(scope: str, ip: str, username: str) -> None:
    with _lock:
        for key, _limit in _keys(scope, ip, username):
            if key.startswith(f"{scope}:user:"):
                _failures.pop(key, None)


def enforce(scope: str, request: Request | None, username: str) -> None:
    wait = retry_after(scope, client_ip(request), username)
    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {wait // 60 + 1} minute(s).",
            headers={"Retry-After": str(wait)},
        )


def reset() -> None:
    with _lock:
        _failures.clear()
