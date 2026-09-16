from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import DownloadJob, HistoryEvent
from app.models.schemas import (
    ArtistOut,
    DownloadJobOut,
    HistoryOut,
    ImportReviewOut,
    LibraryJobOut,
    LinkArtistRequest,
)
from app.services.download_queue import ACTIVE_JOB_STATES, download_queue
from app.services.library import (
    build_import_review,
    link_local_artist,
)
from app.services.monitor import release_monitor
from app.services.settings_service import ensure_settings
from app.api.artists import _artist_group_out
from app.services.artists import effective_quality, find_linked_artists, get_artist_detail

router = APIRouter(tags=["ops"])


class BulkJobIds(BaseModel):
    job_ids: list[int]


def _job_out(job: DownloadJob) -> DownloadJobOut:
    """Serialize a job, defaulting fields that pre-date indexer support."""
    return DownloadJobOut(
        id=job.id,
        target_type=job.target_type,
        target_id=job.target_id,
        album_id=job.album_id,
        artist_name=job.artist_name or "",
        album_title=job.album_title or "",
        state=job.state,
        progress=job.progress or 0.0,
        error=job.error,
        error_category=job.error_category or "",
        retries=job.retries or 0,
        source=getattr(job, "source", None) or "streaming",
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.get("/queue", response_model=list[DownloadJobOut])
def get_queue(db: Session = Depends(get_db), all_jobs: bool = False):
    q = select(DownloadJob).order_by(DownloadJob.created_at.desc())
    if not all_jobs:
        q = q.where(DownloadJob.state.in_([*ACTIVE_JOB_STATES, "failed"]))
    return [_job_out(j) for j in db.scalars(q.limit(200)).all()]


@router.post("/queue/{job_id}/cancel", response_model=DownloadJobOut)
def cancel_job(job_id: int, db: Session = Depends(get_db)):
    job = download_queue.cancel(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_out(job)


@router.post("/queue/{job_id}/retry", response_model=DownloadJobOut)
def retry_job(job_id: int, db: Session = Depends(get_db)):
    job = download_queue.retry(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_out(job)


@router.post("/queue/bulk-cancel")
def bulk_cancel_jobs(payload: BulkJobIds, db: Session = Depends(get_db)):
    cancelled = sum(1 for jid in payload.job_ids if download_queue.cancel(db, jid))
    return {"cancelled": cancelled}


@router.post("/queue/bulk-retry")
def bulk_retry_jobs(payload: BulkJobIds, db: Session = Depends(get_db)):
    retried = sum(1 for jid in payload.job_ids if download_queue.retry(db, jid))
    return {"retried": retried}


@router.post("/queue/retry-failed")
def retry_failed_jobs(
    db: Session = Depends(get_db),
    category: str | None = None,
    skip_permanent: bool = True,
):
    """Retry failed jobs. By default skips auth/rematch (need user action)."""
    exclude = ["auth", "rematch"] if skip_permanent and not category else None
    retried = download_queue.retry_failed(
        db, category=category, exclude_categories=exclude
    )
    return {"retried": retried}


@router.get("/history", response_model=list[HistoryOut])
def get_history(db: Session = Depends(get_db), limit: int = 100):
    return list(
        db.scalars(
            select(HistoryEvent).order_by(HistoryEvent.created_at.desc()).limit(limit)
        ).all()
    )


@router.post("/queue/clear-finished")
def clear_finished(db: Session = Depends(get_db)):
    cleared = download_queue.clear_finished(db)
    return {"cleared": cleared}


@router.post("/library/scan", response_model=LibraryJobOut, status_code=202)
def library_scan():
    from app.services import library_jobs

    if library_jobs.get_job().state == "running":
        raise HTTPException(status_code=409, detail="Library job already running")
    try:
        library_jobs.start_library_job("scan")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return library_jobs.job_dict()


@router.post("/library/import", response_model=LibraryJobOut, status_code=202)
def library_import(link_providers: bool = True):
    """Import a previous on-disk music library into Musicarr (background job)."""
    from app.services import library_jobs

    if library_jobs.get_job().state == "running":
        raise HTTPException(status_code=409, detail="Library job already running")
    try:
        library_jobs.start_library_job("import", link_providers=link_providers)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return library_jobs.job_dict()


@router.get("/library/job", response_model=LibraryJobOut)
def library_job():
    from app.services import library_jobs

    return library_jobs.job_dict()


@router.get("/library/genres")
def library_genres(db: Session = Depends(get_db)):
    from sqlalchemy import func

    from app.models import Track

    rows = db.execute(
        select(Track.genre, func.count())
        .where(Track.genre.is_not(None), Track.genre != "")
        .group_by(Track.genre)
        .order_by(func.count().desc())
    ).all()
    return [{"genre": g, "count": c} for g, c in rows]


@router.get("/library/review", response_model=ImportReviewOut)
def library_review(db: Session = Depends(get_db), suggest: bool = True):
    """Show local / weakly tagged imports that need manual linking."""
    return build_import_review(db, suggest=suggest)


@router.post("/library/review/{artist_id}/link", response_model=ArtistOut)
def library_review_link(
    artist_id: int,
    payload: LinkArtistRequest,
    db: Session = Depends(get_db),
):
    settings = ensure_settings(db)
    try:
        linked = link_local_artist(
            db,
            artist_id,
            provider_id=payload.provider_id,
            provider_name=payload.provider or settings.active_provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    detail = get_artist_detail(db, linked.id)
    group = find_linked_artists(db, detail or linked)
    primary = group[0] if group else None
    target = effective_quality(db, primary) if primary else (settings.bitrate or "flac").lower()
    return _artist_group_out(
        group,
        include_albums=True,
        active=(settings.active_provider or "deezer").lower(),
        target_bitrate=target,
        upgrade_enabled=bool(getattr(settings, "upgrade_enabled", True)),
    )


@router.post("/library/reorganize", response_model=LibraryJobOut, status_code=202)
def library_reorganize():
    from app.services import library_jobs

    if library_jobs.get_job().state == "running":
        raise HTTPException(status_code=409, detail="Library job already running")
    try:
        library_jobs.start_library_job("reorganize")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return library_jobs.job_dict()


@router.post("/monitor/run")
def run_monitor():
    return release_monitor.run_check(force=True)
