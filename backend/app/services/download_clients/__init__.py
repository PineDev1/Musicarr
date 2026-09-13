from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DownloadClient
from app.services.download_clients.base import (
    ClientStatus,
    DownloadClientError,
    DownloadClientProtocol,
)
from app.services.download_clients.qbittorrent import QBittorrentClient
from app.services.download_clients.sabnzbd import SabnzbdClient

__all__ = [
    "ClientStatus",
    "DownloadClientError",
    "DownloadClientProtocol",
    "QBittorrentClient",
    "SabnzbdClient",
    "get_client",
    "pick_client",
]


def get_client(row: DownloadClient) -> DownloadClientProtocol:
    """Build a live client wrapper from a stored download client row."""
    implementation = (row.implementation or "").lower()
    if implementation == "qbittorrent":
        return QBittorrentClient(
            row.host,
            row.port,
            use_ssl=bool(row.use_ssl),
            username=row.username or "",
            password=row.password or "",
            category=row.category or "",
        )
    if implementation == "sabnzbd":
        return SabnzbdClient(
            row.host,
            row.port,
            use_ssl=bool(row.use_ssl),
            api_key=row.api_key or "",
            category=row.category or "",
            username=row.username or "",
            password=row.password or "",
        )
    raise DownloadClientError(f"Unsupported download client '{row.implementation}'")


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
