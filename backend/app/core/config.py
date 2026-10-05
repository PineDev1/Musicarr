from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


APP_VERSION = "1.22.2"


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MUSICARR_")

    host: str = "0.0.0.0"
    port: int = 8787
    data_dir: Path = Path("./data")
    music_dir: Path = Path("./music")
    database_url: str | None = None
    secret_key: str = "musicarr-dev-secret-change-me"
    # Optional JSON array of {"host", "remote_path", "local_path"} objects,
    # applied on every startup — for seeding/managing Remote Path Mappings
    # (download client running in a different container/host than Musicarr)
    # from docker-compose instead of the Settings UI. See
    # services/path_mapping.py::seed_remote_path_mappings_from_env.
    remote_path_mappings: str = ""

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        db_path = self.data_dir / "musicarr.db"
        return f"sqlite:///{db_path}"


settings = AppConfig()
