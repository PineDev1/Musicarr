from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReleaseCandidate:
    title: str
    size: int = 0
    seeders: int = 0
    protocol: str = "usenet"
    download_url: str = ""
    magnet_url: str = ""
    indexer_id: int = 0
    indexer_name: str = ""
    score: float = 0.0

    @property
    def grab_url(self) -> str:
        """URL to hand to the download client (magnet preferred for torrents)."""
        return self.magnet_url or self.download_url


class IndexerError(Exception):
    pass
