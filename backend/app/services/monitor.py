from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.core.database import SessionLocal
from app.models import Artist
from app.services.artists import effective_download_mode, sync_artist_albums
from app.services.download_queue import download_queue
from app.services.history import add_history
from app.services.providers import get_provider
from app.services.providers.base import ProviderError
from app.services.settings_service import ensure_settings

logger = logging.getLogger("musicarr.monitor")


class ReleaseMonitor:
    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler()
        self._started = False
        self._last_run: datetime | None = None

    def start(self) -> None:
        if self._started:
            return
        self.scheduler.add_job(
            self._tick,
            "interval",
            minutes=1,
            id="release_monitor",
            replace_existing=True,
            max_instances=1,
        )
        self.scheduler.start()
        self._started = True
        logger.info("Release monitor started")

    def stop(self) -> None:
        if self._started:
            self.scheduler.shutdown(wait=False)
            self._started = False

    def _tick(self) -> None:
        db = SessionLocal()
        try:
            settings = ensure_settings(db)
            interval = max(5, settings.monitor_interval_minutes or 60)
            now = datetime.now(timezone.utc)
            if self._last_run is not None:
                elapsed = (now - self._last_run).total_seconds() / 60.0
                if elapsed < interval:
                    return
            self.run_check(force=False)
        finally:
            db.close()

    def run_check(self, force: bool = False) -> dict:
        db = SessionLocal()
        try:
            settings = ensure_settings(db)
            active = (settings.active_provider or "deezer").lower()
            artists = (
                db.scalars(
                    select(Artist)
                    .options(joinedload(Artist.albums))
                    .where(
                        Artist.monitored.is_(True),
                        Artist.provider == active,
                        Artist.status == "active",
                    )
                )
                .unique()
                .all()
            )
            new_albums = 0
            queued = 0
            awaiting_manual = 0
            checked = 0
            skipped = 0
            for artist in list(artists):
                try:
                    provider = get_provider(db, artist.provider)
                    ok, err = provider.validate_session()
                    if not ok:
                        skipped += 1
                        logger.info(
                            "Skipping monitor for %s (%s): %s",
                            artist.name,
                            artist.provider,
                            err,
                        )
                        continue
                    before_ids = {a.provider_id for a in artist.albums}
                    # Unattended tick — any newly-discovered "feat." collaborator
                    # goes through the same pending-review gate as any other
                    # unattended add.
                    synced = sync_artist_albums(db, artist, require_approval=True)
                    checked += 1
                    for album in synced:
                        mode = (getattr(artist, "monitor_mode", None) or "all").lower()
                        if mode == "none":
                            continue
                        if album.provider_id not in before_ids and album.status == "wanted":
                            new_albums += 1
                            job = None
                            if effective_download_mode(db, artist) == "auto":
                                job = download_queue.enqueue_album(db, album.id)
                            if job:
                                queued += 1
                            else:
                                # Also covers indexer-only / streaming-disabled setups,
                                # where enqueue_album refuses to auto-queue anything —
                                # those need manual review just like "manual" mode.
                                awaiting_manual += 1
                except ProviderError as exc:
                    skipped += 1
                    logger.warning("Monitor skip %s: %s", artist.name, exc)
                except Exception:  # noqa: BLE001
                    skipped += 1
                    logger.exception("Monitor failed for artist %s", artist.name)
            self._last_run = datetime.now(timezone.utc)
            if new_albums:
                msg = f"Found {new_albums} new album(s); queued {queued}"
                if awaiting_manual:
                    msg += f", {awaiting_manual} waiting for manual approval"
                add_history(db, "monitor", msg)
            elif force:
                add_history(
                    db,
                    "monitor",
                    f"Manual monitor check: {checked} artists checked, {skipped} skipped, no new albums",
                )
            return {
                "artists_checked": checked,
                "artists_skipped": skipped,
                "new_albums": new_albums,
                "queued": queued,
                "awaiting_manual": awaiting_manual,
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("Monitor check failed")
            try:
                add_history(db, "monitor_error", str(exc))
            except Exception:  # noqa: BLE001
                pass
            return {"artists_checked": 0, "new_albums": 0, "error": str(exc)}
        finally:
            db.close()


release_monitor = ReleaseMonitor()
