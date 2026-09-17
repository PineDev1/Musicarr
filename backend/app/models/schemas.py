from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


Bitrate = Literal["flac", "320", "128"]
AlbumStatus = Literal["wanted", "downloaded", "skipped", "missing"]
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
    official_releases_only: bool = True
    mb_catalog_mode: str = "local"
    notify_webhook_url: str = ""
    notify_channel: str = "custom"
    notify_token_set: bool = False
    notify_on_complete: bool = True
    notify_on_failure: bool = True
    notify_on_library_events: bool = False
    upgrade_enabled: bool = True
    fallback_providers_enabled: bool = True
    media_refresh_url: str = ""
    media_refresh_token_set: bool = False
    media_refresh_type: str = "webhook"
    auth_enabled: bool = False
    auth_username: str = "admin"
    auth_password_set: bool = False
    ssl_enabled: bool = False
    public_domain: str = ""
    player_enabled: bool = False
    player_sharing_enabled: bool = True
    download_concurrency: int
    max_retries: int
    default_download_mode: str = "manual"
    lastfm_api_key: str = ""
    lastfm_api_secret_set: bool = False
    spotify_client_id: str = ""
    spotify_client_secret_set: bool = False
    backup_schedule_enabled: bool = True
    backup_retention_count: int = 7
    dedupe_scan_schedule_enabled: bool = True
    low_disk_threshold_gb: int = 10
    notify_on_maintenance: bool = True
    notify_on_health_alerts: bool = True
    preferred_download_method: str = "streaming"
    streaming_enabled: bool = True
    completed_download_scan_interval_seconds: int = 60
    import_mechanism: str = "hardlink"
    remove_completed_downloads: bool = False
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
    official_releases_only: bool | None = None
    mb_catalog_mode: Literal["local", "live", "local_with_live_fallback"] | None = None
    notify_webhook_url: str | None = None
    notify_channel: str | None = None
    notify_token: str | None = None
    notify_on_complete: bool | None = None
    notify_on_failure: bool | None = None
    notify_on_library_events: bool | None = None
    upgrade_enabled: bool | None = None
    fallback_providers_enabled: bool | None = None
    media_refresh_url: str | None = None
    media_refresh_token: str | None = None
    media_refresh_type: Literal["webhook", "plex", "jellyfin", "navidrome"] | None = None
    auth_enabled: bool | None = None
    auth_username: str | None = None
    auth_password: str | None = None
    ssl_enabled: bool | None = None
    public_domain: str | None = None
    player_enabled: bool | None = None
    player_sharing_enabled: bool | None = None
    download_concurrency: int | None = Field(default=None, ge=1, le=4)
    max_retries: int | None = Field(default=None, ge=0, le=10)
    default_download_mode: Literal["auto", "manual"] | None = None
    lastfm_api_key: str | None = None
    lastfm_api_secret: str | None = None
    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None
    backup_schedule_enabled: bool | None = None
    backup_retention_count: int | None = Field(default=None, ge=1, le=60)
    dedupe_scan_schedule_enabled: bool | None = None
    low_disk_threshold_gb: int | None = Field(default=None, ge=1, le=1000)
    notify_on_maintenance: bool | None = None
    notify_on_health_alerts: bool | None = None
    preferred_download_method: Literal["streaming", "indexer", "streaming_then_indexer"] | None = None
    streaming_enabled: bool | None = None
    completed_download_scan_interval_seconds: int | None = Field(default=None, ge=10, le=3600)
    import_mechanism: Literal["hardlink", "copy", "move"] | None = None
    remove_completed_downloads: bool | None = None


class NotifyTestRequest(BaseModel):
    notify_webhook_url: str | None = None
    notify_channel: str | None = None
    notify_token: str | None = None


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
    pending_artists: int = 0
    skipped_albums: int = 0
    disk_free_bytes: int | None = None
    low_disk_warning: bool = False
    streaming_enabled: bool = True


class SearchArtistHit(BaseModel):
    id: int
    name: str
    image_url: str | None = None


class SearchAlbumHit(BaseModel):
    id: int
    title: str
    artist_id: int
    artist_name: str = ""
    cover_url: str | None = None


class SearchResultsOut(BaseModel):
    artists: list[SearchArtistHit] = []
    albums: list[SearchAlbumHit] = []


