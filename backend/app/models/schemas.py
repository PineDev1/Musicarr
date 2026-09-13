from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Bitrate = Literal["flac", "320", "128"]
AlbumStatus = Literal["wanted", "downloaded", "skipped"]
ProviderName = Literal["deezer", "tidal", "qobuz"]


class SettingsOut(BaseModel):
    active_provider: str
    arl_set: bool
    arl_masked: str
    tidal_logged_in: bool
    qobuz_logged_in: bool
    qobuz_email: str
    qobuz_user_id: str
    qobuz_app_id: str
    qobuz_app_secret_set: bool
    qobuz_token_set: bool
    library_path: str
    bitrate: str
    folder_template: str
    track_template: str
    monitor_interval_minutes: int
    include_albums: bool
    include_eps: bool
    include_singles: bool
    include_compilations: bool
    download_concurrency: int
    max_retries: int
    provider_ok: bool | None = None
    provider_error: str | None = None
    deezer_ok: bool | None = None
    deezer_error: str | None = None
    tidal_ok: bool | None = None
    tidal_error: str | None = None
    qobuz_ok: bool | None = None
    qobuz_error: str | None = None


class SettingsUpdate(BaseModel):
    active_provider: ProviderName | None = None
    arl: str | None = None
    qobuz_app_id: str | None = None
    qobuz_app_secret: str | None = None
    library_path: str | None = None
    bitrate: Bitrate | None = None
    folder_template: str | None = None
    track_template: str | None = None
    monitor_interval_minutes: int | None = Field(default=None, ge=5, le=10080)
    include_albums: bool | None = None
    include_eps: bool | None = None
    include_singles: bool | None = None
    include_compilations: bool | None = None
    download_concurrency: int | None = Field(default=None, ge=1, le=4)
    max_retries: int | None = Field(default=None, ge=0, le=10)


class HealthOut(BaseModel):
    status: str
    active_provider: str
    provider_ok: bool
    provider_error: str | None = None
    deezer_ok: bool
    deezer_error: str | None = None
    tidal_ok: bool
    tidal_error: str | None = None
    qobuz_ok: bool
    qobuz_error: str | None = None
    library_path: str
    library_writable: bool
    monitored_artists: int
    wanted_albums: int
    queue_size: int


class ArtistSearchResult(BaseModel):
    provider: str
    provider_id: str
    deezer_id: int | None = None
    name: str
    image_url: str | None = None
    nb_album: int | None = None


class TrackOut(BaseModel):
    id: int
    provider: str = "deezer"
    provider_id: str = ""
    deezer_id: int = 0
    title: str
    track_no: int
    disc_no: int
    duration: int
    path: str | None
    downloaded: bool

    class Config:
        from_attributes = True


class AlbumOut(BaseModel):
    id: int
    provider: str = "deezer"
    provider_id: str = ""
    deezer_id: int = 0
    artist_id: int
    title: str
    album_type: str
    release_date: str | None
    cover_url: str | None
    track_count: int
    monitored: bool
    status: str
    path: str | None
    artist_name: str | None = None
    sources: list[str] = []
    tracks: list[TrackOut] = []

    class Config:
        from_attributes = True


class ArtistOut(BaseModel):
    id: int
    provider: str = "deezer"
    provider_id: str = ""
    deezer_id: int = 0
    name: str
    image_url: str | None
    monitored: bool
    added_at: datetime
    last_synced_at: datetime | None
    album_count: int = 0
    downloaded_count: int = 0
    wanted_count: int = 0
    providers: list[str] = []
    linked_artist_ids: list[int] = []
    albums: list[AlbumOut] = []

    class Config:
        from_attributes = True


class ArtistCreate(BaseModel):
    provider_id: str | None = None
    deezer_id: int | None = None
    provider: ProviderName | None = None
    monitored: bool = True
    download_missing: bool = True


class AlbumPatch(BaseModel):
    monitored: bool | None = None
    status: AlbumStatus | None = None


class DownloadJobOut(BaseModel):
    id: int
    target_type: str
    target_id: int
    album_id: int | None
    artist_name: str
    album_title: str
    state: str
    progress: float
    error: str | None
    retries: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    class Config:
        from_attributes = True


class HistoryOut(BaseModel):
    id: int
    event_type: str
    message: str
    created_at: datetime

    class Config:
        from_attributes = True


class ScanResult(BaseModel):
    files_seen: int
    matched: int
    unmatched: int
    message: str


class ReorganizeResult(BaseModel):
    moved: int
    skipped: int
    message: str


class QobuzLoginRequest(BaseModel):
    email: str
    password: str


class QobuzTokenLoginRequest(BaseModel):
    token: str
    user_id: str = ""
    app_id: str = ""
    app_secret: str = ""


class TidalDeviceOut(BaseModel):
    user_code: str
    verification_uri: str
    verification_uri_complete: str | None = None
    expires_in: int = 300
