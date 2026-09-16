from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas import CalendarEntryOut
from app.services.calendar import upcoming_releases

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("", response_model=list[CalendarEntryOut])
def get_calendar(
    db: Session = Depends(get_db),
    days_back: int = Query(30, ge=0, le=365),
    days_forward: int = Query(90, ge=0, le=365),
):
    return upcoming_releases(db, days_back=days_back, days_forward=days_forward)
