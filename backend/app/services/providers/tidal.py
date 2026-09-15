from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path

import requests
import tidalapi
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

logger = logging.getLogger("musicarr.tidal")

# In-memory device login state
_device_lock = threading.Lock()
_device_login = None
_device_session: tidalapi.Session | None = None


class TidalProvider:
    name = "tidal"

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = ensure_settings(db)
        self._session: tidalapi.Session | None = None

    def _quality(self, bitrate: str):
        if bitrate == "flac":
            return tidalapi.Quality.hi_res_lossless
        if bitrate == "320":
            return tidalapi.Quality.low_320k
        return tidalapi.Quality.low_96k

    def _load_session(self) -> tidalapi.Session:
        if self._session and self._session.check_login():
            return self._session
        session = tidalapi.Session()
        token = self.settings.tidal_access_token
        refresh = self.settings.tidal_refresh_token
        if not token:
            raise ProviderError("Tidal not logged in")
        expiry = None
        if self.settings.tidal_expiry:
            try:
                expiry = datetime.fromisoformat(self.settings.tidal_expiry)
            except ValueError:
                expiry = None
        ok = session.load_oauth_session(
            self.settings.tidal_token_type or "Bearer",
            token,
            refresh,
            expiry,
        )
        if not ok and refresh:
            # try refresh path via login persistence
            try:
                session.token_refresh(refresh)
                ok = session.check_login()
            except Exception as exc:  # noqa: BLE001
                raise ProviderError(f"Tidal session expired: {exc}") from exc
        if not ok:
            raise ProviderError("Tidal session invalid — please log in again")
        if self.settings.tidal_country_code:
            session.country_code = self.settings.tidal_country_code
        self._session = session
        self._persist_session(session)
        return session

    def _persist_session(self, session: tidalapi.Session) -> None:
        self.settings.tidal_access_token = session.access_token or ""
        self.settings.tidal_refresh_token = session.refresh_token or ""
        self.settings.tidal_token_type = session.token_type or "Bearer"
        self.settings.tidal_expiry = (
            session.expiry_time.isoformat() if session.expiry_time else ""
        )
        self.settings.tidal_country_code = session.country_code or ""
        self.db.commit()

    def validate_session(self) -> tuple[bool, str | None]:
        if not self.settings.tidal_access_token:
            return False, "Tidal not logged in"
        try:
            self._load_session()
            return True, None
        except ProviderError as exc:
            return False, str(exc)

    def logout(self) -> None:
        self.settings.tidal_access_token = ""
        self.settings.tidal_refresh_token = ""
        self.settings.tidal_expiry = ""
        self.settings.tidal_country_code = ""
        self.db.commit()
        self._session = None

    def search_artists(self, query: str, limit: int = 25) -> list[ProviderArtist]:
        session = self._load_session()
        results = session.search(query, models=[tidalapi.artist.Artist], limit=limit)
        artists = results.get("artists") or results.get(tidalapi.artist.Artist) or []
        if isinstance(results, dict):
            artists = results.get("artists", artists)
        out: list[ProviderArtist] = []
        for a in artists[:limit]:
            image = None
            try:
                image = a.image(320) if hasattr(a, "image") else None
            except Exception:  # noqa: BLE001
                image = getattr(a, "picture", None)
            out.append(
                ProviderArtist(
                    provider_id=str(a.id),
                    name=a.name,
                    image_url=image,
                    nb_album=None,
                )
            )
        return out

    def search_albums(self, query: str, limit: int = 25) -> list[ProviderAlbum]:
        session = self._load_session()
        results = session.search(query, models=[tidalapi.album.Album], limit=limit)
        albums = []
        if isinstance(results, dict):
            albums = results.get("albums") or results.get(tidalapi.album.Album) or []
        out: list[ProviderAlbum] = []
        for alb in list(albums)[:limit]:
            album_type = "album"
            try:
                atype = str(getattr(alb, "type", "") or "").lower()
                if "ep" in atype:
                    album_type = "ep"
                elif "single" in atype:
                    album_type = "single"
                elif "compil" in atype:
                    album_type = "compilation"
            except Exception:  # noqa: BLE001
                pass
            release = None
            if getattr(alb, "release_date", None):
                release = alb.release_date.isoformat()[:10]
            cover = None
            try:
                cover = alb.image(320)
            except Exception:  # noqa: BLE001
                pass
            out.append(
                ProviderAlbum(
                    provider_id=str(alb.id),
                    title=getattr(alb, "name", None) or "Unknown Album",
                    album_type=album_type,
                    release_date=release,
                    cover_url=cover,
                    track_count=int(getattr(alb, "num_tracks", 0) or 0),
                )
            )
        return out

    def get_artist(self, provider_id: str) -> ProviderArtist:
        session = self._load_session()
        a = session.artist(int(provider_id))
        image = None
        try:
            image = a.image(320)
        except Exception:  # noqa: BLE001
            pass
        return ProviderArtist(provider_id=str(a.id), name=a.name, image_url=image)

    def list_albums(self, artist_id: str) -> list[ProviderAlbum]:
        session = self._load_session()
        artist = session.artist(int(artist_id))
        albums = artist.get_albums(limit=500)
        out: list[ProviderAlbum] = []
        for alb in albums:
            album_type = "album"
            try:
                atype = str(getattr(alb, "type", "") or "").lower()
                if "ep" in atype:
                    album_type = "ep"
                elif "single" in atype:
                    album_type = "single"
                elif "compil" in atype:
                    album_type = "compilation"
            except Exception:  # noqa: BLE001
                pass
            release = None
            if getattr(alb, "release_date", None):
                release = alb.release_date.isoformat()[:10]
            cover = None
            try:
                cover = alb.image(320)
            except Exception:  # noqa: BLE001
                pass
            out.append(
                ProviderAlbum(
                    provider_id=str(alb.id),
                    title=alb.name,
                    album_type=album_type,
                    release_date=release,
                    cover_url=cover,
                    track_count=int(getattr(alb, "num_tracks", 0) or 0),
                )
            )
        return out

    def list_tracks(self, album_id: str) -> list[ProviderTrack]:
        session = self._load_session()
        album = session.album(int(album_id))
        tracks = album.tracks()
        out: list[ProviderTrack] = []
        for t in tracks:
            out.append(
                ProviderTrack(
                    provider_id=str(t.id),
                    title=t.name,
                    track_no=int(getattr(t, "track_num", 0) or 0),
                    disc_no=int(getattr(t, "volume_num", 1) or 1),
                    duration=int(getattr(t, "duration", 0) or 0),
                    isrc=getattr(t, "isrc", None),
                )
            )
        return out

    def download_album(
        self,
        album_id: str,
        staging_dir: Path,
        bitrate: str,
        on_progress=None,
        is_cancelled=None,
    ) -> DownloadResult:
        session = self._load_session()
        try:
            session.audio_quality = self._quality(bitrate)
        except Exception:  # noqa: BLE001
            pass
        album = session.album(int(album_id))
        tracks = album.tracks()
        files: list[Path] = []
        total = max(1, len(tracks))
        for idx, track in enumerate(tracks):
            if is_cancelled and is_cancelled():
                raise ProviderError("cancelled")
            stream = track.get_stream_url() if hasattr(track, "get_stream_url") else None
            if stream is None and hasattr(track, "get_url"):
                stream = track.get_url()
            if not stream:
                # newer tidalapi
                try:
                    manifest = track.get_stream()
                    stream = getattr(manifest, "url", None) or manifest
                except Exception as exc:  # noqa: BLE001
                    raise ProviderError(f"No stream for track {track.id}: {exc}") from exc
            if isinstance(stream, dict):
                stream = stream.get("url") or stream.get("urls", [None])[0]
            ext = ".flac" if (bitrate or "flac") == "flac" else ".m4a"
            dest = staging_dir / f"{idx + 1:02d} - {track.name}{ext}".replace("/", "-")
            with requests.get(stream, stream=True, timeout=120) as resp:
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
            cover_url = album.image(1280)
            if cover_url:
                cover = staging_dir / "cover.jpg"
                r = requests.get(cover_url, timeout=60)
                r.raise_for_status()
                cover.write_bytes(r.content)
        except Exception:  # noqa: BLE001
            cover = None
        return DownloadResult(files=files, cover=cover)


