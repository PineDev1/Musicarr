from __future__ import annotations

import logging
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings as app_config
from app.core.database import SessionLocal
from app.models import Album, Artist, DownloadJob, Indexer
from app.services.history import add_history
from app.services.naming import (
    artist_folder_name,
    build_album_folder,
    build_track_filename,
    year_from_release,
)
from app.services.providers import get_provider
from app.services.providers.base import ProviderError
from app.services.settings_service import ensure_settings, library_root
from app.services.text_match import normalize_key

logger = logging.getLogger("musicarr.download")

# Streaming states this worker drives directly, plus the indexer states an
# indexer-sourced job passes through under completed_download_handler (never
# claimed by this queue's own loop, but counted here so a streaming grab and
# an indexer grab can't both be started on the same album at once).
ACTIVE_JOB_STATES = ["queued", "running", "grabbed", "downloading", "importing"]
DOWNLOAD_METHODS = {"streaming", "indexer", "streaming_then_indexer"}


def resolve_download_method(settings, method: str | None = None) -> str:
    requested = (method or getattr(settings, "preferred_download_method", None) or "").lower()
    resolved = requested if requested in DOWNLOAD_METHODS else "streaming"
    if resolved != "indexer" and not bool(getattr(settings, "streaming_enabled", True)):
        # Streaming turned off entirely — never attempt it, whatever the
        # stored preference says (covers "streaming" and "streaming_then_indexer").
        return "indexer"
    return resolved


def pick_unique_artist_search_hit(artist_name: str, hits: list) -> object | None:
    """Return the provider search hit only when exactly one exact name match exists.

    Matching folds diacritics and a leading "The"/"A"/"An" so e.g. a local tag
    "The Beatles" still auto-links to a provider hit named "Beatles".
    """
    key = normalize_key(artist_name or "")
    if not key or not hits:
        return None
    exact = [h for h in hits if normalize_key(getattr(h, "name", None) or "") == key]
    if len(exact) == 1:
        return exact[0]
    return None


def classify_download_error(message: str) -> str:
    text = (message or "").lower()
    if "not logged in" in text or "arl" in text or "not connected" in text or "not authenticated" in text:
        return "auth"
    if "could not find a matching release" in text or "rematch" in text or "active source is" in text:
        return "rematch"
    if "not available" in text or "unavailable" in text or "404" in text or "geo" in text:
        return "unavailable"
    if "timeout" in text or "timed out" in text or "connection" in text or "network" in text:
        return "network"
    return "other"


