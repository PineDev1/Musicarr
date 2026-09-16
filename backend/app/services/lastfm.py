from __future__ import annotations

import hashlib
import logging
import time

import requests
from sqlalchemy.orm import Session

from app.models import PlayerUser
from app.services.settings_service import ensure_settings

logger = logging.getLogger(__name__)

API_BASE = "https://ws.audioscrobbler.com/2.0/"
AUTH_BASE = "https://www.last.fm/api/auth/"


class LastfmError(Exception):
    pass


def _credentials(db: Session) -> tuple[str, str]:
    settings = ensure_settings(db)
    key = (getattr(settings, "lastfm_api_key", "") or "").strip()
    secret = (getattr(settings, "lastfm_api_secret", "") or "").strip()
    if not key or not secret:
        raise LastfmError("Last.fm API key/secret not configured in Settings")
    return key, secret


def _sign(params: dict[str, str], secret: str) -> str:
    ordered = sorted(params.items())
    raw = "".join(f"{k}{v}" for k, v in ordered) + secret
    return hashlib.md5(raw.encode("utf-8")).hexdigest()  # noqa: S324 (Last.fm's own scheme)


def auth_url(db: Session) -> str:
    key, secret = _credentials(db)
    resp = requests.get(
        API_BASE,
        params={"method": "auth.getToken", "api_key": key, "format": "json"},
        timeout=15,
    )
    resp.raise_for_status()
    token = resp.json().get("token")
    if not token:
        raise LastfmError("Last.fm did not return an auth token")
    return f"{AUTH_BASE}?api_key={key}&token={token}"


def complete_auth(db: Session, user: PlayerUser, token: str) -> None:
    key, secret = _credentials(db)
    params = {"method": "auth.getSession", "api_key": key, "token": token}
    params["api_sig"] = _sign(params, secret)
    params["format"] = "json"
    resp = requests.get(API_BASE, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    session = data.get("session") or {}
    key_val = session.get("key")
    if not key_val:
        raise LastfmError(data.get("message") or "Last.fm session exchange failed")
    user.lastfm_session_key = key_val
    user.lastfm_username = session.get("name")


def _call(db: Session, user: PlayerUser, method: str, extra: dict[str, str]) -> None:
    if not getattr(user, "lastfm_session_key", None):
        return
    try:
        key, secret = _credentials(db)
    except LastfmError:
        return
    params = {"method": method, "api_key": key, "sk": user.lastfm_session_key, **extra}
    params["api_sig"] = _sign(params, secret)
    params["format"] = "json"
    try:
        resp = requests.post(API_BASE, data=params, timeout=15)
        if resp.status_code >= 400:
            logger.warning("Last.fm %s failed: %s", method, resp.text[:200])
    except requests.RequestException as exc:
        logger.warning("Last.fm %s request error: %s", method, exc)


def update_now_playing(db: Session, user: PlayerUser, artist: str, track: str) -> None:
    if not artist or not track:
        return
    _call(db, user, "track.updateNowPlaying", {"artist": artist, "track": track})


def scrobble(db: Session, user: PlayerUser, artist: str, track: str, started_at: int | None = None) -> None:
    if not artist or not track:
        return
    _call(
        db,
        user,
        "track.scrobble",
        {"artist": artist, "track": track, "timestamp": str(started_at or int(time.time()))},
    )


def similar_artists(db: Session, artist_name: str, *, limit: int = 10) -> list[dict]:
    """artist.getSimilar is unauthenticated — only needs the shared api_key,
    no per-user session, so this works for any admin whether or not they've
    personally connected a Last.fm account for scrobbling."""
    if not artist_name:
        return []
    key, _secret = _credentials(db)
    resp = requests.get(
        API_BASE,
        params={
            "method": "artist.getSimilar",
            "artist": artist_name,
            "api_key": key,
            "format": "json",
            "limit": limit,
        },
        timeout=15,
    )
    if resp.status_code >= 400:
        raise LastfmError(f"Last.fm similar-artist lookup failed: {resp.text[:200]}")
    data = resp.json()
    artists = ((data.get("similarartists") or {}).get("artist")) or []
    return [
        {"name": a.get("name"), "match": float(a.get("match") or 0)}
        for a in artists
        if a.get("name")
    ]
