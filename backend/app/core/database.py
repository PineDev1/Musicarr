from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def ensure_dirs() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.music_dir.mkdir(parents=True, exist_ok=True)


ensure_dirs()

engine = create_engine(
    settings.db_url,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _sqlite_on_connect(dbapi_conn, _connection_record) -> None:
    """WAL + busy timeout for request threads + download worker + monitor."""
    if settings.db_url.startswith("sqlite"):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _existing_columns(table: str, engine_: Engine | None = None) -> set[str]:
    insp = inspect(engine_ or engine)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _add_column(table: str, column_def: str, engine_: Engine | None = None) -> None:
    with (engine_ or engine).begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column_def}"))


def migrate_schema(engine_: Engine | None = None) -> None:
    """Lightweight SQLite migrations for multi-provider fields.

    Runs against the module-level `engine` by default; pass `engine_` to
    migrate a different SQLite file in place (used by the backup/restore
    feature to validate + upgrade a staged backup before it's swapped in).
    """
    eng = engine_ or engine

    def existing_columns(table: str) -> set[str]:
        return _existing_columns(table, engine_=eng)

    def add_column(table: str, column_def: str) -> None:
        _add_column(table, column_def, engine_=eng)

    settings_cols = {
        "active_provider": "VARCHAR(32) DEFAULT 'deezer'",
        "tidal_access_token": "TEXT DEFAULT ''",
        "tidal_refresh_token": "TEXT DEFAULT ''",
        "tidal_token_type": "VARCHAR(64) DEFAULT 'Bearer'",
        "tidal_expiry": "VARCHAR(64) DEFAULT ''",
        "tidal_country_code": "VARCHAR(8) DEFAULT ''",
        "qobuz_email": "VARCHAR(512) DEFAULT ''",
        "qobuz_user_id": "VARCHAR(64) DEFAULT ''",
        "qobuz_user_auth_token": "TEXT DEFAULT ''",
        "qobuz_app_id": "VARCHAR(64) DEFAULT ''",
        "qobuz_app_secret": "VARCHAR(128) DEFAULT ''",
        "min_track_count": "INTEGER DEFAULT 0",
        "ignore_junk_titles": "BOOLEAN DEFAULT 1",
        "ignore_live_releases": "BOOLEAN DEFAULT 0",
        "official_releases_only": "BOOLEAN DEFAULT 1",
        "mb_catalog_mode": "VARCHAR(32) DEFAULT 'local'",
        "notify_webhook_url": "TEXT DEFAULT ''",
        "notify_channel": "VARCHAR(32) DEFAULT 'custom'",
        "notify_token": "TEXT DEFAULT ''",
        "notify_on_complete": "BOOLEAN DEFAULT 1",
        "notify_on_failure": "BOOLEAN DEFAULT 1",
        "upgrade_enabled": "BOOLEAN DEFAULT 1",
        "fallback_providers_enabled": "BOOLEAN DEFAULT 1",
        "media_refresh_url": "TEXT DEFAULT ''",
        "media_refresh_token": "TEXT DEFAULT ''",
        "media_refresh_type": "VARCHAR(32) DEFAULT 'webhook'",
        "auth_enabled": "BOOLEAN DEFAULT 0",
        "auth_username": "VARCHAR(128) DEFAULT 'admin'",
        "auth_password_hash": "TEXT DEFAULT ''",
        "auth_secret": "TEXT DEFAULT ''",
        "ssl_enabled": "BOOLEAN DEFAULT 0",
        "public_domain": "VARCHAR(512) DEFAULT ''",
        "player_enabled": "BOOLEAN DEFAULT 0",
        "player_sharing_enabled": "BOOLEAN DEFAULT 1",
        "preferred_download_method": "VARCHAR(32) DEFAULT 'streaming'",
        "completed_download_scan_interval_seconds": "INTEGER DEFAULT 60",
        "import_mechanism": "VARCHAR(16) DEFAULT 'hardlink'",
        "remove_completed_downloads": "BOOLEAN DEFAULT 0",
    }
    existing = existing_columns("app_settings")
    for name, definition in settings_cols.items():
        if existing and name not in existing:
            add_column("app_settings", f"{name} {definition}")

    artist_cols = existing_columns("artists")
    if artist_cols:
        if "monitor_mode" not in artist_cols:
            add_column("artists", "monitor_mode VARCHAR(16) DEFAULT 'all'")
        if "include_singles" not in artist_cols:
            add_column("artists", "include_singles BOOLEAN")
        if "link_group_id" not in artist_cols:
            add_column("artists", "link_group_id VARCHAR(64)")
        if "musicbrainz_id" not in artist_cols:
            add_column("artists", "musicbrainz_id VARCHAR(64)")
        if "related_artists_json" not in artist_cols:
            add_column("artists", "related_artists_json TEXT DEFAULT '[]'")

    album_cols = existing_columns("albums")
    if album_cols:
        if "quality" not in album_cols:
            add_column("albums", "quality VARCHAR(16) DEFAULT ''")
        if "musicbrainz_id" not in album_cols:
            add_column("albums", "musicbrainz_id VARCHAR(64)")
        if "status_reason" not in album_cols:
            add_column("albums", "status_reason TEXT DEFAULT ''")
        if "collaborators_json" not in album_cols:
            add_column("albums", "collaborators_json TEXT DEFAULT '[]'")
        if "artist_credit" not in album_cols:
            add_column("albums", "artist_credit VARCHAR(1024) DEFAULT ''")

    for table, id_col in (
        ("artists", "deezer_id"),
        ("albums", "deezer_id"),
        ("tracks", "deezer_id"),
    ):
        cols = existing_columns(table)
        if not cols:
            continue
        if "provider" not in cols:
            add_column(table, "provider VARCHAR(32) DEFAULT 'deezer'")
        if "provider_id" not in cols:
            add_column(table, "provider_id VARCHAR(64) DEFAULT ''")
        with eng.begin() as conn:
            conn.execute(
                text(
                    f"UPDATE {table} SET provider = 'deezer' "
                    f"WHERE provider IS NULL OR provider = ''"
                )
            )
            conn.execute(
                text(
                    f"UPDATE {table} SET provider_id = CAST({id_col} AS TEXT) "
                    f"WHERE provider_id IS NULL OR provider_id = ''"
                )
            )

    job_cols = existing_columns("download_jobs")
    download_job_cols = {
        "target_provider_id": "VARCHAR(64) DEFAULT ''",
        "error_category": "VARCHAR(32) DEFAULT ''",
        "source": "VARCHAR(32) DEFAULT 'streaming'",
        "indexer_id": "INTEGER",
        "client_id": "INTEGER",
        "release_title": "VARCHAR(1024) DEFAULT ''",
        "download_url": "TEXT DEFAULT ''",
        "client_item_id": "VARCHAR(128) DEFAULT ''",
        "output_path": "VARCHAR(2048) DEFAULT ''",
    }
    for name, definition in download_job_cols.items():
        if job_cols and name not in job_cols:
            add_column("download_jobs", f"{name} {definition}")

    player_user_cols = {
        "show_recently_played": "BOOLEAN DEFAULT 1",
        "show_shuffle_mix": "BOOLEAN DEFAULT 1",
        "wave_height": "REAL DEFAULT 6.0",
        "wave_length": "REAL DEFAULT 20.0",
        "wave_speed": "REAL DEFAULT 12.0",
        "wave_thickness": "REAL DEFAULT 3.0",
        "wave_color": "VARCHAR(32) DEFAULT '#3dba7a'",
        "wave_flatten_when_paused": "BOOLEAN DEFAULT 1",
        "avatar_path": "VARCHAR(1024)",
        "pinned_playlist_ids": "TEXT DEFAULT '[]'",
        "crossfade_enabled": "BOOLEAN DEFAULT 0",
        "show_recommended": "BOOLEAN DEFAULT 1",
        "show_recently_added": "BOOLEAN DEFAULT 1",
        "default_shuffle": "BOOLEAN DEFAULT 0",
        "default_repeat": "VARCHAR(16) DEFAULT 'off'",
        "continue_album_id": "INTEGER",
        "continue_track_id": "INTEGER",
        "continue_position": "REAL DEFAULT 0",
    }
    existing_pu = existing_columns("player_users")
    for name, definition in player_user_cols.items():
        if existing_pu and name not in existing_pu:
            add_column("player_users", f"{name} {definition}")

    pl_cols = existing_columns("player_playlists")
    if pl_cols and "is_smart" not in pl_cols:
        add_column("player_playlists", "is_smart BOOLEAN DEFAULT 0")

    # Drop retired indexer / download-client tables (streaming-only).
    with eng.begin() as conn:
        for table in ("indexers", "download_clients", "remote_path_mappings"):
            conn.execute(text(f"DROP TABLE IF EXISTS {table}"))


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    migrate_schema()