def start_tidal_device_login(db: Session) -> dict:
    global _device_login, _device_session
    session = tidalapi.Session()
    try:
        login, future = session.login_oauth()
    except Exception as exc:  # noqa: BLE001
        raise ProviderError(f"Tidal device login failed: {exc}") from exc
    login._musicarr_future = future  # type: ignore[attr-defined]
    with _device_lock:
        _device_login = login
        _device_session = session
    uri = login.verification_uri
    if uri and not uri.startswith("http"):
        uri = f"https://{uri}"
    complete = login.verification_uri_complete
    if complete and not complete.startswith("http"):
        complete = f"https://{complete}"
    return {
        "user_code": login.user_code,
        "verification_uri": uri or "https://link.tidal.com",
        "verification_uri_complete": complete,
        "expires_in": int(login.expires_in or 300),
    }


def poll_tidal_device_login(db: Session) -> dict:
    global _device_login, _device_session
    with _device_lock:
        login = _device_login
        session = _device_session
    if not login or not session:
        return {"status": "idle"}

    future = getattr(login, "_musicarr_future", None)
    if future is not None:
        if not future.done():
            return {"status": "pending"}
        try:
            future.result()
        except Exception as exc:  # noqa: BLE001
            with _device_lock:
                _device_login = None
                _device_session = None
            return {"status": "error", "error": str(exc)}
        settings = ensure_settings(db)
        settings.tidal_access_token = session.access_token or ""
        settings.tidal_refresh_token = session.refresh_token or ""
        settings.tidal_token_type = session.token_type or "Bearer"
        settings.tidal_expiry = (
            session.expiry_time.isoformat() if session.expiry_time else ""
        )
        settings.tidal_country_code = session.country_code or ""
        db.commit()
        with _device_lock:
            _device_login = None
            _device_session = None
        return {"status": "authenticated"}

    if session.check_login():
        settings = ensure_settings(db)
        settings.tidal_access_token = session.access_token or ""
        settings.tidal_refresh_token = session.refresh_token or ""
        settings.tidal_token_type = session.token_type or "Bearer"
        settings.tidal_expiry = (
            session.expiry_time.isoformat() if session.expiry_time else ""
        )
        settings.tidal_country_code = session.country_code or ""
        db.commit()
        with _device_lock:
            _device_login = None
            _device_session = None
        return {"status": "authenticated"}
    return {"status": "pending"}


def get_tidal_provider(db: Session) -> MusicProvider:
    return TidalProvider(db)