class StatsRecentEvent(BaseModel):
    event_type: str
    message: str
    created_at: datetime


class StatsOut(BaseModel):
    artists: int
    albums_by_status: dict[str, int] = {}
    tracks: int
    disk_usage_bytes: int
    success_rate_30d: float | None = None
    recent_events: list[StatsRecentEvent] = []


class CalendarEntryOut(BaseModel):
    album_id: int
    title: str
    artist_id: int
    artist_name: str = ""
    release_date: str | None = None
    status: str
    cover_url: str | None = None


class OrphanDbTrackOut(BaseModel):
    track_id: int
    path: str
    title: str
    album_title: str = ""
    artist_name: str = ""


class OrphanFileOut(BaseModel):
    path: str
    size_bytes: int = 0


class DuplicateTrackOut(BaseModel):
    track_id: int
    title: str
    path: str | None = None
    album_title: str = ""
    artist_name: str = ""


class DuplicateGroupOut(BaseModel):
    reason: str
    key: str
    tracks: list[DuplicateTrackOut] = []


class MaintenanceScanOut(BaseModel):
    orphan_db_tracks: list[OrphanDbTrackOut] = []
    orphan_files: list[OrphanFileOut] = []
    duplicate_groups: list[DuplicateGroupOut] = []


class MaintenanceResolveRequest(BaseModel):
    unlink_track_id: int | None = None
    delete_file_path: str | None = None
    keep_track_id: int | None = None
    delete_track_ids: list[int] = []


class ArtistSearchResult(BaseModel):
    provider: str
    provider_id: str
    deezer_id: int | None = None
    name: str
    image_url: str | None = None
    nb_album: int | None = None


class BulkArtistSearchRequest(BaseModel):
    names: str


class BulkArtistSearchResult(BaseModel):
    query: str
    results: list[ArtistSearchResult] = []
    error: str | None = None


class ArtistMergeRequest(BaseModel):
    artist_ids: list[int]
    preferred_id: int | None = None


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
    status_reason: str = ""
    skip_reason_code: str = ""
    dismissed: bool = False
    musicbrainz_id: str | None = None
    artist_credit: str = ""
    path: str | None
    quality: str = ""
    upgrade_available: bool = False
    artist_name: str | None = None
    sources: list[str] = []
    tracks: list[TrackOut] = []

    class Config:
        from_attributes = True


class RelatedArtistOut(BaseModel):
    id: int | None = None
    name: str
    musicbrainz_id: str | None = None
    provider: str | None = None


class SimilarArtistOut(BaseModel):
    name: str
    match: float = 0.0
    already_in_library: int | None = None


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
    status: str = "active"
    pending_reason: str = ""
    download_mode: str | None = None
    quality_pref: str | None = None
    musicbrainz_id: str | None = None
    added_at: datetime
    last_synced_at: datetime | None
    album_count: int = 0
    downloaded_count: int = 0
    wanted_count: int = 0
    missing_count: int = 0
    providers: list[str] = []
    linked_artist_ids: list[int] = []
    related_artists: list[RelatedArtistOut] = []
    # True when another artist row shares this display name (identity collision hint)
    name_collision: bool = False
    albums: list[AlbumOut] = []

    class Config:
        from_attributes = True


class ArtistCreate(BaseModel):
    provider_id: str | None = None
    deezer_id: int | None = None
    provider: ProviderName | None = None
    monitored: bool = True
    download_missing: bool = True
    include_singles: bool | None = None
    monitor_mode: Literal["all", "new", "none"] | None = None
    download_mode: Literal["auto", "manual"] | None = None


class ArtistPatch(BaseModel):
    monitored: bool | None = None
    monitor_mode: Literal["all", "new", "none"] | None = None
    include_singles: bool | None = None
    download_mode: Literal["auto", "manual"] | None = None
    quality_pref: Bitrate | None = None


class BulkArtistIdsRequest(BaseModel):
    artist_ids: list[int]


class ImportListCreate(BaseModel):
    name: str
    names_raw: str = ""
    spotify_playlist_url: str | None = None
    interval_minutes: int = Field(default=720, ge=15, le=10080)
    enabled: bool = True


