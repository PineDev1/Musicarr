from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import ImportList
from app.services.artists import add_artist, find_artist_by_normalized_name
from app.services.download_queue import pick_unique_artist_search_hit
from app.services.history import add_history
from app.services.providers import get_active_provider
from app.services.providers.base import ProviderError

logger = logging.getLogger("musicarr.import_lists")

MAX_NAMES_PER_RUN = 40


def _parse_names(names_raw: str) -> list[str]:
    names: list[str] = []
    for line in (names_raw or "").splitlines():
        name = line.strip()
        if name and name not in names:
            names.append(name)
        if len(names) >= MAX_NAMES_PER_RUN:
            break
    return names


def run_import_list(db: Session, import_list: ImportList) -> dict:
    """Add any missing artists from the list's pasted names.

    Reuses the same provider search + exact-match confidence bar as the
    manual bulk-search flow (pick_unique_artist_search_hit) — an import list
    runs unattended, so an ambiguous or fuzzy hit is skipped rather than
    guessed at.
    """
    added: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    playlist_url = (getattr(import_list, "spotify_playlist_url", None) or "").strip()
    if playlist_url:
        from app.services import spotify

        playlist_id = spotify.extract_playlist_id(playlist_url)
        if not playlist_id:
            summary = "Could not parse a playlist id from that Spotify URL"
            import_list.last_run_at = datetime.now(timezone.utc)
            import_list.last_result = summary
            db.commit()
            return {"added": added, "skipped": skipped, "errors": errors, "summary": summary}
        try:
            names = spotify.playlist_artist_names(db, playlist_id)
        except spotify.SpotifyError as exc:
            summary = f"Spotify lookup failed: {exc}"
            import_list.last_run_at = datetime.now(timezone.utc)
            import_list.last_result = summary
            db.commit()
            return {"added": added, "skipped": skipped, "errors": errors, "summary": summary}
    else:
        names = _parse_names(import_list.names_raw)

    if not names:
        summary = "No names in this list"
    else:
        try:
            provider = get_active_provider(db)
        except ProviderError as exc:
            summary = f"Could not reach active provider: {exc}"
            import_list.last_run_at = datetime.now(timezone.utc)
            import_list.last_result = summary
            db.commit()
            return {"added": added, "skipped": skipped, "errors": errors, "summary": summary}

        for name in names:
            existing = find_artist_by_normalized_name(db, name, provider.name)
            if existing:
                skipped.append(name)
                continue
            try:
                hits = provider.search_artists(name, limit=5)
            except ProviderError as exc:
                errors.append(f"{name}: {exc}")
                continue
            match = pick_unique_artist_search_hit(name, hits)
            if not match:
                errors.append(f"{name}: no confident match")
                continue
            try:
                add_artist(
                    db,
                    match.provider_id,
                    monitored=True,
                    download_missing=True,
                    provider_name=provider.name,
                    require_approval=True,
                    pending_reason="import_list",
                )
                added.append(name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Import list add_artist failed for %s: %s", name, exc)
                errors.append(f"{name}: {exc}")

        summary = f"{len(added)} added to pending review, {len(skipped)} already in library"
        if errors:
            summary += f", {len(errors)} not matched"

    import_list.last_run_at = datetime.now(timezone.utc)
    import_list.last_result = summary
    db.commit()
    if added or errors:
        msg = f"Import list '{import_list.name}': {summary}"
        add_history(db, "import_list_run", msg)
        from app.services.notifications import send_notification

        send_notification(db, "Import list run", msg, kind="library")
    return {"added": added, "skipped": skipped, "errors": errors, "summary": summary}


def due_import_lists(db: Session, *, now: datetime | None = None) -> list[ImportList]:
    now = now or datetime.now(timezone.utc)
    rows = db.scalars(select(ImportList).where(ImportList.enabled.is_(True))).all()
    due = []
    for row in rows:
        if row.last_run_at is None:
            due.append(row)
            continue
        last_run = row.last_run_at
        if last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=timezone.utc)
        elapsed_minutes = (now - last_run).total_seconds() / 60.0
        if elapsed_minutes >= max(15, row.interval_minutes or 720):
            due.append(row)
    return due


class ImportListRunner:
    """Periodically runs any enabled import list whose own interval has
    elapsed. Mirrors ReleaseMonitor's start/stop/_tick shape, but ticks over
    a set of independently-scheduled rows instead of one global interval.
    """

    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler()
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self.scheduler.add_job(
            self._tick,
            "interval",
            minutes=5,
            id="import_list_runner",
            replace_existing=True,
            max_instances=1,
        )
        self.scheduler.start()
        self._started = True
        logger.info("Import list runner started")

    def stop(self) -> None:
        if self._started:
            self.scheduler.shutdown(wait=False)
            self._started = False

    def _tick(self) -> None:
        db = SessionLocal()
        try:
            for row in due_import_lists(db):
                try:
                    run_import_list(db, row)
                except Exception:  # noqa: BLE001
                    logger.exception("Import list %s failed", row.id)
        finally:
            db.close()


import_list_runner = ImportListRunner()
