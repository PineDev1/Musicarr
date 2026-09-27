from __future__ import annotations

import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Album, Artist
from app.services.indexers.base import ReleaseCandidate

logger = logging.getLogger("musicarr.indexer_engine")

# Bracketed/parenthesized source-and-quality tags an indexer release title
# almost always carries ("Album [FLAC][WEB]") — stripped before using the
# title verbatim as an Album.title (tier 3 of resolve_or_create_album_for_release).
# Deliberately narrow: real edition markers ("Deluxe Edition", "Remastered")
# are left alone since those are meaningful, not release-packaging noise.
_RELEASE_TAG_RE = re.compile(
    r"[\[\(]\s*(?:flac\d*|mp3|wav|alac|ape|dsd|24\s?bit|\d{2,4}\s?k(?:hz|bps)|web|cd|vinyl|"
    r"hi-?res|lossless|explicit)\b[^\]\)]*[\]\)]",
    re.I,
)


def _clean_release_title(title: str, artist_name: str = "") -> str:
    t = (title or "").strip()
    if artist_name:
        t = re.sub(rf"^\s*{re.escape(artist_name)}\s*[-–—:]\s*", "", t, flags=re.I)
    cleaned = _RELEASE_TAG_RE.sub("", t)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -–—")
    return cleaned or t


def resolve_or_create_album_for_release(db: Session, artist: Artist, release_title: str) -> Album:
    """Find the artist's existing album a release belongs to, or create one.

    The shared building block behind "even a loose single lands in the right
    folder": an indexer grab only ever names a release title, never a
    Musicarr Album id, so every caller that needs to attach a grabbed release
    to an album (artist-level search grabs, the importer's fallback for a
    stale/missing job.album_id) goes through this one function instead of
    re-implementing matching. Resolution order:

    1. An existing Album row for this artist whose title matches (same
       strict/loose normalized-title matching library.py's import path uses).
    2. A MusicBrainz release-group match, if this artist has (or can resolve)
       a MusicBrainz identity — created as "wanted" via the same
       _upsert_mb_album() artist.py already uses for catalog sync.
    3. A bare Album row created straight from the release title, when neither
       of the above found anything — same shape as library.py's own
       last-resort branch, but "wanted" (we don't have the file yet) instead
       of "downloaded".
    """
    from app.services.artists import (
        _legacy_id,
        _unique_provider_album_id,
        _upsert_mb_album,
        ensure_musicbrainz_identity,
    )
    from app.services.library import _slug_id

    title = (release_title or "").strip()
    if not title:
        raise ValueError("release_title is required")

    clean_title = _clean_release_title(title, artist.name)

    # 1. Existing album match, including any explicitly-linked artists'
    # albums (same-person rows across providers) — not just this row's own.
    albums = list(artist.albums or [])
    group_id = (getattr(artist, "link_group_id", None) or "").strip()
    if group_id:
        linked = (
            db.scalars(
                select(Artist).where(Artist.link_group_id == group_id, Artist.id != artist.id)
            )
            .unique()
            .all()
        )
        for a in linked:
            albums.extend(a.albums or [])
    candidate = _best_album_match(albums, clean_title) or _best_album_match(albums, title)
    if candidate:
        return candidate

    # 2. MusicBrainz resolution.
    mbid = ensure_musicbrainz_identity(db, artist)
    if mbid:
        from app.services import musicbrainz

        rg = musicbrainz.search_release_group_for_artist(clean_title, mbid)
        if rg:
            album = _upsert_mb_album(
                db,
                artist=artist,
                rg=rg,
                provider_hit=None,
                provider_name=artist.provider,
                existing_by_mbid={},
                existing_by_pid={},
                force_wanted=True,
            )
            db.commit()
            db.refresh(album)
            return album

    # 3. Bare fallback — no known album, no MB match.
    raw_pid = f"indexer:{_slug_id(clean_title)}"
    pid = _unique_provider_album_id(
        db, provider_name=artist.provider, provider_id=raw_pid, artist_id=artist.id
    )
    album = Album(
        provider=artist.provider,
        provider_id=pid,
        deezer_id=_legacy_id(artist.provider, pid),
        artist_id=artist.id,
        title=clean_title,
        album_type="album",
        release_date=None,
        cover_url=None,
        track_count=0,
        monitored=True,
        status="wanted",
    )
    db.add(album)
    db.commit()
    db.refresh(album)
    return album


