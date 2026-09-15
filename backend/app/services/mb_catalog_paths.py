from __future__ import annotations

from pathlib import Path

from app.core.config import settings as app_config

MAX_CATALOG_BYTES = 20 * 1024 * 1024 * 1024  # 20 GiB
DUMP_BASE = "https://data.metabrainz.org/pub/musicbrainz/data/fullexport"
USER_AGENT = "Musicarr/1.6 (https://github.com/PineDev1/Musicarr)"

# Core dump: mbdump.tar.bz2
CORE_DUMP_TABLES = (
    "artist",
    "artist_alias",
    "artist_credit",
    "artist_credit_name",
    "release_group",
    "release_group_primary_type",
    "release_group_secondary_type",
    "release_group_secondary_type_join",
)

# Derived dump: mbdump-derived.tar.bz2 (includes release_group_meta)
DERIVED_DUMP_TABLES = (
    "release_group_meta",
)

# All tables required in the slim SQLite catalog.
DUMP_TABLES = CORE_DUMP_TABLES + DERIVED_DUMP_TABLES


def catalog_dir() -> Path:
    path = Path(app_config.data_dir) / "musicbrainz"
    path.mkdir(parents=True, exist_ok=True)
    return path


def catalog_db_path() -> Path:
    return catalog_dir() / "musicbrainz_catalog.sqlite"


def catalog_meta_path() -> Path:
    return catalog_dir() / "catalog_meta.json"


def catalog_work_dir() -> Path:
    path = catalog_dir() / "work"
    path.mkdir(parents=True, exist_ok=True)
    return path
