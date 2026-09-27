from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Indexer
from app.services.indexers.base import IndexerError, ReleaseCandidate
from app.services.indexers.newznab import search_newznab
from app.services.release_scoring import score_release

logger = logging.getLogger("musicarr.indexer")

DEFAULT_CATEGORIES = [3000, 3010, 3040]


def parse_categories(raw: str | None) -> list[int]:
    if not raw:
        return list(DEFAULT_CATEGORIES)
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        parts = [p.strip() for p in str(raw).replace(";", ",").split(",")]
        return [int(p) for p in parts if p.isdigit()] or list(DEFAULT_CATEGORIES)
    if isinstance(data, list):
        out = []
        for item in data:
            try:
                out.append(int(item))
            except (TypeError, ValueError):
                continue
        return out or list(DEFAULT_CATEGORIES)
    return list(DEFAULT_CATEGORIES)


def enabled_indexers(db: Session) -> list[Indexer]:
    return list(
        db.scalars(
            select(Indexer)
            .where(Indexer.enabled.is_(True))
            .order_by(Indexer.priority.asc(), Indexer.id.asc())
        ).all()
    )


def search_album(
    db: Session,
    artist_name: str,
    album_title: str,
    *,
    year: str | None = None,
    query_override: str | None = None,
) -> tuple[list[ReleaseCandidate], list[dict]]:
    """Query every enabled indexer for an album, scored best-first.

    Returns (results, errors) — a per-indexer failure (bad API key, network
    error, malformed response) no longer disappears into the server log
    only. A caller that discards `errors` gets the old behavior; callers
    that surface them let the user tell "genuinely no results" apart from
    "your indexer is misconfigured", which otherwise look identical.

    `query_override` replaces the free-text search term sent to indexers
    (the automatic artist+album search misses sometimes — a manual search
    box lets the user try their own wording instead) — scoring still ranks
    results against the real artist/album so a manual search still shows how
    good a match each hit actually is, just widens what indexers return.
    """
    query = (query_override or "").strip() or " ".join(
        p for p in [(artist_name or "").strip(), (album_title or "").strip()] if p
    )
    if not query:
        return [], []

    results: list[ReleaseCandidate] = []
    errors: list[dict] = []
    for indexer in enabled_indexers(db):
        protocol = (indexer.protocol or "usenet").lower()
        try:
            found = search_newznab(
                indexer.base_url,
                indexer.api_key,
                query,
                parse_categories(indexer.categories),
                protocol,
                artist=artist_name or "",
                album=album_title or "",
            )
        except IndexerError as exc:
            logger.warning("Indexer '%s' search failed: %s", indexer.name, exc)
            errors.append(
                {"indexer_id": indexer.id, "indexer_name": indexer.name, "message": str(exc)}
            )
            continue
        except Exception as exc:  # noqa: BLE001
            logger.exception("Indexer '%s' search crashed", indexer.name)
            errors.append(
                {
                    "indexer_id": indexer.id,
                    "indexer_name": indexer.name,
                    "message": f"Unexpected error: {exc}",
                }
            )
            continue

        for candidate in found:
            candidate.indexer_id = indexer.id
            candidate.indexer_name = indexer.name
            candidate.protocol = protocol
            candidate.score = score_release(
                candidate.title,
                candidate.size,
                candidate.seeders,
                protocol,
                artist_name or "",
                album_title or "",
                year=year,
            )
            results.append(candidate)

    results.sort(key=lambda c: (c.score, c.seeders, c.size), reverse=True)
    return results, errors


def pick_best(
    candidates: list[ReleaseCandidate],
    min_score: float = 10.0,
) -> ReleaseCandidate | None:
    for candidate in candidates:
        if candidate.score < min_score:
            continue
        if not candidate.grab_url:
            continue
        return candidate
    return None
