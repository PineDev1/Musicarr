from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas import DiscoveryOut
from app.services.calendar import upcoming_releases
from app.services.discovery import discover_similar

router = APIRouter(prefix="/discovery", tags=["discovery"])


@router.get("", response_model=DiscoveryOut)
def get_discovery(db: Session = Depends(get_db)):
    return DiscoveryOut(
        similar_artists=discover_similar(db),
        upcoming=upcoming_releases(db, days_back=7, days_forward=30),
    )
