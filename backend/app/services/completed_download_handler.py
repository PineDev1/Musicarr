from __future__ import annotations

import logging
import math
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.database import SessionLocal
from app.models import Album, Artist, DownloadClient, DownloadJob, Track
from app.services.download_clients import DownloadClientError, get_client
from app.services.download_clients.base import ClientStatus
from app.services.history import add_history
from app.services.library import AUDIO_EXTS, _norm, _read_tags
from app.services.naming import (
    artist_folder_name,
    build_album_folder,
    build_track_filename,
    year_from_release,
)
from app.services.path_mapping import map_remote_to_local
from app.services.settings_service import ensure_settings, library_root

logger = logging.getLogger("musicarr.completed")

ACTIVE_STATES = ["grabbed", "downloading"]
# Reject an import whose audio-file count falls below this fraction of the
# album's expected track count — catches partial/broken uploads and
# mislabeled singles/EPs before they're filed in as a complete album.
MIN_COMPLETE_RATIO = 0.7


def artist_tags_match_expected(files: list[Path], expected_artist: str) -> bool | None:
    """Return False if tags clearly name a different artist; True if match; None if no tags.

    Uses albumartist preferentially, then artist. A majority of tagged files must agree.
    """
    expected = _norm(expected_artist)
    if not expected or not files:
        return None

    votes_ok = 0
    votes_bad = 0
    for path in files:
        tags = _read_tags(path)
        tagged = _norm(tags.get("album_artist") or "") or _norm(tags.get("artist") or "")
        if not tagged:
            continue
        if tagged == expected or expected in tagged or tagged in expected:
            votes_ok += 1
        else:
            # Token overlap for slight punctuation differences
            exp_tokens = {t for t in expected.split() if len(t) > 1}
            got_tokens = {t for t in tagged.split() if len(t) > 1}
            if exp_tokens and got_tokens and len(exp_tokens & got_tokens) / len(exp_tokens) >= 0.6:
                votes_ok += 1
            else:
                votes_bad += 1

    if votes_ok == 0 and votes_bad == 0:
        return None
    if votes_bad > votes_ok:
        return False
    return True
COVER_NAMES = ("cover.jpg", "cover.png", "folder.jpg", "front.jpg", "album.jpg")
TICK_SECONDS = 30


def _leading_number(name: str) -> int:
    """Track number from names like "01 - Song" or "12_Song" (not "1999 Song")."""
    match = re.match(r"^\s*(\d{1,3})(?!\d)", name)
    return int(match.group(1)) if match else 0


