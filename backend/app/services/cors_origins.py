from __future__ import annotations

from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.services.proxy import public_domain

# Local admin UI + Vite dev (credentials require an explicit allowlist, never *).
LOCAL_CORS_ORIGINS = frozenset(
    {
        "http://127.0.0.1:8787",
        "http://localhost:8787",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://0.0.0.0:8787",
        "http://0.0.0.0:5173",
    }
)


def cors_origins_for_settings(db: Session | None = None) -> list[str]:
    origins = set(LOCAL_CORS_ORIGINS)
    if db is not None:
        host = (public_domain(db) or "").strip().lower()
        if host:
            origins.add(f"https://{host}")
            origins.add(f"http://{host}")
    return sorted(origins)


def origin_is_allowed(origin: str | None, db: Session | None = None) -> bool:
    if not origin:
        return False
    origin = origin.strip()
    if origin in LOCAL_CORS_ORIGINS:
        return True
    if db is None:
        return False
    try:
        host = (urlparse(origin).hostname or "").strip().lower()
    except Exception:  # noqa: BLE001
        return False
    domain = (public_domain(db) or "").strip().lower()
    return bool(host and domain and host == domain)