_ALBUM_MATCH_RATIO = 0.9


def _best_album_match(albums: list[Album], release_title: str) -> Album | None:
    """Best-guess album match for a raw indexer release title.

    An indexer release title is noisy in a different way than an audio tag
    ("Artist - Album (2020) [FLAC][WEB]") — library.py's tag-oriented
    strict/loose matcher assumes edition markers are the only bracket
    content and skips its loose tier entirely once any brackets are present
    at all, which is nearly every real release title. Reuse release_scoring's
    _norm/_match_ratio instead — the same "how much of this album title
    shows up in the release name" check score_release already does for
    per-album search, applied here per-candidate-album.
    """
    from app.services.artists import _norm_album_title
    from app.services.release_scoring import _match_ratio, _norm

    # Exact-title check first, using the same normalizer artist-page display
    # merging (merge_album_rows) uses — guarantees this never creates a
    # second Album row for a title the UI would already treat as identical.
    exact_key = _norm_album_title(release_title)
    if exact_key:
        exact = next((a for a in albums if _norm_album_title(a.title) == exact_key), None)
        if exact:
            return exact

    name = _norm(release_title)
    if not name:
        return None
    best: tuple[float, Album] | None = None
    for a in albums:
        ratio = _match_ratio(a.title, name)
        if ratio >= _ALBUM_MATCH_RATIO and (best is None or ratio > best[0]):
            best = (ratio, a)
    return best[1] if best else None


def _match_album_for_title(artist: Artist, release_title: str) -> Album | None:
    """Read-only best-guess match against just this artist's own albums —
    used to annotate artist-level search results, which must never create
    rows just by being displayed."""
    return _best_album_match(list(artist.albums or []), release_title)


def search_artist_catalog(
    db: Session, artist: Artist
) -> tuple[list[tuple[ReleaseCandidate, Album | None]], list[dict]]:
    """Query indexers by artist name alone, annotated with a best-guess
    existing-album match per result (None = new/unsorted release).

    Reuses search_album's indexer fan-out/scoring as-is by passing an empty
    album title — search_album and the newznab query layer already support
    that shape (an artist-only t=search query, falling back to t=music).
    """
    from app.services.indexers.search import search_album

    candidates, errors = search_album(db, artist.name, "")
    annotated = [(c, _match_album_for_title(artist, c.title)) for c in candidates]
    return annotated, errors


def try_auto_grab_release(db: Session, artist: Artist, album: Album, settings) -> bool:
    """Auto-grab the top-scored indexer result for one wanted album.

    Shared by monitor.py's new-album-detection hook and WantedIndexerSweep's
    periodic pass over the existing Wanted list — one implementation instead
    of two copies of the same score-and-grab logic. Opt-in (see
    AppSettings.auto_grab_indexers_enabled / Artist.auto_grab_override,
    resolved by artists.effective_auto_grab) and gated well above
    release_scoring.REJECT_CEILING. Every outcome is logged to HistoryEvent
    for auditability, since this is an automatic (non-manual) indexer action.
    """
    from app.services.acquisition_actions import GrabError, grab_release_for_album
    from app.services.history import add_history
    from app.services.indexers.search import pick_best, search_album

    candidates, _errors = search_album(db, artist.name, album.title, year=None)
    min_score = float(getattr(settings, "auto_grab_min_score", 20.0) or 20.0)
    best = pick_best(candidates, min_score=min_score)
    if not best:
        return False
    try:
        grab_release_for_album(
            db,
            album,
            grab_url=best.grab_url,
            protocol=best.protocol,
            title=best.title,
            indexer_id=best.indexer_id or None,
        )
    except GrabError as exc:
        add_history(
            db,
            "auto_grab_failed",
            f"Auto-grab failed for {artist.name} – {album.title}: {exc}",
        )
        return False
    add_history(
        db,
        "auto_grab",
        f"Auto-grabbed '{best.title}' (score {best.score:.1f}) for {artist.name} – {album.title}",
    )
    return True


