from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class ClientStatus:
    item_id: str = ""
    # downloading | completed | failed | unknown
    state: str = "unknown"
    progress: float = 0.0
    output_path: str = ""
    title: str = ""


class DownloadClientError(Exception):
    pass


@runtime_checkable
class DownloadClientProtocol(Protocol):
    def test(self) -> tuple[bool, str]:
        """Verify connectivity and credentials."""

    def add_url(self, url: str, category: str = "") -> str:
        """Send a magnet/torrent/NZB URL to the client, returning its item id."""

    def get_status(self, item_id: str) -> ClientStatus:
        """Report progress and completion path for a previously added item."""

    def remove(self, item_id: str, *, delete_data: bool = False) -> None:
        """Remove a finished item from the client."""


def base_url(host: str, port: int, use_ssl: bool) -> str:
    """Build the client's HTTP base URL, tolerating a host with a scheme."""
    text = (host or "localhost").strip().rstrip("/")
    if "://" in text:
        scheme, _, rest = text.partition("://")
        if ":" in rest.split("/")[0]:
            return f"{scheme}://{rest}"
        return f"{scheme}://{rest}:{port}"
    scheme = "https" if use_ssl else "http"
    return f"{scheme}://{text}:{port}"
