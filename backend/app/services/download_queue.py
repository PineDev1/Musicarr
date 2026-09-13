from __future__ import annotations

import logging
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings as app_config
from app.core.database import SessionLocal
from app.models import Album, Artist, DownloadJob
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

logger = logging.getLogger("musicarr.download")

# States that mean "this album is already being worked on". Indexer jobs stay
# active while the download client works, so they must count as busy too.
ACTIVE_JOB_STATES = [
    "queued",
    "running",
    "searching",
    "grabbed",
    "downloading",
    "importing",
]
DOWNLOAD_METHODS = {"streaming", "indexer", "streaming_then_indexer"}


def pick_unique_artist_search_hit(artist_name: str, hits: list) -> object | None:
    """Return the provider search hit only when exactly one exact name match exists."""
    key = " ".join((artist_name or "").strip().lower().split())
    if not key or not hits:
        return None
    exact = [
        h
        for h in hits
        if " ".join((getattr(h, "name", None) or "").strip().lower().split()) == key
    ]
    if len(exact) == 1:
        return exact[0]
    return None


def resolve_download_method(settings, method: str | None = None) -> str:
    requested = (method or getattr(settings, "preferred_download_method", None) or "").lower()
    return requested if requested in DOWNLOAD_METHODS else "streaming"


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

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop = False
        self._thread = threading.Thread(target=self._worker_loop, name="musicarr-dl", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop = True
        self._wake.set()

    def wake(self) -> None:
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
        settings = ensure_settings(db)
        resolved = resolve_download_method(settings, method)
        # Indexer grabs are interactive only — UI opens release search; never auto-enqueue.
        if resolved == "indexer":
            return None
        # streaming_then_indexer starts on streaming; on failure we prompt manual search.
        source = "streaming"
        artist = db.get(Artist, album.artist_id)
        job = DownloadJob(
            target_type="album",
            target_id=int(album.provider_id) if album.provider_id.isdigit() else 0,
            target_provider_id=album.provider_id,
            album_id=album.id,
            artist_name=artist.name if artist else "",
            album_title=album.title,
            state="queued",
            source=source,
            progress=0.0,
        )
        db.add(job)
        db.commit()
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
        # Indexer grabs are interactive — use Search indexers / Search again in the UI.
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

    def _is_cancelled(self, job_id: int) -> bool:
        with self._lock:
            return job_id in self._cancel_ids

    def _worker_loop(self) -> None:
        while not self._stop:
            job_id = self._next_job_id()
            if job_id is None:
                self._wake.wait(timeout=2.0)
                self._wake.clear()
                continue
            try:
                self._process_job(job_id)
            except Exception:  # noqa: BLE001
                logger.exception("Unhandled download error for job %s", job_id)

    def _abort_client_item(self, db: Session, job: DownloadJob) -> None:
        """Remove a grabbed release from its download client."""
        from app.models import DownloadClient
        from app.services.download_clients import get_client

        client_row = db.get(DownloadClient, job.client_id) if job.client_id else None
        if not client_row:
            return
        try:
            client = get_client(client_row)
        except Exception:  # noqa: BLE001
            return
        try:
            client.remove(job.client_item_id, delete_data=True)
        except Exception:  # noqa: BLE001
            logger.warning("Could not remove %s from %s", job.client_item_id, client_row.name)
        finally:
            closer = getattr(client, "close", None)
            if callable(closer):
                closer()

    def _next_job_id(self) -> int | None:
        db = SessionLocal()
        try:
            # Indexer searches are quick, so they are allowed to jump a
            # long-running streaming download.
            job = db.scalar(
                select(DownloadJob)
                .where(DownloadJob.state == "searching", DownloadJob.source == "indexer")
                .order_by(DownloadJob.created_at.asc())
            )
            if job:
                return job.id
            running = db.scalar(select(DownloadJob).where(DownloadJob.state == "running"))
            if running:
                return None
            job = db.scalar(
                select(DownloadJob)
                .where(DownloadJob.state == "queued")
                .order_by(DownloadJob.created_at.asc())
            )
            return job.id if job else None
        finally:
            db.close()

    def _process_job(self, job_id: int) -> None:
        db = SessionLocal()
        try:
            job = db.get(DownloadJob, job_id)
            if not job:
                return
            if job.source == "indexer":
                # Legacy auto-search jobs: fail with guidance (manual picker only).
                if job.state == "searching":
                    self._fail_indexer_job(
                        db,
                        job,
                        "Automatic indexer grabs are disabled. Open Search indexers "
                        "on the album and pick a release.",
                        "config",
                    )
                return
            if job.state != "queued":
                return
            settings = ensure_settings(db)
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
                active = (settings.active_provider or "deezer").lower()
                # Always download through the active source — never keep using
                # a previous provider just because that album row still exists.
                if album.provider != active:
                    rematched = self._rematch_album_to_active(db, album, artist, active)
                    if not rematched:
                        raise ProviderError(
                            f"This album is from {album.provider}, but active source is {active}. "
                            f"Could not find a matching release on {active}. "
                            f"Re-add the artist while {active} is selected."
                        )
                    album = rematched
                    job.album_id = album.id
                    job.target_provider_id = album.provider_id
                    job.album_title = album.title
                    if album.artist:
                        job.artist_name = album.artist.name
                    db.commit()
                    artist = db.get(Artist, album.artist_id)

                provider = get_provider(db, active)
                ok, err = provider.validate_session()
                if not ok:
                    raise ProviderError(
                        err
                        or f"{active} is not connected. Log in under Settings."
                    )
                logger.info(
                    "Downloading '%s' via %s (id=%s)",
                    album.title,
                    active,
                    album.provider_id,
                )
            except ProviderError as exc:
                logger.error("Download auth/rematch failed for job %s: %s", job_id, exc)
                category = classify_download_error(str(exc))
                job.state = "failed"
                job.error = str(exc)
                job.error_category = category
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
                add_history(db, "auth_error" if category == "auth" else "download_failed", str(exc))
                from app.services.notifications import send_notification

                send_notification(
                    db,
                    "Download failed",
                    f"{job.artist_name} – {job.album_title}\n{exc}",
                    kind="auth" if category == "auth" else "failure",
                )
                self._maybe_fallback_to_indexer(db, job)
                return

            from app.services.artists import sync_album_tracks

            sync_album_tracks(db, album)
            db.refresh(album)

            root = library_root(db)
            staging = app_config.data_dir / "downloads" / f"job_{job_id}"
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            staging.mkdir(parents=True, exist_ok=True)

            def on_progress(value):
                if value is None:
                    return
                s = SessionLocal()
                try:
                    j = s.get(DownloadJob, job_id)
                    if j and j.state == "running":
                        j.progress = float(value)
                        s.commit()
                finally:
                    s.close()

            try:
                result = provider.download_album(
                    album.provider_id,
                    staging,
                    settings.bitrate or "flac",
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
                job.state = "failed"
                job.error = str(exc)
                job.error_category = category
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
                add_history(
                    db,
                    "download_failed",
                    f"Failed {artist.name if artist else ''} – {album.title}: {exc}",
                )
                from app.services.notifications import send_notification

                send_notification(
                    db,
                    "Download failed",
                    f"{artist.name if artist else ''} – {album.title}\n{exc}",
                    kind="failure",
                )
                shutil.rmtree(staging, ignore_errors=True)
                self._maybe_fallback_to_indexer(db, job)
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
                album.quality = (settings.bitrate or "flac").lower()
            job.state = "completed"
            job.progress = 100.0
            job.finished_at = datetime.now(timezone.utc)
            job.error = None
            job.error_category = ""
            db.commit()
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

    def _fail_indexer_job(
        self,
        db: Session,
        job: DownloadJob,
        message: str,
        category: str,
    ) -> None:
        job.state = "failed"
        job.error = message
        job.error_category = category
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        add_history(
            db,
            "download_failed",
            f"Failed {job.artist_name} – {job.album_title}: {message}",
        )
        from app.services.notifications import send_notification

        send_notification(
            db,
            "Download failed",
            f"{job.artist_name} – {job.album_title}\n{message}",
            kind="failure",
        )

    def _maybe_fallback_to_indexer(self, db: Session, job: DownloadJob) -> None:
        """After streaming failure, nudge the user toward manual release search."""
        if job.source != "streaming" or not job.album_id:
            return
        settings = ensure_settings(db)
        if resolve_download_method(settings) != "streaming_then_indexer":
            return
        from app.models import Indexer

        has_indexer = db.scalar(select(Indexer).where(Indexer.enabled.is_(True)))
        if not has_indexer:
            return
        note = (
            " Streaming failed — use Search indexers on this album to pick a torrent/NZB."
        )
        if job.error and note.strip() not in job.error:
            job.error = f"{job.error}{note}"
            db.commit()
        add_history(
            db,
            "download_failed",
            f"Streaming failed for {job.artist_name} – {job.album_title}; "
            f"open Search indexers to grab manually",
        )

    def _rematch_album_to_active(
        self,
        db: Session,
        album: Album,
        artist: Artist | None,
        active: str,
    ) -> Album | None:
        """Find the same album on the active provider and return/update that Album row."""
        from app.services.artists import add_artist, sync_album_tracks, sync_artist_albums
        from app.services.providers import get_provider
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload
        import re

        def norm(title: str) -> str:
            t = (title or "").lower().strip()
            t = re.sub(r"\([^)]*\)", "", t)
            t = re.sub(r"\[[^\]]*\]", "", t)
            t = re.sub(r"\s+", " ", t).strip()
            return t

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
                            from app.services.artists import _legacy_id

                            candidate = Album(
                                provider=active,
                                provider_id=hit.provider_id,
                                deezer_id=_legacy_id(active, hit.provider_id),
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