class WantedIndexerSweep:
    """Periodically re-searches indexers for every already-wanted album —
    not just brand-new detections (monitor.py's job). Catches releases that
    weren't available on any indexer the first time an album was checked.

    A no-op for any artist that hasn't opted into auto-grab (effective_auto_grab),
    which stays default-off — this sweep makes the engine capable of working
    through the whole Wanted list, it doesn't change who's opted in.
    """

    def __init__(self) -> None:
        from apscheduler.schedulers.background import BackgroundScheduler

        self.scheduler = BackgroundScheduler()
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        from app.core.database import SessionLocal
        from app.services.settings_service import ensure_settings

        db = SessionLocal()
        try:
            interval = max(
                30, int(getattr(ensure_settings(db), "indexer_sweep_interval_minutes", 360) or 360)
            )
        finally:
            db.close()
        self.scheduler.add_job(
            self.run_once,
            "interval",
            minutes=interval,
            id="wanted_indexer_sweep",
            replace_existing=True,
            max_instances=1,
        )
        self.scheduler.start()
        self._started = True
        logger.info("Wanted indexer sweep started (every %s minutes)", interval)

    def stop(self) -> None:
        if self._started:
            self.scheduler.shutdown(wait=False)
            self._started = False

    def run_once(self, force: bool = False, db: Session | None = None) -> dict:
        """Grab whatever indexers now have for the existing Wanted list.

        `force=True` (the manual-trigger endpoint) still checks each
        artist's own effective_auto_grab — this is "run the sweep now", not
        "grab everything regardless of settings". `db` is normally omitted
        (a fresh session is opened and closed here, same as the other
        scheduler jobs) — tests pass one in directly instead of going
        through the real configured database.
        """
        from app.models import Album, DownloadJob
        from app.services.artists import effective_auto_grab
        from app.services.download_queue import ACTIVE_JOB_STATES
        from app.services.settings_service import ensure_settings

        owns_session = db is None
        if db is None:
            from app.core.database import SessionLocal

            db = SessionLocal()
        checked = 0
        grabbed = 0
        try:
            settings = ensure_settings(db)
            if not force and not bool(getattr(settings, "indexer_sweep_enabled", True)):
                return {"ok": True, "skipped": True}

            active_job_album_ids = set(
                db.scalars(
                    select(DownloadJob.album_id).where(
                        DownloadJob.album_id.is_not(None),
                        DownloadJob.state.in_(ACTIVE_JOB_STATES),
                    )
                ).all()
            )
            albums = (
                db.scalars(
                    select(Album)
                    .join(Artist, Album.artist_id == Artist.id)
                    .options(joinedload(Album.artist))
                    .where(
                        Album.status == "wanted",
                        Artist.monitored.is_(True),
                        Artist.status == "active",
                    )
                )
                .unique()
                .all()
            )
            for album in albums:
                artist = album.artist
                if not artist or album.id in active_job_album_ids:
                    continue
                if not effective_auto_grab(db, artist, settings):
                    continue
                checked += 1
                try:
                    if try_auto_grab_release(db, artist, album, settings):
                        grabbed += 1
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Wanted-sweep grab failed for %s – %s", artist.name, album.title
                    )
            if checked:
                from app.services.history import add_history

                add_history(
                    db, "indexer_sweep", f"Wanted sweep: checked {checked} album(s), grabbed {grabbed}"
                )
            return {"ok": True, "checked": checked, "grabbed": grabbed}
        finally:
            if owns_session:
                db.close()


wanted_indexer_sweep = WantedIndexerSweep()
