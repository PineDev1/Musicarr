from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import DownloadJob, HistoryEvent
from app.models.schemas import DownloadJobOut, HistoryOut, ReorganizeResult, ScanResult
from app.services.download_queue import download_queue
from app.services.library import reorganize_library, scan_library
from app.services.monitor import release_monitor

router = APIRouter(tags=["ops"])


@router.get("/queue", response_model=list[DownloadJobOut])
def get_queue(db: Session = Depends(get_db), all_jobs: bool = False):
    q = select(DownloadJob).order_by(DownloadJob.created_at.desc())
    if not all_jobs:
        q = q.where(DownloadJob.state.in_(["queued", "running", "failed"]))
    return list(db.scalars(q.limit(200)).all())


@router.post("/queue/{job_id}/cancel", response_model=DownloadJobOut)
def cancel_job(job_id: int, db: Session = Depends(get_db)):
    job = download_queue.cancel(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/queue/{job_id}/retry", response_model=DownloadJobOut)
def retry_job(job_id: int, db: Session = Depends(get_db)):
    job = download_queue.retry(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


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


@router.post("/library/reorganize", response_model=ReorganizeResult)
def library_reorganize(db: Session = Depends(get_db)):
    return reorganize_library(db)


@router.post("/monitor/run")
def run_monitor():
    return release_monitor.run_check(force=True)
