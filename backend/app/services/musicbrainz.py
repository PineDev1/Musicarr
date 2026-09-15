from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

import httpx

logger = logging.getLogger("musicarr.musicbrainz")

API_BASE = "https://musicbrainz.org/ws/2"
USER_AGENT = "Musicarr/1.6 (https://github.com/PineDev1/Musicarr)"
MIN_INTERVAL_S = 1.25
SEARCH_SCORE_MIN = 80
MATCH_RATIO_MIN = 0.78
MAX_RETRIES = 5

_lock = threading.Lock()
_last_request = 0.0
_rg_cache: dict[str, list["ReleaseGroup"]] = {}
_credit_cache: dict[str, tuple["CreditArtist", ...]] = {}

_EDITION_NOISE = re.compile(
    r"\s*[\(\[][^)\]]*(remaster|deluxe|expanded|anniversary|edition|bonus|explicit|"
    r"clean|super\s*deluxe|legacy|reissue|expanded)[^)\]]*[\)\]]",
    re.I,
)
_PUNCT = re.compile(r"[^\w\s]", re.U)
_SPACE = re.compile(r"\s+")


@dataclass
class CreditArtist:
    mbid: str
    name: str
    joinphrase: str = ""


@dataclass
class ReleaseGroup:
    mbid: str
    title: str
    primary_type: str  # album | ep | single | compilation | other
    year: str = ""
    secondary_types: tuple[str, ...] = ()
    credits: tuple[CreditArtist, ...] = ()


@dataclass
class CatalogResult:
    release_groups: list[ReleaseGroup] = field(default_factory=list)
    collaborators: list[CreditArtist] = field(default_factory=list)
    error: str | None = None


