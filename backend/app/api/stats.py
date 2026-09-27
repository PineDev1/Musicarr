from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas import StatsHistoryOut, StatsOut
from app.services import stats_history
from app.services.stats import compute_stats

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", response_model=StatsOut)
def get_stats(db: Session = Depends(get_db)):
    return StatsOut(**compute_stats(db))


@router.get("/history", response_model=StatsHistoryOut)
def get_stats_history(db: Session = Depends(get_db)):
    return StatsHistoryOut(
        growth=stats_history.growth_series(db),
        download_trend=stats_history.download_trend(db),
        storage_by_quality=stats_history.storage_breakdown(db),
        top_genres=stats_history.top_genres(db),
    )
