from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import DownloadJob, HistoryEvent
from app.models.schemas import (
    DownloadJobOut,
    HistoryOut,
    ImportResult,
    ImportReviewOut,
    LinkArtistRequest,
    ReorganizeResult,
    ScanResult,
)
from app.services.download_queue import ACTIVE_JOB_STATES, download_queue
from app.services.library import (
    build_import_review,
    import_existing_library,
    link_local_artist,
    reorganize_library,
    scan_library,
)
from app.services.monitor import release_monitor
from app.services.settings_service import ensure_settings
from app.api.artists import _artist_group_out
from app.services.artists import find_linked_artists, get_artist_detail
from app.models.schemas import ArtistOut

router = APIRouter(tags=["ops"])


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


@router.post("/library/scan", response_model=ScanResult)
def library_scan(db: Session = Depends(get_db)):
    return scan_library(db)


@router.post("/library/import", response_model=ImportResult)
def library_import(db: Session = Depends(get_db), link_providers: bool = True):
    """Import a previous on-disk music library into Musicarr."""
    return import_existing_library(db, link_providers=link_providers)


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
    return _artist_group_out(
        group,
        include_albums=True,
        active=(settings.active_provider or "deezer").lower(),
        target_bitrate=(settings.bitrate or "flac").lower(),
        upgrade_enabled=bool(getattr(settings, "upgrade_enabled", True)),
    )


@router.post("/library/reorganize", response_model=ReorganizeResult)
def library_reorganize(db: Session = Depends(get_db)):
    return reorganize_library(db)


@router.post("/monitor/run")
def run_monitor():
    return release_monitor.run_check(force=True)