class ImportListUpdate(BaseModel):
    name: str | None = None
    names_raw: str | None = None
    spotify_playlist_url: str | None = None
    interval_minutes: int | None = Field(default=None, ge=15, le=10080)
    enabled: bool | None = None


class ImportListOut(BaseModel):
    id: int
    name: str
    names_raw: str
    spotify_playlist_url: str | None = None
    interval_minutes: int
    enabled: bool
    last_run_at: datetime | None
    last_result: str
    created_at: datetime


class ImportListRunResult(BaseModel):
    added: list[str]
    skipped: list[str]
    errors: list[str]
    summary: str


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
    source: str = "streaming"
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


class LibraryJobOut(BaseModel):
    state: str
    kind: str = ""
    phase: str = ""
    progress_pct: float = 0.0
    message: str = ""
    error: str = ""
    started_at: str = ""
    finished_at: str = ""
    files_seen: int = 0
    files_done: int = 0
    artists_created: int = 0
    albums_imported: int = 0
    tracks_linked: int = 0
    provider_linked: int = 0
    matched: int = 0
    unmatched: int = 0
    moved: int = 0
    skipped: int = 0
    result: dict = {}
    link_providers: bool = True


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


class AdminUserOut(BaseModel):
    id: int
    username: str
    display_name: str = ""
    is_active: bool = True
    created_at: datetime

    class Config:
        from_attributes = True


class AdminUserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=4, max_length=256)
    display_name: str = ""


class AdminUserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=4, max_length=256)
    display_name: str | None = None
    is_active: bool | None = None


class PlayerUserOut(BaseModel):
    id: int
    username: str
    display_name: str = ""
    is_active: bool = True
    created_at: datetime
    avatar_url: str | None = None

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
    avatar_url: str | None = None


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
    genre: str = ""


class PlayerLyricsOut(BaseModel):
    plain: str | None = None
    synced: str | None = None


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


class PlayerSmartRule(BaseModel):
    field: str
    op: str
    value: Any = None


class PlayerSmartCriteria(BaseModel):
    match: str = "all"
    rules: list[PlayerSmartRule] = []
    sort: str = "random"
    limit: int = Field(default=50, ge=1, le=500)


class PlayerPlaylistOut(BaseModel):
    id: int | str
    name: str
    track_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    tracks: list[PlayerTrackOut] = []
    is_smart: bool = False
    criteria: PlayerSmartCriteria | None = None
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


class PlayerPlaylistImportResult(BaseModel):
    playlist_id: int
    matched: int
    total: int


class PlayerCastTokenOut(BaseModel):
    token: str
    expires_at: datetime


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
    pinned_playlist_ids: list[int] = []
    crossfade_enabled: bool = False
    show_recommended: bool = True
    show_recently_added: bool = True
    default_shuffle: bool = False
    default_repeat: str = "off"


class PlayerPrefsUpdate(BaseModel):
    show_recently_played: bool | None = None
    show_shuffle_mix: bool | None = None
    wave_height: float | None = Field(default=None, ge=0, le=24)
    wave_length: float | None = Field(default=None, ge=4, le=80)
    wave_speed: float | None = Field(default=None, ge=0, le=60)
    wave_thickness: float | None = Field(default=None, ge=1, le=12)
    wave_color: str | None = Field(default=None, max_length=32)
    wave_flatten_when_paused: bool | None = None
    pinned_playlist_ids: list[int] | None = None
    crossfade_enabled: bool | None = None
    show_recommended: bool | None = None
    show_recently_added: bool | None = None
    default_shuffle: bool | None = None
    default_repeat: str | None = None


class PlayerArtistDetailOut(BaseModel):
    id: int
    name: str
    image_url: str | None = None
    album_count: int = 0
    featured_album: PlayerAlbumOut | None = None
    top_songs: list[PlayerTrackOut] = []
    essential_albums: list[PlayerAlbumOut] = []
    albums: list[PlayerAlbumOut] = []


class PlayerSearchGroupedOut(BaseModel):
    top: PlayerTrackOut | None = None
    songs: list[PlayerTrackOut] = []
    albums: list[PlayerAlbumOut] = []
    artists: list[PlayerArtistOut] = []


class PlayerShareCreate(BaseModel):
    track_id: int


