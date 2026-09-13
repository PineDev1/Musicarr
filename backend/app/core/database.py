from sqlalchemy import create_engine, inspect, text
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
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _existing_columns(table: str) -> set[str]:
    insp = inspect(engine)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _add_column(table: str, column_def: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column_def}"))


def migrate_schema() -> None:
    """Lightweight SQLite migrations for multi-provider fields."""
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
        "notify_webhook_url": "TEXT DEFAULT ''",
        "notify_on_complete": "BOOLEAN DEFAULT 1",
        "notify_on_failure": "BOOLEAN DEFAULT 1",
        "upgrade_enabled": "BOOLEAN DEFAULT 1",
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
    }
    existing = _existing_columns("app_settings")
    for name, definition in settings_cols.items():
        if existing and name not in existing:
            _add_column("app_settings", f"{name} {definition}")

    artist_cols = _existing_columns("artists")
    if artist_cols:
        if "monitor_mode" not in artist_cols:
            _add_column("artists", "monitor_mode VARCHAR(16) DEFAULT 'all'")
        if "include_singles" not in artist_cols:
            _add_column("artists", "include_singles BOOLEAN")

    album_cols = _existing_columns("albums")
    if album_cols and "quality" not in album_cols:
        _add_column("albums", "quality VARCHAR(16) DEFAULT ''")

    for table, id_col in (
        ("artists", "deezer_id"),
        ("albums", "deezer_id"),
        ("tracks", "deezer_id"),
    ):
        cols = _existing_columns(table)
        if not cols:
            continue
        if "provider" not in cols:
            _add_column(table, "provider VARCHAR(32) DEFAULT 'deezer'")
        if "provider_id" not in cols:
            _add_column(table, "provider_id VARCHAR(64) DEFAULT ''")
        with engine.begin() as conn:
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

    job_cols = _existing_columns("download_jobs")
    if job_cols and "target_provider_id" not in job_cols:
        _add_column("download_jobs", "target_provider_id VARCHAR(64) DEFAULT ''")
    if job_cols and "error_category" not in job_cols:
        _add_column("download_jobs", "error_category VARCHAR(32) DEFAULT ''")

    player_user_cols = {
        "show_recently_played": "BOOLEAN DEFAULT 1",
        "show_shuffle_mix": "BOOLEAN DEFAULT 1",
        "wave_height": "REAL DEFAULT 6.0",
        "wave_length": "REAL DEFAULT 20.0",
        "wave_speed": "REAL DEFAULT 12.0",
        "wave_thickness": "REAL DEFAULT 3.0",
        "wave_color": "VARCHAR(32) DEFAULT '#3dba7a'",
        "wave_flatten_when_paused": "BOOLEAN DEFAULT 1",
    }
    existing_pu = _existing_columns("player_users")
    for name, definition in player_user_cols.items():
        if existing_pu and name not in existing_pu:
            _add_column("player_users", f"{name} {definition}")

    pl_cols = _existing_columns("player_playlists")
    if pl_cols and "is_smart" not in pl_cols:
        _add_column("player_playlists", "is_smart BOOLEAN DEFAULT 0")


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    migrate_schema()
