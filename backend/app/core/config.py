from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MUSICARR_")

    host: str = "0.0.0.0"
    port: int = 8787
    data_dir: Path = Path("./data")
    music_dir: Path = Path("./music")
    database_url: str | None = None
    secret_key: str = "musicarr-dev-secret-change-me"

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        db_path = self.data_dir / "musicarr.db"
        return f"sqlite:///{db_path}"


settings = AppConfig()
