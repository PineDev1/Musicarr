from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from sqlalchemy.orm import Session

from app.services.settings_service import ensure_settings

logger = logging.getLogger("musicarr.media")


def _request(url: str, *, method: str = "POST", headers: dict | None = None, body: bytes | None = None) -> None:
    req = urllib.request.Request(
        url,
        data=body,
        headers={"User-Agent": "Musicarr/1.2", **(headers or {})},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        resp.read()


def trigger_media_refresh(db: Session, reason: str = "download") -> None:
    """Notify Plex / Jellyfin / Navidrome / generic webhook to rescan."""
    settings = ensure_settings(db)
    url = (getattr(settings, "media_refresh_url", None) or "").strip()
    if not url:
        return
    kind = (getattr(settings, "media_refresh_type", None) or "webhook").lower()
    token = (getattr(settings, "media_refresh_token", None) or "").strip()
    try:
        if kind == "plex":
            # Expect full refresh URL or base; append token if needed
            sep = "&" if "?" in url else "?"
            full = url if "X-Plex-Token" in url else f"{url}{sep}X-Plex-Token={urllib.parse.quote(token)}"
            _request(full, method="GET")
        elif kind == "jellyfin":
            headers = {"Content-Type": "application/json"}
            if token:
                headers["X-Emby-Token"] = token
                headers["Authorization"] = f"MediaBrowser Token=\"{token}\""
            # Jellyfin library refresh: POST /Library/Refresh
            refresh_url = url.rstrip("/")
            if not refresh_url.lower().endswith("/refresh"):
                refresh_url = f"{refresh_url}/Library/Refresh"
            _request(refresh_url, method="POST", headers=headers, body=b"{}")
        elif kind == "navidrome":
            # Generic: POST JSON to configured URL (often a startscan wrapper)
            payload = json.dumps({"event": "library_refresh", "reason": reason}).encode()
            headers = {"Content-Type": "application/json"}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            _request(url, method="POST", headers=headers, body=payload)
        else:
            payload = json.dumps(
                {"event": "library_refresh", "reason": reason, "source": "musicarr"}
            ).encode()
            headers = {"Content-Type": "application/json"}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            _request(url, method="POST", headers=headers, body=payload)
        logger.info("Media refresh triggered (%s): %s", kind, reason)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("Media refresh failed: %s", exc)
