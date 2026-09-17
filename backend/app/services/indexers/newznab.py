from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import httpx

from app.services.indexers.base import IndexerError, ReleaseCandidate

logger = logging.getLogger("musicarr.indexer")

TIMEOUT = httpx.Timeout(30.0, connect=10.0)
USER_AGENT = "Musicarr/1.2"

# Namespaced <newznab:attr> / <torznab:attr> children.
ATTR_TAG = re.compile(r"\}attr$")


def api_endpoint(base_url: str) -> str:
    """Resolve the newznab/torznab API endpoint from a configured base URL.

    Accepts bare hosts ("https://indexer.tld"), explicit API paths and
    Jackett/Prowlarr style feed URLs, which are already complete.
    """
    url = (base_url or "").strip().rstrip("/")
    if not url:
        raise IndexerError("Indexer base URL is not set")
    if "://" not in url:
        url = f"http://{url}"
    path = urlparse(url).path.lower().rstrip("/")
    if path.endswith("/api") or path.endswith("torznab") or path.endswith("newznab"):
        return url
    return f"{url}/api"


def _text(item: ET.Element, tag: str) -> str:
    node = item.find(tag)
    if node is not None and node.text:
        return node.text.strip()
    return ""


def _attrs(item: ET.Element) -> dict[str, str]:
    """Collect newznab:attr / torznab:attr name-value pairs."""
    out: dict[str, str] = {}
    for child in item:
        tag = child.tag
        if tag.endswith("attr") or ATTR_TAG.search(tag):
            name = (child.get("name") or "").strip().lower()
            if name:
                out[name] = (child.get("value") or "").strip()
    return out


def _to_int(value: str | None) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def _check_error(root: ET.Element) -> None:
    tag = root.tag.split("}")[-1].lower()
    if tag == "error":
        code = root.get("code") or "?"
        desc = root.get("description") or "Unknown indexer error"
        raise IndexerError(f"Indexer error {code}: {desc}")
    inner = root.find("error")
    if inner is not None:
        code = inner.get("code") or "?"
        desc = inner.get("description") or "Unknown indexer error"
        raise IndexerError(f"Indexer error {code}: {desc}")


def _parse_items(xml_text: str, protocol: str) -> list[ReleaseCandidate]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise IndexerError(f"Indexer returned invalid XML: {exc}") from exc
    _check_error(root)

    results: list[ReleaseCandidate] = []
    for item in root.iter():
        if item.tag.split("}")[-1].lower() != "item":
            continue
        title = _text(item, "title")
        if not title:
            continue
        attrs = _attrs(item)

        download_url = ""
        magnet_url = ""
        size = _to_int(_text(item, "size"))

        enclosure = None
        for child in item:
            if child.tag.split("}")[-1].lower() == "enclosure":
                enclosure = child
                break
        if enclosure is not None:
            url = (enclosure.get("url") or "").strip()
            if url.startswith("magnet:"):
                magnet_url = url
            elif url:
                download_url = url
            size = size or _to_int(enclosure.get("length"))

        link = _text(item, "link")
        if link.startswith("magnet:"):
            magnet_url = magnet_url or link
        elif link and not download_url:
            download_url = link

        for key in ("magneturl", "magnet"):
            if attrs.get(key, "").startswith("magnet:"):
                magnet_url = magnet_url or attrs[key]
        if not size:
            size = _to_int(attrs.get("size"))

        seeders = _to_int(attrs.get("seeders"))
        if not seeders and attrs.get("peers"):
            leechers = _to_int(attrs.get("leechers"))
            seeders = max(0, _to_int(attrs.get("peers")) - leechers)

        if not download_url and not magnet_url:
            continue

        results.append(
            ReleaseCandidate(
                title=title,
                size=size,
                seeders=seeders,
                protocol=protocol,
                download_url=download_url,
                magnet_url=magnet_url,
            )
        )
    return results


def _get(url: str, params: dict[str, str]) -> str:
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, params=params, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            return resp.text
    except httpx.HTTPStatusError as exc:
        raise IndexerError(
            f"Indexer returned HTTP {exc.response.status_code}"
        ) from exc
    except httpx.HTTPError as exc:
        raise IndexerError(f"Indexer request failed: {exc}") from exc


def search_newznab(
    base_url: str,
    api_key: str,
    query: str,
    categories: list[int] | None = None,
    protocol: str = "usenet",
    *,
    artist: str = "",
    album: str = "",
    limit: int = 100,
) -> list[ReleaseCandidate]:
    """Search a newznab or torznab indexer (identical query API).

    Falls back to the music-specific `t=music` search when the generic search
    returns nothing, which some indexers require for audio categories.
    """
    endpoint = api_endpoint(base_url)
    cats = ",".join(str(c) for c in (categories or []) if c)

    base_params = {"apikey": (api_key or "").strip(), "extended": "1", "limit": str(limit)}
    if cats:
        base_params["cat"] = cats

    candidates: list[ReleaseCandidate] = []
    if query:
        params = {**base_params, "t": "search", "q": query}
        candidates = _parse_items(_get(endpoint, params), protocol)

    if not candidates and (artist or album):
        music_params = {**base_params, "t": "music"}
        if artist:
            music_params["artist"] = artist
        if album:
            music_params["album"] = album
        try:
            candidates = _parse_items(_get(endpoint, music_params), protocol)
        except IndexerError as exc:
            # Not every indexer implements t=music; the generic miss stands.
            logger.debug("Music search unsupported on %s: %s", base_url, exc)

    return candidates


def check_indexer_connection(
    base_url: str,
    api_key: str,
    protocol: str = "usenet",
) -> tuple[bool, str]:
    """Verify credentials via t=caps, which every newznab/torznab exposes."""
    try:
        endpoint = api_endpoint(base_url)
        xml_text = _get(endpoint, {"t": "caps", "apikey": (api_key or "").strip()})
        root = ET.fromstring(xml_text)
        _check_error(root)
        tag = root.tag.split("}")[-1].lower()
        if tag not in {"caps", "rss"}:
            return False, f"Unexpected response root <{tag}>"
        return True, f"Connected to {urlparse(endpoint).netloc}"
    except IndexerError as exc:
        return False, str(exc)
    except ET.ParseError as exc:
        return False, f"Indexer returned invalid XML: {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
