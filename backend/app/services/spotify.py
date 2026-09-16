from __future__ import annotations

import re
import time

import requests
from sqlalchemy.orm import Session

from app.services.settings_service import ensure_settings

TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"

_token_cache: dict[str, tuple[str, float]] = {}


class SpotifyError(Exception):
    pass


def _credentials(db: Session) -> tuple[str, str]:
    settings = ensure_settings(db)
    client_id = (getattr(settings, "spotify_client_id", "") or "").strip()
    client_secret = (getattr(settings, "spotify_client_secret", "") or "").strip()
    if not client_id or not client_secret:
        raise SpotifyError("Spotify client ID/secret not configured in Settings")
    return client_id, client_secret


def _get_token(db: Session) -> str:
    client_id, client_secret = _credentials(db)
    cached = _token_cache.get(client_id)
    if cached and cached[1] > time.time() + 30:
        return cached[0]
    resp = requests.post(
        TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        timeout=15,
    )
    if resp.status_code >= 400:
        raise SpotifyError(f"Spotify auth failed: {resp.text[:200]}")
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise SpotifyError("Spotify did not return an access token")
    expires_in = int(data.get("expires_in") or 3600)
    _token_cache[client_id] = (token, time.time() + expires_in)
    return token


def extract_playlist_id(url_or_id: str) -> str | None:
    value = (url_or_id or "").strip()
    if not value:
        return None
    match = re.search(r"playlist[/:]([A-Za-z0-9]+)", value)
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9]{16,}", value):
        return value
    return None


def playlist_artist_names(db: Session, playlist_id: str, *, limit: int = 200) -> list[str]:
    """Unique artist names across every track in a public playlist, in
    playlist order. Paginates the tracks endpoint (100 per page)."""
    token = _get_token(db)
    headers = {"Authorization": f"Bearer {token}"}
    names: list[str] = []
    seen: set[str] = set()
    url = f"{API_BASE}/playlists/{playlist_id}/tracks"
    params: dict[str, object] = {"limit": 100, "fields": "items(track(artists(name))),next"}
    while url and len(names) < limit:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code >= 400:
            raise SpotifyError(f"Spotify playlist lookup failed: {resp.text[:200]}")
        data = resp.json()
        for item in data.get("items", []):
            track = item.get("track") or {}
            for artist in track.get("artists") or []:
                name = (artist.get("name") or "").strip()
                key = name.lower()
                if name and key not in seen:
                    seen.add(key)
                    names.append(name)
        url = data.get("next")
        params = None  # "next" already carries its own query string
    return names[:limit]
