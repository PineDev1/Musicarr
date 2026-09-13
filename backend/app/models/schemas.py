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
    min_track_count: int = 0
    ignore_junk_titles: bool = True
    ignore_live_releases: bool = False
    notify_webhook_url: str = ""
    notify_on_complete: bool = True
    notify_on_failure: bool = True
    upgrade_enabled: bool = True
    media_refresh_url: str = ""
    media_refresh_token_set: bool = False
    media_refresh_type: str = "webhook"
    auth_enabled: bool = False
    auth_username: str = "admin"
    auth_password_set: bool = False
    ssl_enabled: bool = False
    public_domain: str = ""
    player_enabled: bool = False
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
    min_track_count: int | None = Field(default=None, ge=0, le=100)
    ignore_junk_titles: bool | None = None
    ignore_live_releases: bool | None = None
    notify_webhook_url: str | None = None
    notify_on_complete: bool | None = None
    notify_on_failure: bool | None = None
    upgrade_enabled: bool | None = None
    media_refresh_url: str | None = None
    media_refresh_token: str | None = None
    media_refresh_type: Literal["webhook", "plex", "jellyfin", "navidrome"] | None = None
    auth_enabled: bool | None = None
    auth_username: str | None = None
    auth_password: str | None = None
    ssl_enabled: bool | None = None
    public_domain: str | None = None
    player_enabled: bool | None = None
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
    quality: str = ""
    upgrade_available: bool = False
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
    monitor_mode: str = "all"
    include_singles: bool | None = None
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


class ArtistPatch(BaseModel):
    monitored: bool | None = None
    monitor_mode: Literal["all", "new", "none"] | None = None
    include_singles: bool | None = None


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
    error_category: str = ""
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


class ImportResult(BaseModel):
    files_seen: int
    artists_created: int = 0
    albums_imported: int = 0
    tracks_linked: int = 0
    provider_linked: int = 0
    matched: int = 0
    unmatched: int = 0
    message: str


class ImportReviewArtist(BaseModel):
    id: int
    name: str
    provider: str
    album_count: int
    reason: str
    suggestions: list[ArtistSearchResult] = []


class ImportReviewAlbum(BaseModel):
    id: int
    title: str
    artist_id: int
    artist_name: str
    reason: str


class ImportReviewOut(BaseModel):
    local_artists: list[ImportReviewArtist] = []
    weak_albums: list[ImportReviewAlbum] = []
    message: str = ""


class LinkArtistRequest(BaseModel):
    provider_id: str
    provider: ProviderName | None = None


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


class AppLoginRequest(BaseModel):
    username: str
    password: str


class AppAuthStatus(BaseModel):
    enabled: bool
    authenticated: bool
    username: str | None = None
    password_set: bool = False


class PlayerUserOut(BaseModel):
    id: int
    username: str
    display_name: str = ""
    is_active: bool = True
    created_at: datetime

    class Config:
        from_attributes = True


class PlayerUserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=4, max_length=256)
    display_name: str = ""


class PlayerUserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=4, max_length=256)
    display_name: str | None = None
    is_active: bool | None = None


class PlayerLoginRequest(BaseModel):
    username: str
    password: str


class PlayerAuthStatus(BaseModel):
    enabled: bool
    authenticated: bool
    username: str | None = None
    user_id: int | None = None
    display_name: str | None = None


class PlayerTrackOut(BaseModel):
    id: int
    title: str
    track_no: int = 0
    disc_no: int = 1
    duration: int = 0
    album_id: int
    album_title: str = ""
    artist_id: int = 0
    artist_name: str = ""
    cover_url: str | None = None
    quality: str = ""
    format: str = ""


class PlayerAlbumOut(BaseModel):
    id: int
    title: str
    artist_id: int
    artist_name: str = ""
    cover_url: str | None = None
    release_date: str | None = None
    track_count: int = 0
    quality: str = ""
    tracks: list[PlayerTrackOut] = []


class PlayerArtistOut(BaseModel):
    id: int
    name: str
    image_url: str | None = None
    album_count: int = 0


class PlayerPlaylistOut(BaseModel):
    id: int | str
    name: str
    track_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    tracks: list[PlayerTrackOut] = []
    is_smart: bool = False
    builtin: bool = False
    kind: str | None = None


class PlayerPlaylistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    is_smart: bool = False


class PlayerPlaylistUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    is_smart: bool | None = None


class PlayerPlaylistAddTracks(BaseModel):
    track_ids: list[int]


class PlayerPasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=4, max_length=256)


class PlayerPrefsOut(BaseModel):
    show_recently_played: bool = True
    show_shuffle_mix: bool = True
    wave_height: float = 6.0
    wave_length: float = 20.0
    wave_speed: float = 12.0
    wave_thickness: float = 3.0
    wave_color: str = "#3dba7a"
    wave_flatten_when_paused: bool = True


class PlayerPrefsUpdate(BaseModel):
    show_recently_played: bool | None = None
    show_shuffle_mix: bool | None = None
    wave_height: float | None = Field(default=None, ge=0, le=24)
    wave_length: float | None = Field(default=None, ge=4, le=80)
    wave_speed: float | None = Field(default=None, ge=0, le=60)
    wave_thickness: float | None = Field(default=None, ge=1, le=12)
    wave_color: str | None = Field(default=None, max_length=32)
    wave_flatten_when_paused: bool | None = None


class PlayerPlayingUpdate(BaseModel):
    track_id: int | None = None
    position: float = 0
    playing: bool = False
    title: str | None = None
    artist_name: str | None = None
    cover_url: str | None = None


class PlayerNowPlayingOut(BaseModel):
    user_id: int
    username: str
    display_name: str = ""
    track_id: int | None = None
    title: str | None = None
    artist_name: str | None = None
    cover_url: str | None = None
    playing: bool = False
    position: float = 0
    updated_at: float


class PlayerCommandsOut(BaseModel):
    stop: bool = False
