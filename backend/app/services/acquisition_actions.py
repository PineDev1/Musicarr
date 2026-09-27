from __future__ import annotations

import threading
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Album, DownloadJob
from app.services.download_clients import DownloadClientError, get_client, pick_client
from app.services.history import add_history

# Serializes the check-then-act sequence below (query for an active job, send
# to the download client, insert the job row). Without this, two
# near-simultaneous grabs for the same album (two manual clicks, or a manual
# click racing an auto-grab) both pass the active-job query before either
# inserts, so both get sent to the download client — the DB unique index
# alone only stops the second row, not the second grab.
_grab_lock = threading.Lock()


class GrabError(Exception):
    """A release could not be sent to a download client."""

    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def grab_release_for_album(
    db: Session,
    album: Album,
    *,
    grab_url: str,
    protocol: str,
    title: str = "",
    indexer_id: int | None = None,
) -> DownloadJob:
    """Send a release to the matching download client and record the job.

    Shared by the manual "Search releases" grab endpoint and the auto-grab
    path in monitor.py, so the check-dispatch-commit sequence (and its
    concurrency guard) lives in exactly one place.
    """
    grab_url = (grab_url or "").strip()
    if not grab_url:
        raise GrabError("grab_url is required")

    protocol = (protocol or "torrent").lower()
    client_row = pick_client(db, protocol)
    if not client_row:
        label = "qBittorrent" if protocol == "torrent" else "SABnzbd"
        raise GrabError(
            f"No enabled {protocol} download client. Add {label} under Settings → Download clients."
        )

    # Preflight: confirm the client still answers.
    try:
        ok, message = get_client(client_row).test()
    except DownloadClientError as exc:
        raise GrabError(f"Download client '{client_row.name}' failed: {exc}") from exc
    if not ok:
        raise GrabError(f"Download client '{client_row.name}' failed: {message}")

    artist = album.artist
    artist_name = artist.name if artist else ""

    with _grab_lock:
        # Avoid duplicate active jobs for the same album, from either source —
        # a streaming download already in flight must not also get an indexer grab.
        active = db.scalar(
            select(DownloadJob).where(
                DownloadJob.album_id == album.id,
                DownloadJob.state.in_(
                    ["queued", "running", "grabbed", "downloading", "importing"]
                ),
            )
        )
        if active:
            raise GrabError("A download is already in progress for this album", status_code=409)

        client = get_client(client_row)
        try:
            item_id = client.add_url(grab_url, client_row.category or "")
        except DownloadClientError as exc:
            raise GrabError(str(exc)) from exc
        finally:
            closer = getattr(client, "close", None)
            if callable(closer):
                closer()

        try:
            from app.services.artists import sync_album_tracks

            if not album.tracks:
                sync_album_tracks(db, album)
        except Exception:  # noqa: BLE001
            pass

        job = DownloadJob(
            target_type="album",
            target_id=album.id,
            album_id=album.id,
            artist_name=artist_name,
            album_title=album.title,
            state="grabbed",
            source="indexer",
            indexer_id=indexer_id,
            client_id=client_row.id,
            release_title=(title or "").strip()[:1024],
            download_url=grab_url,
            client_item_id=item_id,
            progress=1.0,
            started_at=datetime.now(timezone.utc),
        )
        db.add(job)
        try:
            db.commit()
        except IntegrityError:
            # Belt-and-suspenders: the lock above already prevents this in a
            # single-process deployment, but the DB constraint (see
            # database.py's uq_download_jobs_album_active_indexer) still
            # backstops it if that ever changes.
            db.rollback()
            raise GrabError(
                "A download is already in progress for this album", status_code=409
            ) from None
        db.refresh(job)

    add_history(
        db,
        "grabbed",
        f"Grabbed '{job.release_title or 'release'}' for {artist_name} – {album.title} "
        f"(sent to {client_row.name})",
    )
    from app.services.download_queue import download_queue

    download_queue.wake()

    return job
