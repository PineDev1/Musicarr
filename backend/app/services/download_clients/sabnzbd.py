from __future__ import annotations

import logging

import httpx

from app.services.download_clients.base import (
    ClientStatus,
    DownloadClientError,
    base_url,
)

logger = logging.getLogger("musicarr.client.sabnzbd")

TIMEOUT = httpx.Timeout(30.0, connect=10.0)

QUEUE_FAILED_STATES = {"failed"}
HISTORY_ACTIVE_STATES = {"extracting", "verifying", "repairing", "running", "queued", "moving"}


class SabnzbdClient:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        use_ssl: bool = False,
        api_key: str = "",
        category: str = "musicarr",
        username: str = "",
        password: str = "",
        verify_ssl: bool = True,
    ) -> None:
        self.base = base_url(host, port, use_ssl)
        self.api_key = (api_key or "").strip()
        self.category = (category or "").strip()
        self.username = (username or "").strip()
        self.password = password or ""
        self.verify_ssl = verify_ssl
        self._client: httpx.Client | None = None

    # -- plumbing ---------------------------------------------------------
    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base,
                timeout=TIMEOUT,
                follow_redirects=True,
                verify=self.verify_ssl,
                headers={"User-Agent": "Musicarr/1.4"},
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "SabnzbdClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def _call(self, mode: str, **params) -> dict:
        if not self.api_key:
            raise DownloadClientError("SABnzbd API key is not set")
        query = {"mode": mode, "output": "json", "apikey": self.api_key}
        if self.username:
            query["ma_username"] = self.username
            query["ma_password"] = self.password
        for key, value in params.items():
            if value is not None and value != "":
                query[key] = value
        try:
            resp = self._http().get("/api", params=query)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise DownloadClientError(
                f"SABnzbd returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise DownloadClientError(
                f"Cannot reach SABnzbd at {self.base}. "
                f"If Musicarr is in Docker, use host.docker.internal or the compose "
                f"service name — not localhost. ({exc})"
            ) from exc
        try:
            data = resp.json()
        except ValueError as exc:
            raise DownloadClientError("SABnzbd returned an invalid response") from exc
        if not isinstance(data, dict):
            raise DownloadClientError("SABnzbd returned an unexpected response")
        if data.get("status") is False and data.get("error"):
            raise DownloadClientError(f"SABnzbd error: {data['error']}")
        return data

    # -- API --------------------------------------------------------------
    def test(self) -> tuple[bool, str]:
        try:
            data = self._call("version")
            version = str(data.get("version") or "unknown")
            return True, f"Connected to SABnzbd {version}"
        except DownloadClientError as exc:
            return False, str(exc)
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
        finally:
            self.close()

    def add_url(self, url: str, category: str = "") -> str:
        if not url:
            raise DownloadClientError("No download URL for this release")
        cat = (category or self.category or "").strip()
        data = self._call("addurl", name=url, cat=cat)
        ids = data.get("nzo_ids") or []
        if not ids:
            raise DownloadClientError("SABnzbd did not accept the NZB")
        return str(ids[0])

    def _queue_slot(self, item_id: str) -> dict | None:
        data = self._call("queue", limit=250)
        slots = ((data.get("queue") or {}).get("slots")) or []
        return next((s for s in slots if str(s.get("nzo_id")) == item_id), None)

    def _history_slot(self, item_id: str) -> dict | None:
        data = self._call("history", limit=250)
        slots = ((data.get("history") or {}).get("slots")) or []
        return next((s for s in slots if str(s.get("nzo_id")) == item_id), None)

    def get_status(self, item_id: str) -> ClientStatus:
        if not item_id:
            return ClientStatus(state="unknown")

        slot = self._queue_slot(item_id)
        if slot is not None:
            try:
                percent = float(slot.get("percentage") or 0.0) / 100.0
            except (TypeError, ValueError):
                percent = 0.0
            status = str(slot.get("status") or "").lower()
            state = "failed" if status in QUEUE_FAILED_STATES else "downloading"
            return ClientStatus(
                item_id=item_id,
                state=state,
                progress=max(0.0, min(0.99, percent)),
                title=str(slot.get("filename") or ""),
            )

        slot = self._history_slot(item_id)
        if slot is None:
            return ClientStatus(item_id=item_id, state="failed")

        status = str(slot.get("status") or "").lower()
        storage = str(slot.get("storage") or slot.get("path") or "").strip()
        title = str(slot.get("name") or slot.get("nzb_name") or "")
        if status == "completed" and storage:
            return ClientStatus(
                item_id=item_id,
                state="completed",
                progress=1.0,
                output_path=storage,
                title=title,
            )
        if status in HISTORY_ACTIVE_STATES or (status == "completed" and not storage):
            return ClientStatus(
                item_id=item_id, state="downloading", progress=0.99, title=title
            )
        return ClientStatus(item_id=item_id, state="failed", title=title)

    def remove(self, item_id: str, *, delete_data: bool = False) -> None:
        if not item_id:
            return
        try:
            self._call(
                "history",
                name="delete",
                value=item_id,
                del_files=1 if delete_data else 0,
            )
        except DownloadClientError as exc:
            logger.warning("Could not remove SABnzbd item %s: %s", item_id, exc)