def _transfer(src: Path, dest: Path, mechanism: str) -> None:
    """Place a downloaded file in the library without losing the original."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    mode = (mechanism or "hardlink").lower()
    if mode == "move":
        shutil.move(str(src), str(dest))
        return
    if mode == "hardlink":
        try:
            os.link(src, dest)
            return
        except OSError as exc:
            # Different filesystem or unsupported — fall back to a copy.
            logger.info("Hardlink failed (%s); copying %s instead", exc, src.name)
    shutil.copy2(src, dest)


class CompletedDownloadHandler:
    """Imports indexer downloads once the download client reports them done."""

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
            seconds=TICK_SECONDS,
            id="completed_download_handler",
            replace_existing=True,
            max_instances=1,
        )
        self.scheduler.start()
        self._started = True
        logger.info("Completed download handler started")

    def stop(self) -> None:
        if self._started:
            self.scheduler.shutdown(wait=False)
            self._started = False

    def _tick(self) -> None:
        db = SessionLocal()
        try:
            settings = ensure_settings(db)
            interval = max(
                10,
                int(
                    getattr(settings, "completed_download_scan_interval_seconds", 60)
                    or 60
                ),
            )
        except Exception:  # noqa: BLE001
            interval = 60
        finally:
            db.close()
        now = datetime.now(timezone.utc)
        if self._last_run is not None:
            if (now - self._last_run).total_seconds() < interval - 1:
                return
        self.run_once()

    def run_once(self) -> dict:
        """Poll every active indexer job once; import the finished ones."""
        self._last_run = datetime.now(timezone.utc)
        db = SessionLocal()
        polled = 0
        imported = 0
        failed = 0
        try:
            jobs = list(
                db.scalars(
                    select(DownloadJob)
                    .where(
                        DownloadJob.source == "indexer",
                        DownloadJob.state.in_(ACTIVE_STATES),
                    )
                    .order_by(DownloadJob.created_at.asc())
                ).all()
            )
            for job in jobs:
                polled += 1
                try:
                    result = self._poll_job(db, job)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Completed handler failed for job %s", job.id)
                    db.rollback()
                    self._fail_job(db, job, f"Import failed: {exc}")
                    failed += 1
                    continue
                if result == "imported":
                    imported += 1
                elif result == "failed":
                    failed += 1
        except Exception:  # noqa: BLE001
            logger.exception("Completed download scan failed")
        finally:
            db.close()
        return {"polled": polled, "imported": imported, "failed": failed}

    # -- job handling -----------------------------------------------------
    def _poll_job(self, db: Session, job: DownloadJob) -> str:
        if not job.client_item_id:
            self._fail_job(db, job, "Release was never handed to a download client")
            return "failed"
        client_row = db.get(DownloadClient, job.client_id) if job.client_id else None
        if not client_row:
            self._fail_job(db, job, "Download client for this job no longer exists")
            return "failed"

        client = get_client(client_row)
        try:
            status = client.get_status(job.client_item_id)
        except DownloadClientError as exc:
            # Transient client outage: keep the job active and retry next tick.
            logger.warning("Could not poll %s for job %s: %s", client_row.name, job.id, exc)
            return "pending"
        finally:
            closer = getattr(client, "close", None)
            if callable(closer):
                closer()

        if status.state == "failed":
            self._fail_job(
                db,
                job,
                f"{client_row.name} reported the download as failed or removed",
            )
            return "failed"

        if status.state != "completed":
            job.state = "downloading"
            job.progress = round(max(0.0, min(0.99, status.progress)) * 100, 1)
            if status.title and not job.release_title:
                job.release_title = status.title
            if not job.started_at:
                job.started_at = datetime.now(timezone.utc)
            db.commit()
            return "pending"

        return self._import_job(db, job, client_row, status)

    def _import_job(
        self,
        db: Session,
        job: DownloadJob,
        client_row: DownloadClient,
        status: ClientStatus,
    ) -> str:
        settings = ensure_settings(db)
        local = map_remote_to_local(db, status.output_path)
        if not local or not local.exists():
            self._fail_job(
                db,
                job,
                f"Completed download not found at '{status.output_path}'. "
                "Add a remote path mapping if the client runs in another container.",
            )
            return "failed"

        album = (
            db.scalar(
                select(Album)
                .options(joinedload(Album.tracks), joinedload(Album.artist))
                .where(Album.id == job.album_id)
            )
            if job.album_id
            else None
        )
        if not album:
            self._fail_job(db, job, "Album for this job no longer exists")
            return "failed"

        artist: Artist | None = album.artist
        artist_name = artist.name if artist else (job.artist_name or "Unknown Artist")
        folder_artist = artist_folder_name(artist, db=db) if artist else artist_name

        files = self._audio_files(local)
        if not files:
            self._fail_job(db, job, f"No audio files found in '{local}'")
            return "failed"

        # Reject wrong-artist grabs before filing into this artist's library
        tag_gate = artist_tags_match_expected(files, artist_name)
        if tag_gate is False:
            self._fail_job(
                db,
                job,
                f"Downloaded files look like a different artist than '{artist_name}' "
                f"(album/artist tags do not match). Not importing.",
            )
            return "failed"

        if not album.tracks:
            try:
                from app.services.artists import sync_album_tracks

                sync_album_tracks(db, album)
                db.refresh(album)
            except Exception:  # noqa: BLE001
                logger.info("Could not refresh tracks for album %s", album.id)

        # Reject a release that's missing most of its tracks (mislabeled single,
        # partial/broken upload, wrong-length rip) instead of silently filing an
        # incomplete album as "downloaded". Expected count comes from whichever
        # of the known track count or the DB's synced track rows is larger, so
        # a stale/short album.track_count doesn't produce false rejections.
        expected = max(int(album.track_count or 0), len(album.tracks or []))
        if expected >= 3 and len(files) < math.ceil(expected * MIN_COMPLETE_RATIO):
            self._fail_job(
                db,
                job,
                f"Only found {len(files)} audio file(s) in '{local}' but expected "
                f"around {expected} tracks. Looks incomplete — not importing.",
            )
            return "failed"

        job.state = "importing"
        job.progress = 99.0
        job.output_path = str(local)
        db.commit()

        root = library_root(db)
        dest_folder = build_album_folder(
            root,
            settings.folder_template,
            artist=folder_artist,
            album=album.title,
            year=year_from_release(album.release_date),
            album_type=album.album_type,
        )
        dest_folder.mkdir(parents=True, exist_ok=True)

        mechanism = (getattr(settings, "import_mechanism", None) or "hardlink").lower()
        tracks = sorted(album.tracks or [], key=lambda t: (t.disc_no or 1, t.track_no or 0))
        used: set[int] = set()
        placed: list[Path] = []
        matched = 0

        for idx, src in enumerate(files):
            tags = _read_tags(src)
            track = self._match_track(tracks, tags, src, idx, len(files), used)
            if track is not None:
                used.add(track.id)
                filename = build_track_filename(
                    settings.track_template,
                    title=track.title,
                    track=track.track_no or (idx + 1),
                    disc=track.disc_no or 1,
                    artist=artist_name,
                    album=album.title,
                    ext=src.suffix.lower(),
                )
            else:
                title = (tags.get("title") or "").strip() or src.stem
                filename = build_track_filename(
                    settings.track_template,
                    title=title,
                    track=self._track_number(tags, src) or (idx + 1),
                    disc=self._disc_number(tags),
                    artist=artist_name,
                    album=album.title,
                    ext=src.suffix.lower(),
                )
            dest = dest_folder / filename
            try:
                _transfer(src, dest, mechanism)
            except OSError as exc:
                self._fail_job(db, job, f"Could not import '{src.name}': {exc}")
                return "failed"
            placed.append(dest)
            if track is not None:
                track.path = str(dest)
                isrc = (tags.get("isrc") or "").strip()
                if isrc and not track.isrc:
                    track.isrc = isrc
                matched += 1

        self._copy_cover(local, dest_folder)

        album.path = str(dest_folder)
        album.status = "downloaded"
        album.monitored = True
        quality = self._detect_quality(placed)
        if quality:
            album.quality = quality
        if not album.track_count:
            album.track_count = len(placed)

        job.state = "completed"
        job.progress = 100.0
        job.error = None
        job.error_category = ""
        job.finished_at = datetime.now(timezone.utc)
        db.commit()

        message = (
            f"Imported {artist_name} – {album.title} "
            f"({len(placed)} files, {matched} matched) from {job.release_title or 'indexer release'}"
        )
        add_history(db, "downloaded", message)
        try:
            from app.services.notifications import send_notification

            send_notification(
                db,
                "Download complete",
                f"{artist_name} – {album.title} ({len(placed)} files)",
                kind="complete",
            )
        except Exception:  # noqa: BLE001
            logger.debug("Notification failed for job %s", job.id)
        try:
            from app.services.media_refresh import trigger_media_refresh

            trigger_media_refresh(db, reason="download")
        except Exception:  # noqa: BLE001
            logger.debug("Media refresh failed for job %s", job.id)

        if getattr(settings, "remove_completed_downloads", False):
            self._remove_from_client(client_row, job.client_item_id, mechanism)

        logger.info("%s", message)
        return "imported"

    # -- helpers ----------------------------------------------------------
    def _audio_files(self, target: Path) -> list[Path]:
        if target.is_file():
            return [target] if target.suffix.lower() in AUDIO_EXTS else []
        found = [
            p
            for p in target.rglob("*")
            if p.is_file() and p.suffix.lower() in AUDIO_EXTS
        ]
        return sorted(found, key=lambda p: (str(p.parent).lower(), p.name.lower()))

    def _track_number(self, tags: dict, src: Path) -> int:
        try:
            if tags.get("track"):
                return int(str(tags["track"]).split("/")[0])
        except (TypeError, ValueError):
            pass
        return _leading_number(src.stem)

    def _disc_number(self, tags: dict) -> int:
        try:
            if tags.get("disc"):
                return max(1, int(str(tags["disc"]).split("/")[0]))
        except (TypeError, ValueError):
            pass
        return 1

    def _match_track(
        self,
        tracks: list[Track],
        tags: dict,
        src: Path,
        index: int,
        total: int,
        used: set[int],
    ) -> Track | None:
        """Match a downloaded file to a known track: ISRC, then number, then title."""
        available = [t for t in tracks if t.id not in used]
        if not available:
            return None

        isrc = (tags.get("isrc") or "").strip()
        if isrc:
            hit = next((t for t in available if t.isrc and t.isrc == isrc), None)
            if hit:
                return hit

        track_no = self._track_number(tags, src)
        disc_no = self._disc_number(tags)
        if track_no:
            hit = next(
                (
                    t
                    for t in available
                    if t.track_no == track_no and (t.disc_no or 1) == disc_no
                ),
                None,
            )
            if hit:
                return hit
            if len({(t.disc_no or 1) for t in tracks}) == 1:
                hit = next((t for t in available if t.track_no == track_no), None)
                if hit:
                    return hit

        title = _norm(tags.get("title") or "") or _norm(
            re.sub(r"^\s*\d{1,3}\s*[\.\-_]\s*", "", src.stem)
        )
        if title:
            hit = next((t for t in available if _norm(t.title) == title), None)
            if hit:
                return hit
            hit = next(
                (
                    t
                    for t in available
                    if _norm(t.title) and (_norm(t.title) in title or title in _norm(t.title))
                ),
                None,
            )
            if hit:
                return hit

        # Last resort: identical file/track counts means positional order is safe.
        if total == len(tracks) and index < len(tracks) and tracks[index].id not in used:
            return tracks[index]
        return None

    def _copy_cover(self, source: Path, dest_folder: Path) -> None:
        target = dest_folder / "cover.jpg"
        if target.exists():
            return
        search_root = source if source.is_dir() else source.parent
        for name in COVER_NAMES:
            for candidate in (search_root / name, *search_root.glob(f"*/{name}")):
                if candidate.is_file():
                    try:
                        shutil.copy2(candidate, target)
                    except OSError:
                        return
                    return

    def _detect_quality(self, files: list[Path]) -> str:
        from app.services.quality import detect_file_quality, quality_rank

        qualities = [detect_file_quality(p) for p in files if p.exists()]
        return max(qualities, key=quality_rank, default="")

    def _remove_from_client(
        self, client_row: DownloadClient, item_id: str, mechanism: str
    ) -> None:
        try:
            client = get_client(client_row)
        except DownloadClientError as exc:
            logger.warning("Cannot remove completed download: %s", exc)
            return
        try:
            # "move" already consumed the payload, so there is nothing to delete.
            client.remove(item_id, delete_data=mechanism != "move")
        except Exception:  # noqa: BLE001
            logger.warning("Could not remove completed download %s", item_id)
        finally:
            closer = getattr(client, "close", None)
            if callable(closer):
                closer()

    def _fail_job(self, db: Session, job: DownloadJob, message: str) -> None:
        try:
            job.state = "failed"
            job.error = message
            job.error_category = "import"
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
            return
        logger.warning("Job %s failed: %s", job.id, message)
        try:
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
        except Exception:  # noqa: BLE001
            logger.debug("Could not record failure for job %s", job.id)


completed_download_handler = CompletedDownloadHandler()
