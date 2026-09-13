from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class ProviderArtist:
    provider_id: str
    name: str
    image_url: str | None = None
    nb_album: int | None = None


@dataclass
class ProviderAlbum:
    provider_id: str
    title: str
    album_type: str = "album"
    release_date: str | None = None
    cover_url: str | None = None
    track_count: int = 0


@dataclass
class ProviderTrack:
    provider_id: str
    title: str
    track_no: int = 0
    disc_no: int = 1
    duration: int = 0
    isrc: str | None = None


@dataclass
class DownloadProgress:
    current: int = 0
    total: int = 0
    message: str = ""


@dataclass
class DownloadResult:
    files: list[Path] = field(default_factory=list)
    cover: Path | None = None


class ProviderError(Exception):
    pass


class MusicProvider(Protocol):
    name: str

    def validate_session(self) -> tuple[bool, str | None]: ...

    def logout(self) -> None: ...

    def search_artists(self, query: str, limit: int = 25) -> list[ProviderArtist]: ...

    def get_artist(self, provider_id: str) -> ProviderArtist: ...

    def list_albums(self, artist_id: str) -> list[ProviderAlbum]: ...

    def list_tracks(self, album_id: str) -> list[ProviderTrack]: ...

    def download_album(
        self,
        album_id: str,
        staging_dir: Path,
        bitrate: str,
        on_progress=None,
        is_cancelled=None,
    ) -> DownloadResult: ...
