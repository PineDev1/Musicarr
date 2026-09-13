from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.providers.base import MusicProvider, ProviderError
from app.services.providers.deezer import get_deezer_provider
from app.services.providers.qobuz import get_qobuz_provider
from app.services.providers.tidal import get_tidal_provider
from app.services.settings_service import ensure_settings


def get_active_provider(db: Session) -> MusicProvider:
    settings = ensure_settings(db)
    name = (settings.active_provider or "deezer").lower()
    if name == "tidal":
        return get_tidal_provider(db)
    if name == "qobuz":
        return get_qobuz_provider(db)
    if name == "deezer":
        return get_deezer_provider(db)
    raise ProviderError(f"Unknown provider: {name}")


def get_provider(db: Session, name: str) -> MusicProvider:
    name = name.lower()
    if name == "tidal":
        return get_tidal_provider(db)
    if name == "qobuz":
        return get_qobuz_provider(db)
    if name == "deezer":
        return get_deezer_provider(db)
    raise ProviderError(f"Unknown provider: {name}")