class PlayerShareOut(BaseModel):
    token: str
    url: str
    expires_at: datetime
    track_title: str = ""
    artist_name: str = ""
    cover_url: str | None = None
    play_count: int = 0
    revoked: bool = False
    created_at: datetime


class PlayerSharePublicOut(BaseModel):
    title: str
    artist: str
    album: str = ""
    cover_url: str | None = None
    duration: int = 0
    shared_by_display_name: str = ""
    shared_by_avatar_url: str | None = None


class PlayerContinueOut(BaseModel):
    album: PlayerAlbumOut | None = None
    track: PlayerTrackOut | None = None
    position: float = 0
    source_label: str = ""


class PlayerLibrarySongsPage(BaseModel):
    items: list[PlayerTrackOut]
    total: int
    offset: int
    limit: int


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


# -- Indexers / download clients / acquisition -----------------------------
class IndexerOut(BaseModel):
    id: int
    name: str
    protocol: str
    implementation: str
    base_url: str
    api_key_set: bool
    categories: list[int]
    enabled: bool
    priority: int


class IndexerCreate(BaseModel):
    name: str
    protocol: Literal["usenet", "torrent"] = "usenet"
    implementation: Literal["newznab", "torznab"] = "newznab"
    base_url: str
    api_key: str | None = None
    categories: list[int] | None = None
    enabled: bool = True
    priority: int = 25


class IndexerUpdate(BaseModel):
    name: str | None = None
    protocol: Literal["usenet", "torrent"] | None = None
    implementation: Literal["newznab", "torznab"] | None = None
    base_url: str | None = None
    api_key: str | None = None
    categories: list[int] | None = None
    enabled: bool | None = None
    priority: int | None = None


class DownloadClientOut(BaseModel):
    id: int
    name: str
    protocol: str
    implementation: str
    host: str
    port: int
    use_ssl: bool
    verify_ssl: bool
    username: str
    password_set: bool
    api_key_set: bool
    category: str
    enabled: bool
    priority: int
    base_url: str


class DownloadClientCreate(BaseModel):
    name: str
    protocol: Literal["usenet", "torrent"] = "torrent"
    implementation: Literal["qbittorrent", "sabnzbd"] = "qbittorrent"
    host: str = "localhost"
    port: int = 8080
    use_ssl: bool = False
    verify_ssl: bool = True
    username: str | None = None
    password: str | None = None
    api_key: str | None = None
    category: str = "musicarr"
    enabled: bool = True
    priority: int = 1


class DownloadClientUpdate(BaseModel):
    name: str | None = None
    protocol: Literal["usenet", "torrent"] | None = None
    implementation: Literal["qbittorrent", "sabnzbd"] | None = None
    host: str | None = None
    port: int | None = None
    use_ssl: bool | None = None
    verify_ssl: bool | None = None
    username: str | None = None
    password: str | None = None
    api_key: str | None = None
    category: str | None = None
    enabled: bool | None = None
    priority: int | None = None


class DownloadClientTestDraft(BaseModel):
    client_id: int | None = None
    implementation: Literal["qbittorrent", "sabnzbd"] = "qbittorrent"
    host: str = "localhost"
    port: int = 8080
    use_ssl: bool = False
    verify_ssl: bool = True
    username: str | None = None
    password: str | None = None
    api_key: str | None = None


class RemotePathMappingOut(BaseModel):
    id: int
    host: str
    remote_path: str
    local_path: str


class RemotePathMappingCreate(BaseModel):
    host: str | None = None
    remote_path: str
    local_path: str


class RemotePathMappingUpdate(BaseModel):
    host: str | None = None
    remote_path: str | None = None
    local_path: str | None = None


class TestResultOut(BaseModel):
    ok: bool
    message: str


class AcquisitionStatusOut(BaseModel):
    indexers_enabled: int
    torrent_client: bool
    usenet_client: bool
    path_mappings: int
    messages: list[str]


class ReleaseCandidateOut(BaseModel):
    title: str
    size: int
    seeders: int
    protocol: str
    download_url: str
    magnet_url: str
    grab_url: str
    indexer_id: int
    indexer_name: str
    score: float


class ReleaseGrabRequest(BaseModel):
    album_id: int
    grab_url: str
    protocol: Literal["usenet", "torrent"] = "torrent"
    indexer_id: int = 0
    title: str = ""
