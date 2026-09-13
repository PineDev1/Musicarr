from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from urllib.parse import urlparse


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
    """Build the client's HTTP base URL.

    Accepts:
      - hostname
      - host:port
      - host:port/path
      - http(s)://host[:port][/path]
    Never appends port twice; preserves URL base paths (e.g. /qbittorrent).
    """
    text = (host or "localhost").strip().rstrip("/")
    if not text:
        text = "localhost"

    if "://" not in text:
        # Bare host, host:port, or host:port/path — normalize via urlparse.
        text = f"{'https' if use_ssl else 'http'}://{text}"

    parsed = urlparse(text)
    scheme = parsed.scheme or ("https" if use_ssl else "http")
    hostname = parsed.hostname or "localhost"
    # Prefer explicit port in the host string; else use the form port.
    resolved_port = parsed.port if parsed.port is not None else int(port or 0)
    path = (parsed.path or "").rstrip("/")

    if resolved_port and not (
        (scheme == "http" and resolved_port == 80)
        or (scheme == "https" and resolved_port == 443)
    ):
        netloc = f"{hostname}:{resolved_port}"
    else:
        netloc = hostname

    if path:
        return f"{scheme}://{netloc}{path}"
    return f"{scheme}://{netloc}"
