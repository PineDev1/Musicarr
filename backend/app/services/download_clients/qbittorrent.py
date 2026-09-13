from __future__ import annotations

import base64
import logging
import re
import time
from urllib.parse import parse_qs, urlparse

import httpx

from app.services.download_clients.base import (
    ClientStatus,
    DownloadClientError,
    base_url,
)

logger = logging.getLogger("musicarr.client.qbittorrent")

TIMEOUT = httpx.Timeout(30.0, connect=10.0)

DOWNLOADING_STATES = {
    "downloading",
    "metadl",
    "stalleddl",
    "queueddl",
    "forceddl",
    "allocating",
    "checkingdl",
    "pauseddl",
    "checkingresumedata",
    "moving",
}
COMPLETED_STATES = {
    "uploading",
    "stalledup",
    "queuedup",
    "pausedup",
    "forcedup",
    "checkingup",
    "completed",
}
FAILED_STATES = {"error", "missingfiles", "unknown"}

HEX_HASH = re.compile(r"^[0-9a-fA-F]{40}$")


def hash_from_magnet(url: str) -> str:
    """Extract the info hash from a magnet link, normalised to lowercase hex."""
    if not url.startswith("magnet:"):
        return ""
    params = parse_qs(urlparse(url).query)
    for xt in params.get("xt", []):
        if not xt.lower().startswith("urn:btih:"):
            continue
        raw = xt.split(":")[-1].strip()
        if HEX_HASH.match(raw):
            return raw.lower()
        if len(raw) == 32:
            try:
                return base64.b32decode(raw.upper()).hex()
            except (ValueError, TypeError):
                continue
    return ""


class QBittorrentClient:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        use_ssl: bool = False,
        username: str = "",
        password: str = "",
        category: str = "musicarr",
    ) -> None:
        self.base = base_url(host, port, use_ssl)
        self.username = (username or "").strip()
        self.password = password or ""
        self.category = (category or "").strip()
        self._client: httpx.Client | None = None

    # -- plumbing ---------------------------------------------------------
    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base,
                timeout=TIMEOUT,
                follow_redirects=True,
                headers={
                    "User-Agent": "Musicarr/1.2",
                    "Referer": self.base,
                    "Origin": self.base,
                },
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "QBittorrentClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def login(self) -> None:
        if not self.username:
            # qBittorrent can bypass auth for local clients; nothing to do.
            return
        client = self._http()
        try:
            resp = client.post(
                "/api/v2/auth/login",
                data={"username": self.username, "password": self.password},
            )
        except httpx.HTTPError as exc:
            raise DownloadClientError(f"Cannot reach qBittorrent: {exc}") from exc
        if resp.status_code == 403:
            raise DownloadClientError(
                "qBittorrent refused the login (too many failed attempts or banned IP)"
            )
        if resp.status_code >= 400:
            raise DownloadClientError(f"qBittorrent login returned HTTP {resp.status_code}")
        if resp.text.strip().lower() != "ok.":
            raise DownloadClientError("qBittorrent rejected the username or password")

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        client = self._http()
        try:
            resp = client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise DownloadClientError(f"Cannot reach qBittorrent: {exc}") from exc
        if resp.status_code == 403:
            # Session may have expired — log in again and retry once.
            self.login()
            try:
                resp = client.request(method, path, **kwargs)
            except httpx.HTTPError as exc:
                raise DownloadClientError(f"Cannot reach qBittorrent: {exc}") from exc
        return resp

    # -- API --------------------------------------------------------------
    def test(self) -> tuple[bool, str]:
        try:
            self.login()
            resp = self._request("GET", "/api/v2/app/version")
            if resp.status_code >= 400:
                return False, f"qBittorrent returned HTTP {resp.status_code}"
            version = resp.text.strip() or "unknown"
            return True, f"Connected to qBittorrent {version}"
        except DownloadClientError as exc:
            return False, str(exc)
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
        finally:
            self.close()

    def _hashes_in_category(self, category: str) -> set[str]:
        params = {"category": category} if category else {}
        resp = self._request("GET", "/api/v2/torrents/info", params=params)
        if resp.status_code >= 400:
            return set()
        try:
            rows = resp.json()
        except ValueError:
            return set()
        return {str(r.get("hash", "")).lower() for r in rows if r.get("hash")}

    def add_url(self, url: str, category: str = "") -> str:
        """Add a magnet or .torrent URL and return its info hash."""
        if not url:
            raise DownloadClientError("No download URL for this release")
        self.login()
        cat = (category or self.category or "").strip()

        expected = hash_from_magnet(url)
        before: set[str] = set() if expected else self._hashes_in_category(cat)

        data = {"urls": url}
        if cat:
            data["category"] = cat
        resp = self._request("POST", "/api/v2/torrents/add", data=data)
        if resp.status_code >= 400 or resp.text.strip().lower() not in {"ok.", ""}:
            raise DownloadClientError(
                f"qBittorrent rejected the release (HTTP {resp.status_code} {resp.text.strip()[:120]})"
            )

        if expected:
            return expected

        # Non-magnet adds do not report the hash, so watch the category for it.
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            time.sleep(1.0)
            added = self._hashes_in_category(cat) - before
            if added:
                return sorted(added)[0]
        raise DownloadClientError(
            "qBittorrent accepted the release but it did not appear in the queue"
        )

    def get_status(self, item_id: str) -> ClientStatus:
        if not item_id:
            return ClientStatus(state="unknown")
        self.login()
        resp = self._request(
            "GET", "/api/v2/torrents/info", params={"hashes": item_id.lower()}
        )
        if resp.status_code >= 400:
            raise DownloadClientError(f"qBittorrent returned HTTP {resp.status_code}")
        try:
            rows = resp.json()
        except ValueError as exc:
            raise DownloadClientError("qBittorrent returned an invalid response") from exc
        if not rows:
            # Removed from the client — nothing left to import.
            return ClientStatus(item_id=item_id, state="failed")

        row = rows[0]
        raw_state = str(row.get("state", "")).lower()
        progress = float(row.get("progress") or 0.0)
        if raw_state in FAILED_STATES:
            state = "failed"
        elif raw_state in COMPLETED_STATES or progress >= 1.0:
            state = "completed"
        elif raw_state in DOWNLOADING_STATES:
            state = "downloading"
        else:
            state = "unknown"

        output = str(row.get("content_path") or "").strip()
        if not output:
            save_path = str(row.get("save_path") or "").strip()
            name = str(row.get("name") or "").strip()
            if save_path and name:
                output = f"{save_path.rstrip('/')}/{name}"
            else:
                output = save_path
        return ClientStatus(
            item_id=str(row.get("hash") or item_id),
            state=state,
            progress=max(0.0, min(1.0, progress)),
            output_path=output,
            title=str(row.get("name") or ""),
        )

    def remove(self, item_id: str, *, delete_data: bool = False) -> None:
        if not item_id:
            return
        try:
            self.login()
            self._request(
                "POST",
                "/api/v2/torrents/delete",
                data={
                    "hashes": item_id.lower(),
                    "deleteFiles": "true" if delete_data else "false",
                },
            )
        except DownloadClientError as exc:
            logger.warning("Could not remove torrent %s: %s", item_id, exc)
