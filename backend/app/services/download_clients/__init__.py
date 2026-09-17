from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DownloadClient
from app.services.download_clients.base import (
    ClientStatus,
    DownloadClientError,
    DownloadClientProtocol,
    base_url,
)
from app.services.download_clients.qbittorrent import QBittorrentClient
from app.services.download_clients.sabnzbd import SabnzbdClient

__all__ = [
    "ClientStatus",
    "DownloadClientError",
    "DownloadClientProtocol",
    "QBittorrentClient",
    "SabnzbdClient",
    "base_url",
    "get_client",
    "client_from_params",
    "pick_client",
]


def _verify_ssl(row: DownloadClient) -> bool:
    return bool(getattr(row, "verify_ssl", True))


def get_client(row: DownloadClient) -> DownloadClientProtocol:
    """Build a live client wrapper from a stored download client row."""
    return client_from_params(
        implementation=row.implementation or "",
        host=row.host or "",
        port=int(row.port or 8080),
        use_ssl=bool(row.use_ssl),
        verify_ssl=_verify_ssl(row),
        username=row.username or "",
        password=row.password or "",
        api_key=row.api_key or "",
        category=row.category or "",
    )


def client_from_params(
    *,
    implementation: str,
    host: str,
    port: int,
    use_ssl: bool = False,
    verify_ssl: bool = True,
    username: str = "",
    password: str = "",
    api_key: str = "",
    category: str = "",
) -> DownloadClientProtocol:
    impl = (implementation or "").lower()
    if impl == "qbittorrent":
        return QBittorrentClient(
            host,
            port,
            use_ssl=use_ssl,
            username=username,
            password=password,
            category=category,
            verify_ssl=verify_ssl,
        )
    if impl == "sabnzbd":
        return SabnzbdClient(
            host,
            port,
            use_ssl=use_ssl,
            api_key=api_key,
            category=category,
            username=username,
            password=password,
            verify_ssl=verify_ssl,
        )
    raise DownloadClientError(f"Unsupported download client '{implementation}'")


def pick_client(db: Session, protocol: str) -> DownloadClient | None:
    """Highest priority enabled client that speaks the release's protocol."""
    return db.scalar(
        select(DownloadClient)
        .where(
            DownloadClient.enabled.is_(True),
            DownloadClient.protocol == (protocol or "").lower(),
        )
        .order_by(DownloadClient.priority.asc(), DownloadClient.id.asc())
    )
