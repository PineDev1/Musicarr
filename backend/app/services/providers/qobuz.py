from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

import requests
from sqlalchemy.orm import Session

from app.services.providers.base import (
    DownloadResult,
    MusicProvider,
    ProviderAlbum,
    ProviderArtist,
    ProviderError,
    ProviderTrack,
)
from app.services.settings_service import ensure_settings

logger = logging.getLogger("musicarr.qobuz")

API_BASE = "https://www.qobuz.com/api.json/0.2"


class QobuzProvider:
    name = "qobuz"

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = ensure_settings(db)

    @property
    def app_id(self) -> str:
        return (self.settings.qobuz_app_id or "").strip()

    @property
    def app_secret(self) -> str:
        return (self.settings.qobuz_app_secret or "").strip()

    def _headers(self) -> dict:
        headers = {
            "X-App-Id": self.app_id,
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        if self.settings.qobuz_user_auth_token:
            headers["X-User-Auth-Token"] = self.settings.qobuz_user_auth_token
        return headers

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        params = dict(params or {})
        params.setdefault("app_id", self.app_id)
        if self.settings.qobuz_user_auth_token:
            params.setdefault("user_auth_token", self.settings.qobuz_user_auth_token)
        resp = requests.get(
            f"{API_BASE}/{endpoint}",
            params=params,
            headers=self._headers(),
            timeout=60,
        )
        if resp.status_code >= 400:
            raise ProviderError(f"Qobuz API error ({resp.status_code}): {resp.text[:200]}")
        data = resp.json()
        if isinstance(data, dict) and data.get("status") == "error":
            raise ProviderError(data.get("message") or "Qobuz API error")
        if isinstance(data, dict) and data.get("code") in {401, 402, 403}:
            raise ProviderError(data.get("message") or "Qobuz authentication failed")
        return data

    def login_with_token(
        self,
        *,
        token: str,
        user_id: str = "",
        app_id: str = "",
        app_secret: str = "",
    ) -> None:
        """QobuzDownloaderX-style login: paste token (+ optional user id / app creds)."""
        token = (token or "").strip().strip('"')
        if not token:
            token = (self.settings.qobuz_user_auth_token or "").strip()
        if not token:
            raise ProviderError("Qobuz token is required")
        if app_id.strip():
            self.settings.qobuz_app_id = app_id.strip()
        if app_secret.strip():
            self.settings.qobuz_app_secret = app_secret.strip()
        if not (self.settings.qobuz_app_id or "").strip():
            raise ProviderError("Qobuz app ID is required — set it in Settings before login")
        if not (self.settings.qobuz_app_secret or "").strip():
            raise ProviderError("Qobuz app secret is required — set it in Settings before login")
        self.settings.qobuz_user_auth_token = token
        if user_id.strip():
            self.settings.qobuz_user_id = user_id.strip()
        self.db.commit()
        ok, err = self.validate_session()
        if not ok:
            self.settings.qobuz_user_auth_token = ""
            self.db.commit()
            raise ProviderError(err or "Qobuz token rejected")

    def login(self, email: str, password: str) -> None:
        if not email or not password:
            raise ProviderError("Email and password required")
        params = {
            "email": email,
            "password": hashlib.md5(password.encode("utf-8")).hexdigest(),
            "app_id": self.app_id,
        }
        resp = requests.get(
            f"{API_BASE}/user/login",
            params=params,
            headers={"X-App-Id": self.app_id},
            timeout=60,
        )
        if resp.status_code >= 400:
            raise ProviderError(f"Qobuz login failed: {resp.text[:200]}")
        data = resp.json()
        token = data.get("user_auth_token")
        if not token:
            raise ProviderError("Qobuz login failed — no auth token returned")
        user = data.get("user") or {}
        self.settings.qobuz_email = email
        self.settings.qobuz_user_auth_token = token
        self.settings.qobuz_user_id = str(user.get("id") or "")
        self.db.commit()

    def validate_session(self) -> tuple[bool, str | None]:
        if not self.settings.qobuz_user_auth_token:
            return False, "Qobuz not logged in — paste token, user ID, app ID, and app secret"
        try:
            params = {}
            if self.settings.qobuz_user_id:
                params["user_id"] = self.settings.qobuz_user_id
            data = self._get("user/get", params)
            # Persist user id if missing
            user_id = str((data.get("id") if isinstance(data, dict) else "") or "")
            if user_id and not self.settings.qobuz_user_id:
                self.settings.qobuz_user_id = user_id
                self.db.commit()
            return True, None
        except ProviderError as exc:
            return False, str(exc)

    def logout(self) -> None:
        self.settings.qobuz_user_auth_token = ""
        self.settings.qobuz_user_id = ""
        self.settings.qobuz_email = ""
        self.db.commit()

    def search_artists(self, query: str, limit: int = 25) -> list[ProviderArtist]:
        data = self._get(
            "artist/search",
            {"query": query, "limit": limit},
        )
        items = (data.get("artists") or {}).get("items") or []
        out: list[ProviderArtist] = []
        for a in items:
            image = None
            pic = a.get("image") or {}
            if isinstance(pic, dict):
                image = pic.get("medium") or pic.get("small") or pic.get("large")
            out.append(
                ProviderArtist(
                    provider_id=str(a.get("id")),
                    name=a.get("name") or "Unknown",
                    image_url=image,
                    nb_album=a.get("albums_count"),
                )
            )
        return out

    def search_albums(self, query: str, limit: int = 25) -> list[ProviderAlbum]:
        data = self._get(
            "album/search",
            {"query": query, "limit": limit},
        )
        items = (data.get("albums") or {}).get("items") or []
        out: list[ProviderAlbum] = []
        for alb in items:
            release = alb.get("release_date_original") or alb.get("released_at")
            if isinstance(release, int):
                release = time.strftime("%Y-%m-%d", time.gmtime(release))
            cover = None
            img = alb.get("image") or {}
            if isinstance(img, dict):
                cover = img.get("large") or img.get("small")
            qtype = (alb.get("product_type") or "album").lower()
            album_type = "album"
            if "ep" in qtype:
                album_type = "ep"
            elif "single" in qtype:
                album_type = "single"
            elif "compil" in qtype:
                album_type = "compilation"
            out.append(
                ProviderAlbum(
                    provider_id=str(alb.get("id")),
                    title=alb.get("title") or "Unknown Album",
                    album_type=album_type,
                    release_date=str(release) if release else None,
                    cover_url=cover,
                    track_count=int(alb.get("tracks_count") or 0),
                )
            )
        return out

    def get_artist(self, provider_id: str) -> ProviderArtist:
        a = self._get("artist/get", {"artist_id": provider_id})
        image = None
        pic = a.get("image") or {}
        if isinstance(pic, dict):
            image = pic.get("medium") or pic.get("small")
        return ProviderArtist(
            provider_id=str(a.get("id") or provider_id),
            name=a.get("name") or f"Artist {provider_id}",
            image_url=image,
            nb_album=a.get("albums_count"),
        )

    def list_albums(self, artist_id: str) -> list[ProviderAlbum]:
        data = self._get(
            "artist/get",
            {"artist_id": artist_id, "extra": "albums", "limit": 200},
        )
        items = (data.get("albums") or {}).get("items") or []
        out: list[ProviderAlbum] = []
        for alb in items:
            release = alb.get("release_date_original") or alb.get("released_at")
            if isinstance(release, int):
                release = time.strftime("%Y-%m-%d", time.gmtime(release))
            cover = None
            img = alb.get("image") or {}
            if isinstance(img, dict):
                cover = img.get("large") or img.get("small")
            qtype = (alb.get("product_type") or "album").lower()
            album_type = "album"
            if "ep" in qtype:
                album_type = "ep"
            elif "single" in qtype:
                album_type = "single"
            elif "compil" in qtype:
                album_type = "compilation"
            out.append(
                ProviderAlbum(
                    provider_id=str(alb.get("id")),
                    title=alb.get("title") or "Unknown Album",
                    album_type=album_type,
                    release_date=str(release) if release else None,
                    cover_url=cover,
                    track_count=int(alb.get("tracks_count") or 0),
                )
            )
        return out

    def list_tracks(self, album_id: str) -> list[ProviderTrack]:
        # Do not pass extra=tracks — current Qobuz API rejects it.
        # Tracks are included on a plain album/get response.
        data = self._get("album/get", {"album_id": album_id})
        items = (data.get("tracks") or {}).get("items") or []
        out: list[ProviderTrack] = []
        for t in items:
            out.append(
                ProviderTrack(
                    provider_id=str(t.get("id")),
                    title=t.get("title") or "Unknown Track",
                    track_no=int(t.get("track_number") or 0),
                    disc_no=int(t.get("media_number") or 1),
                    duration=int(t.get("duration") or 0),
                    isrc=t.get("isrc"),
                )
            )
        return out

    def _format_id(self, bitrate: str) -> int:
        # 5=MP3 320, 6=FLAC 16/44.1, 7=FLAC 24/96, 27=FLAC 24/192
        if bitrate == "320":
            return 5
        if bitrate == "128":
            return 5
        return 6

    def _file_url(self, track_id: str, bitrate: str) -> str:
        if not self.app_secret:
            raise ProviderError("Qobuz app secret required for downloads.")
        fmt = self._format_id(bitrate)
        # Prefer integer timestamp (QobuzDownloaderX-style); fall back across qualities.
        formats = [fmt]
        for candidate in (6, 5, 7, 27):
            if candidate not in formats:
                formats.append(candidate)
        last_err: Exception | None = None
        for format_id in formats:
            ts = int(time.time())
            sig_raw = (
                f"trackgetFileUrlformat_id{format_id}intentstreamtrack_id{track_id}"
                f"{ts}{self.app_secret}"
            )
            sig = hashlib.md5(sig_raw.encode("utf-8")).hexdigest()
            try:
                data = self._get(
                    "track/getFileUrl",
                    {
                        "track_id": track_id,
                        "format_id": format_id,
                        "intent": "stream",
                        "request_ts": ts,
                        "request_sig": sig,
                    },
                )
            except ProviderError as exc:
                last_err = exc
                continue
            url = data.get("url")
            if url:
                return url
            last_err = ProviderError(f"No download URL for track {track_id}")
        raise ProviderError(str(last_err) if last_err else f"No download URL for track {track_id}")

    def download_album(
        self,
        album_id: str,
        staging_dir: Path,
        bitrate: str,
        on_progress=None,
        is_cancelled=None,
    ) -> DownloadResult:
        tracks = self.list_tracks(album_id)
        files: list[Path] = []
        total = max(1, len(tracks))
        for idx, track in enumerate(tracks):
            if is_cancelled and is_cancelled():
                raise ProviderError("cancelled")
            url = self._file_url(track.provider_id, bitrate)
            ext = ".mp3" if bitrate in {"320", "128"} else ".flac"
            safe = track.title.replace("/", "-")
            dest = staging_dir / f"{track.track_no or idx + 1:02d} - {safe}{ext}"
            with requests.get(url, stream=True, timeout=120) as resp:
                resp.raise_for_status()
                with open(dest, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            fh.write(chunk)
            files.append(dest)
            if on_progress:
                on_progress((idx + 1) / total * 100)
        cover = None
        try:
            alb = self._get("album/get", {"album_id": album_id})
            img = (alb.get("image") or {}).get("large")
            if img:
                cover = staging_dir / "cover.jpg"
                r = requests.get(img, timeout=60)
                r.raise_for_status()
                cover.write_bytes(r.content)
        except Exception:  # noqa: BLE001
            cover = None
        return DownloadResult(files=files, cover=cover)


def get_qobuz_provider(db: Session) -> MusicProvider:
    return QobuzProvider(db)
