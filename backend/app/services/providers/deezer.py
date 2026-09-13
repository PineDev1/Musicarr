from __future__ import annotations

import shutil
from pathlib import Path

from deemix import generateDownloadObject
from deemix.downloader import Downloader
from deemix.settings import DEFAULTS
from deemix.utils import getBitrateNumberFromText
from sqlalchemy.orm import Session

from app.services.deezer_client import (
    DeezerError,
    classify_album_type,
    deezer_session,
)
from app.services.providers.base import (
    DownloadResult,
    MusicProvider,
    ProviderAlbum,
    ProviderArtist,
    ProviderError,
    ProviderTrack,
)
from app.services.settings_service import ensure_settings


class DeezerProvider:
    name = "deezer"

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = ensure_settings(db)

    def validate_session(self) -> tuple[bool, str | None]:
        if not self.settings.arl:
            return False, "ARL not configured"
        return deezer_session.validate(self.settings.arl)

    def logout(self) -> None:
        self.settings.arl = ""
        self.db.commit()
        deezer_session.invalidate()

    def search_artists(self, query: str, limit: int = 25) -> list[ProviderArtist]:
        try:
            raw = deezer_session.search_artists(query, limit=limit)
        except DeezerError as exc:
            raise ProviderError(str(exc)) from exc
        return [
            ProviderArtist(
                provider_id=str(item["deezer_id"]),
                name=item["name"],
                image_url=item.get("image_url"),
                nb_album=item.get("nb_album"),
            )
            for item in raw
        ]

    def search_albums(self, query: str, limit: int = 25) -> list[ProviderAlbum]:
        try:
            raw = deezer_session.search_albums(query, limit=limit)
        except DeezerError as exc:
            raise ProviderError(str(exc)) from exc
        return [
            ProviderAlbum(
                provider_id=str(item["id"]),
                title=item.get("title") or "Unknown Album",
                album_type=classify_album_type(item) if item.get("record_type") else "album",
                release_date=item.get("release_date"),
                cover_url=item.get("cover_url"),
                track_count=int(item.get("nb_tracks") or 0),
            )
            for item in raw
        ]

    def get_artist(self, provider_id: str) -> ProviderArtist:
        try:
            meta = deezer_session.get_artist(int(provider_id))
        except DeezerError as exc:
            raise ProviderError(str(exc)) from exc
        return ProviderArtist(
            provider_id=str(meta.get("id") or provider_id),
            name=meta.get("name") or f"Artist {provider_id}",
            image_url=meta.get("picture_medium") or meta.get("picture"),
            nb_album=meta.get("nb_album"),
        )

    def list_albums(self, artist_id: str) -> list[ProviderAlbum]:
        try:
            raw = deezer_session.get_artist_albums(int(artist_id))
        except DeezerError as exc:
            raise ProviderError(str(exc)) from exc
        out: list[ProviderAlbum] = []
        for item in raw:
            out.append(
                ProviderAlbum(
                    provider_id=str(item["id"]),
                    title=item.get("title") or "Unknown Album",
                    album_type=classify_album_type(item),
                    release_date=item.get("release_date"),
                    cover_url=item.get("cover_medium") or item.get("cover"),
                    track_count=int(item.get("nb_tracks") or 0),
                )
            )
        return out

    def list_tracks(self, album_id: str) -> list[ProviderTrack]:
        try:
            full = deezer_session.get_album(int(album_id))
            raw = full.get("tracks", {}).get("data", [])
        except DeezerError as exc:
            raise ProviderError(str(exc)) from exc
        return [
            ProviderTrack(
                provider_id=str(t["id"]),
                title=t.get("title") or "Unknown Track",
                track_no=int(t.get("track_position") or 0),
                disc_no=int(t.get("disk_number") or 1),
                duration=int(t.get("duration") or 0),
                isrc=t.get("isrc"),
            )
            for t in raw
        ]

    def download_album(
        self,
        album_id: str,
        staging_dir: Path,
        bitrate: str,
        on_progress=None,
        is_cancelled=None,
    ) -> DownloadResult:
        try:
            deezer_session.ensure(self.settings.arl)
        except DeezerError as exc:
            raise ProviderError(str(exc)) from exc

        deemix_settings = dict(DEFAULTS)
        deemix_settings["downloadLocation"] = str(staging_dir)
        deemix_settings["createArtistFolder"] = False
        deemix_settings["createAlbumFolder"] = False
        deemix_settings["createCDFolder"] = False
        deemix_settings["createSingleFolder"] = False
        deemix_settings["albumTracknameTemplate"] = "%tracknumber% - %title%"
        deemix_settings["tracknameTemplate"] = "%tracknumber% - %title%"
        deemix_settings["overwriteFile"] = "y"
        deemix_settings["fallbackBitrate"] = True
        deemix_settings["queueConcurrency"] = 1

        class _Listener:
            def send(self, key, value=None):
                if on_progress and key == "updateQueue" and isinstance(value, dict):
                    if value.get("progress") is not None:
                        on_progress(float(value["progress"]))
                    elif value.get("downloaded"):
                        on_progress(None)

        listener = _Listener()
        url = f"https://www.deezer.com/album/{album_id}"
        dz = deezer_session.client
        br = getBitrateNumberFromText(bitrate or "flac")
        download_obj = generateDownloadObject(dz, url, br)
        if isinstance(download_obj, list):
            for obj in download_obj:
                if is_cancelled and is_cancelled():
                    raise ProviderError("cancelled")
                Downloader(dz, obj, deemix_settings, listener).start()
        else:
            Downloader(dz, download_obj, deemix_settings, listener).start()

        audio_exts = {".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav"}
        files = sorted(
            p for p in staging_dir.rglob("*") if p.is_file() and p.suffix.lower() in audio_exts
        )
        cover = next(
            (
                p
                for p in staging_dir.rglob("*")
                if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"}
            ),
            None,
        )
        return DownloadResult(files=files, cover=cover)


def get_deezer_provider(db: Session) -> MusicProvider:
    return DeezerProvider(db)
