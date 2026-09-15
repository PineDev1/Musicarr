from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    active_provider: Mapped[str] = mapped_column(String(32), default="deezer")
    arl: Mapped[str] = mapped_column(Text, default="")
    tidal_access_token: Mapped[str] = mapped_column(Text, default="")
    tidal_refresh_token: Mapped[str] = mapped_column(Text, default="")
    tidal_token_type: Mapped[str] = mapped_column(String(64), default="Bearer")
    tidal_expiry: Mapped[str] = mapped_column(String(64), default="")
    tidal_country_code: Mapped[str] = mapped_column(String(8), default="")
    qobuz_email: Mapped[str] = mapped_column(String(512), default="")
    qobuz_user_id: Mapped[str] = mapped_column(String(64), default="")
    qobuz_user_auth_token: Mapped[str] = mapped_column(Text, default="")
    qobuz_app_id: Mapped[str] = mapped_column(String(64), default="")
    qobuz_app_secret: Mapped[str] = mapped_column(String(128), default="")
    library_path: Mapped[str] = mapped_column(String(1024), default="")
    bitrate: Mapped[str] = mapped_column(String(16), default="flac")
    folder_template: Mapped[str] = mapped_column(
        String(512), default="{artist}/{album} ({year})"
    )
    track_template: Mapped[str] = mapped_column(
        String(512), default="{track:02d} - {title}"
    )
    monitor_interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    include_albums: Mapped[bool] = mapped_column(Boolean, default=True)
    include_eps: Mapped[bool] = mapped_column(Boolean, default=True)
    include_singles: Mapped[bool] = mapped_column(Boolean, default=False)
    include_compilations: Mapped[bool] = mapped_column(Boolean, default=False)
    min_track_count: Mapped[int] = mapped_column(Integer, default=0)
    ignore_junk_titles: Mapped[bool] = mapped_column(Boolean, default=True)
    ignore_live_releases: Mapped[bool] = mapped_column(Boolean, default=False)
    official_releases_only: Mapped[bool] = mapped_column(Boolean, default=True)
    # local | live | local_with_live_fallback
    mb_catalog_mode: Mapped[str] = mapped_column(String(32), default="local")
    notify_webhook_url: Mapped[str] = mapped_column(Text, default="")
    notify_channel: Mapped[str] = mapped_column(String(32), default="custom")
    notify_token: Mapped[str] = mapped_column(Text, default="")
    notify_on_complete: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_failure: Mapped[bool] = mapped_column(Boolean, default=True)
    upgrade_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    fallback_providers_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    media_refresh_url: Mapped[str] = mapped_column(Text, default="")
    media_refresh_token: Mapped[str] = mapped_column(Text, default="")
    media_refresh_type: Mapped[str] = mapped_column(String(32), default="webhook")
    # Optional UI/API login gate (disabled by default)
    auth_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auth_username: Mapped[str] = mapped_column(String(128), default="admin")
    auth_password_hash: Mapped[str] = mapped_column(Text, default="")
    auth_secret: Mapped[str] = mapped_column(Text, default="")
    # Behind Traefik / HTTPS reverse proxy (Musicarr still listens on HTTP)
    ssl_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    public_domain: Mapped[str] = mapped_column(String(512), default="")
    player_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    player_sharing_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    download_concurrency: Mapped[int] = mapped_column(Integer, default=1)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Artist(Base):
    __tablename__ = "artists"
    __table_args__ = (
        UniqueConstraint("provider", "provider_id", name="uq_artist_provider"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), default="deezer", index=True)
    provider_id: Mapped[str] = mapped_column(String(64), index=True)
    # Legacy alias kept for compatibility during transition
    deezer_id: Mapped[int] = mapped_column(Integer, default=0, index=True)
    name: Mapped[str] = mapped_column(String(512))
    image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Explicit / MusicBrainz cross-provider identity
    link_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    musicbrainz_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # JSON list of {id,name,musicbrainz_id} featured / collaborating artists
    related_artists_json: Mapped[str] = mapped_column(Text, default="[]")
    monitored: Mapped[bool] = mapped_column(Boolean, default=True)
    # all = full discography; new = only releases after added_at; none = never auto-grab
    monitor_mode: Mapped[str] = mapped_column(String(16), default="all")
    # None/empty = inherit global include_singles; "0"/"1" stored as bool
    include_singles: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    albums: Mapped[list["Album"]] = relationship(
        back_populates="artist", cascade="all, delete-orphan"
    )