def normalize_title(title: str) -> str:
    t = (title or "").strip().lower()
    t = _EDITION_NOISE.sub("", t)
    # Strip (feat. X) / feat. X so provider collab titles match MB clean titles
    t = re.sub(
        r"\s*[\(\[][^)\]]*(?:feat\.?|ft\.?|featuring)[^)\]]*[\)\]]",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(r"\s*(?:feat\.?|ft\.?|featuring)\s+.+$", "", t, flags=re.I)
    t = _PUNCT.sub(" ", t)
    t = _SPACE.sub(" ", t).strip()
    return t


def _year_prefix(date_str: str | None) -> str:
    if not date_str:
        return ""
    text = str(date_str).strip()
    return text[:4] if len(text) >= 4 and text[:4].isdigit() else ""


def _map_primary_type(raw: str | None, secondary: list[str] | None = None) -> str:
    sec = [s.lower() for s in (secondary or [])]
    if any(s == "compilation" or "compilation" in s for s in sec):
        return "compilation"
    key = (raw or "").strip().lower()
    if key in {"ep"}:
        return "ep"
    if key in {"single"}:
        return "single"
    if key in {"album", "other", ""}:
        return "album" if key == "album" or not key else "other"
    if "compil" in key:
        return "compilation"
    return "other"


def _should_keep_rg(secondary: list[str] | None) -> bool:
    sec = {s.lower() for s in (secondary or [])}
    skip = {"live", "demo", "dj-mix", "mixtape/street", "interview", "audiobook", "spokenword"}
    return not bool(sec & skip)


def _throttle() -> None:
    global _last_request
    with _lock:
        now = time.monotonic()
        wait = MIN_INTERVAL_S - (now - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


_consecutive_failures = 0
_CIRCUIT_OPEN_AFTER = 8


def _catalog_mode() -> str:
    """local | live | local_with_live_fallback"""
    try:
        from app.core.database import SessionLocal
        from app.services.settings_service import ensure_settings

        db = SessionLocal()
        try:
            row = ensure_settings(db)
            mode = (getattr(row, "mb_catalog_mode", None) or "").strip().lower()
        finally:
            db.close()
        if mode in {"local", "live", "local_with_live_fallback"}:
            return mode
    except Exception:  # noqa: BLE001
        pass
    return "local"


def _local_available() -> bool:
    try:
        from app.services import mb_local

        return mb_local.is_available()
    except Exception:  # noqa: BLE001
        return False


def _prefer_local() -> bool:
    mode = _catalog_mode()
    if mode == "live":
        return False
    return _local_available()


def _allow_live() -> bool:
    mode = _catalog_mode()
    if mode == "live":
        return True
    if mode == "local_with_live_fallback":
        return True
    # local-only: still allow live if catalog missing so app isn't bricked
    return not _local_available()


def reload_local_store() -> None:
    try:
        from app.services import mb_local

        mb_local.reload()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to reload local MusicBrainz store")


def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    global _consecutive_failures
    if _consecutive_failures >= _CIRCUIT_OPEN_AFTER:
        return {"_error": "MusicBrainz temporarily unavailable (circuit open)", "_status": 503}

    query = {"fmt": "json", **(params or {})}
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        _throttle()
        try:
            with httpx.Client(timeout=30.0, headers=headers) as client:
                res = client.get(f"{API_BASE}{path}", params=query)
                if res.status_code in {503, 429, 502}:
                    # MB often sends Retry-After: 0 — never sleep 0 or we hammer 503s.
                    backoff = 1.5 * (attempt + 1)
                    raw_ra = (res.headers.get("Retry-After") or "").strip()
                    try:
                        retry_after = max(float(raw_ra), backoff) if raw_ra else backoff
                    except ValueError:
                        retry_after = backoff
                    logger.warning(
                        "MusicBrainz %s (attempt %s/%s), retry in %.1fs",
                        res.status_code,
                        attempt + 1,
                        MAX_RETRIES,
                        retry_after,
                    )
                    time.sleep(retry_after)
                    continue
                if res.status_code >= 400:
                    try:
                        body = res.json()
                        err = body.get("error") or body.get("help") or res.text[:200]
                    except Exception:  # noqa: BLE001
                        err = res.text[:200]
                    logger.warning(
                        "MusicBrainz request failed %s: %s %s", path, res.status_code, err
                    )
                    _consecutive_failures += 1
                    return {"_error": str(err), "_status": res.status_code}
                _consecutive_failures = 0
                return res.json()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(1.2 * (attempt + 1))
    _consecutive_failures += 1
    logger.warning("MusicBrainz request failed %s: %s", path, last_exc)
    return {"_error": str(last_exc or "MusicBrainz unavailable")}


def resolve_artist(name: str) -> str | None:
    """Return MusicBrainz artist MBID when the search hit is confident."""
    q = (name or "").strip()
    if not q:
        return None
    if _prefer_local():
        from app.services import mb_local

        hit = mb_local.resolve_artist(q)
        if hit:
            return hit
        if not _allow_live():
            return None
    elif not _allow_live():
        return None

    data = _get("/artist/", {"query": f'artist:"{q}"', "limit": 5})
    artists = data.get("artists") or []
    if not artists:
        data = _get("/artist/", {"query": q, "limit": 5})
        artists = data.get("artists") or []
    want = normalize_title(q)
    best_id: str | None = None
    best_score = -1
    for row in artists:
        score = int(row.get("score") or 0)
        hit_name = normalize_title(row.get("name") or "")
        if hit_name == want and score >= SEARCH_SCORE_MIN:
            return str(row.get("id") or "") or None
        if hit_name == want and score > best_score:
            best_score = score
            best_id = str(row.get("id") or "") or None
        elif score >= 90 and SequenceMatcher(None, hit_name, want).ratio() >= 0.9:
            if score > best_score:
                best_score = score
                best_id = str(row.get("id") or "") or None
    if best_id and best_score >= SEARCH_SCORE_MIN:
        return best_id
    return None


def _parse_credits(row: dict[str, Any]) -> list[CreditArtist]:
    out: list[CreditArtist] = []
    credit = row.get("artist-credit") or []
    for part in credit:
        artist = part.get("artist") or {}
        mbid = str(artist.get("id") or "").strip()
        name = str(artist.get("name") or part.get("name") or "").strip()
        joinphrase = str(part.get("joinphrase") or "")
        if mbid and name:
            out.append(CreditArtist(mbid=mbid, name=name, joinphrase=joinphrase))
    return out


def format_artist_credit(credits: tuple[CreditArtist, ...] | list[CreditArtist]) -> str:
    """Rebuild MusicBrainz artist-credit including join phrases (feat., &, etc.)."""
    if not credits:
        return ""
    return "".join(f"{c.name}{c.joinphrase or ''}" for c in credits).strip()


def search_release_group_for_artist(
    title: str,
    artist_mbid: str,
    *,
    limit: int = 5,
) -> ReleaseGroup | None:
    """Find a release-group by title for an artist and return it with artist-credit."""
    if _prefer_local():
        from app.services import mb_local

        hit = mb_local.search_release_group_for_artist(title, artist_mbid, limit=limit)
        if hit:
            return hit
        if not _allow_live():
            return None
    elif not _allow_live():
        return None

    import re

    search_title = re.sub(
        r"\s*[\(\[][^)\]]*(?:feat\.?|ft\.?|featuring)[^)\]]*[\)\]]",
        "",
        title or "",
        flags=re.I,
    ).strip() or (title or "")
    # Drop trailing feat. without brackets too
    search_title = re.sub(
        r"\s*(?:feat\.?|ft\.?|featuring)\s+.+$",
        "",
        search_title,
        flags=re.I,
    ).strip() or search_title
    clean = normalize_title(search_title)
    aid = (artist_mbid or "").strip()
    if not clean or not aid:
        return None
    queries = [
        f'releasegroup:"{search_title}" AND arid:{aid}',
        f"releasegroup:{search_title} AND arid:{aid}",
    ]
    rows: list[dict] = []
    seen_ids: set[str] = set()
    for q in queries:
        data = _get("/release-group/", {"query": q, "limit": limit})
        for row in data.get("release-groups") or []:
            rid = str(row.get("id") or "")
            if not rid or rid in seen_ids:
                continue
            seen_ids.add(rid)
            rows.append(row)

    # Provider titles like "Life Goes On (feat. Luke Combs)" under Luke often only
    # exist as Ed Sheeran's RG — arid:luke search returns nothing.
    if not rows and re.search(r"feat\.?|ft\.?|featuring", title or "", re.I):
        data = _get(
            "/release-group/",
            {"query": f'releasegroup:"{search_title}"', "limit": max(limit, 10)},
        )
        for row in data.get("release-groups") or []:
            rid = str(row.get("id") or "")
            if not rid or rid in seen_ids:
                continue
            seen_ids.add(rid)
            rows.append(row)

    best: ReleaseGroup | None = None
    best_score = 0.0
    for row in rows:
        rg = ReleaseGroup(
            mbid=str(row.get("id") or ""),
            title=str(row.get("title") or ""),
            primary_type=_map_primary_type(row.get("primary-type"), row.get("secondary-types") or []),
            year=_year_prefix(row.get("first-release-date")),
            secondary_types=tuple(str(s) for s in (row.get("secondary-types") or [])),
            credits=tuple(_parse_credits(row)),
        )
        if not rg.credits:
            enrich_release_group_credits(rg)
        credit_mbids = {c.mbid for c in rg.credits}
        cand = normalize_title(rg.title)
        ratio = SequenceMatcher(None, clean, cand).ratio()
        if cand == clean or clean in cand or cand in clean:
            ratio = 1.0
        score = int(row.get("score") or 0)
        combined = ratio + (0.05 if score >= 90 else 0)
        if aid in credit_mbids:
            combined += 0.15
        elif rg.credits and aid not in credit_mbids:
            # Wide search hit that doesn't credit this artist at all
            combined -= 0.35
        if combined > best_score:
            best_score = combined
            best = rg
    if best and best_score >= 0.75:
        return best
    return None


def list_official_release_groups(mbid: str, *, use_cache: bool = True) -> list[ReleaseGroup]:
    return fetch_catalog(mbid, use_cache=use_cache).release_groups


def count_release_groups(mbid: str) -> int | None:
    """Release-group count for search UI; prefers local catalog."""
    key = (mbid or "").strip()
    if not key:
        return None
    if _prefer_local():
        from app.services import mb_local

        return mb_local.count_release_groups(key)
    if not _allow_live():
        return None
    return len(fetch_catalog(key).release_groups)


def fetch_catalog(mbid: str, *, use_cache: bool = True) -> CatalogResult:
    """Browse release-groups for an artist. MusicBrainz is the catalog source of truth."""
    key = (mbid or "").strip()
    if not key:
        return CatalogResult(error="No MusicBrainz artist id")
    if use_cache and key in _rg_cache:
        return CatalogResult(release_groups=list(_rg_cache[key]))

    if _prefer_local():
        from app.services import mb_local

        local = mb_local.fetch_catalog(key)
        if not local.error:
            # Drop "other" types to match live filter behavior
            filtered = [rg for rg in local.release_groups if rg.primary_type != "other"]
            _rg_cache[key] = filtered
            return CatalogResult(release_groups=list(filtered), collaborators=list(local.collaborators))
        if not _allow_live():
            return local
    elif not _allow_live():
        return CatalogResult(error="Local MusicBrainz catalog is not installed")

    out: list[ReleaseGroup] = []
    collaborators: dict[str, CreditArtist] = {}
    offset = 0
    while offset < 1000:
        # Do NOT pass status= — invalid on release-group browse (returns an error body).
        data = _get(
            "/release-group",
            {
                "artist": key,
                "limit": 100,
                "offset": offset,
            },
        )
        if data.get("_error"):
            return CatalogResult(error=str(data["_error"]))
        rows = data.get("release-groups") or []
        if not rows:
            break
        for row in rows:
            secondary = row.get("secondary-types") or []
            if not _should_keep_rg(secondary):
                continue
            primary = row.get("primary-type")
            mapped = _map_primary_type(primary, secondary)
            if mapped == "other":
                continue
            first_date = row.get("first-release-date") or ""
            credits = _parse_credits(row)
            for c in credits:
                if c.mbid != key:
                    collaborators[c.mbid] = c
            out.append(
                ReleaseGroup(
                    mbid=str(row.get("id") or ""),
                    title=str(row.get("title") or ""),
                    primary_type=mapped,
                    year=_year_prefix(first_date),
                    secondary_types=tuple(str(s) for s in secondary),
                    credits=tuple(credits),
                )
            )
        count = int(data.get("release-group-count") or 0)
        offset += len(rows)
        if offset >= count or len(rows) < 100:
            break

    _rg_cache[key] = out
    return CatalogResult(
        release_groups=list(out),
        collaborators=list(collaborators.values()),
    )


def cover_url_for_release_group(rg_mbid: str) -> str | None:
    key = (rg_mbid or "").strip()
    if not key:
        return None
    return f"https://coverartarchive.org/release-group/{key}/front-250"


def clear_cache() -> None:
    global _consecutive_failures
    _rg_cache.clear()
    _credit_cache.clear()
    _consecutive_failures = 0


def enrich_release_group_credits(rg: ReleaseGroup) -> ReleaseGroup:
    """Fetch artist-credit (browse omits it; lookup needs inc=artists)."""
    if rg.credits or not rg.mbid:
        return rg
    cached = _credit_cache.get(rg.mbid)
    if cached is not None:
        rg.credits = cached
        return rg

    if _prefer_local():
        from app.services import mb_local

        mb_local.enrich_release_group_credits(rg)
        if rg.credits:
            _credit_cache[rg.mbid] = rg.credits
            return rg
        if not _allow_live():
            _credit_cache[rg.mbid] = ()
            return rg
    elif not _allow_live():
        _credit_cache[rg.mbid] = ()
        return rg

    data = _get(f"/release-group/{rg.mbid}", {"inc": "artists"})
    if data.get("_error") or not data.get("id"):
        _credit_cache[rg.mbid] = ()
        return rg
    credits = tuple(_parse_credits(data))
    _credit_cache[rg.mbid] = credits
    rg.credits = credits
    return rg


def collaborator_names_for_rg(rg: ReleaseGroup, primary_mbid: str | None = None) -> list[str]:
    """Other credited artists on a release-group (excludes primary MBID when known)."""
    primary = (primary_mbid or "").strip()
    names: list[str] = []
    seen: set[str] = set()
    for credit in rg.credits:
        if primary and credit.mbid == primary:
            continue
        key = normalize_title(credit.name)
        if not key or key in seen:
            continue
        seen.add(key)
        names.append(credit.name)
    return names


def match_release(
    title: str,
    year: str | None,
    album_type: str,
    catalog: list[ReleaseGroup],
) -> ReleaseGroup | None:
    """Return the best matching official release-group, or None."""
    want = normalize_title(title)
    if not want or not catalog:
        return None
    want_year = _year_prefix(year)
    want_type = (album_type or "album").lower()
    best: ReleaseGroup | None = None
    best_score = 0.0
    for rg in catalog:
        cand = normalize_title(rg.title)
        if not cand:
            continue
        ratio = SequenceMatcher(None, want, cand).ratio()
        if want == cand:
            ratio = 1.0
        elif want in cand or cand in want:
            ratio = max(ratio, 0.9)
        if want_type and rg.primary_type == want_type:
            ratio += 0.03
        elif want_type == "album" and rg.primary_type == "compilation":
            ratio -= 0.05
        if want_year and rg.year:
            if want_year == rg.year:
                ratio += 0.05
            elif abs(int(want_year) - int(rg.year)) <= 1:
                ratio += 0.02
            else:
                ratio -= 0.08
        if ratio > best_score:
            best_score = ratio
            best = rg
    if best and best_score >= MATCH_RATIO_MIN:
        return best
    return None


def match_provider_album(rg: ReleaseGroup, provider_albums: list[Any]) -> Any | None:
    """Find the best provider album for a MusicBrainz release-group."""
    want = normalize_title(rg.title)
    if not want:
        return None
    best = None
    best_score = 0.0
    for alb in provider_albums:
        title = normalize_title(getattr(alb, "title", "") or "")
        if not title:
            continue
        ratio = SequenceMatcher(None, want, title).ratio()
        if want == title:
            ratio = 1.0
        elif want in title or title in want:
            ratio = max(ratio, 0.9)
        year = _year_prefix(getattr(alb, "release_date", None))
        if year and rg.year:
            if year == rg.year:
                ratio += 0.05
            elif abs(int(year) - int(rg.year)) <= 1:
                ratio += 0.02
            else:
                ratio -= 0.06
        atype = (getattr(alb, "album_type", None) or "album").lower()
        if atype == rg.primary_type:
            ratio += 0.02
        if ratio > best_score:
            best_score = ratio
            best = alb
    if best and best_score >= MATCH_RATIO_MIN:
        return best
    return None


def is_official_match(
    title: str,
    year: str | None,
    album_type: str,
    catalog: list[ReleaseGroup],
) -> bool:
    return match_release(title, year, album_type, catalog) is not None
