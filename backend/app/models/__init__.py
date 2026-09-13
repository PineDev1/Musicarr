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
    notify_webhook_url: Mapped[str] = mapped_column(Text, default="")
    notify_on_complete: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_failure: Mapped[bool] = mapped_column(Boolean, default=True)
    upgrade_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    media_refresh_url: Mapped[str] = mapped_column(Text, default="")
    media_refresh_token: Mapped[str] = mapped_column(Text, default="")
    media_refresh_type: Mapped[str] = mapped_column(String(32), default="webhook")
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