class Album(Base):
    __tablename__ = "albums"
    __table_args__ = (
        UniqueConstraint("provider", "provider_id", name="uq_album_provider"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), default="deezer", index=True)
    provider_id: Mapped[str] = mapped_column(String(64), index=True)
    deezer_id: Mapped[int] = mapped_column(Integer, default=0, index=True)
    artist_id: Mapped[int] = mapped_column(ForeignKey("artists.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(512))
    album_type: Mapped[str] = mapped_column(String(64), default="album")
    release_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    track_count: Mapped[int] = mapped_column(Integer, default=0)
    monitored: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(32), default="wanted")
    # e.g. "Qobuz doesn't have this release"
    status_reason: Mapped[str] = mapped_column(Text, default="")
    musicbrainz_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # JSON list of collaborator display names for this release
    collaborators_json: Mapped[str] = mapped_column(Text, default="[]")
    # Full MusicBrainz artist-credit string e.g. "Ed Sheeran feat. Luke Combs"
    artist_credit: Mapped[str] = mapped_column(String(1024), default="")
    path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # flac | 320 | 128 | "" unknown
    quality: Mapped[str] = mapped_column(String(16), default="")

    artist: Mapped["Artist"] = relationship(back_populates="albums")
    tracks: Mapped[list["Track"]] = relationship(
        back_populates="album", cascade="all, delete-orphan"
    )


class Track(Base):
    __tablename__ = "tracks"
    __table_args__ = (
        UniqueConstraint("provider", "provider_id", name="uq_track_provider"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), default="deezer", index=True)
    provider_id: Mapped[str] = mapped_column(String(64), index=True)
    deezer_id: Mapped[int] = mapped_column(Integer, default=0, index=True)
    album_id: Mapped[int] = mapped_column(ForeignKey("albums.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(512))
    track_no: Mapped[int] = mapped_column(Integer, default=0)
    disc_no: Mapped[int] = mapped_column(Integer, default=1)
    duration: Mapped[int] = mapped_column(Integer, default=0)
    isrc: Mapped[str | None] = mapped_column(String(32), nullable=True)
    path: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    album: Mapped["Album"] = relationship(back_populates="tracks")


class DownloadJob(Base):
    __tablename__ = "download_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[int] = mapped_column(Integer, default=0)
    target_provider_id: Mapped[str] = mapped_column(String(64), default="")
    album_id: Mapped[int | None] = mapped_column(
        ForeignKey("albums.id", ondelete="SET NULL"), nullable=True
    )
    artist_name: Mapped[str] = mapped_column(String(512), default="")
    album_title: Mapped[str] = mapped_column(String(512), default="")
    state: Mapped[str] = mapped_column(String(32), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_category: Mapped[str] = mapped_column(String(32), default="")
    retries: Mapped[int] = mapped_column(Integer, default=0)
    # Kept for DB compatibility; always "streaming" after indexer removal
    source: Mapped[str] = mapped_column(String(32), default="streaming")
    indexer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    client_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    release_title: Mapped[str] = mapped_column(String(1024), default="")
    download_url: Mapped[str] = mapped_column(Text, default="")
    client_item_id: Mapped[str] = mapped_column(String(128), default="")
    output_path: Mapped[str] = mapped_column(String(2048), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class HistoryEvent(Base):
    __tablename__ = "history_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ImportList(Base):
    __tablename__ = "import_lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), default="")
    names_raw: Mapped[str] = mapped_column(Text, default="")
    interval_minutes: Mapped[int] = mapped_column(Integer, default=720)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_result: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PlayerUser(Base):
    __tablename__ = "player_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text, default="")
    display_name: Mapped[str] = mapped_column(String(256), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    show_recently_played: Mapped[bool] = mapped_column(Boolean, default=True)
    show_shuffle_mix: Mapped[bool] = mapped_column(Boolean, default=True)
    wave_height: Mapped[float] = mapped_column(Float, default=6.0)
    wave_length: Mapped[float] = mapped_column(Float, default=20.0)
    wave_speed: Mapped[float] = mapped_column(Float, default=12.0)
    wave_thickness: Mapped[float] = mapped_column(Float, default=3.0)
    wave_color: Mapped[str] = mapped_column(String(32), default="#3dba7a")
    wave_flatten_when_paused: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    pinned_playlist_ids: Mapped[str] = mapped_column(Text, default="[]")
    crossfade_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    show_recommended: Mapped[bool] = mapped_column(Boolean, default=True)
    show_recently_added: Mapped[bool] = mapped_column(Boolean, default=True)
    default_shuffle: Mapped[bool] = mapped_column(Boolean, default=False)
    default_repeat: Mapped[str] = mapped_column(String(16), default="off")
    continue_album_id: Mapped[int | None] = mapped_column(
        ForeignKey("albums.id", ondelete="SET NULL"), nullable=True
    )
    continue_track_id: Mapped[int | None] = mapped_column(
        ForeignKey("tracks.id", ondelete="SET NULL"), nullable=True
    )
    continue_position: Mapped[float] = mapped_column(Float, default=0.0)

    playlists: Mapped[list["PlayerPlaylist"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    favorites: Mapped[list["PlayerFavorite"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class PlayerPlaylist(Base):
    __tablename__ = "player_playlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("player_users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(256))
    is_smart: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["PlayerUser"] = relationship(back_populates="playlists")
    tracks: Mapped[list["PlayerPlaylistTrack"]] = relationship(
        back_populates="playlist",
        cascade="all, delete-orphan",
        order_by="PlayerPlaylistTrack.position",
    )


class PlayerPlaylistTrack(Base):
    __tablename__ = "player_playlist_tracks"
    __table_args__ = (
        UniqueConstraint("playlist_id", "track_id", name="uq_playlist_track"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    playlist_id: Mapped[int] = mapped_column(
        ForeignKey("player_playlists.id", ondelete="CASCADE"), index=True
    )
    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)

    playlist: Mapped["PlayerPlaylist"] = relationship(back_populates="tracks")
    track: Mapped["Track"] = relationship()


class PlayerFavorite(Base):
    __tablename__ = "player_favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "track_id", name="uq_player_favorite"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("player_users.id", ondelete="CASCADE"), index=True
    )
    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["PlayerUser"] = relationship(back_populates="favorites")
    track: Mapped["Track"] = relationship()


class PlayerPlayEvent(Base):
    __tablename__ = "player_play_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("player_users.id", ondelete="CASCADE"), index=True
    )
    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), index=True
    )
    played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    track: Mapped["Track"] = relationship()


class PlayerShareLink(Base):
    __tablename__ = "player_share_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), index=True
    )
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("player_users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    play_count: Mapped[int] = mapped_column(Integer, default=0)

    track: Mapped["Track"] = relationship()
    created_by: Mapped["PlayerUser"] = relationship()