class DownloadQueue:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._stop = False
        self._cancel_ids: set[int] = set()
        self._active_workers: set[threading.Thread] = set()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop = False
        self._thread = threading.Thread(target=self._supervisor_loop, name="musicarr-dl", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop = True
        self._wake.set()

    def wake(self) -> None:
        self._wake.set()

    def _concurrency(self) -> int:
        db = SessionLocal()
        try:
            settings = ensure_settings(db)
            raw = int(getattr(settings, "download_concurrency", 1) or 1)
            return max(1, min(4, raw))
        except Exception:  # noqa: BLE001
            return 1
        finally:
            db.close()

    def _reap_workers(self) -> None:
        with self._lock:
            dead = {t for t in self._active_workers if not t.is_alive()}
            self._active_workers -= dead

    def _active_count(self) -> int:
        with self._lock:
            return sum(1 for t in self._active_workers if t.is_alive())

    def _supervisor_loop(self) -> None:
        while not self._stop:
            self._reap_workers()
            concurrency = self._concurrency()
            launched = False
            while self._active_count() < concurrency:
                job_id = self._claim_next_job(concurrency)
                if job_id is None:
                    break
                worker = threading.Thread(
                    target=self._run_claimed_job,
                    args=(job_id,),
                    name=f"musicarr-dl-{job_id}",
                    daemon=True,
                )
                with self._lock:
                    self._active_workers.add(worker)
                worker.start()
                launched = True
            if not launched:
                self._wake.wait(timeout=2.0)
                self._wake.clear()

    def _claim_next_job(self, concurrency: int) -> int | None:
        """Atomically move one queued job to running if under concurrency cap."""
        db = SessionLocal()
        try:
            running = (
                db.scalar(
                    select(func.count()).select_from(DownloadJob).where(DownloadJob.state == "running")
                )
                or 0
            )
            if running >= concurrency:
                return None
            job = db.scalar(
                select(DownloadJob)
                .where(DownloadJob.state == "queued")
                .order_by(DownloadJob.created_at.asc())
            )
            if not job:
                return None
            result = db.execute(
                update(DownloadJob)
                .where(DownloadJob.id == job.id, DownloadJob.state == "queued")
                .values(
                    state="running",
                    started_at=datetime.now(timezone.utc),
                    progress=1.0,
                )
            )
            db.commit()
            if result.rowcount != 1:
                return None
            return int(job.id)
        finally:
            db.close()

    def _run_claimed_job(self, job_id: int) -> None:
        try:
            self._process_job(job_id, already_claimed=True)
        except Exception:  # noqa: BLE001
            logger.exception("Unhandled download error for job %s", job_id)
        finally:
            with self._lock:
                self._active_workers.discard(threading.current_thread())
            self._wake.set()

    def enqueue_album(
        self,
        db: Session,
        album_id: int,
        *,
        allow_upgrade: bool = False,
        method: str | None = None,
    ) -> DownloadJob | None:
        album = db.get(Album, album_id)
        if not album:
            return None
        if album.status == "skipped" and not allow_upgrade:
            return None
        if album.status == "missing":
            return None
        settings = ensure_settings(db)
        # Indexer grabs are interactive only (Search releases → pick → grab) —
        # never auto-enqueued here, whether triggered by a manual "download
        # missing" click or the release monitor.
        if resolve_download_method(settings, method) == "indexer":
            return None
        from app.services.artists import effective_provider_album_id

        stream_pid = effective_provider_album_id(album.provider_id or "")
        if stream_pid.startswith("mb:") or not stream_pid:
            return None
        if allow_upgrade and album.status == "downloaded":
            album.status = "wanted"
            album.monitored = True
            db.commit()
        existing = db.scalar(
            select(DownloadJob).where(
                DownloadJob.album_id == album_id,
                DownloadJob.state.in_(ACTIVE_JOB_STATES),
            )
        )
        if existing:
            return existing
        artist = db.get(Artist, album.artist_id)
        from app.services.artists import album_display_artist

        display = album_display_artist(artist, album) if artist else ""
        album_title = album.title or ""
        job = DownloadJob(
            target_type="album",
            target_id=int(stream_pid) if stream_pid.isdigit() else 0,
            target_provider_id=stream_pid,
            album_id=album.id,
            artist_name=display or (artist.name if artist else ""),
            album_title=album_title,
            state="queued",
            source="streaming",
            progress=0.0,
        )
        db.add(job)
        try:
            db.commit()
        except IntegrityError:
            # Lost the race to a concurrent caller (e.g. a monitor tick firing
            # at the same moment as an add-artist sweep) — the partial unique
            # index on (album_id) for active states caught it. Return whatever
            # job actually won instead of raising.
            db.rollback()
            return db.scalar(
                select(DownloadJob).where(
                    DownloadJob.album_id == album_id,
                    DownloadJob.state.in_(ACTIVE_JOB_STATES),
                )
            )
        db.refresh(job)
        add_history(db, "queued", f"Queued {job.artist_name} – {job.album_title}")
        self.wake()
        return job

    def enqueue_artist_missing(
        self,
        db: Session,
        artist_id: int,
        *,
        method: str | None = None,
    ) -> list[DownloadJob]:
        albums = db.scalars(
            select(Album).where(
                Album.artist_id == artist_id,
                Album.status == "wanted",
                Album.monitored.is_(True),
            )
        ).all()
        jobs = []
        for album in albums:
            job = self.enqueue_album(db, album.id, method=method)
            if job:
                jobs.append(job)
        return jobs

    def _abort_client_item(self, db: Session, job: DownloadJob) -> None:
        """Best-effort: tell the download client to drop an in-progress indexer grab."""
        if not job.client_id or not job.client_item_id:
            return
        from app.models import DownloadClient
        from app.services.download_clients import DownloadClientError, get_client

        client_row = db.get(DownloadClient, job.client_id)
        if not client_row:
            return
        try:
            client = get_client(client_row)
        except DownloadClientError as exc:
            logger.warning("Cannot abort client item %s: %s", job.client_item_id, exc)
            return
        try:
            client.remove(job.client_item_id, delete_data=True)
        except Exception:  # noqa: BLE001
            logger.warning("Could not abort client item %s", job.client_item_id)
        finally:
            closer = getattr(client, "close", None)
            if callable(closer):
                closer()

    def cancel(self, db: Session, job_id: int) -> DownloadJob | None:
        job = db.get(DownloadJob, job_id)
        if not job:
            return None
        if job.state in {"completed", "failed", "cancelled"}:
            return job
        if job.source == "indexer" and job.client_item_id:
            self._abort_client_item(db, job)
        job.state = "cancelled"
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(job)
        with self._lock:
            self._cancel_ids.add(job_id)
        return job

    def retry(self, db: Session, job_id: int) -> DownloadJob | None:
        job = db.get(DownloadJob, job_id)
        if not job or not job.album_id:
            return None
        # Indexer grabs are interactive — use Search releases on the album again.
        if job.source == "indexer":
            return None
        job.state = "queued"
        job.progress = 0.0
        job.error = None
        job.error_category = ""
        job.started_at = None
        job.finished_at = None
        job.retries = (job.retries or 0) + 1
        db.commit()
        db.refresh(job)
        self.wake()
        return job

    def retry_failed(
        self,
        db: Session,
        *,
        category: str | None = None,
        exclude_categories: list[str] | None = None,
    ) -> int:
        q = select(DownloadJob).where(DownloadJob.state == "failed")
        jobs = list(db.scalars(q).all())
        exclude = set(exclude_categories or [])
        count = 0
        for job in jobs:
            cat = (job.error_category or classify_download_error(job.error or "")).lower()
            if category and cat != category.lower():
                continue
            if cat in exclude:
                continue
            if self.retry(db, job.id):
                count += 1
        return count

    def clear_finished(self, db: Session) -> int:
        jobs = db.scalars(
            select(DownloadJob).where(DownloadJob.state.in_(["completed", "failed", "cancelled"]))
        ).all()
        count = len(jobs)
        for job in jobs:
            db.delete(job)
        db.commit()
        return count

    def _indexer_nudge_suffix(self, db: Session, settings) -> str:
        """Extra hint appended to a streaming failure when the user opted into
        streaming_then_indexer — streaming never auto-falls-back to an indexer
        grab (that's always a manual pick), so just point at the escape hatch."""
        if resolve_download_method(settings) != "streaming_then_indexer":
            return ""
        has_indexer = db.scalar(select(Indexer).where(Indexer.enabled.is_(True)))
        if not has_indexer:
            return ""
        return " — streaming failed; open Search releases on this album to grab a torrent/NZB manually."

    def _is_cancelled(self, job_id: int) -> bool:
        with self._lock:
            return job_id in self._cancel_ids

    def _process_job(self, job_id: int, *, already_claimed: bool = False) -> None:
        db = SessionLocal()
        try:
            job = db.get(DownloadJob, job_id)
            if not job:
                return
            if already_claimed:
                if job.state != "running":
                    return
            elif job.state != "queued":
                return
            settings = ensure_settings(db)
            if not already_claimed:
                job.state = "running"
                job.started_at = datetime.now(timezone.utc)
                job.progress = 1.0
                db.commit()

            album = db.get(Album, job.album_id) if job.album_id else None
            if not album:
                job.state = "failed"
                job.error = "Album not found"
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
                return

            artist = db.get(Artist, album.artist_id)
            if self._is_cancelled(job_id):
                job.state = "cancelled"
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
                return

            try:
                provider, album, candidate_name = self._resolve_download_target(
                    db, album, artist, settings
                )
                job.album_id = album.id
                job.target_provider_id = album.provider_id
                job.target_id = int(album.provider_id) if album.provider_id.isdigit() else 0
                job.album_title = album.title
                if album.artist:
                    job.artist_name = album.artist.name
                db.commit()
                artist = db.get(Artist, album.artist_id)
                logger.info(
                    "Downloading '%s' via %s (id=%s)",
                    album.title,
                    candidate_name,
                    album.provider_id,
                )
            except ProviderError as exc:
                logger.error("Download auth/rematch failed for job %s: %s", job_id, exc)
                category = classify_download_error(str(exc))
                message = str(exc) + self._indexer_nudge_suffix(db, settings)
                job.state = "failed"
                job.error = message
                job.error_category = category
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
                add_history(db, "auth_error" if category == "auth" else "download_failed", message)
                from app.services.notifications import send_notification

                send_notification(
                    db,
                    "Download failed",
                    f"{job.artist_name} – {job.album_title}\n{message}",
                    kind="auth" if category == "auth" else "failure",
                )
                return

            from app.services.artists import sync_album_tracks

            sync_album_tracks(db, album)
            db.refresh(album)

            root = library_root(db)
            staging = app_config.data_dir / "downloads" / f"job_{job_id}"
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            staging.mkdir(parents=True, exist_ok=True)

            # Provider download loops call this many times per second (once per
            # chunk). Each call used to open a session and commit unconditionally,
            # which meant a download in progress held SQLite's single writer lock
            # almost continuously — starving other writes (like pressing Cancel,
            # or the queue polling for status) behind busy_timeout waits. Only
            # persist when progress has moved meaningfully or enough time has
            # passed, so the UI still updates smoothly but the DB isn't hammered.
            progress_state = {"value": -1.0, "at": 0.0}

            def on_progress(value):
                if value is None:
                    return
                value = float(value)
                now = time.monotonic()
                # Providers report 0-100 (deemix's "progress" key, and
                # Qobuz/Tidal's (idx+1)/total*100), not a 0-1 fraction —
                # comparing against 1.0 here made this throttle a no-op for
                # every real tick, reintroducing the DB-writer-lock
                # contention this was written to fix.
                if (
                    value < 100.0
                    and value - progress_state["value"] < 1.0
                    and now - progress_state["at"] < 0.5
                ):
                    return
                progress_state["value"] = value
                progress_state["at"] = now
                s = SessionLocal()
                try:
                    j = s.get(DownloadJob, job_id)
                    if j and j.state == "running":
                        j.progress = value
                        s.commit()
                finally:
                    s.close()

            try:
                from app.services.artists import effective_provider_album_id, effective_quality

                target_quality = (
                    effective_quality(db, artist) if artist else (settings.bitrate or "flac")
                )
                result = provider.download_album(
                    effective_provider_album_id(album.provider_id),
                    staging,
                    target_quality,
                    on_progress=on_progress,
                    is_cancelled=lambda: self._is_cancelled(job_id),
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Download failed for job %s", job_id)
                if str(exc) == "cancelled" or self._is_cancelled(job_id):
                    job.state = "cancelled"
                    job.finished_at = datetime.now(timezone.utc)
                    db.commit()
                    shutil.rmtree(staging, ignore_errors=True)
                    return
                category = classify_download_error(str(exc))
                # Never auto-retry auth/rematch misses — user must fix source or re-add.
                retryable = category not in {"auth", "rematch", "unavailable"}
                max_retries = settings.max_retries or 0
                if retryable and (job.retries or 0) < max_retries:
                    job.state = "queued"
                    job.retries = (job.retries or 0) + 1
                    job.error = str(exc)
                    job.error_category = category
                    job.progress = 0.0
                    job.started_at = None
                    db.commit()
                    add_history(
                        db,
                        "retry",
                        f"Retrying {album.title} ({job.retries}/{max_retries}): {exc}",
                    )
                    time.sleep(2)
                    self.wake()
                    shutil.rmtree(staging, ignore_errors=True)
                    return
                message = str(exc) + self._indexer_nudge_suffix(db, settings)
                job.state = "failed"
                job.error = message
                job.error_category = category
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
                add_history(
                    db,
                    "download_failed",
                    f"Failed {artist.name if artist else ''} – {album.title}: {message}",
                )
                from app.services.notifications import send_notification

                send_notification(
                    db,
                    "Download failed",
                    f"{artist.name if artist else ''} – {album.title}\n{message}",
                    kind="failure",
                )
                shutil.rmtree(staging, ignore_errors=True)
                return

            if self._is_cancelled(job_id):
                job.state = "cancelled"
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
                shutil.rmtree(staging, ignore_errors=True)
                return

            year = year_from_release(album.release_date)
            folder_artist = artist_folder_name(artist, db=db) if artist else "Unknown Artist"
            dest_folder = build_album_folder(
                root,
                settings.folder_template,
                artist=folder_artist,
                album=album.title,
                year=year,
                album_type=album.album_type,
            )
            dest_folder.mkdir(parents=True, exist_ok=True)

            downloaded_files = list(result.files)
            if result.cover:
                target_cover = dest_folder / "cover.jpg"
                if not target_cover.exists():
                    shutil.copy2(result.cover, target_cover)

            tracks = sorted(album.tracks, key=lambda t: (t.disc_no, t.track_no))
            matched = 0
            for idx, src in enumerate(downloaded_files):
                track = tracks[idx] if idx < len(tracks) else None
                if track:
                    filename = build_track_filename(
                        settings.track_template,
                        title=track.title,
                        track=track.track_no or (idx + 1),
                        disc=track.disc_no or 1,
                        artist=artist.name if artist else "",
                        album=album.title,
                        ext=src.suffix.lower(),
                    )
                else:
                    filename = build_track_filename(
                        settings.track_template,
                        title=src.stem,
                        track=idx + 1,
                        ext=src.suffix.lower(),
                    )
                dest = dest_folder / filename
                shutil.move(str(src), str(dest))
                if track:
                    track.path = str(dest)
                    matched += 1

            album.path = str(dest_folder)
            if matched > 0 or downloaded_files:
                album.status = "downloaded"
                album.quality = target_quality.lower()
            job.state = "completed"
            job.progress = 100.0
            job.finished_at = datetime.now(timezone.utc)
            job.error = None
            job.error_category = ""
            db.commit()

            if artist:
                from app.services.artists import (
                    mirror_downloaded_album_to_collaborators,
                    retag_downloaded_album,
                )

                try:
                    retag_downloaded_album(db, album, artist)
                    mirror_downloaded_album_to_collaborators(db, album, artist)
                except Exception:  # noqa: BLE001
                    logger.exception("Collab retag/mirror failed for album %s", album.id)

            add_history(
                db,
                "downloaded",
                f"Downloaded {artist.name if artist else ''} – {album.title} ({len(downloaded_files)} files)",
            )
            from app.services.notifications import send_notification
            from app.services.media_refresh import trigger_media_refresh

            send_notification(
                db,
                "Download complete",
                f"{artist.name if artist else ''} – {album.title} ({len(downloaded_files)} files)",
                kind="complete",
            )
            trigger_media_refresh(db, reason="download")
            shutil.rmtree(staging, ignore_errors=True)
        finally:
            with self._lock:
                self._cancel_ids.discard(job_id)
            db.close()

    def _resolve_download_target(
        self,
        db: Session,
        album: Album,
        artist: Artist | None,
        settings,
    ) -> tuple[object, Album, str]:
        """Pick a provider + Album row to download, trying the active provider
        first and falling back to other authenticated providers if enabled.

        Raises the last ProviderError if no candidate provider could resolve
        this album.
        """
        active = (settings.active_provider or "deezer").lower()
        fallback_enabled = getattr(settings, "fallback_providers_enabled", True)
        # Active provider always goes first — other providers are only even
        # checked (each check can be a network call, e.g. Qobuz's
        # validate_session) once the active one actually fails to resolve
        # this album, so the common case pays no extra cost.
        order = [active]
        if fallback_enabled:
            order += [p for p in ("deezer", "tidal", "qobuz") if p != active]

        last_error: ProviderError | None = None
        for candidate_name in order:
            try:
                provider, resolved_album = self._resolve_for_provider(db, album, artist, candidate_name)
            except ProviderError as exc:
                last_error = exc
                if candidate_name != active:
                    logger.info(
                        "Fallback candidate %s could not resolve '%s': %s",
                        candidate_name,
                        album.title,
                        exc,
                    )
                continue
            if candidate_name != active:
                add_history(
                    db,
                    "rematch",
                    f"'{resolved_album.title}' unavailable on {active}, using {candidate_name} instead",
                )
            return provider, resolved_album, candidate_name
        raise last_error or ProviderError("No provider available")

    def _resolve_for_provider(
        self,
        db: Session,
        album: Album,
        artist: Artist | None,
        provider_name: str,
    ) -> tuple[object, Album]:
        """Get a validated provider + the Album row to download from it.

        Rematches to `provider_name`'s catalog first if the current Album row
        belongs to a different provider. Raises ProviderError if the provider
        isn't authenticated or no matching release could be found there.
        """
        if album.provider != provider_name:
            rematched = self._rematch_album_to_provider(db, album, artist, provider_name)
            if not rematched:
                raise ProviderError(
                    f"This album is from {album.provider}. Could not find a matching "
                    f"release on {provider_name}."
                )
            album = rematched
        provider = get_provider(db, provider_name)
        ok, err = provider.validate_session()
        if not ok:
            raise ProviderError(err or f"{provider_name} is not connected. Log in under Settings.")
        return provider, album

    def _rematch_album_to_provider(
        self,
        db: Session,
        album: Album,
        artist: Artist | None,
        active: str,
    ) -> Album | None:
        """Find the same album on the given provider and return/update that Album row.

        `active` names the target provider to search — despite the historical
        name it's just "the provider to try," which is what lets this same
        function serve both the active-provider rematch case and multi-provider
        fallback (see _process_job).
        """
        from app.services.artists import add_artist, sync_album_tracks, sync_artist_albums
        from app.services.providers import get_provider
        from app.services.text_match import normalize_key as norm
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload

        try:
            provider = get_provider(db, active)
            ok, _ = provider.validate_session()
            if not ok:
                logger.warning("Rematch aborted: %s not authenticated", active)
                return None
            artist_name = artist.name if artist else ""
            if not artist_name:
                return None
            hits = provider.search_artists(artist_name, limit=8)
            if not hits:
                logger.warning("Rematch: no %s artists for %s", active, artist_name)
                return None
            match = pick_unique_artist_search_hit(artist_name, hits)
            if match is None:
                logger.warning(
                    "Rematch: ambiguous or missing exact name match for %s on %s (%d hits)",
                    artist_name,
                    active,
                    len(hits),
                )
                return None
            existing = db.scalar(
                select(Artist)
                .options(joinedload(Artist.albums))
                .where(
                    Artist.provider == active,
                    Artist.provider_id == match.provider_id,
                )
            )
            if not existing:
                existing = add_artist(
                    db,
                    match.provider_id,
                    monitored=True,
                    download_missing=False,
                    provider_name=active,
                )
            else:
                sync_artist_albums(db, existing)

            existing = db.scalar(
                select(Artist)
                .options(joinedload(Artist.albums))
                .where(Artist.id == existing.id)
            )
            if not existing:
                return None

            target = norm(album.title)
            albums = list(existing.albums or [])
            from app.services.filters import is_junk_title, is_live_title

            def rank(a: Album) -> tuple:
                type_rank = {"album": 0, "ep": 1, "single": 2, "compilation": 3}.get(
                    (a.album_type or "").lower(), 9
                )
                return (
                    1 if is_junk_title(a.title or "") else 0,
                    1 if is_live_title(a.title or "") else 0,
                    type_rank,
                    -(a.track_count or 0),
                    a.id,
                )

            exact = [a for a in albums if norm(a.title) == target]
            if exact:
                candidate = sorted(exact, key=rank)[0]
            else:
                fuzzy = [
                    a
                    for a in albums
                    if target
                    and (target in norm(a.title) or norm(a.title) in target)
                    and not is_junk_title(a.title or "")
                ]
                candidate = sorted(fuzzy, key=rank)[0] if fuzzy else None

            # Fallback: provider album search (catches singles missing from discography lists)
            if not candidate:
                search_fn = getattr(provider, "search_albums", None)
                if callable(search_fn):
                    query = f"{artist_name} {album.title}".strip()
                    hits_alb = search_fn(query, limit=15)
                    hit = next(
                        (
                            h
                            for h in hits_alb
                            if norm(h.title) == target
                            or (target and target in norm(h.title))
                        ),
                        None,
                    )
                    if hit:
                        candidate = next(
                            (
                                a
                                for a in albums
                                if a.provider_id == hit.provider_id
                            ),
                            None,
                        )
                        if not candidate:
                            from app.services.artists import _legacy_id, _unique_provider_album_id

                            unique_pid = _unique_provider_album_id(
                                db,
                                provider_name=active,
                                provider_id=str(hit.provider_id),
                                artist_id=existing.id,
                            )
                            candidate = Album(
                                provider=active,
                                provider_id=unique_pid,
                                deezer_id=_legacy_id(active, unique_pid),
                                artist_id=existing.id,
                                title=hit.title,
                                album_type=hit.album_type or "album",
                                release_date=hit.release_date,
                                cover_url=hit.cover_url,
                                track_count=hit.track_count or 0,
                                monitored=True,
                                status="wanted",
                            )
                            db.add(candidate)
                            db.commit()
                            db.refresh(candidate)

            if not candidate:
                logger.warning(
                    "Rematch: no album titled '%s' on %s for %s (%d albums)",
                    album.title,
                    active,
                    existing.name,
                    len(albums),
                )
                return None
            candidate.status = "wanted"
            candidate.monitored = True
            db.commit()
            db.refresh(candidate)
            sync_album_tracks(db, candidate)
            add_history(
                db,
                "rematch",
                f"Rematched '{album.title}' from {album.provider} → {active} ({candidate.provider_id})",
            )
            logger.info(
                "Rematched '%s' %s/%s → %s/%s",
                album.title,
                album.provider,
                album.provider_id,
                active,
                candidate.provider_id,
            )
            return candidate
        except Exception as exc:  # noqa: BLE001
            logger.warning("Rematch failed: %s", exc, exc_info=True)
            return None


download_queue = DownloadQueue()
