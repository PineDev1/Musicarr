from __future__ import annotations

import re
import threading
from typing import Any

from deezer import Deezer

from app.core.config import settings as app_config
from app.core.database import SessionLocal
from app.models import AppSettings


class DeezerError(Exception):
    pass


class DeezerSession:
    """Thread-safe Deezer ARL session wrapper."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._dz: Deezer | None = None
        self._arl: str = ""
        self._last_error: str | None = None

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def _load_arl_from_db(self) -> str:
        db = SessionLocal()
        try:
            row = db.get(AppSettings, 1)
            return (row.arl if row else "") or ""
        finally:
            db.close()

    def ensure(self, arl: str | None = None) -> Deezer:
        with self._lock:
            token = (arl if arl is not None else self._load_arl_from_db()).strip()
            if not token:
                self._last_error = "ARL not configured"
                raise DeezerError(self._last_error)
            if self._dz is not None and self._arl == token:
                return self._dz
            dz = Deezer()
            try:
                ok = dz.login_via_arl(token)
            except Exception as exc:  # noqa: BLE001
                self._dz = None
                self._arl = ""
                self._last_error = f"ARL login failed: {exc}"
                raise DeezerError(self._last_error) from exc
            if not ok:
                self._dz = None
                self._arl = ""
                self._last_error = "Invalid or expired ARL"
                raise DeezerError(self._last_error)
            self._dz = dz
            self._arl = token
            self._last_error = None
            return dz

    def invalidate(self) -> None:
        with self._lock:
            self._dz = None
            self._arl = ""

    def validate(self, arl: str | None = None) -> tuple[bool, str | None]:
        try:
            self.ensure(arl)
            return True, None
        except DeezerError as exc:
            return False, str(exc)

    def search_artists(self, query: str, limit: int = 25) -> list[dict[str, Any]]:
        dz = self.ensure()
        result = dz.api.search_artist(query, limit=limit)
        data = result.get("data", []) if isinstance(result, dict) else []
        out = []
        for item in data:
            out.append(
                {
                    "deezer_id": int(item["id"]),
                    "name": item.get("name", ""),
                    "image_url": item.get("picture_medium") or item.get("picture"),
                    "nb_album": item.get("nb_album"),
                }
            )
        return out

    def search_albums(self, query: str, limit: int = 25) -> list[dict[str, Any]]:
        dz = self.ensure()
        result = dz.api.search_album(query, limit=limit)
        data = result.get("data", []) if isinstance(result, dict) else []
        out = []
        for item in data:
            artist = item.get("artist") or {}
            out.append(
                {
                    "id": int(item["id"]),
                    "title": item.get("title") or "Unknown Album",
                    "artist_name": artist.get("name") or "",
                    "artist_id": int(artist["id"]) if artist.get("id") else None,
                    "cover_url": item.get("cover_medium") or item.get("cover"),
                    "nb_tracks": int(item.get("nb_tracks") or 0),
                    "release_date": item.get("release_date"),
                    "record_type": item.get("record_type"),
                }
            )
        return out

    def get_artist(self, deezer_id: int) -> dict[str, Any]:
        dz = self.ensure()
        return dz.api.get_artist(deezer_id)

    def get_artist_albums(self, deezer_id: int, limit: int = 500) -> list[dict[str, Any]]:
        dz = self.ensure()
        albums: list[dict[str, Any]] = []
        index = 0
        while True:
            page = dz.api.get_artist_albums(deezer_id, index=index, limit=min(100, limit))
            data = page.get("data", []) if isinstance(page, dict) else []
            if not data:
                break
            albums.extend(data)
            index += len(data)
            if len(data) < 100 or len(albums) >= limit:
                break
        return albums[:limit]

    def get_album(self, deezer_id: int) -> dict[str, Any]:
        dz = self.ensure()
        return dz.api.get_album(deezer_id)

    def get_album_tracks(self, deezer_id: int) -> list[dict[str, Any]]:
        album = self.get_album(deezer_id)
        tracks = album.get("tracks", {}).get("data", []) if isinstance(album, dict) else []
        return tracks

    @property
    def client(self) -> Deezer:
        return self.ensure()


deezer_session = DeezerSession()


def default_library_path() -> str:
    return str(app_config.music_dir.resolve())


def classify_album_type(album: dict[str, Any]) -> str:
    record_type = (album.get("record_type") or album.get("type") or "album").lower()
    title = (album.get("title") or "").lower()
    if record_type in {"ep"}:
        return "ep"
    if record_type in {"single"}:
        return "single"
    if record_type in {"compile", "compilation"} or "greatest hits" in title:
        return "compilation"
    nb = album.get("nb_tracks") or 0
    if nb and nb <= 3 and "ep" not in title:
        # Deezer sometimes mislabels; keep as album unless clear single
        pass
    return "album" if record_type in {"album", "album"} else record_type or "album"


_SAFE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(name: str, max_len: int = 180) -> str:
    cleaned = _SAFE_RE.sub("", name).strip().rstrip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        cleaned = "Unknown"
    return cleaned[:max_len]
